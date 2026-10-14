from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from pdpa_guard.breach import build_case, notify_deadline
from pdpa_guard.monitor import Finding, evaluate, live_score, run_actions
from pdpa_guard.policy import compile_policy, load_policy, policy_errors

YAML = (Path(__file__).resolve().parent.parent / "policies" / "tuition_centre.yaml").read_text()
POL = load_policy(YAML)


def test_policy_valid_and_compiles():
    c = compile_policy(POL)
    sql = ";\n".join(c.statements)
    assert "CREATE VIEW \"v_admin_staff\".\"students\"" in sql
    assert "'S****'" not in sql and "upper(left(" in sql
    assert "parent_consent" in sql and "WITH LOCAL CHECK OPTION" in sql
    assert ("admin_staff", "v_admin_staff", "students") in c.expected
    # secure by default: teacher has no NRIC column in its view
    teacher_view = [s for s in c.statements if s.startswith('CREATE VIEW "v_teacher"')][0]
    assert '"nric"' not in teacher_view.split("FROM")[0]


@pytest.mark.parametrize("patch,needle", [
    (("edit: [phone, email, parent_consent]", "edit: [nric]"), "cannot see it in full"),
    (("row_filter: \"parent_consent = 'yes'\"", "row_filter: \"1=1; drop table x\""), "row_filter"),
    (("student_name: name", "student_name: wizard"), "unknown data class"),
    (("then: [alert, notify_dpo]", "then: [self_destruct]"), "unknown action"),
    (("type: denied_access", "type: made_up"), "when.type"),
    (("  dpo:        {", "  Dpo-X:      {"), "must match"),
])
def test_invalid_policies_rejected(patch, needle):
    errs = policy_errors(YAML.replace(*patch, 1))
    assert errs and any(needle in e for e in errs), errs


def test_injection_in_identifiers_rejected():
    bad = YAML.replace("      nric: nric\n", "      \"nric; drop table x\": nric\n", 1)
    errs = policy_errors(bad)
    assert errs and not any("YAML syntax" in e for e in errs) and any("must match" in e for e in errs), errs


def _ev(i, **kw):
    base = dict(id=i, ts=datetime(2026, 10, 10, 10, 0, tzinfo=timezone(timedelta(hours=8))), app_user="amy", db_role="admin_staff",
                purpose="x", stmt_type="SELECT", tables=["students"], rows=3, denied=False, reason=None, unmasked_nric=0)
    base.update(kw)
    return base


def test_rules_fire():
    night = datetime(2026, 10, 10, 2, 0, tzinfo=timezone(timedelta(hours=8)))
    evs = [_ev(1, rows=500), _ev(2, ts=night), _ev(3, denied=True, reason="permission denied: x", rows=0),
           _ev(4, denied=True, reason="purpose_required", rows=0), _ev(5, unmasked_nric=4, db_role="intern"),
           _ev(6, unmasked_nric=4, db_role="dpo"), _ev(7, rows=500, reason="dpo_approved"),
           _ev(8, rows=500, db_role="dpo")]
    got = {(f.rule_id, f.event_id) for f in evaluate(evs, POL)}
    assert ("bulk-read", 1) in got and ("off-hours", 2) in got and ("denied-attempt", 3) in got
    assert ("no-purpose", 4) in got and ("unmasked-nric", 5) in got
    assert ("unmasked-nric", 6) not in got            # DPO is allowed full NRIC
    assert not any(e == 7 or e == 8 for r, e in got if r == "bulk-read")   # approved / exempt role


def test_rules_do_not_leak_across_each_other():
    evs = [_ev(1, db_role="dpo", rows=500), _ev(2, rows=500)]
    got = {(f.rule_id, f.event_id) for f in evaluate(evs, POL)}
    assert ("bulk-read", 2) in got and ("bulk-read", 1) not in got
    assert ("off-hours", 1) not in got


def test_bulk_change_window():
    t0 = datetime(2026, 10, 10, 10, 0, tzinfo=timezone.utc)
    ch = [dict(id=i, ts=t0 + timedelta(seconds=i), app_user="amy", db_role="admin_staff", tbl="public.students", op="UPDATE") for i in range(20)]
    assert any(f.rule_id == "mass-edit" for f in evaluate([], POL, ch))


def test_actions_and_dedup():
    class Mem:
        def __init__(s): s.f, s.n, s.c, s.seen = [], [], [], set()
        def save_finding(s, f):
            k = (f.rule_id, f.event_id)
            if k in s.seen: return None
            s.seen.add(k); s.f.append(f); return len(s.f)
        def notify(s, to, msg, fid): s.n.append(msg)
        def save_case(s, fid, body): s.c.append(body)
    sink = Mem()
    fs = evaluate([_ev(1, rows=500)], POL)
    assert run_actions(fs, POL, sink) == 1 and sink.n and sink.c
    assert run_actions(fs, POL, sink) == 0 and len(sink.c) == 1     # idempotent


def test_live_score_and_breach_deadline():
    assert live_score(80, []) == 80 and live_score(80, [{"severity": "high"}] * 3) == 62.0
    assert live_score(10, [{"severity": "high"}] * 99) == 0.0
    d = notify_deadline(datetime(2026, 10, 10, 15, 0, tzinfo=timezone(timedelta(hours=8))))
    assert (d.year, d.month, d.day) == (2026, 10, 13)         # s.26D(1): 3 calendar days after the day of assessment
    f = Finding("bulk-read", "", "high", 1, "amy", "admin_staff", "students", "x", event={"rows": 900})
    case = build_case(f, POL, internal_only=False)
    assert case["significant_scale_indicated"] and "NOTIFIABLE" in case["preliminary_verdict"]
    assert "not notifiable" in build_case(f, POL)["preliminary_verdict"].lower()   # s.26B(4)

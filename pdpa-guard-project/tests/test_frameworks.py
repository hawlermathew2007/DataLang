import pandas as pd
import pytest
from pathlib import Path

from pdpa_guard.catalogue import PDPA_RULE_IDS, RULES
from pdpa_guard.masking import mask_value
from pdpa_guard.policy import load_policy, policy_errors, compile_policy
from pdpa_guard.remediate import apply_governance
from pdpa_guard.sample import ANCHOR, messy_clients, messy_payroll, messy_students
from pdpa_guard.scoring import assess

ACCT = (Path(__file__).resolve().parent.parent / "policies" / "accounting_firm.yaml").read_text()


def test_every_rule_declares_source_and_confidence():
    for r in RULES.values():
        assert r.confidence in {"primary", "secondary", "firm-policy", "unverified"}, r.id
        assert r.source, r.id
    # legacy-page rules must never be presented as primary
    assert RULES["AM-TRAIN"].confidence == "unverified" and RULES["AM-AUDIT"].confidence == "unverified"
    assert RULES["AM-REG"].confidence == "primary" and RULES["AC-QM"].confidence == "primary"
    assert len(PDPA_RULE_IDS) == 22


def test_pdpa_score_unchanged_by_other_frameworks():
    df = messy_students()
    base = assess(df).pdpa_score
    with_scope = assess(df, {"AM-REG": True, "AC-QM": False}, scopes={"csp", "pae"}).pdpa_score
    assert base == with_scope                      # AML/ACRA answers never leak into the PDPA number


def test_aml_scoring_needs_scope_and_a_client_file():
    c = messy_clients()
    assert assess(c, scopes=set()).frameworks["AML/CFT"]["score"] is None
    r = assess(c, scopes={"csp"}, as_of=ANCHOR)
    assert r.frameworks["AML/CFT"]["score"] is not None
    ids = {x.rule.id for x in r.failing()}
    assert {"X-CDD-BO", "X-CDD-REVIEW", "X-CDD-SCREEN"} <= ids
    # a student table is not a client file -> CDD rules not assessed rather than failed
    assert assess(messy_students(), scopes={"csp"}, as_of=ANCHOR).frameworks["AML/CFT"]["score"] is None


def test_cdd_review_cycle_is_a_parameter():
    c = messy_clients()
    short = assess(c, scopes={"csp"}, review_days=30, as_of=ANCHOR).frameworks["AML/CFT"]["score"]
    long_ = assess(c, scopes={"csp"}, review_days=1000, as_of=ANCHOR).frameworks["AML/CFT"]["score"]
    assert long_ > short


def test_acra_and_attestation_scoring():
    c = messy_clients()
    none = assess(c, scopes={"pae"}, as_of=ANCHOR).frameworks["ACRA"]
    assert none["score"] is None                    # unanswered = not assessed
    yes = assess(c, {"AC-QM": True, "AC-PMP": True, "AC-AML-INSP": True}, scopes={"pae"}, as_of=ANCHOR).frameworks["ACRA"]["score"]
    no = assess(c, {"AC-QM": False, "AC-PMP": False, "AC-AML-INSP": False}, scopes={"pae"}, as_of=ANCHOR).frameworks["ACRA"]["score"]
    assert yes == 100.0 and no == 0.0
    # out-of-scope questions are ignored
    assert assess(c, {"AC-QM": False}, scopes=set()).frameworks["ACRA"]["score"] is None


def test_data_intermediary_scope_s4_2():
    p = messy_payroll()
    normal = assess(p, as_of=ANCHOR)
    di = assess(p, as_of=ANCHOR, intermediary=True)
    ids = {c.rule.id for c in di.checks if c.applicable and c.rule.id in PDPA_RULE_IDS}
    assert ids <= {"D-PROT-NRIC", "D-PROT-OTHER", "D-RET", "P-ACCESS", "P-DRIFT", "P-AUDIT", "A-BREACH"}
    assert "D-CONS" in {c.rule.id for c in normal.failing()} and "D-CONS" not in {c.rule.id for c in di.failing()}
    assert "D-PROT-NRIC" in {c.rule.id for c in di.failing()}      # s.24 still applies


def test_new_detectors():
    r = assess(messy_payroll(), as_of=ANCHOR)
    classes = {f.column: f.data_class for f in r.findings}
    assert classes["basic_salary"] == "salary" and classes["cpf_employee"] == "cpf" and classes["bank_account"] == "financial"


def test_salary_band_masking_and_detection():
    assert mask_value("3650.5", "salary", "generalise") == "band 3000-3999"
    assert mask_value("abc", "salary", "generalise") == "[GENERALISED]"
    out, _ = apply_governance(messy_payroll())
    assert out["basic_salary"].str.startswith("band ").all()
    # banded salary is recognised as no longer exposed
    sal = [f for f in assess(out, as_of=ANCHOR).findings if f.column == "basic_salary"][0]
    assert sal.unmasked_ratio == 0.0


def test_legal_hold_enforced_in_policy_and_governance():
    assert policy_errors(ACCT) == []
    bad = ACCT.replace("retention_days: 2190", "retention_days: 365")
    assert any("legal minimum" in e for e in policy_errors(bad))
    no_basis = ACCT.replace("  legal_basis:", "  #legal_basis:", 1)
    assert policy_errors(no_basis)                  # a legal hold must cite its legal basis
    out, log = apply_governance(messy_clients(), retention_days=365, legal_hold_days=1825, legal_basis="test basis")
    assert any("Retention raised" in x for x in log)
    d = pd.to_datetime(out["retention_until"]) - pd.to_datetime(out["date_onboarded"])
    assert (d.dt.days == 1825).all()


def test_accounting_policy_compiles_with_client_segregation():
    sql = ";\n".join(compile_policy(load_policy(ACCT)).statements)
    assert "current_setting('pdpa.app_user', true)" in sql
    assert 'CREATE VIEW "v_junior"."payroll"' in sql and "band " in sql and "'^[0-9]+" in sql
    # roles with no payroll grant get no payroll view
    assert 'CREATE VIEW "v_intern"."payroll"' not in sql and 'CREATE VIEW "v_compliance_officer"."payroll"' not in sql


def test_client_breach_notice_s26c3a():
    from pdpa_guard.breach import draft_client_notice
    txt = draft_client_notice({"opened_at": "x", "trigger": "t", "data_classes": ["nric"], "estimated_individuals": 3}, "Firm", "ClientCo")
    assert "26C(3)(a)" in txt and "without undue delay" in txt

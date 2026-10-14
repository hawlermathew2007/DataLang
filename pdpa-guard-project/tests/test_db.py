"""Integration tests - need PostgreSQL. Set PDPA_GUARD_TEST_DSN to run (a scratch database!)."""
import os
from pathlib import Path

import pytest

DSN = os.environ.get("PDPA_GUARD_TEST_DSN")
pytestmark = pytest.mark.skipif(not DSN, reason="PDPA_GUARD_TEST_DSN not set")

from pdpa_guard.db import Database, Gateway          # noqa: E402
from pdpa_guard.policy import load_policy           # noqa: E402
from pdpa_guard.remediate import apply_governance   # noqa: E402
from pdpa_guard.sample import messy_students        # noqa: E402

YAML = (Path(__file__).resolve().parent.parent / "policies" / "tuition_centre.yaml").read_text()


@pytest.fixture(scope="module")
def env():
    db = Database(DSN); db.install()
    clean, _ = apply_governance(messy_students(), mask=False, default_purpose="enrolment")
    db.load_dataframe(clean, "students")
    pol = load_policy(YAML); db.apply_policy(pol, YAML); db.reset_audit()
    return db, pol, Gateway(db, pol)


def test_masking_enforced(env):
    db, pol, gw = env
    r = gw.execute("amy", "admin_staff", "select nric from students limit 3", purpose="enrol")
    assert r.ok and all("****" in row[0] for row in r.rows)
    r = gw.execute("pyaesonephyo", "dpo", "select nric from students limit 3")
    assert r.ok and all("*" not in row[0] for row in r.rows)


def test_least_privilege(env):
    db, pol, gw = env
    assert not gw.execute("tom", "teacher", "select nric from students").ok
    assert not gw.execute("tom", "teacher", "select * from public.students").ok
    assert not gw.execute("tom", "teacher", "update students set country='SG'").ok
    assert not gw.execute("ivy", "intern", "select pdpa_audit.tok('S1234567D')").ok
    r = gw.execute("ivy", "intern", "select student_name from students limit 2")
    assert r.ok and r.rows[0][0].startswith("tok_")


def test_edit_rules_and_purpose(env):
    db, pol, gw = env
    assert not gw.execute("amy", "admin_staff", "select * from students limit 1").ok          # no purpose
    assert gw.execute("amy", "admin_staff", "update students set phone='+6590000000' where id=1", purpose="fix").ok
    assert not gw.execute("amy", "admin_staff", "update students set nric='S0000000I' where id=1", purpose="x").ok
    assert any(c["app_user"] == "amy" and c["op"] == "UPDATE" for c in db.changes())


def test_row_filter_consent(env):
    db, pol, gw = env
    r = gw.execute("mia", "marketing", "select distinct parent_consent from students", purpose="newsletter")
    assert r.ok and r.rows == [("yes",)]


def test_block_approval_monitor_and_drift(env):
    db, pol, gw = env
    db.reset_audit()
    r = gw.execute("amy", "admin_staff", "select * from students", purpose="export")
    assert not r.ok and r.blocked_by == "bulk-read"
    assert gw.execute("amy", "admin_staff", "select * from students", purpose="export", approved=True).ok
    assert db.run_monitor(pol) >= 1 and db.cases()
    assert db.live_score(90) < 90
    assert db.detect_drift(pol) == []
    db.conn.execute("GRANT SELECT ON public.students TO pdpa_intern")
    assert any(d["role"] == "intern" for d in db.detect_drift(pol))
    db.apply_policy(pol, YAML)
    assert db.detect_drift(pol) == []


def test_sql_literals_not_logged(env):
    db, pol, gw = env
    gw.execute("pyaesonephyo", "dpo", "select * from students where nric = 'S1234567D'")
    assert not any("S1234567D" in (e["sql_text"] or "") for e in db.events())


# ---------------- accounting firm: client segregation ----------------
ACCT_YAML = (Path(__file__).resolve().parent.parent / "policies" / "accounting_firm.yaml").read_text()


@pytest.fixture(scope="module")
def acct():
    from pdpa_guard.sample import assignments, messy_clients, messy_payroll
    db = Database(DSN); db.install()
    pol = load_policy(ACCT_YAML)
    s = pol.settings
    kw = dict(mask=False, default_purpose=s.default_purpose, retention_days=s.retention_days,
              legal_hold_days=s.legal_hold_days, legal_basis=s.legal_basis)
    db.load_dataframe(apply_governance(messy_clients(), **kw)[0], "clients_cdd")
    db.load_dataframe(apply_governance(messy_payroll(), **kw)[0], "payroll")
    db.load_dataframe(assignments(), "assignments")
    db.apply_policy(pol, ACCT_YAML); db.reset_audit()
    return db, pol, Gateway(db, pol)


def test_client_segregation_row_filter(acct):
    db, pol, gw = acct
    r = gw.execute("sam", "senior", "select distinct client_id from payroll", purpose="payroll run")
    assert r.ok and {x[0] for x in r.rows} == {f"C{i:03d}" for i in range(1, 7)}
    r = gw.execute("jo", "junior", "select count(*) from payroll where client_id = 'C001'", purpose="review")
    assert r.ok and r.rows == [(0,)]                    # C001 belongs to sam, not jo


def test_junior_sees_salary_band_and_token_only(acct):
    db, pol, gw = acct
    r = gw.execute("jo", "junior", "select employee_name, basic_salary from payroll limit 3", purpose="review")
    assert r.ok and all(n.startswith("tok_") and b.startswith("band ") for n, b in r.rows)
    assert not gw.execute("jo", "junior", "select nric from payroll", purpose="review").ok
    assert not gw.execute("jo", "junior", "select bank_account from payroll", purpose="review").ok


def test_no_payroll_for_compliance_officer_and_intern(acct):
    db, pol, gw = acct
    assert not gw.execute("carol", "compliance_officer", "select * from payroll", purpose="x").ok
    assert not gw.execute("ivy", "intern", "select * from payroll").ok
    r = gw.execute("carol", "compliance_officer", "select beneficial_owner, risk_rating from clients_cdd limit 2", purpose="CDD")
    assert r.ok


def test_senior_edit_limits_and_bulk_block(acct):
    db, pol, gw = acct
    assert gw.execute("sam", "senior", "update clients_cdd set last_cdd_date='2026-10-10' where client_id='C001'", purpose="refresh").ok
    assert not gw.execute("sam", "senior", "update clients_cdd set risk_rating='low' where client_id='C001'", purpose="x").ok
    r = gw.execute("sam", "senior", "select * from payroll", purpose="export")
    assert not r.ok and r.blocked_by == "bulk-read"
    assert db.detect_drift(pol) == []

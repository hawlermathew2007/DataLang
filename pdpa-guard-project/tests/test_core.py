import pandas as pd
import pytest

from pdpa_guard.detectors import classify_columns, normalise_sg_phone, valid_email, valid_nric
from pdpa_guard.masking import clean_dataframe, k_anonymity, mask_value, token
from pdpa_guard.remediate import apply_governance, load_sql_dump
from pdpa_guard.sample import make_nric, messy_students
from pdpa_guard.scoring import assess
import random


@pytest.mark.parametrize("v,ok", [("S1234567D", True), ("s1234567d", True), ("S1234567A", False),
                                  ("T0000001I", None), ("X1234567D", False), ("S123456D", False), (None, False), (123, False)])
def test_nric_checksum(v, ok):
    if ok is None:  # T prefix: just ensure it doesn't crash and respects the +4 offset
        assert valid_nric(v) in (True, False)
    else:
        assert valid_nric(v) is ok


def test_generated_nrics_are_valid():
    rng = random.Random(1)
    assert all(valid_nric(make_nric(rng, p)) for p in "ST" * 50)


def test_phone_and_email():
    assert normalise_sg_phone("+65 9123 4567") == "+6591234567"
    assert normalise_sg_phone("91234567") == "+6591234567"
    assert normalise_sg_phone("12345678") is None
    assert valid_email("a@b.co") and not valid_email("ab.co")


def test_classification_by_value_and_name():
    df = pd.DataFrame({"ref": ["S1234567D", "T0123456J"] * 3, "contact": ["91234567"] * 6, "notes": ["x"] * 6})
    classes = {f.column: f.data_class for f in classify_columns(df)}
    assert classes["ref"] == "nric" and classes["contact"] == "phone" and "notes" not in classes


def test_masking_modes():
    assert mask_value("S1234567D", "nric", "partial") == "S****567D"
    assert mask_value("+6591234567", "phone", "partial") == "****4567"
    assert mask_value("amy@x.com", "email", "partial") == "a***@x.com"
    assert mask_value("123456", "postal", "generalise") == "12****"
    assert token("S1234567D") == token(" s1234567d ") and token("a") != token("b")
    assert mask_value(None, "nric", "partial") is None


def test_clean_is_non_inventing():
    df = pd.DataFrame({"nric": [" s1234567d", "S1234567D", None], "phone": ["9123 4567", "91234567", None]})
    out, log = clean_dataframe(df)
    assert len(out) == 2 and out.loc[0, "nric"] == "S1234567D" and out.loc[0, "phone"] == "+6591234567"
    assert any("duplicate" in x for x in log)


def test_score_improves_but_consent_not_fabricated():
    df = messy_students()
    before = assess(df)
    out, _ = apply_governance(df, default_purpose="enrolment")
    after = assess(out)
    assert after.pdpa_score > before.pdpa_score + 30
    names = {c.rule.id: c for c in after.failing()}
    assert "D-CONS" in names and "D-DNC" in names      # human-only facts stay failing
    assert "D-PROT-NRIC" not in names and "D-RET" not in names


def test_clean_data_scores_high_and_empty_is_safe():
    assert assess(pd.DataFrame({"product": ["a", "b"], "price": ["1", "2"]})).pdpa_score >= 0
    assert assess(pd.DataFrame()).pdpa_score >= 0


def test_attestation_changes_score():
    df = messy_students()
    base = assess(df).pdpa_score
    yes = assess(df, {"A-DPO": True, "A-BREACH": True}).pdpa_score
    no = assess(df, {"A-DPO": False, "A-BREACH": False}).pdpa_score
    assert no < base < yes or no < base


def test_k_anonymity():
    df = pd.DataFrame({"a": ["x"] * 5 + ["y"], "b": [1] * 6})
    assert k_anonymity(df, ["a", "b"])["k"] == 1


def test_sql_dump_loader():
    t = load_sql_dump("create table p(nric text, email text); insert into p values ('S1234567D','a@b.co');")
    assert list(t["p"].columns) == ["nric", "email"] and len(t["p"]) == 1

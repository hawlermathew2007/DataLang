"""Deterministic PDPA readiness and AI-readiness scoring.

Scores are explainable: every point lost traces to a rule in the catalogue,
which cites a section of the Act. No LLM is involved in scoring.

The score measures *observable evidence*. It is not a legal conclusion.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re

import pandas as pd

from .catalogue import PDPA_RULE_IDS, RULES, Rule
from .detectors import (
    BO_HINTS, CDD_DATE_HINTS, CLIENT_HINTS, CONSENT_HINTS, COUNTRY_HINTS, DATA_CLASSES, DNC_HINTS,
    PURPOSE_HINTS, RETENTION_HINTS, RISK_HINTS, SCREEN_HINTS, SOF_HINTS, ColumnFinding,
    classify_columns, find_columns, normalise_sg_phone, nric_shape, valid_email, valid_nric,
)

UNKNOWN_VALUES = {"", "unknown", "n/a", "na", "none", "null", "nan", "tbd", "-", "?", "unverified"}


@dataclass
class CheckResult:
    rule: Rule
    score: float | None          # 0..1, None = not assessed
    detail: str
    columns: list[str] = field(default_factory=list)

    @property
    def applicable(self) -> bool:
        return self.score is not None

    @property
    def points_lost(self) -> float:
        return 0.0 if self.score is None else self.rule.weight * (1 - self.score)


@dataclass
class Report:
    pdpa_score: float
    coverage: float                      # share of PDPA rule weight that could be assessed
    checks: list[CheckResult]
    findings: list[ColumnFinding]
    ai: dict
    n_rows: int
    n_cols: int
    frameworks: dict = field(default_factory=dict)   # name -> {"score": float|None, "coverage": float}

    def failing(self) -> list[CheckResult]:
        return sorted([c for c in self.checks if c.applicable and c.score < 0.999],
                      key=lambda c: -c.points_lost)

    def band(self) -> str:
        s = self.pdpa_score
        return "Strong" if s >= 80 else "Fair" if s >= 60 else "Weak" if s >= 40 else "Critical"


def _populated_share(series: pd.Series) -> float:
    s = series.astype("string").str.strip().str.lower()
    ok = s.notna() & ~s.isin(UNKNOWN_VALUES)
    return float(ok.mean()) if len(s) else 0.0


def _date_share(series: pd.Series) -> float:
    if not len(series):
        return 0.0
    parsed = pd.to_datetime(series, errors="coerce", format="mixed")
    return float(parsed.notna().mean())


def run_data_checks(df: pd.DataFrame, findings: list[ColumnFinding]) -> list[CheckResult]:
    out: list[CheckResult] = []
    R = RULES
    pii = [f for f in findings if f.data_class not in ("uen",)]
    has_pii = bool(pii)

    def na(rid: str, why: str) -> CheckResult:
        return CheckResult(R[rid], None, why)

    # --- Protection ---------------------------------------------------------
    nric = [f for f in findings if f.data_class == "nric"]
    if nric:
        worst = max(f.unmasked_ratio for f in nric)
        out.append(CheckResult(R["D-PROT-NRIC"], 1 - worst,
                               f"{round(worst*100)}% of NRIC/FIN values are fully visible", [f.column for f in nric]))
    else:
        out.append(na("D-PROT-NRIC", "No NRIC/FIN column detected"))

    others = [f for f in findings if f.data_class not in ("nric", "uen") and f.sensitivity in ("high", "medium")]
    if others:
        wt = {"high": 1.0, "medium": 0.5}
        num = sum(f.unmasked_ratio * wt[f.sensitivity] for f in others)
        den = sum(wt[f.sensitivity] for f in others)
        loss = num / den
        out.append(CheckResult(R["D-PROT-OTHER"], 1 - loss,
                               f"{len(others)} identifier columns, average {round(loss*100)}% exposure (sensitivity-weighted)",
                               [f.column for f in others]))
    else:
        out.append(na("D-PROT-OTHER", "No other identifier columns detected"))

    # --- Consent / purpose / retention --------------------------------------
    for rid, hints, label in (("D-CONS", CONSENT_HINTS, "consent"), ("D-PURP", PURPOSE_HINTS, "purpose")):
        if not has_pii:
            out.append(na(rid, "No personal data detected")); continue
        cols = find_columns(df, hints)
        if not cols:
            out.append(CheckResult(R[rid], 0.0, f"No {label} column found"))
        else:
            share = max(_populated_share(df[c]) for c in cols)
            out.append(CheckResult(R[rid], share, f"{round(share*100)}% of rows have a recorded {label}", cols))

    if not has_pii:
        out.append(na("D-RET", "No personal data detected"))
    else:
        cols = find_columns(df, RETENTION_HINTS)
        if not cols:
            out.append(CheckResult(R["D-RET"], 0.0, "No retention / deletion date column found"))
        else:
            share = max(_date_share(df[c]) for c in cols)
            out.append(CheckResult(R["D-RET"], share, f"{round(share*100)}% of rows have a valid retention date", cols))

    # --- Accuracy -------------------------------------------------------------
    if pii:
        cols = [f.column for f in pii]
        comp = float(1 - df[cols].isna().mean().mean()) if len(df) else 1.0
        out.append(CheckResult(R["D-ACC-COMP"], comp, f"{round(comp*100)}% of identifier cells are filled", cols))

        dup_rows = int(df.duplicated().sum())
        dup_ids = 0
        for f in nric:
            dup_ids = max(dup_ids, int(df[f.column].dropna().astype(str).str.upper().duplicated().sum()))
        dups = max(dup_rows, dup_ids)
        share = dups / len(df) if len(df) else 0
        out.append(CheckResult(R["D-ACC-DUP"], max(0.0, 1 - share * 3),
                               f"{dups} duplicate records ({round(share*100,1)}%)", [f.column for f in nric]))

        tests = []
        for f in pii:
            s = df[f.column].dropna().astype(str).str.strip()
            s = s[s != ""]
            s = s[~s.str.contains(r"\*{3,}|REDACTED|^tok_", regex=True)]
            if s.empty:
                continue
            if f.data_class == "nric":
                tests.append((f.column, float(s.map(valid_nric).mean())))
            elif f.data_class == "email":
                tests.append((f.column, float(s.map(valid_email).mean())))
            elif f.data_class == "phone":
                tests.append((f.column, float(s.map(lambda v: normalise_sg_phone(v) is not None).mean())))
        if tests:
            avg = sum(v for _, v in tests) / len(tests)
            out.append(CheckResult(R["D-ACC-VALID"], avg, f"{round(avg*100)}% of identifiers are valid", [c for c, _ in tests]))
        else:
            out.append(na("D-ACC-VALID", "Nothing to validate (values already masked or no identifiers)"))
    else:
        for rid in ("D-ACC-COMP", "D-ACC-DUP", "D-ACC-VALID"):
            out.append(na(rid, "No personal data detected"))

    # --- DNC --------------------------------------------------------------------
    phones = [f for f in findings if f.data_class == "phone"]
    if phones:
        cols = find_columns(df, DNC_HINTS)
        if not cols:
            out.append(CheckResult(R["D-DNC"], 0.0, "Phone numbers held but no DNC / marketing-consent column"))
        else:
            share = max(_populated_share(df[c]) for c in cols)
            out.append(CheckResult(R["D-DNC"], share, f"{round(share*100)}% of rows have DNC / marketing status", cols))
    else:
        out.append(na("D-DNC", "No phone numbers detected"))

    # --- Cross-border -----------------------------------------------------------
    ccols = find_columns(df, COUNTRY_HINTS)
    if ccols:
        s = df[ccols[0]].astype("string").str.strip().str.lower()
        s = s[s.notna() & ~s.isin(UNKNOWN_VALUES)]
        if len(s):
            sg = s.isin({"sg", "sgp", "singapore"}).mean()
            out.append(CheckResult(R["D-XBORDER"], 0.5 + 0.5 * float(sg) if sg < 1 else 1.0,
                                   f"{round((1-sg)*100)}% of records reference a location outside Singapore - verify s.26 requirements",
                                   ccols))
        else:
            out.append(na("D-XBORDER", "Location column empty"))
    else:
        out.append(na("D-XBORDER", "No location column"))
    return out


# PDPA s.4(2): for personal data processed on behalf of and for the purposes of another organisation under a
# contract evidenced or made in writing, Parts 3, 4, 5, 6 (except ss.24-25), 6A (except s.26C(3)(a)) and 6B impose
# no obligation on the data intermediary. Under s.4(3) the client keeps those obligations.
INTERMEDIARY_APPLIES = {"D-PROT-NRIC", "D-PROT-OTHER", "D-RET", "P-ACCESS", "P-DRIFT", "P-AUDIT", "A-BREACH"}


def _in_scope(r: Rule, scopes: set[str]) -> bool:
    return r.applies_to == "all" or r.applies_to in scopes


def run_attest_checks(answers: dict[str, bool | None] | None, scopes: set[str] | None = None) -> list[CheckResult]:
    out = []
    scopes = scopes or set()
    for r in RULES.values():
        if r.kind != "attest" or not _in_scope(r, scopes):
            continue
        a = (answers or {}).get(r.id)
        if a is None:
            out.append(CheckResult(r, None, "Not answered"))
        else:
            out.append(CheckResult(r, 1.0 if a else 0.0, "Yes (self-attested)" if a else "No"))
    return out


def run_aml_checks(df: pd.DataFrame, scopes: set[str], review_days: int = 365,
                   as_of: pd.Timestamp | None = None) -> list[CheckResult]:
    """CDD completeness on a client table. Only when the firm declares it is a CSP."""
    ids = ("X-CDD-BO", "X-CDD-RISK", "X-CDD-SCREEN", "X-CDD-SOF", "X-CDD-REVIEW")
    if "csp" not in scopes:
        return [CheckResult(RULES[i], None, "Firm not in AML/CFT (CSP) scope") for i in ids]
    groups = {"X-CDD-BO": BO_HINTS, "X-CDD-RISK": RISK_HINTS, "X-CDD-SCREEN": SCREEN_HINTS,
              "X-CDD-SOF": SOF_HINTS, "X-CDD-REVIEW": CDD_DATE_HINTS}
    cols_by = {i: find_columns(df, h) for i, h in groups.items()}
    looks_like_clients = any(cols_by.values()) or bool(find_columns(df, CLIENT_HINTS)) or \
        any(f.data_class == "uen" for f in classify_columns(df))
    if not looks_like_clients or df.empty:
        return [CheckResult(RULES[i], None, "This table does not look like a client / CDD file") for i in ids]
    out = []
    as_of = as_of or pd.Timestamp.today().normalize()
    for i in ids:
        cols = cols_by[i]
        if not cols:
            out.append(CheckResult(RULES[i], 0.0, "No matching column found in the client file")); continue
        if i == "X-CDD-REVIEW":
            best = 0.0
            for c in cols:
                d = pd.to_datetime(df[c], errors="coerce", format="mixed")
                best = max(best, float(((as_of - d).dt.days.between(0, review_days)).mean()))
            out.append(CheckResult(RULES[i], best, f"{round(best*100)}% of clients reviewed within {review_days} days (your policy)", cols))
        else:
            share = max(_populated_share(df[c]) for c in cols)
            out.append(CheckResult(RULES[i], share, f"{round(share*100)}% of clients have this recorded", cols))
    return out


def run_policy_checks(state: dict | None) -> list[CheckResult]:
    """state: {'enforced': bool, 'drift': int, 'audit': bool} or None"""
    out = []
    for rid in ("P-ACCESS", "P-DRIFT", "P-AUDIT"):
        r = RULES[rid]
        if state is None:
            out.append(CheckResult(r, None, "No database connected")); continue
        if rid == "P-ACCESS":
            out.append(CheckResult(r, 1.0 if state.get("enforced") else 0.0,
                                   "Policy compiled and applied" if state.get("enforced") else "Policy not applied to the database"))
        elif rid == "P-DRIFT":
            d = state.get("drift", 0)
            out.append(CheckResult(r, 1.0 if d == 0 else max(0.0, 1 - 0.25 * d), f"{d} permission(s) drift from policy"))
        else:
            out.append(CheckResult(r, 1.0 if state.get("audit") else 0.0,
                                   "Audit gateway active" if state.get("audit") else "No audit trail"))
    return out


# --------------------------------------------------------------------------
# AI readiness
# --------------------------------------------------------------------------
def ai_readiness(df: pd.DataFrame, findings: list[ColumnFinding]) -> dict:
    if df.empty:
        return {"score": 0.0, "dimensions": {}}
    completeness = float(1 - df.isna().mean().mean())
    uniqueness = float(1 - df.duplicated().mean())
    # consistency: share of values in each text column that share the dominant "shape"
    def shape(v: object) -> str:
        return re.sub(r"[a-z]+", "a", re.sub(r"[A-Z]+", "A", re.sub(r"\d+", "9", str(v))))
    cons = []
    for c in df.columns:
        s = df[c].dropna()
        if len(s) and s.nunique() > 1:
            sh = s.map(shape)
            cons.append(float(sh.value_counts(normalize=True).iloc[0]) if s.nunique() > len(s) * 0.5 else 1.0)
    consistency = sum(cons) / len(cons) if cons else 1.0
    val = [1.0]
    for f in findings:
        s = df[f.column].dropna().astype(str)
        s = s[~s.str.contains(r"\*{3,}|REDACTED|^tok_", regex=True)]
        if not len(s):
            continue
        if f.data_class == "nric":
            val.append(float(s.map(valid_nric).mean()))
        elif f.data_class == "email":
            val.append(float(s.map(valid_email).mean()))
        elif f.data_class == "phone":
            val.append(float(s.map(lambda v: normalise_sg_phone(v) is not None).mean()))
    validity = sum(val) / len(val)
    hi = [f for f in findings if f.sensitivity == "high"]
    pii_safety = float(1 - sum(f.unmasked_ratio for f in hi) / len(hi)) if hi else 1.0
    dims = {"completeness": completeness, "uniqueness": uniqueness, "consistency": consistency,
            "validity": validity, "pii_safety": pii_safety}
    w = {"completeness": 0.25, "uniqueness": 0.15, "consistency": 0.2, "validity": 0.2, "pii_safety": 0.2}
    return {"score": round(100 * sum(dims[k] * w[k] for k in dims), 1),
            "dimensions": {k: round(v * 100, 1) for k, v in dims.items()}}


# --------------------------------------------------------------------------
def _score(checks: list[CheckResult], universe: float) -> tuple[float | None, float]:
    app = [c for c in checks if c.applicable]
    den = sum(c.rule.weight for c in app)
    num = sum(c.rule.weight * c.score for c in app)
    return (round(100 * num / den, 1) if den else None), (round(den / universe, 2) if universe else 0.0)


def assess(df: pd.DataFrame, attestation: dict | None = None, policy_state: dict | None = None,
           scopes: set[str] | None = None, review_days: int = 365, as_of: pd.Timestamp | None = None,
           intermediary: bool = False) -> Report:
    """PDPA score is computed from PDPA rules only. AML/CFT, ACRA and RETENTION get their own scores
    and are never blended into the PDPA number (different laws, different regulators)."""
    scopes = scopes or set()
    findings = classify_columns(df)
    checks = (run_data_checks(df, findings) + run_attest_checks(attestation, scopes)
              + run_policy_checks(policy_state) + run_aml_checks(df, scopes, review_days, as_of))
    if intermediary:
        checks = [CheckResult(c.rule, None, "Not applicable to a data intermediary under a written contract (s.4(2)); "
                                            "the client keeps this obligation (s.4(3))")
                  if c.rule.id in PDPA_RULE_IDS and c.rule.id not in INTERMEDIARY_APPLIES and c.applicable else c
                  for c in checks]
    pdpa = [c for c in checks if c.rule.id in PDPA_RULE_IDS]
    # 'not applicable' data rules (e.g. no NRIC column) are neither a pass nor a fail:
    # coverage only counts rules that could not be assessed because information is missing.
    score, coverage = _score(pdpa, sum(RULES[i].weight for i in PDPA_RULE_IDS))
    fw = {}
    for name in ("AML/CFT", "ACRA", "RETENTION"):
        sub = [c for c in checks if c.rule.framework == name]
        universe = sum(r.weight for r in RULES.values() if r.framework == name and _in_scope(r, scopes))
        fw[name] = dict(zip(("score", "coverage"), _score(sub, universe)))
    return Report(pdpa_score=score or 0.0, coverage=coverage, checks=checks, findings=findings,
                  ai=ai_readiness(df, findings), n_rows=len(df), n_cols=df.shape[1], frameworks=fw)

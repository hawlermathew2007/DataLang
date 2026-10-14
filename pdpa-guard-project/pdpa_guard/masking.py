"""Masking and cleaning.

Important legal distinction (shown in the UI):
* partial / redact / token = *pseudonymisation*: still personal data under the PDPA
  if the person can be identified with other information the organisation has (s.2(1)).
* truly anonymised output needs a re-identification check - see k_anonymity().
"""
from __future__ import annotations

import hashlib
import hmac
import os

import pandas as pd

from .detectors import (
    DATA_CLASSES, classify_columns, normalise_sg_phone, valid_email,
)

MASK_MODES = ("partial", "redact", "token", "generalise", "none")


def _key() -> bytes:
    return os.environ.get("PDPA_GUARD_TOKEN_KEY", "demo-key-change-me").encode()


def token(value: object, key: bytes | None = None) -> str:
    """Deterministic HMAC token: same input -> same token, so joins still work."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return value  # type: ignore[return-value]
    digest = hmac.new(key or _key(), str(value).strip().lower().encode(), hashlib.sha256).hexdigest()
    return "tok_" + digest[:12]


def mask_value(value: object, data_class: str, mode: str) -> object:
    if value is None or (isinstance(value, float) and pd.isna(value)) or mode == "none":
        return value
    v = str(value).strip()
    if v == "":
        return value
    if mode == "redact":
        return "[REDACTED]"
    if mode == "token":
        return token(v)
    if mode == "generalise":
        if data_class == "salary":
            try:
                n = float(v.replace(",", "").replace("$", ""))
                lo = int(n // 1000 * 1000)
                return f"band {lo}-{lo + 999}"
            except ValueError:
                return "[GENERALISED]"
        if data_class == "postal":
            return v[:2] + "****" if len(v) >= 2 else "******"
        if data_class == "dob":
            return v[:4] if len(v) >= 4 else "****"
        return "[GENERALISED]"
    # partial
    if data_class == "nric":
        return v[0].upper() + "****" + v[-4:].upper() if len(v) >= 5 else "*****"
    if data_class == "phone":
        n = normalise_sg_phone(v) or v
        return "****" + n[-4:]
    if data_class == "email":
        if valid_email(v):
            local, domain = v.split("@", 1)
            return local[0] + "***@" + domain
        return "[REDACTED]"
    return v[:1] + "***"


def mask_dataframe(df: pd.DataFrame, plan: dict[str, tuple[str, str]]) -> pd.DataFrame:
    """plan: column -> (data_class, mode)"""
    out = df.copy()
    for col, (cls, mode) in plan.items():
        if col in out.columns:
            out[col] = out[col].map(lambda x, c=cls, m=mode: mask_value(x, c, m))
    return out


def default_plan(df: pd.DataFrame) -> dict[str, tuple[str, str]]:
    return {f.column: (f.data_class, DATA_CLASSES[f.data_class].default_mask)
            for f in classify_columns(df) if DATA_CLASSES[f.data_class].default_mask != "none"}


# --------------------------------------------------------------------------
# Cleaning (Accuracy obligation, s.23)
# --------------------------------------------------------------------------
def clean_dataframe(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Return cleaned copy and a human-readable change log. Never invents data."""
    log: list[str] = []
    out = df.copy()
    findings = {f.column: f.data_class for f in classify_columns(out)}

    # trim whitespace in text columns
    n_trim = 0
    for c in out.columns:
        if out[c].dtype == object or str(out[c].dtype).startswith("str"):
            before = out[c].copy()
            out[c] = out[c].map(lambda x: x.strip() if isinstance(x, str) else x)
            out[c] = out[c].map(lambda x: pd.NA if isinstance(x, str) and x == "" else x)
            n_trim += int((before.fillna("") != out[c].fillna("")).sum())
    if n_trim:
        log.append(f"Trimmed whitespace / blanked empty strings in {n_trim} cells")

    for col, cls in findings.items():
        if cls == "nric":
            before = out[col].copy()
            out[col] = out[col].map(lambda x: x.upper() if isinstance(x, str) else x)
            n = int((before.fillna("") != out[col].fillna("")).sum())
            if n:
                log.append(f"[{col}] upper-cased {n} NRIC/FIN values")
        elif cls == "phone":
            before = out[col].copy()
            out[col] = out[col].map(lambda x: normalise_sg_phone(x) or x)
            n = int((before.fillna("") != out[col].fillna("")).sum())
            if n:
                log.append(f"[{col}] normalised {n} phone numbers to +65XXXXXXXX")
        elif cls == "email":
            before = out[col].copy()
            out[col] = out[col].map(lambda x: x.lower() if isinstance(x, str) else x)
            n = int((before.fillna("") != out[col].fillna("")).sum())
            if n:
                log.append(f"[{col}] lower-cased {n} emails")

    n0 = len(out)
    out = out.drop_duplicates().reset_index(drop=True)
    if len(out) < n0:
        log.append(f"Removed {n0 - len(out)} exact duplicate rows")
    # duplicate people by NRIC (keep first, report only)
    for col, cls in findings.items():
        if cls == "nric":
            dup = out[col].dropna().duplicated(keep=False).sum()
            if dup:
                log.append(f"[{col}] {int(dup)} rows share an NRIC with another row - review manually (not auto-deleted)")
    return out, log


# --------------------------------------------------------------------------
# Re-identification risk
# --------------------------------------------------------------------------
def k_anonymity(df: pd.DataFrame, quasi_identifiers: list[str]) -> dict:
    """Smallest equivalence-class size over the quasi-identifiers."""
    qi = [c for c in quasi_identifiers if c in df.columns]
    if not qi or df.empty:
        return {"k": None, "risky_rows": 0, "quasi_identifiers": qi}
    sizes = df.groupby(qi, dropna=False).size()
    k = int(sizes.min())
    risky = int(sizes[sizes < 5].sum())
    return {"k": k, "risky_rows": risky, "quasi_identifiers": qi,
            "verdict": "low risk (k>=5)" if k >= 5 else "re-identification risk: generalise further or suppress small groups"}

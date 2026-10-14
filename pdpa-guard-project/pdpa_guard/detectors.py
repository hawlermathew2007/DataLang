"""Singapore-specific PII detection.

Local only: nothing here calls an external service. Detection combines
column-name heuristics with value sampling and validates NRIC/FIN checksums
so that random 9-character strings are not flagged.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd

# --------------------------------------------------------------------------
# Validators
# --------------------------------------------------------------------------
_NRIC_RE = re.compile(r"^[STFGM]\d{7}[A-Z]$")
_ST = "JZIHGFEDCBA"
_FG = "XWUTRQPNMLK"
_M = "KLJNPQRTUWX"
_WEIGHTS = (2, 7, 6, 5, 4, 3, 2)


def valid_nric(value: object) -> bool:
    """Validate NRIC / FIN with the official checksum."""
    if not isinstance(value, str):
        return False
    v = value.strip().upper()
    if not _NRIC_RE.match(v):
        return False
    total = sum(int(d) * w for d, w in zip(v[1:8], _WEIGHTS))
    prefix = v[0]
    if prefix in "TG":
        total += 4
    elif prefix == "M":
        total += 3
    table = {"S": _ST, "T": _ST, "F": _FG, "G": _FG, "M": _M}[prefix]
    return table[total % 11] == v[8]


def nric_shape(value: object) -> bool:
    return isinstance(value, str) and bool(_NRIC_RE.match(value.strip().upper()))


_SG_PHONE_RE = re.compile(r"^(?:\+?65[\s-]?)?([3689]\d{3})[\s-]?(\d{4})$")


def normalise_sg_phone(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    m = _SG_PHONE_RE.match(value.strip())
    return f"+65{m.group(1)}{m.group(2)}" if m else None


_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def valid_email(value: object) -> bool:
    return isinstance(value, str) and bool(_EMAIL_RE.match(value.strip()))


_POSTAL_RE = re.compile(r"^\d{6}$")
_UEN_RE = re.compile(r"^(\d{8,9}[A-Z]|[TSR]\d{2}[A-Z]{2}\d{4}[A-Z])$")


def luhn(value: str) -> bool:
    digits = [int(c) for c in re.sub(r"\D", "", value)]
    if not 13 <= len(digits) <= 19:
        return False
    s = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2:
            d *= 2
            if d > 9:
                d -= 9
        s += d
    return s % 10 == 0


# --------------------------------------------------------------------------
# Column classification
# --------------------------------------------------------------------------
# data class -> (name hints, value test, sensitivity)
@dataclass(frozen=True)
class DataClass:
    name: str
    hints: tuple[str, ...]
    sensitivity: str  # high | medium | low
    default_mask: str  # partial | redact | token | generalise | none


DATA_CLASSES: dict[str, DataClass] = {
    "nric": DataClass("nric", ("nric", "fin", "ic_no", "ic_number", "identity_no", "id_number"), "high", "partial"),
    "phone": DataClass("phone", ("phone", "mobile", "contact_no", "tel", "hp"), "medium", "partial"),
    "email": DataClass("email", ("email", "e_mail"), "medium", "partial"),
    "address": DataClass("address", ("address", "addr", "street", "unit_no"), "medium", "redact"),
    "postal": DataClass("postal", ("postal", "postcode", "zip"), "low", "generalise"),
    "name": DataClass("name", ("name", "full_name", "first_name", "last_name", "surname"), "medium", "token"),
    "dob": DataClass("dob", ("dob", "birth", "date_of_birth", "birthday"), "medium", "generalise"),
    "financial": DataClass("financial", ("card", "credit", "iban", "bank_account", "account_no", "paynow"), "high", "redact"),
    "salary": DataClass("salary", ("salary", "gross_pay", "basic_pay", "basic_salary", "wage", "bonus", "income"), "high", "generalise"),
    "cpf": DataClass("cpf", ("cpf",), "high", "redact"),
    "taxref": DataClass("taxref", ("tax_ref", "income_tax_no", "tax_no", "tin"), "high", "redact"),
    "health": DataClass("health", ("diagnosis", "medical", "health", "condition", "medication", "allergy"), "high", "redact"),
    "uen": DataClass("uen", ("uen",), "low", "none"),
}

# columns that signal governance metadata, not personal data
CONSENT_HINTS = ("consent",)
PURPOSE_HINTS = ("purpose",)
RETENTION_HINTS = ("retention", "delete_after", "expiry", "expires", "purge")
DNC_HINTS = ("dnc", "do_not_call", "marketing_consent", "marketing_opt")
COUNTRY_HINTS = ("country", "region", "server_location", "data_location", "hosted_in")
# accounting / AML-CFT client-file columns
BO_HINTS = ("beneficial_owner", "ubo", "bo_name")
RISK_HINTS = ("risk_rating", "risk_level", "risk_score")
SCREEN_HINTS = ("pep", "sanction", "screening")
CDD_DATE_HINTS = ("cdd_date", "kyc_date", "last_review", "cdd_review")
SOF_HINTS = ("source_of_funds", "source_of_wealth", "sof", "sow")
CLIENT_HINTS = ("client", "customer")
COLLECTED_HINTS = ("collected", "created", "signup", "registered", "joined", "onboard", "client_since")


def _name_matches(col: str, hints: tuple[str, ...]) -> bool:
    c = col.lower().replace(" ", "_")
    tokens = set(re.split(r"[^a-z0-9]+", c))
    for h in hints:
        if "_" in h or len(h) > 4:
            if h in c:
                return True
        elif h in tokens:
            return True
    return False


def find_columns(df: pd.DataFrame, hints: tuple[str, ...]) -> list[str]:
    return [c for c in df.columns if _name_matches(str(c), hints)]


@dataclass
class ColumnFinding:
    column: str
    data_class: str
    sensitivity: str
    evidence: str            # "name", "values", "name+values"
    match_ratio: float       # share of non-null values that look like this class
    unmasked_ratio: float    # share of values that are fully visible
    sample_size: int = 0
    notes: list[str] = field(default_factory=list)


def _sample(series: pd.Series, n: int = 500) -> pd.Series:
    s = series.dropna().astype(str).str.strip()
    s = s[s != ""]
    return s.head(n)


def _value_ratio(cls: str, s: pd.Series) -> float:
    if s.empty:
        return 0.0
    if cls == "nric":
        return float(s.map(nric_shape).mean())
    if cls == "phone":
        return float(s.map(lambda v: normalise_sg_phone(v) is not None).mean())
    if cls == "email":
        return float(s.map(valid_email).mean())
    if cls == "postal":
        return float(s.map(lambda v: bool(_POSTAL_RE.match(v))).mean())
    if cls == "uen":
        return float(s.map(lambda v: bool(_UEN_RE.match(v.upper()))).mean())
    if cls == "financial":
        return float(s.map(luhn).mean())
    return 0.0


def _unmasked_ratio(cls: str, s: pd.Series) -> float:
    """Share of values that expose the full identifier."""
    if s.empty:
        return 0.0
    masked = s.str.contains(r"[\*xX#]{3,}|REDACTED|^tok_|^band \d", regex=True)
    if cls in ("nric", "phone", "email", "postal", "financial"):
        full = s.map({
            "nric": nric_shape, "phone": lambda v: normalise_sg_phone(v) is not None,
            "email": valid_email, "postal": lambda v: bool(_POSTAL_RE.match(v)),
            "financial": luhn,
        }[cls])
        return float((full & ~masked).mean())
    return float((~masked).mean())


def classify_columns(df: pd.DataFrame) -> list[ColumnFinding]:
    findings: list[ColumnFinding] = []
    for col in df.columns:
        s = _sample(df[col])
        for cname, dc in DATA_CLASSES.items():
            by_name = _name_matches(str(col), dc.hints)
            ratio = _value_ratio(cname, s)
            by_value = ratio >= 0.6 and cname not in ("uen",) or (cname == "uen" and ratio >= 0.8)
            # "name" is too generic to trust from the header alone on tiny samples
            if cname == "name" and by_name and any(k in str(col).lower() for k in ("file", "product", "company", "business", "item", "brand")):
                by_name = False
            if not (by_name or by_value):
                continue
            evidence = "name+values" if by_name and by_value else ("name" if by_name else "values")
            f = ColumnFinding(
                column=str(col), data_class=cname, sensitivity=dc.sensitivity,
                evidence=evidence, match_ratio=round(ratio, 3),
                unmasked_ratio=round(_unmasked_ratio(cname, s), 3), sample_size=len(s),
            )
            if cname == "nric" and by_value:
                valid = float(s.map(valid_nric).mean())
                if valid < ratio:
                    f.notes.append(f"{round((ratio - valid) * 100)}% of NRIC-shaped values fail the checksum")
            findings.append(f)
            break  # one class per column
    return findings

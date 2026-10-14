"""One-click governance fixes.

Rule: the tool may clean, mask, and *derive* values from facts already in the data
or declared by the user. It never fabricates consent, DNC status or any other fact
only the organisation can confirm - those rules stay failing until a human supplies them.
"""
from __future__ import annotations

import io
from pathlib import Path

import pandas as pd

from .detectors import COLLECTED_HINTS, PURPOSE_HINTS, RETENTION_HINTS, find_columns
from .masking import clean_dataframe, default_plan, mask_dataframe


def load_table(name: str, data: bytes | str | Path) -> dict[str, pd.DataFrame]:
    """Load CSV / Excel (all sheets) / SQL INSERT dump into DataFrames."""
    lower = name.lower()
    if isinstance(data, (str, Path)):
        data = Path(data).read_bytes()
    if lower.endswith((".xlsx", ".xlsm", ".xls")):
        sheets = pd.read_excel(io.BytesIO(data), sheet_name=None, dtype=str)
        return {k: v for k, v in sheets.items()}
    if lower.endswith(".sql"):
        return load_sql_dump(data.decode("utf-8", "replace"))
    return {Path(name).stem: pd.read_csv(io.BytesIO(data), dtype=str, keep_default_na=True)}


def load_sql_dump(text: str) -> dict[str, pd.DataFrame]:
    """Load a SQL file by executing it in an in-memory SQLite database.

    Works for portable CREATE TABLE / INSERT dumps. For PostgreSQL-specific dumps,
    connect directly to the database instead (see db.py).
    """
    import sqlite3
    con = sqlite3.connect(":memory:")
    try:
        con.executescript(text)
        names = [r[0] for r in con.execute("select name from sqlite_master where type='table'")]
        return {n: pd.read_sql_query(f'select * from "{n}"', con).astype(str).replace({"None": pd.NA}) for n in names}
    finally:
        con.close()


def apply_governance(df: pd.DataFrame, *, retention_days: int = 730, default_purpose: str | None = None,
                     mask: bool = True, legal_hold_days: int | None = None,
                     legal_basis: str | None = None) -> tuple[pd.DataFrame, list[str]]:
    out, log = clean_dataframe(df)
    if legal_hold_days and retention_days < legal_hold_days:
        log.append(f"Retention raised from {retention_days} to {legal_hold_days} days: a legal minimum applies ({legal_basis or 'basis not stated'}). "
                   "PDPA s.25(b) permits retention while legally necessary - do not delete earlier.")
        retention_days = legal_hold_days

    # derive retention date from a collection date already in the data
    if not find_columns(out, RETENTION_HINTS):
        cdates = find_columns(out, COLLECTED_HINTS)
        if cdates:
            d = pd.to_datetime(out[cdates[0]], errors="coerce", format="mixed")
            out["retention_until"] = (d + pd.Timedelta(days=retention_days)).dt.strftime("%Y-%m-%d")
            log.append(f"Added retention_until = {cdates[0]} + {retention_days} days (from your retention policy)")
        else:
            log.append("No collection date column found - cannot derive retention dates; add one or set them manually")

    # purpose: only if the user declared one
    if default_purpose and not find_columns(out, PURPOSE_HINTS):
        out["purpose"] = default_purpose
        log.append(f"Added purpose = '{default_purpose}' (declared by you - confirm it matches what individuals were told, s.20)")

    if mask:
        plan = default_plan(out)
        # keep fields that are *not* identifiers in the clear
        out = mask_dataframe(out, plan)
        log.append("Masked: " + ", ".join(f"{c} ({m})" for c, (_, m) in plan.items()))
    return out, log

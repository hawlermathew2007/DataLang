"""PostgreSQL integration: install audit schema, apply compiled policy, audit gateway,
drift detection, monitoring, access/correction requests, retention sweep."""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import psycopg
import sqlglot
from psycopg import errors as pgerr
from psycopg.rows import dict_row
from sqlglot import exp

from .detectors import nric_shape, normalise_sg_phone, valid_nric
from .monitor import Finding, _sensitive_tables, evaluate, live_score, run_actions
from .policy import Compiled, Policy, compile_policy, db_role, q, resolve_view, view_schema

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"
_NRIC_FIND = re.compile(r"[STFGMstfgm]\d{7}[A-Za-z]")


def sanitise_ident(name: str) -> str:
    s = re.sub(r"[^a-z0-9_]+", "_", str(name).strip().lower()).strip("_") or "col"
    return ("c_" + s) if s[0].isdigit() else s


class Database:
    def __init__(self, dsn: str | None = None):
        self.dsn = dsn or os.environ.get("PDPA_GUARD_DSN", "postgresql://postgres:postgres@localhost:5432/pdpa_demo")
        self.conn = psycopg.connect(self.dsn, autocommit=True, row_factory=dict_row)

    def close(self) -> None:
        self.conn.close()

    # ---- setup -------------------------------------------------------------
    def install(self, token_key: str | None = None) -> None:
        key = token_key or os.environ.get("PDPA_GUARD_TOKEN_KEY", "demo-key-change-me")
        with self.conn.cursor() as cur:
            cur.execute((SQL_DIR / "audit_schema.sql").read_text())
            cur.execute("INSERT INTO pdpa_audit.secrets(name, value) VALUES ('token_key', %s) "
                        "ON CONFLICT (name) DO UPDATE SET value = EXCLUDED.value", (key,))

    def load_dataframe(self, df: pd.DataFrame, table: str, schema: str = "public") -> list[str]:
        cols = [sanitise_ident(c) for c in df.columns]
        seen: dict[str, int] = {}
        uniq = []
        for c in cols:
            seen[c] = seen.get(c, 0) + 1
            uniq.append(c if seen[c] == 1 else f"{c}_{seen[c]}")
        tbl = f"{q(schema)}.{q(sanitise_ident(table))}"
        with self.conn.cursor() as cur:
            cur.execute(f"DROP TABLE IF EXISTS {tbl} CASCADE")
            cur.execute(f"CREATE TABLE {tbl} (id serial PRIMARY KEY, " + ", ".join(f"{q(c)} text" for c in uniq) + ")")
            with cur.copy(f"COPY {tbl} ({', '.join(q(c) for c in uniq)}) FROM STDIN") as cp:
                for row in df.itertuples(index=False):
                    cp.write_row([None if pd.isna(v) else str(v) for v in row])
        return uniq

    # ---- policy ------------------------------------------------------------
    def apply_policy(self, policy: Policy, yaml_text: str = "") -> Compiled:
        compiled = compile_policy(policy)
        with self.conn.transaction():
            with self.conn.cursor() as cur:
                for stmt in compiled.statements:
                    cur.execute(stmt)
                cur.execute("INSERT INTO pdpa_audit.policy_state(id, applied_at, policy_name, policy_yaml) "
                            "VALUES (1, now(), %s, %s) ON CONFLICT (id) DO UPDATE SET "
                            "applied_at = now(), policy_name = EXCLUDED.policy_name, policy_yaml = EXCLUDED.policy_yaml",
                            (policy.name, yaml_text))
        return compiled

    def detect_drift(self, policy: Policy) -> list[dict]:
        """Compare *effective* privileges (incl. PUBLIC and inheritance) with the policy."""
        compiled = compile_policy(policy)
        drift: list[dict] = []
        roles = compiled.managed_roles
        with self.conn.cursor() as cur:
            for tname, t in policy.tables.items():
                schema, table = tname.split(".", 1) if "." in tname else ("public", tname)
                base = f"{q(schema)}.{q(table)}"
                cur.execute("SELECT to_regclass(%s) AS r", (base,))
                if cur.fetchone()["r"] is None:
                    continue
                for r in roles:
                    dr = db_role(r)
                    for priv in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                        cur.execute("SELECT has_table_privilege(%s, %s, %s) AS ok", (dr, base, priv))
                        if cur.fetchone()["ok"]:
                            drift.append({"role": r, "object": f"{schema}.{table}", "privilege": priv,
                                          "problem": "direct access to the base table bypasses masking"})
                    for r2 in roles:
                        vs = view_schema(r2)
                        rel = f"{q(vs)}.{q(table)}"
                        cur.execute("SELECT to_regclass(%s) AS r", (rel,))
                        if cur.fetchone()["r"] is None:
                            continue
                        exp_p = compiled.expected.get((r2, vs, table), {}) if r == r2 else {}
                        for priv, key in (("SELECT", "select"), ("INSERT", "insert"), ("DELETE", "delete")):
                            cur.execute("SELECT has_table_privilege(%s, %s, %s) AS ok", (dr, rel, priv))
                            actual = cur.fetchone()["ok"]
                            wanted = bool(exp_p.get(key))
                            if actual and not wanted:
                                drift.append({"role": r, "object": f"{vs}.{table}", "privilege": priv,
                                              "problem": "privilege not granted by policy"})
                            if wanted and not actual:
                                drift.append({"role": r, "object": f"{vs}.{table}", "privilege": priv,
                                              "problem": "privilege required by policy is missing"})
                        want_cols = set(exp_p.get("update_cols", set()))
                        for col in t.columns:
                            cur.execute("SELECT 1 FROM information_schema.columns WHERE table_schema=%s AND table_name=%s "
                                        "AND column_name=%s", (vs, table, col))
                            if cur.fetchone() is None:
                                continue
                            cur.execute("SELECT has_column_privilege(%s, %s, %s, 'UPDATE') AS ok", (dr, rel, col))
                            actual = cur.fetchone()["ok"]
                            if actual and col not in want_cols:
                                drift.append({"role": r, "object": f"{vs}.{table}.{col}", "privilege": "UPDATE",
                                              "problem": "edit right not granted by policy"})
                            if col in want_cols and not actual:
                                drift.append({"role": r, "object": f"{vs}.{table}.{col}", "privilege": "UPDATE",
                                              "problem": "edit right required by policy is missing"})
        return drift

    def policy_state(self, policy: Policy | None) -> dict:
        with self.conn.cursor() as cur:
            cur.execute("SELECT applied_at FROM pdpa_audit.policy_state WHERE id = 1")
            row = cur.fetchone()
            cur.execute("SELECT count(*) AS n FROM pdpa_audit.events")
            n = cur.fetchone()["n"]
        drift = self.detect_drift(policy) if (policy and row) else []
        return {"enforced": row is not None, "drift": len(drift), "audit": n > 0 or row is not None, "drift_items": drift}

    # ---- reading audit data --------------------------------------------------
    def events(self, limit: int = 2000) -> list[dict]:
        with self.conn.cursor() as cur:
            cur.execute("SELECT * FROM pdpa_audit.events ORDER BY id DESC LIMIT %s", (limit,))
            return list(reversed(cur.fetchall()))

    def changes(self, limit: int = 2000) -> list[dict]:
        with self.conn.cursor() as cur:
            cur.execute("SELECT * FROM pdpa_audit.changes ORDER BY id DESC LIMIT %s", (limit,))
            return list(reversed(cur.fetchall()))

    def findings(self, status: str | None = "open") -> list[dict]:
        with self.conn.cursor() as cur:
            if status:
                cur.execute("SELECT * FROM pdpa_audit.findings WHERE status = %s ORDER BY id DESC", (status,))
            else:
                cur.execute("SELECT * FROM pdpa_audit.findings ORDER BY id DESC")
            return cur.fetchall()

    def notifications(self, limit: int = 50) -> list[dict]:
        with self.conn.cursor() as cur:
            cur.execute("SELECT * FROM pdpa_audit.notifications ORDER BY id DESC LIMIT %s", (limit,))
            return cur.fetchall()

    def cases(self) -> list[dict]:
        with self.conn.cursor() as cur:
            cur.execute("SELECT * FROM pdpa_audit.breach_cases ORDER BY id DESC")
            return cur.fetchall()

    def resolve_finding(self, finding_id: int) -> None:
        with self.conn.cursor() as cur:
            cur.execute("UPDATE pdpa_audit.findings SET status = 'resolved' WHERE id = %s", (finding_id,))

    def reset_audit(self) -> None:
        with self.conn.cursor() as cur:
            cur.execute("TRUNCATE pdpa_audit.events, pdpa_audit.changes, pdpa_audit.findings, "
                        "pdpa_audit.notifications, pdpa_audit.breach_cases RESTART IDENTITY")

    # ---- monitoring -----------------------------------------------------------
    def run_monitor(self, policy: Policy) -> int:
        findings = evaluate(self.events(), policy, self.changes())
        return run_actions(findings, policy, PgSink(self))

    def live_score(self, base: float) -> float:
        return live_score(base, self.findings("open"))

    # ---- retention -----------------------------------------------------------
    def retention_overdue(self, table: str, column: str = "retention_until") -> int:
        with self.conn.cursor() as cur:
            cur.execute(f"SELECT count(*) AS n FROM {q('public')}.{q(sanitise_ident(table))} "
                        f"WHERE NULLIF({q(column)}, '')::date < current_date")
            return cur.fetchone()["n"]

    # ---- s.21 access / s.22 correction -------------------------------------------
    def find_subject(self, policy: Policy, identifier: str, years_back: int = 1) -> dict:
        ident = identifier.strip()
        phone = normalise_sg_phone(ident)
        out: dict[str, Any] = {"records": {}, "uses_last_year": [], "changes_last_year": []}
        touched: list[str] = []
        with self.conn.cursor() as cur:
            for tname, t in policy.tables.items():
                schema, table = tname.split(".", 1) if "." in tname else ("public", tname)
                conds, params = [], []
                for col, cls in t.columns.items():
                    if cls == "nric" and nric_shape(ident):
                        conds.append(f"upper({q(col)}) = %s"); params.append(ident.upper())
                    elif cls == "email" and "@" in ident:
                        conds.append(f"lower({q(col)}) = %s"); params.append(ident.lower())
                    elif cls == "phone" and phone:
                        conds.append(f"right(regexp_replace({q(col)}, '\\D', '', 'g'), 8) = %s"); params.append(phone[-8:])
                if not conds:
                    continue
                cur.execute(f"SELECT * FROM {q(schema)}.{q(table)} WHERE " + " OR ".join(conds), params)
                rows = cur.fetchall()
                if rows:
                    out["records"][tname] = rows
                    touched.append(table)
            if touched:
                cur.execute(
                    "SELECT db_role, purpose, stmt_type, count(*) AS n, min(ts) AS first, max(ts) AS last "
                    "FROM pdpa_audit.events WHERE ts > now() - make_interval(years => %s) AND NOT denied "
                    "AND tables && %s GROUP BY db_role, purpose, stmt_type ORDER BY n DESC", (years_back, touched))
                out["uses_last_year"] = cur.fetchall()
                cols = [c for t in policy.tables.values() for c, k in t.columns.items() if k in ("nric", "email", "phone")]
                if cols:
                    like = [ident.upper(), ident.lower()]
                    cur.execute("SELECT ts, app_user, tbl, op FROM pdpa_audit.changes WHERE ts > now() - make_interval(years => %s) "
                                "AND (old_row::text ILIKE %s OR new_row::text ILIKE %s) ORDER BY ts DESC",
                                (years_back, f"%{ident}%", f"%{ident}%"))
                    out["changes_last_year"] = cur.fetchall()
        return out

    def correct_field(self, policy: Policy, tname: str, pk_value: int, column: str, new_value: str, app_user: str) -> int:
        t = policy.tables[tname]
        if column not in t.columns:
            raise ValueError("unknown column")
        schema, table = tname.split(".", 1) if "." in tname else ("public", tname)
        with self.conn.transaction():
            with self.conn.cursor() as cur:
                cur.execute("SELECT set_config('pdpa.app_user', %s, true), set_config('pdpa.db_role', 'dpo', true)", (app_user,))
                cur.execute(f"UPDATE {q(schema)}.{q(table)} SET {q(column)} = %s WHERE id = %s", (new_value, pk_value))
                return cur.rowcount


class PgSink:
    def __init__(self, db: Database):
        self.db = db

    def save_finding(self, f: Finding) -> int | None:
        with self.db.conn.cursor() as cur:
            cur.execute("INSERT INTO pdpa_audit.findings(rule_id, obligation, severity, app_user, db_role, tbl, event_id, detail) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (rule_id, event_id) DO NOTHING RETURNING id",
                        (f.rule_id, f.obligation, f.severity, f.app_user, f.db_role, f.tbl, f.event_id, f.detail))
            r = cur.fetchone()
            return r["id"] if r else None

    def notify(self, to_role: str, message: str, finding_id: int | None) -> None:
        with self.db.conn.cursor() as cur:
            cur.execute("INSERT INTO pdpa_audit.notifications(to_role, message, finding_id) VALUES (%s,%s,%s)",
                        (to_role, message, finding_id))

    def save_case(self, finding_id: int | None, body: dict) -> None:
        import json
        with self.db.conn.cursor() as cur:
            cur.execute("INSERT INTO pdpa_audit.breach_cases(finding_id, body) VALUES (%s, %s::jsonb)",
                        (finding_id, json.dumps(body)))


# --------------------------------------------------------------------------
# Audit gateway: the only supported way for staff to query personal data
# --------------------------------------------------------------------------
@dataclass
class Result:
    ok: bool
    columns: list[str] = field(default_factory=list)
    rows: list[tuple] = field(default_factory=list)
    rowcount: int = 0
    error: str | None = None
    blocked_by: str | None = None
    event_id: int | None = None


class _Blocked(Exception):
    def __init__(self, rule_id: str):
        self.rule_id = rule_id


class Gateway:
    ALLOWED = (exp.Select, exp.Update, exp.Delete, exp.Insert, exp.Union)

    def __init__(self, db: Database, policy: Policy):
        self.db = db
        self.policy = policy
        self.sens = _sensitive_tables(policy)
        self.bare = {n.split(".")[-1]: t for n, t in policy.tables.items()}

    def _log(self, app_user, role, purpose, stmt, sql_text, tables, rows, denied, reason, unmasked, ms) -> int:
        with self.db.conn.cursor() as cur:
            cur.execute("INSERT INTO pdpa_audit.events(app_user, db_role, purpose, stmt_type, sql_text, tables, rows, denied, "
                        "reason, unmasked_nric, duration_ms) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                        (app_user, role, purpose or None, stmt, sql_text, tables, rows, denied, reason, unmasked, ms))
            return cur.fetchone()["id"]

    def execute(self, app_user: str, role: str, sql: str, purpose: str | None = None, approved: bool = False) -> Result:
        t0 = time.perf_counter()
        if role not in self.policy.roles:
            return Result(False, error=f"unknown role '{role}'")
        try:
            parsed = sqlglot.parse(sql, read="postgres")
        except Exception as e:  # noqa: BLE001
            return Result(False, error=f"could not parse SQL: {e}")
        if len(parsed) != 1 or parsed[0] is None or not isinstance(parsed[0], self.ALLOWED):
            return Result(False, error="only a single SELECT / INSERT / UPDATE / DELETE statement is allowed")
        tree = parsed[0]
        if "pdpa_audit" in sql.lower() or "pg_" in sql.lower().replace("pg_catalog", ""):
            return Result(False, error="statements may not reference the audit schema or system catalogs")
        stmt = {exp.Select: "SELECT", exp.Union: "SELECT", exp.Update: "UPDATE", exp.Delete: "DELETE", exp.Insert: "INSERT"}[type(tree)]
        tables = sorted({t.name.lower() for t in tree.find_all(exp.Table)})
        safe = tree.copy()
        for lit in list(safe.find_all(exp.Literal)):
            lit.replace(exp.Placeholder())            # never store literal values (may be personal data)
        safe_sql = safe.sql(dialect="postgres")
        ms = lambda: (time.perf_counter() - t0) * 1000   # noqa: E731

        # purpose limitation (s.18): refuse before touching data
        for tb in tables:
            t = self.bare.get(tb)
            if t and role in t.access and t.access[role].purpose_required and not (purpose or "").strip():
                eid = self._log(app_user, role, purpose, stmt, safe_sql, tables, 0, True, "purpose_required", 0, ms())
                return Result(False, error="A purpose is required for this data (s.18). State why you need it.", event_id=eid)

        try:
            with self.db.conn.transaction():
                with self.db.conn.cursor() as cur:
                    cur.execute("SELECT set_config('pdpa.app_user', %s, true), set_config('pdpa.db_role', %s, true)", (app_user, role))
                    cur.execute(f"SET LOCAL ROLE {q(db_role(role))}")
                    cur.execute(f"SET LOCAL search_path = {q(view_schema(role))}")
                    cur.execute(tree.sql(dialect="postgres"))
                    cols, rows = [], []
                    if cur.description:
                        cols = [d.name for d in cur.description]
                        rows = [tuple(r.values()) for r in cur.fetchall()]
                    n = len(rows) if stmt == "SELECT" else cur.rowcount
                    used_approval = self._maybe_block(stmt, n, tables, approved, role)
        except _Blocked as b:
            eid = self._log(app_user, role, purpose, stmt, safe_sql, tables, 0, True, f"blocked:{b.rule_id}", 0, ms())
            return Result(False, error=f"Blocked by rule '{b.rule_id}': DPO approval required.", blocked_by=b.rule_id, event_id=eid)
        except pgerr.InsufficientPrivilege as e:
            eid = self._log(app_user, role, purpose, stmt, safe_sql, tables, 0, True, f"permission denied: {e.diag.message_primary}", 0, ms())
            return Result(False, error=f"permission denied: {e.diag.message_primary}", event_id=eid)
        except pgerr.FeatureNotSupported as e:   # e.g. UPDATE of a masked view column
            eid = self._log(app_user, role, purpose, stmt, safe_sql, tables, 0, True,
                            f"column not editable by role: {e.diag.message_primary}", 0, ms())
            return Result(False, error=f"column not editable by your role: {e.diag.message_primary}", event_id=eid)
        except (pgerr.UndefinedColumn, pgerr.UndefinedTable) as e:
            kind = "column" if isinstance(e, pgerr.UndefinedColumn) else "relation"
            eid = self._log(app_user, role, purpose, stmt, safe_sql, tables, 0, True, f"{kind} not visible to role: {e.diag.message_primary}", 0, ms())
            return Result(False, error=f"{kind} not available to your role: {e.diag.message_primary}", event_id=eid)
        except psycopg.Error as e:
            eid = self._log(app_user, role, purpose, stmt, safe_sql, tables, 0, True, f"error: {e}", 0, ms())
            return Result(False, error=str(e), event_id=eid)

        unmasked = 0
        for r in rows[:20000]:
            for cell in r:
                if isinstance(cell, str) and _NRIC_FIND.search(cell):
                    unmasked += sum(1 for m in _NRIC_FIND.findall(cell) if valid_nric(m))
        eid = self._log(app_user, role, purpose, stmt, safe_sql, tables, n, False,
                        "dpo_approved" if used_approval else None, unmasked, ms())
        return Result(True, cols, rows, n, event_id=eid)

    def _maybe_block(self, stmt: str, n: int, tables: list[str], approved: bool, role: str) -> bool:
        """Raise _Blocked if a blocking rule applies; return True if DPO approval was consumed."""
        used = False
        if stmt != "SELECT" or not (set(tables) & self.sens):
            return False
        for rule in self.policy.monitor:
            if rule.when["type"] != "bulk_select":
                continue
            if role in rule.when.get("except_roles", []):
                continue
            names = {a: arg for a, arg in rule.actions()}
            if "block" in names and n >= int(rule.when.get("rows", 100)):
                arg = names["block"]
                unless = arg.get("unless") if isinstance(arg, dict) else arg
                if unless == "dpo_approval" and approved:
                    used = True
                    continue
                raise _Blocked(rule.id)
        return used

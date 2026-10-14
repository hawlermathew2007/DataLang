"""YAML policy language.

Two layers:

* DECLARATIVE - `roles`, `tables` (data classes and who may view/edit what, with
  which masking mode, optional row filter) and the `when:` part of monitor rules.
  Says what must be true.
* IMPERATIVE - the `then:` list of monitor rules: named Python actions
  (alert, notify_dpo, block, open_breach_case ...). Says what to do on violation.

The declarative part compiles to PostgreSQL roles, masked views and grants.
Policy files are TRUSTED ADMINISTRATOR INPUT (row filters become SQL), but all
identifiers are validated and row filters are parsed before use.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Union

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from .detectors import DATA_CLASSES

IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")
VIEW_MODES = {"full", "partial", "redact", "token", "generalise", "deny"}
RULE_TYPES = {"bulk_select", "off_hours", "denied_access", "unmasked_ids", "purpose_missing", "bulk_change"}
KNOWN_ACTIONS = {"alert", "notify_dpo", "block", "open_breach_case", "recommend"}
SEVERITIES = {"high", "medium", "low"}
CLASS_NAMES = set(DATA_CLASSES) | {"other"}


def _ident(v: str, what: str) -> str:
    if not IDENT.match(v):
        raise ValueError(f"{what} '{v}' must match [a-z_][a-z0-9_]* (lower-case, no spaces)")
    return v


class Settings(BaseModel):
    organisation: str = "My Organisation"
    retention_days: int = Field(730, ge=1)
    timezone: str = "Asia/Singapore"
    business_hours: str = "08:00-20:00"
    default_purpose: str | None = None
    sector: str = "general"                  # general | accounting
    legal_hold_days: int | None = Field(None, ge=1)   # statutory minimum retention you must honour
    legal_basis: str | None = None           # e.g. "Companies Act s.199(2); IRAS 5 years"

    @model_validator(mode="after")
    def _retention_vs_legal(self) -> "Settings":
        if self.legal_hold_days and self.retention_days < self.legal_hold_days:
            raise ValueError(f"retention_days ({self.retention_days}) is shorter than the legal minimum "
                             f"legal_hold_days ({self.legal_hold_days}); PDPA s.25(b) allows retention while legally necessary")
        if self.legal_hold_days and not self.legal_basis:
            raise ValueError("legal_hold_days requires legal_basis (cite the law)")
        return self

    @field_validator("business_hours")
    @classmethod
    def _hours(cls, v: str) -> str:
        if not re.match(r"^\d{2}:\d{2}-\d{2}:\d{2}$", v):
            raise ValueError("business_hours must look like 08:00-20:00")
        return v


class RoleDef(BaseModel):
    description: str = ""


class RoleAccess(BaseModel):
    """What one role may do on one table."""
    view: dict[str, str] = Field(default_factory=dict)   # data class | column | 'default' -> mode
    edit: list[str] = Field(default_factory=list)        # columns (shown in full) the role may update
    insert: bool = False
    delete: bool = False
    row_filter: str | None = None
    purpose_required: bool = False

    @field_validator("view")
    @classmethod
    def _modes(cls, v: dict[str, str]) -> dict[str, str]:
        for k, m in v.items():
            if m not in VIEW_MODES:
                raise ValueError(f"view mode '{m}' for '{k}' must be one of {sorted(VIEW_MODES)}")
        return v

    @field_validator("row_filter")
    @classmethod
    def _filter(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if ";" in v or "--" in v or "/*" in v:
            raise ValueError("row_filter must be a single expression without ';' or comments")
        import sqlglot
        try:
            sqlglot.parse_one(v, into=sqlglot.exp.Condition, read="postgres")
        except Exception as e:  # noqa: BLE001
            raise ValueError(f"row_filter is not a valid condition: {e}") from e
        return v


class TableDef(BaseModel):
    schema_: str = Field("public", alias="schema")
    columns: dict[str, str]                      # column -> data class
    access: dict[str, RoleAccess] = Field(default_factory=dict)  # role -> access
    pk: str | None = None

    model_config = {"populate_by_name": True}

    @field_validator("columns")
    @classmethod
    def _cols(cls, v: dict[str, str]) -> dict[str, str]:
        for c, k in v.items():
            _ident(c, "column")
            if k not in CLASS_NAMES:
                raise ValueError(f"column '{c}' has unknown data class '{k}' (use one of {sorted(CLASS_NAMES)})")
        return v


ActionItem = Union[str, dict[str, Any]]


class MonitorRule(BaseModel):
    id: str
    obligation: str = ""
    severity: str = "medium"
    when: dict[str, Any]
    then: list[ActionItem] = Field(default_factory=lambda: ["alert"])

    @field_validator("severity")
    @classmethod
    def _sev(cls, v: str) -> str:
        if v not in SEVERITIES:
            raise ValueError(f"severity must be one of {sorted(SEVERITIES)}")
        return v

    @model_validator(mode="after")
    def _check(self) -> "MonitorRule":
        t = self.when.get("type")
        if t not in RULE_TYPES:
            raise ValueError(f"rule {self.id}: when.type must be one of {sorted(RULE_TYPES)}")
        for a in self.then:
            name = a if isinstance(a, str) else next(iter(a))
            if name not in KNOWN_ACTIONS:
                raise ValueError(f"rule {self.id}: unknown action '{name}' (known: {sorted(KNOWN_ACTIONS)})")
        return self

    def actions(self) -> list[tuple[str, Any]]:
        out = []
        for a in self.then:
            if isinstance(a, str):
                out.append((a, None))
            else:
                k = next(iter(a))
                out.append((k, a[k]))
        return out


class Policy(BaseModel):
    version: int = 1
    name: str = "policy"
    settings: Settings = Field(default_factory=Settings)
    roles: dict[str, RoleDef]
    tables: dict[str, TableDef]
    monitor: list[MonitorRule] = Field(default_factory=list)

    @field_validator("roles")
    @classmethod
    def _roles(cls, v):
        for r in v:
            _ident(r, "role")
        return v

    @model_validator(mode="after")
    def _cross(self) -> "Policy":
        for tname, t in self.tables.items():
            if "." in tname:
                s, n = tname.split(".", 1)
                _ident(s, "schema"); _ident(n, "table")
            else:
                _ident(tname, "table")
            if t.pk:
                _ident(t.pk, "pk")
            for role, acc in t.access.items():
                if role not in self.roles:
                    raise ValueError(f"table {tname}: access given to undefined role '{role}'")
                for k in acc.view:
                    if k != "default" and k not in t.columns and k not in CLASS_NAMES:
                        raise ValueError(f"table {tname}/{role}: view key '{k}' is not a column, data class or 'default'")
                shown = set(resolve_view(t, acc))
                for c in acc.edit:
                    if c not in t.columns:
                        raise ValueError(f"table {tname}/{role}: cannot edit unknown column '{c}'")
                    if resolve_view(t, acc).get(c) != "full":
                        raise ValueError(f"table {tname}/{role}: role may edit '{c}' but cannot see it in full - "
                                         "editing a masked or hidden column is not allowed")
                _ = shown
        ids = [m.id for m in self.monitor]
        if len(ids) != len(set(ids)):
            raise ValueError("monitor rule ids must be unique")
        return self

    @property
    def table_names(self) -> list[str]:
        return [n if "." in n else f"public.{n}" for n in self.tables]


def resolve_view(t: TableDef, acc: RoleAccess) -> dict[str, str]:
    """column -> mode ('deny' columns are included with mode 'deny').

    Precedence: column name > data class > 'default' > deny (secure by default).
    """
    out = {}
    for col, cls in t.columns.items():
        out[col] = acc.view.get(col) or acc.view.get(cls) or acc.view.get("default") or "deny"
    return out


# --------------------------------------------------------------------------
def load_policy(text: str) -> Policy:
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError("policy YAML must be a mapping")
    return Policy.model_validate(data)


def policy_errors(text: str) -> list[str]:
    try:
        load_policy(text)
        return []
    except yaml.YAMLError as e:
        return [f"YAML syntax error: {e}"]
    except Exception as e:  # noqa: BLE001 - pydantic ValidationError
        if hasattr(e, "errors"):
            return [f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}" for err in e.errors()]  # type: ignore[attr-defined]
        return [str(e)]


# --------------------------------------------------------------------------
# Compiler: declarative policy -> PostgreSQL
# --------------------------------------------------------------------------
def q(ident: str) -> str:
    return '"' + ident.replace('"', '""') + '"'


def mask_sql(col: str, cls: str, mode: str) -> str:
    c = q(col)
    t = f"{c}::text"
    if mode == "full":
        return c
    if mode == "redact":
        return "'[REDACTED]'::text"
    if mode == "token":
        return f"pdpa_audit.tok({t})"
    if mode == "generalise":
        if cls == "salary":
            return (f"(CASE WHEN {t} ~ '^[0-9]+(\\.[0-9]+)?$' THEN 'band ' || (floor({t}::numeric / 1000) * 1000)::bigint "
                    f"|| '-' || ((floor({t}::numeric / 1000) * 1000)::bigint + 999) ELSE '[GENERALISED]' END)")
        if cls == "postal":
            return f"(left({t}, 2) || '****')"
        if cls == "dob":
            return f"left({t}, 4)"
        return "'[GENERALISED]'::text"
    if mode == "partial":
        if cls == "nric":
            return f"(upper(left({t}, 1)) || '****' || upper(right({t}, 4)))"
        if cls == "phone":
            return f"('****' || right({t}, 4))"
        if cls == "email":
            return f"(left({t}, 1) || '***@' || split_part({t}, '@', 2))"
        return f"(left({t}, 1) || '***')"
    raise ValueError(mode)


@dataclass
class Compiled:
    statements: list[str]
    # (role, schema, table) -> {"select": bool, "update_cols": set, "insert": bool, "delete": bool}
    expected: dict[tuple[str, str, str], dict] = field(default_factory=dict)
    managed_roles: list[str] = field(default_factory=list)


def db_role(name: str) -> str:
    return f"pdpa_{name}"


def view_schema(role: str) -> str:
    return f"v_{role}"


def compile_policy(p: Policy) -> Compiled:
    st: list[str] = ["CREATE EXTENSION IF NOT EXISTS pgcrypto"]
    exp: dict = {}
    roles = list(p.roles)
    needs_tok: set[str] = set()
    for r in roles:
        dr = db_role(r)
        st.append(f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{dr}') "
                  f"THEN CREATE ROLE {q(dr)} NOLOGIN; END IF; END $$")
        st.append(f"GRANT {q(dr)} TO CURRENT_USER")
        st.append(f"REVOKE ALL ON SCHEMA pdpa_audit FROM {q(dr)}")
        st.append(f"REVOKE ALL ON FUNCTION pdpa_audit.tok(text) FROM {q(dr)}")
        st.append(f"DROP SCHEMA IF EXISTS {q(view_schema(r))} CASCADE")
        st.append(f"CREATE SCHEMA {q(view_schema(r))}")
        st.append(f"GRANT USAGE ON SCHEMA {q(view_schema(r))} TO {q(dr)}")

    for tname, t in p.tables.items():
        schema, table = tname.split(".", 1) if "." in tname else ("public", tname)
        base = f"{q(schema)}.{q(table)}"
        st.append(f"REVOKE ALL ON {base} FROM PUBLIC")
        for r in roles:
            st.append(f"REVOKE ALL ON {base} FROM {q(db_role(r))}")
        # audit trigger so every change is attributable
        st.append(f"DROP TRIGGER IF EXISTS pdpa_audit_trg ON {base}")
        st.append(f"CREATE TRIGGER pdpa_audit_trg AFTER INSERT OR UPDATE OR DELETE ON {base} "
                  f"FOR EACH ROW EXECUTE FUNCTION pdpa_audit.log_change()")
        for role, acc in t.access.items():
            dr = db_role(role)
            vs = view_schema(role)
            modes = resolve_view(t, acc)
            shown = [(c, t.columns[c], m) for c, m in modes.items() if m != "deny"]
            if not shown:
                continue
            if any(m == "token" for _, _, m in shown):
                needs_tok.add(role)
            cols = ", ".join(f"{mask_sql(c, cls, m)} AS {q(c)}" for c, cls, m in shown)
            where = f" WHERE {acc.row_filter}" if acc.row_filter else ""
            check = " WITH LOCAL CHECK OPTION" if acc.row_filter else ""
            vname = f"{q(vs)}.{q(table)}"
            st.append(f"CREATE VIEW {vname} WITH (security_barrier = true) AS SELECT {cols} FROM {base}{where}{check}")
            st.append(f"GRANT SELECT ON {vname} TO {q(dr)}")
            privs = {"select": True, "update_cols": set(acc.edit), "insert": acc.insert, "delete": acc.delete}
            if acc.edit:
                st.append(f"GRANT UPDATE ({', '.join(q(c) for c in acc.edit)}) ON {vname} TO {q(dr)}")
            if acc.insert:
                st.append(f"GRANT INSERT ON {vname} TO {q(dr)}")
            if acc.delete:
                st.append(f"GRANT DELETE ON {vname} TO {q(dr)}")
            exp[(role, vs, table)] = privs
    # Function privileges inside a view are checked against the *invoking* role, so token masking
    # needs EXECUTE. The gateway rejects any statement mentioning pdpa_audit, so staff cannot call tok()
    # as an oracle; see README "Known limitations".
    for role in sorted(needs_tok):
        st.append(f"GRANT USAGE ON SCHEMA pdpa_audit TO {q(db_role(role))}")
        st.append(f"GRANT EXECUTE ON FUNCTION pdpa_audit.tok(text) TO {q(db_role(role))}")
    return Compiled(statements=st, expected=exp, managed_roles=roles)

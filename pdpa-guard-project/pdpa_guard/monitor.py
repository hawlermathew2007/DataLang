"""Database activity monitoring: pure rule evaluation + imperative action registry.

`evaluate()` is a pure function over event dictionaries so it can be unit-tested
without a database. Actions are plain Python callables registered by name; the
YAML `then:` list refers to them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Protocol
from zoneinfo import ZoneInfo

from .policy import MonitorRule, Policy, resolve_view

SEV_PENALTY = {"high": 6.0, "medium": 3.0, "low": 1.0}
MAX_PENALTY = 45.0


@dataclass
class Finding:
    rule_id: str
    obligation: str
    severity: str
    event_id: int | None
    app_user: str | None
    db_role: str | None
    tbl: str | None
    detail: str
    actions: list[tuple[str, Any]] = field(default_factory=list)
    event: dict | None = None


def _sensitive_tables(policy: Policy) -> set[str]:
    out = set()
    for tname, t in policy.tables.items():
        if any(c in ("nric", "financial", "health", "phone", "email", "name", "address", "dob", "salary", "cpf", "taxref") for c in t.columns.values()):
            out.add(tname.split(".")[-1])
    return out


def _in_hours(ts: datetime, hours: str, tz: str) -> bool:
    start, end = hours.split("-")
    t = ts.astimezone(ZoneInfo(tz)).time()
    s = datetime.strptime(start, "%H:%M").time()
    e = datetime.strptime(end, "%H:%M").time()
    return s <= t <= e


def _role_sees_full(policy: Policy, role: str | None, table: str, cls: str) -> bool:
    for tname, t in policy.tables.items():
        if tname.split(".")[-1] != table or role not in t.access:
            continue
        modes = resolve_view(t, t.access[role])
        return any(modes[c] == "full" for c, k in t.columns.items() if k == cls)
    return False


def evaluate(events: list[dict], policy: Policy, changes: list[dict] | None = None) -> list[Finding]:
    out: list[Finding] = []
    sens = _sensitive_tables(policy)
    tz = policy.settings.timezone
    for rule in policy.monitor:
        w = rule.when
        t = w["type"]
        skip = set(w.get("except_roles", []))
        evs = [e for e in events if e.get("db_role") not in skip]
        if t == "bulk_select":
            evs = [e for e in evs if e.get("reason") != "dpo_approved"]
            thr = int(w.get("rows", 100))
            for e in evs:
                if e["denied"] and (e.get("reason") or "") == f"blocked:{rule.id}":
                    out.append(_f(rule, e, "Bulk read of personal data blocked pending DPO approval"))
            for e in evs:
                if e["stmt_type"] == "SELECT" and not e["denied"] and e["rows"] >= thr and set(e["tables"]) & sens:
                    out.append(_f(rule, e, f"{e['rows']} rows read from {', '.join(e['tables'])} (limit {thr})"))
        elif t == "off_hours":
            for e in evs:
                if not e["denied"] and set(e["tables"]) & sens and not _in_hours(e["ts"], policy.settings.business_hours, tz):
                    out.append(_f(rule, e, f"Access to personal data outside {policy.settings.business_hours} ({tz})"))
        elif t == "denied_access":
            for e in evs:
                if e["denied"] and (e.get("reason") or "").startswith(("permission", "column", "relation")):
                    out.append(_f(rule, e, f"Attempted access beyond role permissions: {e['reason']}"))
        elif t == "purpose_missing":
            for e in evs:
                if e["denied"] and e.get("reason") == "purpose_required":
                    out.append(_f(rule, e, "Access attempted without a stated purpose (s.18)"))
        elif t == "unmasked_ids":
            thr = int(w.get("count", 1))
            for e in evs:
                if e["denied"] or e["unmasked_nric"] < thr:
                    continue
                tbls = [x for x in e["tables"] if x in sens]
                if tbls and not any(_role_sees_full(policy, e["db_role"], x, "nric") for x in tbls):
                    out.append(_f(rule, e, f"{e['unmasked_nric']} full NRIC/FIN values were returned to a role the policy "
                                           f"only allows masked access - possible leak or policy drift"))
        elif t == "bulk_change":
            thr = int(w.get("rows", 20))
            window = timedelta(minutes=int(w.get("window_minutes", 10)))
            by: dict[tuple, list[dict]] = {}
            for c in changes or []:
                if c.get("db_role") in skip:
                    continue
                if c["op"] in ("UPDATE", "DELETE"):
                    by.setdefault((c["app_user"], c["tbl"]), []).append(c)
            for (user, tbl), cs in by.items():
                cs.sort(key=lambda x: x["ts"])
                i = 0
                for j in range(len(cs)):
                    while cs[j]["ts"] - cs[i]["ts"] > window:
                        i += 1
                    if j - i + 1 >= thr:
                        ev = {"id": cs[j]["id"] * -1, "app_user": user, "db_role": cs[j].get("db_role"), "tables": [tbl],
                              "ts": cs[j]["ts"]}
                        out.append(_f(rule, ev, f"{j-i+1} row changes by {user} on {tbl} within {w.get('window_minutes', 10)} min"))
                        break
    return out


def _f(rule: MonitorRule, e: dict, detail: str) -> Finding:
    return Finding(rule_id=rule.id, obligation=rule.obligation, severity=rule.severity, event_id=e.get("id"),
                   app_user=e.get("app_user"), db_role=e.get("db_role"),
                   tbl=(e.get("tables") or [None])[0], detail=detail, actions=rule.actions(), event=e)


def live_score(base: float, open_findings: list[dict]) -> float:
    """Static score minus a capped penalty for open monitoring findings."""
    pen = sum(SEV_PENALTY.get(f["severity"], 1.0) for f in open_findings)
    return round(max(0.0, base - min(pen, MAX_PENALTY)), 1)


# --------------------------------------------------------------------------
# Imperative actions
# --------------------------------------------------------------------------
class Sink(Protocol):
    def save_finding(self, f: Finding) -> int | None: ...
    def notify(self, to_role: str, message: str, finding_id: int | None) -> None: ...
    def save_case(self, finding_id: int | None, body: dict) -> None: ...


ACTIONS: dict[str, Callable[..., None]] = {}


def action(name: str):
    def deco(fn):
        ACTIONS[name] = fn
        return fn
    return deco


@dataclass
class Ctx:
    finding: Finding
    finding_id: int | None
    sink: Sink
    policy: Policy


@action("alert")
def _alert(ctx: Ctx, arg: Any) -> None:
    pass  # finding is persisted before actions run


@action("notify_dpo")
def _notify(ctx: Ctx, arg: Any) -> None:
    f = ctx.finding
    ctx.sink.notify("dpo", f"[{f.severity.upper()}] {f.rule_id}: {f.detail} (user={f.app_user}, role={f.db_role})", ctx.finding_id)


@action("recommend")
def _recommend(ctx: Ctx, arg: Any) -> None:
    ctx.sink.notify("dpo", f"Recommendation for {ctx.finding.rule_id}: {arg}", ctx.finding_id)


@action("block")
def _block(ctx: Ctx, arg: Any) -> None:
    pass  # enforced inside the gateway before results are returned (see db.Gateway)


@action("open_breach_case")
def _open_case(ctx: Ctx, arg: Any) -> None:
    from .breach import build_case
    ctx.sink.save_case(ctx.finding_id, build_case(ctx.finding, ctx.policy))


def run_actions(findings: list[Finding], policy: Policy, sink: Sink) -> int:
    n = 0
    for f in findings:
        fid = sink.save_finding(f)
        if fid is None:   # already recorded earlier -> don't repeat actions
            continue
        n += 1
        for name, arg in f.actions:
            ACTIONS[name](Ctx(f, fid, sink, policy), arg)
    return n

"""Data breach response helper (Part 6A of the PDPA).

What the Act (as supplied) says, and what it does not:
* s.26C(2): assess "in a reasonable and expeditious manner" whether it is a notifiable breach.
* s.26D(1): if assessed notifiable, notify the Commission as soon as practicable and in any
  case no later than 3 calendar days after the day the assessment is made.
* s.26D(2): also notify each affected individual if the breach is likely to cause significant harm.
* s.26B(4): a breach only within an organisation is deemed NOT notifiable.
* "Significant harm" classes and the "significant scale" number are prescribed in
  REGULATIONS, not in the Act. They are configurable defaults below - verify them.
"""
from __future__ import annotations

from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo

from .catalogue import DELEGATED_PARAMS
from .policy import Policy

HIGH_HARM_CLASSES = {"nric", "financial", "health"}   # configurable default, verify against regulations


def _classes_for(policy: Policy, table: str | None) -> set[str]:
    out: set[str] = set()
    for tname, t in policy.tables.items():
        if table and tname.split(".")[-1] == table.split(".")[-1]:
            out |= set(t.columns.values())
    return out - {"other"}


def notify_deadline(assessed_at: datetime, tz: str = "Asia/Singapore") -> datetime:
    """s.26D(1): no later than 3 calendar days after the day of assessment (end of that day)."""
    d = assessed_at.astimezone(ZoneInfo(tz)).date() + timedelta(days=DELEGATED_PARAMS["breach_notify_calendar_days"])
    return datetime.combine(d, time(23, 59, 59), ZoneInfo(tz))


def build_case(finding, policy: Policy, *, now: datetime | None = None, internal_only: bool = True,
               affected: int | None = None) -> dict:
    now = now or datetime.now(ZoneInfo(policy.settings.timezone))
    e = finding.event or {}
    rows = affected if affected is not None else int(e.get("rows") or 0)
    classes = sorted(_classes_for(policy, finding.tbl))
    harm = bool(set(classes) & HIGH_HARM_CLASSES)
    scale = rows >= DELEGATED_PARAMS["breach_significant_scale_count"]
    notes = []
    if internal_only:
        notes.append("Access appears to be within the organisation. s.26B(4) deems a breach only within an organisation "
                     "NOT notifiable - but s.24 (security arrangements) still applies, and the individual may be liable "
                     "under s.48D/48E if the access was unauthorised.")
    verdict = ("Not notifiable on current facts (internal only, s.26B(4))" if internal_only else
               "Likely NOTIFIABLE - significant harm and/or scale indicated" if (harm or scale) else
               "Assess further - neither significant harm nor significant scale indicated yet")
    return {
        "title": f"Suspected data breach: {finding.rule_id}",
        "opened_at": now.isoformat(),
        "trigger": finding.detail,
        "who": {"app_user": finding.app_user, "db_role": finding.db_role},
        "table": finding.tbl,
        "estimated_individuals": rows,
        "data_classes": classes,
        "significant_harm_indicated": harm,
        "significant_scale_indicated": scale,
        "internal_only": internal_only,
        "preliminary_verdict": verdict,
        "assessment_due_note": (f"s.26C(2): assess reasonably and expeditiously. PDPC guidance (not in the Act): "
                                f"aim to complete within {DELEGATED_PARAMS['breach_assessment_target_days']} days. Verify."),
        "if_notifiable_deadline": notify_deadline(now, policy.settings.timezone).isoformat(),
        "notes": notes,
        "checklist": [
            "Contain: suspend the account / revoke the role; preserve logs (do not delete evidence)",
            "Establish what data, whose, how many, and whether access was authorised",
            "Record the assessment and the time it was concluded (starts the 3-day clock if notifiable)",
            "If notifiable: notify PDPC within 3 calendar days after the day of assessment (s.26D(1))",
            "If significant harm: notify affected individuals (s.26D(2)) unless an exception applies (s.26D(5)-(7))",
            "Tell any data intermediary involved; they must tell you without undue delay (s.26C(3))",
            "Remediate and record lessons learned",
        ],
        "disclaimer": "Draft aid only. Not legal advice. Thresholds marked as delegated come from regulations, not from the Act.",
    }


def draft_pdpc_notification(case: dict, organisation: str, contact: str = "<DPO name / email / phone>") -> str:
    return f"""DRAFT - Notification of data breach to the Personal Data Protection Commission (s.26D(1))
Organisation: {organisation}
Contact for follow-up: {contact}
Date/time breach discovered: {case['opened_at']}
Date/time assessed as notifiable: <fill in>
Summary of what happened: {case['trigger']}
Personal data involved (categories): {', '.join(case['data_classes']) or '<fill in>'}
Estimated number of affected individuals: {case['estimated_individuals']}
Access by: {case['who']['app_user']} (role {case['who']['db_role']})
Containment / remediation steps taken: <fill in>
Whether affected individuals have been or will be notified: <fill in>
Note: confirm the prescribed content and form with the Commission's current notification requirements (s.26D(3)-(4)).
"""


def draft_individual_notice(case: dict, organisation: str) -> str:
    return f"""DRAFT - Notice to affected individual (s.26D(2))
Dear <name>,
{organisation} has discovered that some of your personal data ({', '.join(case['data_classes']) or '<categories>'}) may have been accessed without authorisation.
What happened: <plain-language summary>
What we have done: <containment steps>
What you can do: <e.g. watch for scam calls, change passwords>
Contact: <DPO business contact>
"""


def draft_client_notice(case: dict, firm: str, client: str = "<client name>") -> str:
    """s.26C(3)(a): a data intermediary that has reason to believe a breach occurred must notify the
    organisation on whose behalf it processes the data WITHOUT UNDUE DELAY. The client then assesses (s.26C(3)(b))."""
    return f"""DRAFT - Notice from data intermediary to client (s.26C(3)(a), without undue delay)
To: {client}
From: {firm}
We have reason to believe a data breach may have occurred in personal data we process on your behalf.
Discovered: {case['opened_at']}
What we know: {case['trigger']}
Data categories: {', '.join(case['data_classes']) or '<fill in>'}
Estimated individuals affected: {case['estimated_individuals']}
Containment steps taken: <fill in>
You are responsible for assessing whether this is a notifiable data breach (s.26C(3)(b)). We will support your assessment.
Contact: <partner / DPO>
"""

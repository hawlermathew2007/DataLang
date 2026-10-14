"""PDPA rule catalogue.

Each rule maps a check to a section of the Personal Data Protection Act 2012
(as supplied in sample_data/PDPA_2012.txt). Parameters that the Act delegates
to regulations (e.g. the breach "significant scale" threshold) are configurable
and flagged `delegated=True` so they are verified against current regulations
and PDPC guidelines rather than hard-coded as law.

NOT LEGAL ADVICE.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    id: str
    title: str
    section: str          # PDPA reference
    obligation: str
    kind: str             # "data" (observable in data) | "attest" (questionnaire) | "policy" (DB/policy)
    severity: str         # high | medium | low
    weight: float
    remediation: str
    delegated: bool = False
    framework: str = "PDPA"          # PDPA | AML/CFT | ACRA | RETENTION
    applies_to: str = "all"          # all | csp | pae   (scope the firm declares)
    confidence: str = "primary"      # primary = official page/Act text read; secondary = law-firm/industry article;
                                     # firm-policy = a configurable internal parameter, not a legal rule
    source: str = "PDPA 2012 (supplied text)"


CONFIDENCE_NOTE = {
    "primary": "Traceable to an official page / the Act text that was read",
    "secondary": "From a law-firm or industry article: verify against the CSP Regulations 2025 and ACRA Guidelines",
    "firm-policy": "A configurable internal parameter, not a legal rule",
    "unverified": "From a pre-2025 / legacy page: treat as good practice until verified",
}

SEVERITY_FACTOR = {"high": 1.0, "medium": 0.6, "low": 0.3}

RULES: dict[str, Rule] = {r.id: r for r in [
    # ---- observable in data ------------------------------------------------
    Rule("D-PROT-NRIC", "NRIC/FIN values stored in the clear", "s.24",
         "Protection", "data", "high", 12,
         "Mask or tokenise NRIC/FIN; show only partial values to staff who need them. Collect NRIC only where required by law or clearly necessary."),
    Rule("D-PROT-OTHER", "Other direct identifiers / sensitive data in the clear", "s.24",
         "Protection", "data", "high", 8,
         "Apply masking to financial, health, address and contact columns for roles that do not need full values."),
    Rule("D-CONS", "No populated consent record", "s.13, s.14",
         "Consent", "data", "high", 10,
         "Record consent (or the lawful basis relied on) per individual: status, date and source. Only the organisation can confirm this."),
    Rule("D-PURP", "No populated purpose column", "s.18, s.20",
         "Purpose limitation / notification", "data", "medium", 6,
         "Record the purpose(s) each record was collected for and notified to the individual."),
    Rule("D-RET", "No retention / deletion date", "s.25",
         "Retention limitation", "data", "medium", 8,
         "Add a retention date derived from the collection date and your retention policy; sweep and delete or de-identify when it passes."),
    Rule("D-ACC-COMP", "Incomplete personal data", "s.23",
         "Accuracy", "data", "medium", 5,
         "Fill or verify missing values where data is used for decisions about individuals or disclosed to others."),
    Rule("D-ACC-DUP", "Duplicate records for the same individual", "s.23",
         "Accuracy", "data", "medium", 4,
         "Merge or remove duplicate individuals so corrections (s.22) reach every copy."),
    Rule("D-ACC-VALID", "Invalid identifiers (bad NRIC checksum, email, phone)", "s.23",
         "Accuracy", "data", "medium", 4,
         "Correct or flag values that cannot be valid."),
    Rule("D-DNC", "Phone numbers held without Do Not Call / marketing-consent status", "Part 9, s.43",
         "Do Not Call", "data", "medium", 4,
         "Track marketing consent and DNC check date before sending any specified message (ss.43-44)."),
    Rule("D-XBORDER", "Records or hosting location outside Singapore", "s.26",
         "Transfer limitation", "data", "medium", 5,
         "Confirm the transfer requirements (comparable protection) are met for each overseas recipient.", True),
    # ---- policy / database -------------------------------------------------
    Rule("P-ACCESS", "Access rules not enforced in the database", "s.24, s.53(2)",
         "Protection", "policy", "high", 10,
         "Compile the YAML policy to database roles, masked views and grants, so staff cannot see more than their role allows."),
    Rule("P-DRIFT", "Database permissions drift from the written policy", "s.24",
         "Protection", "policy", "high", 8,
         "Revoke grants that the policy does not allow, or update the policy and re-approve it."),
    Rule("P-AUDIT", "No activity log of who accessed personal data", "s.21(1)(b), s.24",
         "Access request / Protection", "policy", "medium", 6,
         "Route staff access through the audit gateway so uses/disclosures in the last year can be reported."),
    # ---- attestation ---------------------------------------------------------
    Rule("A-DPO", "No individual designated responsible for PDPA", "s.11(3)",
         "Accountability", "attest", "high", 8, "Designate at least one individual (a 'DPO')."),
    Rule("A-DPO-PUBLIC", "Business contact of the designated individual not public", "s.11(5)",
         "Accountability", "attest", "medium", 4, "Publish the DPO's business contact information (e.g. website footer)."),
    Rule("A-POLICY", "No written data protection policies and practices", "s.12(a), s.12(d)",
         "Policies", "attest", "high", 6, "Write and implement policies; make information about them available on request."),
    Rule("A-COMPLAINT", "No complaint handling process", "s.12(b)",
         "Policies", "attest", "medium", 4, "Define how complaints are received and answered."),
    Rule("A-STAFF", "Policies not communicated to staff", "s.12(c)",
         "Policies", "attest", "medium", 4, "Brief staff on the policies; keep a record."),
    Rule("A-NOTICE", "Individuals not told the purposes at collection", "s.20",
         "Notification of purpose", "attest", "high", 6, "Give a notice stating the purposes on or before collection."),
    Rule("A-ACCESS-PROC", "No process for access and correction requests", "s.21, s.22",
         "Access / correction", "attest", "medium", 4, "Define who handles requests, and how they are verified and answered."),
    Rule("A-BREACH", "No data breach response plan", "s.26C, s.26D",
         "Breach notification", "attest", "high", 8,
         "Plan how to assess a suspected breach and notify the PDPC no later than 3 calendar days after assessing it is notifiable.", True),
    Rule("A-DI", "Vendors handling personal data not bound by written contract", "s.4(2)-(3)",
         "Data intermediaries", "attest", "medium", 4, "Use written contracts with security and breach-notification clauses."),
]}

_ACRA_CSP = "https://www.acra.gov.sg/regulations/legislation/corporate-service-providers-act/"
_AG = "https://www.allenandgledhill.com/sg/publication/articles/30601/corporate-service-providers-act-2024-to-come-into-effect-on-9-june-2025"
_ANL = "https://anliangroup.com/insights/cdd-aml-cspa-2024-corporate-service-providers"
_ACRA_725 = "https://www.acra.gov.sg/news-events/news-announcements/725/"
_IRAS = "https://www.iras.gov.sg/irashome/Businesses/Self-Employed/Learning-the-basics/Keeping-Proper-Records-and-Accounts/"
_LEGACY = "https://www.ingenique.net/7-things-you-need-to-do-to-comply-with-acra-amlcft-requirements/"

NON_PDPA_RULES: dict[str, Rule] = {r.id: r for r in [
    # ---------------- AML/CFT (Corporate Service Providers Act 2024) ----------------
    Rule("AM-REG", "Registered with ACRA as a corporate service provider", "CSP Act 2024",
         "Registration", "attest", "high", 8,
         "Any business providing corporate services (incl. designated accounting activities) in/from Singapore must register; failure is an offence (up to $50,000 and/or 2 years).",
         framework="AML/CFT", applies_to="csp", confidence="primary", source=_ACRA_CSP),
    Rule("AM-RQI", "Registered Qualified Individual(s) designated for AML/CFT/PF", "CSP Act 2024 / Regs 2025",
         "Accountability", "attest", "high", 6,
         "Designate and register the individual(s) personally responsible for AML/CFT/PF compliance. Confirm the exact term and duties in the CSP Regulations 2025.",
         framework="AML/CFT", applies_to="csp", confidence="secondary", source=_ANL),
    Rule("AM-POLICY", "Written AML/CFT/PF policies, procedures and risk assessment", "CSP Act 2024 / ACRA Guidelines",
         "Internal controls", "attest", "high", 8,
         "Document risk assessment of customers, jurisdictions and services, plus CDD, ongoing monitoring, record keeping and STR procedures. Align with ACRA's guidelines for registered CSPs (9 May 2025).",
         framework="AML/CFT", applies_to="csp", confidence="secondary", source=_ANL),
    Rule("AM-CDD-PROC", "Customer due diligence performed before designated transactions", "CSP Regs 2025",
         "Customer due diligence", "attest", "high", 8,
         "Identify and verify the customer and beneficial owner and the purpose of the relationship before incorporation, address, nominee or other designated transactions.",
         framework="AML/CFT", applies_to="csp", confidence="secondary", source=_ANL),
    Rule("AM-SCREEN", "Sanctions and PEP screening", "ACRA Guidelines",
         "Screening", "attest", "medium", 5,
         "Screen customers and beneficial owners against sanctions lists and for PEP status at onboarding and on an ongoing basis.",
         framework="AML/CFT", applies_to="csp", confidence="secondary", source=_ANL),
    Rule("AM-STR", "Process to file suspicious transaction reports; no tipping-off", "CDSA s.39, s.48 (per secondary source)",
         "Suspicious transaction reporting", "attest", "high", 7,
         "Know how to file with STRO (STROLLS), who decides, and that the client must not be told. Verify the provisions on the Singapore Statutes Online.",
         framework="AML/CFT", applies_to="csp", confidence="secondary", source=_ANL),
    Rule("AM-TRAIN", "AML/CFT staff training with records", "ACRA guidance (legacy page; verify)",
         "Training", "attest", "medium", 4,
         "Train new staff soon after joining and at least annually, and keep attendance records. The 3-month / annual cadence comes from a pre-2025 industry page: check the current ACRA guidelines.",
         framework="AML/CFT", applies_to="csp", confidence="unverified", source=_LEGACY),
    Rule("AM-AUDIT", "Independent review of AML/CFT controls", "ACRA guidance (legacy page; verify)",
         "Independent review", "attest", "medium", 4,
         "Have someone other than the compliance officer review control effectiveness periodically.",
         framework="AML/CFT", applies_to="csp", confidence="unverified", source=_LEGACY),
    # data-observable CDD completeness on a client table
    Rule("X-CDD-BO", "Beneficial owner recorded for each client", "CSP Regs 2025 (CDD)",
         "Customer due diligence", "data", "high", 8,
         "Record and verify the beneficial owner for every client in a designated relationship.",
         framework="AML/CFT", applies_to="csp", confidence="secondary", source=_ANL),
    Rule("X-CDD-RISK", "Customer risk rating recorded", "ACRA Guidelines (risk-based CDD)",
         "Risk assessment", "data", "medium", 5,
         "Record a risk rating per client (jurisdiction, source of funds, nature of business, nominee/trust use, PEP).",
         framework="AML/CFT", applies_to="csp", confidence="secondary", source=_ANL),
    Rule("X-CDD-SCREEN", "Sanctions / PEP screening status recorded", "ACRA Guidelines",
         "Screening", "data", "high", 6,
         "Record the screening result and date for the client and its beneficial owners.",
         framework="AML/CFT", applies_to="csp", confidence="secondary", source=_ANL),
    Rule("X-CDD-SOF", "Source of funds / wealth recorded", "ACRA Guidelines (risk factors)",
         "Risk assessment", "data", "medium", 4,
         "Record source of funds or wealth, especially for higher-risk clients.",
         framework="AML/CFT", applies_to="csp", confidence="secondary", source=_ANL),
    Rule("X-CDD-REVIEW", "CDD refreshed within your review cycle", "Firm policy",
         "Ongoing monitoring", "data", "medium", 5,
         "Refresh CDD on a risk basis. The cycle (default 12 months) is YOUR policy parameter, not a statutory number.",
         framework="AML/CFT", applies_to="csp", confidence="firm-policy", source=_ANL),
    # ---------------- ACRA oversight of public accounting entities ----------------
    Rule("AC-QM", "Firm-level quality management system in place", "Accountants Act (as amended 2022)",
         "Quality management", "attest", "high", 8,
         "ACRA can conduct statutory quality control inspections of public accounting entities (in force from 1 July 2023) and require remediation or impose sanctions.",
         framework="ACRA", applies_to="pae", confidence="primary", source=_ACRA_725),
    Rule("AC-PMP", "Prepared for Practice Monitoring Programme inspection", "Accountants Act (as amended 2022)",
         "Practice monitoring", "attest", "medium", 6,
         "Inspections use a four-level outcome (Satisfactory ... Not Satisfactory); ACRA may require disclosure of a 'Not Satisfactory' finding to the audited entity.",
         framework="ACRA", applies_to="pae", confidence="primary", source=_ACRA_725),
    Rule("AC-AML-INSP", "Prepared for ACRA AML/CFT inspection", "Accountants Act (as amended 2022)",
         "AML/CFT oversight", "attest", "high", 7,
         "ACRA has explicit powers to inspect public accountants and public accounting entities for AML/CFT compliance and to sanction failures.",
         framework="ACRA", applies_to="pae", confidence="primary", source=_ACRA_725),
    # ---------------- Legal retention (the counterweight to PDPA s.25) ----------------
    Rule("R-ACCT", "Accounting records kept for at least the statutory period", "Companies Act s.199(2); IRAS",
         "Legal retention", "attest", "medium", 5,
         "Companies must keep accounting records for not less than 5 years (from the end of the financial year in which the transactions were completed); IRAS also requires 5 years. PDPA s.25(b) permits retention while it is necessary for legal purposes. Record the legal basis for each retention period.",
         framework="RETENTION", confidence="primary", source=_IRAS),
]}
RULES.update(NON_PDPA_RULES)
PDPA_RULE_IDS = {rid for rid, r in RULES.items() if r.framework == "PDPA"}

FRAMEWORK_QUESTIONS = [
    ("AM-REG", "Are you registered with ACRA as a corporate service provider?"),
    ("AM-RQI", "Have you designated Registered Qualified Individual(s) for AML/CFT/PF?"),
    ("AM-POLICY", "Do you have written AML/CFT/PF policies, procedures and a documented risk assessment?"),
    ("AM-CDD-PROC", "Do you complete CDD (customer and beneficial owner) before designated transactions?"),
    ("AM-SCREEN", "Do you screen clients and beneficial owners for sanctions and PEP status?"),
    ("AM-STR", "Do you know how to file an STR with STRO, and who decides?"),
    ("AM-TRAIN", "Do you train staff on AML/CFT and keep records?"),
    ("AM-AUDIT", "Does someone independent review your AML/CFT controls?"),
    ("AC-QM", "Do you operate a firm-level quality management system?"),
    ("AC-PMP", "Are you ready for a Practice Monitoring Programme inspection?"),
    ("AC-AML-INSP", "Are you ready for an ACRA AML/CFT inspection?"),
    ("R-ACCT", "Do you retain accounting records for at least 5 years and record the legal basis?"),
]

ATTESTATION_QUESTIONS = [
    ("A-DPO", "Have you designated at least one person responsible for PDPA compliance?"),
    ("A-DPO-PUBLIC", "Is that person's business contact information available to the public?"),
    ("A-POLICY", "Do you have written data protection policies, available on request?"),
    ("A-COMPLAINT", "Do you have a process to receive and respond to complaints?"),
    ("A-STAFF", "Have you communicated these policies to staff?"),
    ("A-NOTICE", "Do you tell individuals the purposes on or before collecting their data?"),
    ("A-ACCESS-PROC", "Do you have a process for access and correction requests?"),
    ("A-BREACH", "Do you have a data breach response plan?"),
    ("A-DI", "Are vendors that process personal data for you bound by written contracts?"),
]

# Parameters delegated to regulations / PDPC guidance - verify before relying on them.
DELEGATED_PARAMS = {
    "breach_notify_calendar_days": 3,      # s.26D(1): in the Act
    "breach_significant_scale_count": 500,  # prescribed in regulations, NOT in the Act text
    "breach_assessment_target_days": 30,    # PDPC guidance, NOT in the Act text
}

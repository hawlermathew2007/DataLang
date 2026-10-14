# Regulatory sources and how far each one is verified

Checked 11 Oct 2026. **Not legal advice.** Every rule in `catalogue.py` carries a `confidence` label and a `source`.
The app shows that label next to each finding so nobody mistakes a guideline for a statute.

| Label | Meaning |
|---|---|
| `primary` | Taken from the PDPA text supplied, or from an official ACRA / IRAS page that was read |
| `secondary` | From a law-firm or industry article. Verify against the CSP Regulations 2025 and ACRA's Guidelines before relying on it |
| `firm-policy` | A parameter you choose (e.g. CDD refresh cycle). Not a legal rule |
| `unverified` | From a pre-2025 industry page. Good practice until verified |

## What was verified, and where

| Topic | Rule IDs | Status | Source |
|---|---|---|---|
| CSP registration; offences and penalties; Act in force 9 Jun 2025; AML/CFT/PF duties exist and are in the CSP Regulations 2025; designated accounting activities are in scope | AM-REG | primary | [ACRA: Corporate Service Providers Act](https://www.acra.gov.sg/regulations/legislation/corporate-service-providers-act/) |
| ACRA powers from 1 Jul 2023: statutory quality-control inspections, AML/CFT inspections and sanctions for public accounting entities, practice monitoring outcomes | AC-QM, AC-PMP, AC-AML-INSP | primary | [ACRA announcement](https://www.acra.gov.sg/news-events/news-announcements/725/) |
| Accounting records kept at least 5 years (s.199(2) Companies Act); IRAS 5 years | R-ACCT, legal-hold setting | primary (IRAS); statute read via a mirror: confirm on Singapore Statutes Online | [IRAS](https://www.iras.gov.sg/irashome/Businesses/Self-Employed/Learning-the-basics/Keeping-Proper-Records-and-Accounts/), [s.199 text](https://lawplayer.com/sg/act/CoA1967/199) |
| PDPA s.4(2)-(3): data intermediary under a written contract is bound only by ss.24, 25 and 26C(3)(a) | scoring `intermediary` mode | primary | PDPA text supplied |
| PDPA s.25(b): retention allowed while necessary for legal purposes | legal hold | primary | PDPA text supplied |
| PDPA s.26C(3)(a): intermediary notifies the client without undue delay | `draft_client_notice` | primary | PDPA text supplied |
| CDD triggers, beneficial owner, risk-based approach, screening, STR via CDSA s.39, no tipping-off s.48, Registered Qualified Individual | AM-RQI, AM-POLICY, AM-CDD-PROC, AM-SCREEN, AM-STR, X-CDD-* | secondary | [Allen & Gledhill](https://www.allenandgledhill.com/sg/publication/articles/30601/corporate-service-providers-act-2024-to-come-into-effect-on-9-june-2025), [Anlian Group](https://anliangroup.com/insights/cdd-aml-cspa-2024-corporate-service-providers) |
| AML training cadence and independent review | AM-TRAIN, AM-AUDIT | unverified (legacy 2015-era page) | [Ingenique](https://www.ingenique.net/7-things-you-need-to-do-to-comply-with-acra-amlcft-requirements/) |

## Not found, so deliberately NOT hard-coded
- **AML/CFT record-keeping period.** No source read states it. The tool does not invent one. Look it up in the CSP Regulations 2025 / ACRA Guidelines (9 May 2025) and set it in your policy.
- **STR filing deadline.** Not stated in any source read.
- **Exact CDD "designated transactions" list** and the precise duties of a Registered Qualified Individual.
- **Public accountants:** retention of audit working papers, ISCA/ACRA professional standards, GST rules, MAS rules. Not covered.
- **PDPA access request vs. tipping-off.** The Fifth Schedule (supplied) lists exceptions such as legal privilege (1(f)) and investigations (1(h)), but none names suspicious transaction reports. The app warns and tells you to ask counsel.

## Design decisions that follow from this
1. AML/CFT, ACRA and retention-law scores are **separate** from the PDPA score. They are different laws with different regulators.
2. CDD checks measure whether the **client file is complete** (beneficial owner recorded, risk rating present...). They cannot show that CDD was done properly.
3. The CDD refresh cycle (default 365 days) is labelled `firm-policy`.
4. A policy with `legal_hold_days` is rejected if `retention_days` is shorter, or if no `legal_basis` is cited.

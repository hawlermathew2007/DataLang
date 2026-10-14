# 🛡️ PDPA Guard

Data-foundation scoring, masking, policy-as-code and activity monitoring for Singapore SMEs.
Upload a CSV / Excel / SQL file → get a PDPA readiness score and an AI-readiness score → clean and mask →
govern access with a YAML policy that compiles to real PostgreSQL permissions → monitor activity with a live score.

Author: **pyaesonephyo** · Python + PostgreSQL · built against the Personal Data Protection Act 2012 text in `sample_data/PDPA_2012.txt`

> **Not legal advice.** Scores measure *observable evidence*, not legal compliance. See [Limitations](#limitations).

## Accounting firms (AML/CFT, ACRA, legal retention)
A second policy and demo set target small accounting firms: `policies/accounting_firm.yaml`, demo clients / payroll / staff assignments.
- **Separate scores** for PDPA, AML/CFT (CSP Act 2024), ACRA oversight and legal retention. Never blended.
- **Every rule is labelled** `primary` / `secondary` / `firm-policy` / `unverified`. See [docs/REGULATORY_SOURCES.md](docs/REGULATORY_SOURCES.md) for what was verified and what was not.
- **Data intermediary mode (PDPA s.4(2))**: for client data processed under a written contract, only ss.24, 25 and 26C(3)(a) are scored; the client keeps the rest.
- **Client segregation**: staff see only clients assigned to them (a `row_filter` on the `assignments` table). Juniors see salary as a band and tokenised names.
- **Legal hold**: `legal_hold_days` + `legal_basis` stop the tool recommending deletion before a statutory minimum; policies that set a shorter retention are rejected.
- **Breach**: a client notice (s.26C(3)(a)) is drafted before the PDPC notice.
- Run: `python -m pdpa_guard setup-demo --policy policies/accounting_firm.yaml`, then in the app load **Accounting firm** demo data.

## Documents + BERT (optional NLP layer)
Tab **6 · Documents** and `python -m pdpa_guard scan-doc FILE [--policy-check] [--bert] [--redact]` read PDF / Word / text:
- **Personal data inside documents**: NRIC/FIN (checksum), +65 phones, emails, Luhn cards, postal codes always run. With `--bert`, a BERT NER model (default `dslim/bert-base-NER`) also finds person names and locations. Results are masked in the UI; a redacted `.txt` can be downloaded.
- **Policy-document check**: compares each sentence of a privacy policy / notice with 11 PDPA duties (DPO, purposes, consent, access/correction, retention, security, transfer, breach, complaints, vendors, DNC). Keyword matching by default; with `--bert` a multilingual BERT-family sentence encoder (default `paraphrase-multilingual-MiniLM-L12-v2`) matches by meaning, so Burmese or Chinese wording can match English duty descriptions. Each duty shows the best matching sentence as evidence.
- Results can pre-fill the sidebar self-assessment, but only as **Yes**, only for what the document says, and only when you click. It never answers "No" for you.
- Install: `pip install -r requirements.txt -r requirements-nlp.txt` (about 2 GB with torch). Pre-download the models and set `HF_HUB_OFFLINE=1` plus `PDPA_GUARD_NER_MODEL` / `PDPA_GUARD_ENCODER_MODEL` to local folders if data must not touch the network.
- Scores stay deterministic: BERT output is evidence shown beside the score, never a hidden input to it.

## SaaS web app (FastAPI + HTML/JS frontend)
`server.py` serves the API and the `web/` frontend. Login: **admin / rootadmin** (override with `PDPA_ADMIN_USER` / `PDPA_ADMIN_PASSWORD`; change before real use).
```bash
pip install -r requirements.txt
uvicorn server:app --port 8000      # open http://localhost:8000
```
The Streamlit `app.py` still works unchanged.

## Quick start

**Docker (self-hosted, recommended):**
```bash
cp .env.example .env            # change the passwords / token key
docker compose up --build       # app on http://localhost:8501, Postgres on 5432
```

**Local:**
```bash
pip install -r requirements.txt
export PDPA_GUARD_DSN=postgresql://postgres:postgres@localhost:5432/pdpa_demo
python -m pdpa_guard setup-demo       # installs audit schema, loads demo data, applies policy
streamlit run app.py
python -m pdpa_guard scan sample_data/messy_students.csv --fix      # CLI, no database needed
pytest                                 # DB tests run if PDPA_GUARD_TEST_DSN points at a scratch database
```

## 5-minute demo script

1. **Tab 1** → *Use demo data*. Score **33 / 100 (Critical)**: NRICs in clear (s.24), no retention (s.25), no purpose (s.18/20), no DNC status (Part 9)…
   Each lost point names the PDPA section and a fix. Answer a few sidebar questions (DPO, breach plan…) and watch the score move.
2. **Tab 2** → *Apply governance*. **33 → 85**. NRIC → `S****632Z`, names tokenised, retention date derived, duplicates removed.
   Consent and DNC stay failing: the tool never invents facts only the business can confirm.
3. **Tab 3** → edit the YAML (e.g. give `teacher` `nric: partial`, or an invalid edit to see validation). *Preview compiled SQL*.
4. **Tab 4** → *Connect* → *Load demo table + apply policy*. As `admin_staff`: query without purpose (refused, s.18) → with purpose (NRIC masked) →
   `select * from students` (**blocked**, needs DPO approval) → tick DPO approval (allowed, logged). Click the three attack buttons, then *Run monitor now*:
   findings, DPO notifications, a breach case, and the **live score drops**.
5. **Tab 5** → breach case with the s.26D 3-day deadline and draft PDPC/individual notices; look up a person by phone/NRIC/email (s.21), correct a field (s.22), see retention overdue (s.25).

## How it works

| Layer | Module | What it does |
|---|---|---|
| Detection | `detectors.py` | NRIC/FIN **checksum**, +65 phones, emails, postal, UEN, Luhn cards; column-name + value sampling. Local only. |
| Catalogue | `catalogue.py` | Every rule → PDPA section → severity → remediation. Parameters the Act delegates to regulations are flagged `delegated`. |
| Scoring | `scoring.py` | Deterministic. Data checks + self-attestation + database/policy checks. Unassessable rules are excluded and reported as *coverage*. Separate AI-readiness score. |
| Clean / mask | `masking.py`, `remediate.py` | Non-inventing cleaning; partial / redact / HMAC token / generalise; k-anonymity check. |
| Policy | `policy.py` | Pydantic-validated YAML. **Declarative** (roles, view/edit per column or class, row filters, `when:`) + **imperative** (`then:` named Python actions). Compiles to roles, masked `security_barrier` views, column-level `UPDATE` grants. Secure by default (unlisted = deny). |
| Enforcement | `db.py`, `sql/audit_schema.sql` | Staff query through the **audit gateway** (as a role, in a transaction): purpose check, blocking with DPO approval, literal-stripped logging, NRIC-leak detection on results, row-level change triggers, **drift detection** on *effective* privileges. |
| Monitoring | `monitor.py` | Pure rule evaluation (bulk read, off-hours, denied access, missing purpose, unmasked NRIC, mass edits) → action registry → findings, DPO notifications, breach cases → live score. |
| Breach | `breach.py` | s.26C/26D helper: 3-calendar-day deadline, s.26B(4) internal-only note, harm/scale indicators, draft notices. |

### PDPA coverage (from the supplied Act)
s.11 accountability · s.12 policies · s.13–14 consent · s.18/20 purpose · s.21 access · s.22 correction · s.23 accuracy ·
s.24 protection · s.25 retention · s.26 transfer · Part 6A breach notification · Part 9 Do Not Call · s.48D–48F individual offences ·
s.53(2) employer defence (the policy + audit log is your evidence of "practicable steps").

## Policy snippet
```yaml
tables:
  public.students:
    columns: { nric: nric, phone: phone, parent_consent: other }
    access:
      admin_staff:
        view: { default: full, nric: partial }     # S****567D
        edit: [phone, parent_consent]
        purpose_required: true                     # s.18
      marketing:
        view: { phone: full, default: deny }
        row_filter: "parent_consent = 'yes'"       # s.13: consenting people only
monitor:
  - id: bulk-read
    when: { type: bulk_select, rows: 50, except_roles: [dpo] }
    then: [{ block: { unless: dpo_approval } }, alert, notify_dpo, open_breach_case]
```

## Limitations
Read these before showing this to a regulator or customer.

- **NLP layer.** BERT NER models are trained mostly on English news; they miss names in other scripts and can flag non-personal words. Check the model card for your languages: Burmese NER is not covered by common pretrained models. Policy-check thresholds (`covered_at`, `weak_at`) are uncalibrated starting points. A sentence matching a duty shows the document *mentions* it, not that the wording is legally adequate or followed. Scanned PDFs need OCR first (not included). Redaction only changes the extracted text, not the original file.

- **Evidence, not compliance.** A high score does not mean you comply with the PDPA, and a low one does not mean you breach it. Self-attested answers are unverified.
- **Not everything is in the Act.** The "significant scale" threshold (default 500), harm classes (NRIC / financial / health), the 30-day assessment target and access-request timelines are set by **regulations / PDPC guidance**, not the PDF supplied. They are configurable defaults (`catalogue.DELEGATED_PARAMS`, `breach.HIGH_HARM_CLASSES`): verify against current sources.
- **Monitoring covers the gateway.** Direct database logins bypass the event log (permissions and row-change triggers still apply). Do not give staff direct DB credentials; add `pgaudit` for production-grade coverage.
- **Token masking** needs `EXECUTE` on `pdpa_audit.tok()` for the role; the gateway rejects statements mentioning `pdpa_audit`, but a role with a direct connection could use it as a lookup oracle. Same advice: gateway only.
- **Audit tables hold personal data** (`changes` stores old/new rows). Protect and apply retention to them.
- **Policy YAML is trusted admin input** (row filters become SQL). Identifiers are validated and filters parsed, but do not accept policies from untrusted users.
- Detection is heuristic (name hints + value sampling); the SQL-dump loader handles portable dumps only (via SQLite); the access-request usage log is table-level, not row-level.
- Masking is **pseudonymisation**, which can still be personal data (s.2(1)). Check k-anonymity before calling data anonymised; unauthorised re-identification is an offence (s.48F).
- **AML/CFT and ACRA coverage is partial.** Only the points in docs/REGULATORY_SOURCES.md marked `primary` come from official pages that were read; most CDD detail is from secondary sources. The AML/CFT record-keeping period and STR deadline were not found, so they are not encoded. Read the CSP Regulations 2025 and ACRA's Guidelines before relying on those scores.
- CDD checks test file completeness, not whether CDD was actually performed.
- Demo credentials and token key are placeholders: change them.
- If you process customers' data as a hosted service you may be a *data intermediary* (s.4(2)–(3)); self-hosting avoids sending data to you at all.

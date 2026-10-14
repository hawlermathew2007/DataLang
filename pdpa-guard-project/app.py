"""PDPA Guard - Streamlit demo.   Run:  streamlit run app.py"""
from __future__ import annotations

import io
import os
from pathlib import Path

import pandas as pd
import streamlit as st

from pdpa_guard import __version__
from pdpa_guard.breach import draft_client_notice, draft_individual_notice, draft_pdpc_notification
from pdpa_guard.catalogue import ATTESTATION_QUESTIONS, CONFIDENCE_NOTE, DELEGATED_PARAMS, FRAMEWORK_QUESTIONS, RULES
from pdpa_guard.detectors import DATA_CLASSES
from pdpa_guard.masking import MASK_MODES, k_anonymity, mask_dataframe
from pdpa_guard.policy import compile_policy, load_policy, policy_errors
from pdpa_guard.remediate import apply_governance, load_table
from pdpa_guard.sample import SAMPLES, assignments, messy_clients, messy_payroll, messy_students
from pdpa_guard.scoring import assess

ROOT = Path(__file__).parent
DEFAULT_USER = "pyaesonephyo"
POLICIES = {"Tuition centre": ROOT / "policies" / "tuition_centre.yaml",
            "Accounting firm": ROOT / "policies" / "accounting_firm.yaml"}
POLICY_PATH = POLICIES["Tuition centre"]

st.set_page_config(page_title="PDPA Guard", page_icon="🛡️", layout="wide")


def run_assess(df, policy_state=None):
    return assess(df, attest, policy_state, scopes=scopes, intermediary=is_di)


def band_color(score: float) -> str:
    return "🟢" if score >= 80 else "🟡" if score >= 60 else "🟠" if score >= 40 else "🔴"


# ----------------------------------------------------------------------------- sidebar
with st.sidebar:
    st.title("🛡️ PDPA Guard")
    st.caption(f"v{__version__} · data foundations for Singapore SMEs")
    user = st.text_input("Signed in as", DEFAULT_USER)
    st.divider()
    st.subheader("About your firm")
    is_csp = st.checkbox("We provide corporate services / designated accounting activities (CSP Act 2024 -> AML/CFT)", False)
    is_pae = st.checkbox("We are a public accounting entity / audit firm (ACRA oversight)", False)
    is_di = st.checkbox("This table is client data we process on their behalf under a WRITTEN contract (data intermediary, s.4(2))", False,
                        help="Only if every client has a written contract. Then only ss.24, 25 and 26C(3)(a) apply to you for this data; the client keeps the rest (s.4(3)).")
    scopes = {s for s, on in (("csp", is_csp), ("pae", is_pae)) if on}
    st.divider()
    st.subheader("Self-assessment (not detectable from data)")
    st.caption("Answer to include organisational duties in the score. Unanswered = not assessed.")
    attest: dict[str, bool | None] = {}
    for rid, text in ATTESTATION_QUESTIONS:
        v = st.radio(f"{RULES[rid].section} · {text}", ["Not answered", "Yes", "No"], horizontal=True, key=f"att_{rid}")
        attest[rid] = None if v == "Not answered" else v == "Yes"
    if scopes:
        st.caption("AML/CFT, ACRA and retention-law questions (scored separately from PDPA)")
        for rid, text in FRAMEWORK_QUESTIONS:
            r_ = RULES[rid]
            if r_.applies_to != "all" and r_.applies_to not in scopes:
                continue
            v = st.radio(f"{r_.framework} · {text}", ["Not answered", "Yes", "No"], horizontal=True, key=f"att_{rid}")
            attest[rid] = None if v == "Not answered" else v == "Yes"
    st.divider()
    st.warning("Decision-support tool. **Not legal advice.** Scores measure observable evidence only.", icon="⚖️")

tab_scan, tab_fix, tab_policy, tab_mon, tab_breach, tab_docs = st.tabs(
    ["1 · Scan & score", "2 · Clean & mask", "3 · Policy (YAML)", "4 · Live monitoring", "5 · Breach & requests", "6 · Documents (NLP)"])

# ----------------------------------------------------------------------------- 1. scan
with tab_scan:
    st.header("Upload data and get a PDPA score")
    st.caption("Files are analysed in memory on this server; only findings are shown. Run self-hosted for sensitive data.")
    c1, c2 = st.columns([3, 1])
    up = c1.file_uploader("CSV, Excel or SQL dump", type=["csv", "xlsx", "xls", "sql"])
    sample = c2.selectbox("Demo data", list(SAMPLES), label_visibility="collapsed")
    if c2.button("Load demo data", width="stretch"):
        st.session_state["tables"] = {sample.split(": ")[1].replace(" ", "_"): SAMPLES[sample]()}
        st.session_state["tpl"] = "Accounting firm" if sample.startswith("Accounting") else "Tuition centre"
    if up is not None and st.session_state.get("_up_name") != up.name:
        try:
            st.session_state["tables"] = load_table(up.name, up.getvalue())
            st.session_state["_up_name"] = up.name
        except Exception as e:  # noqa: BLE001
            st.error(f"Could not read file: {e}")

    tables: dict[str, pd.DataFrame] = st.session_state.get("tables", {})
    if not tables:
        st.info("Upload a file or load the demo data to begin.")
    else:
        name = st.selectbox("Table / sheet", list(tables))
        df = tables[name]
        st.session_state["current_name"] = name
        rep = run_assess(df, st.session_state.get("policy_state"))
        st.session_state["last_report"] = rep
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("PDPA readiness", f"{band_color(rep.pdpa_score)} {rep.pdpa_score}/100", rep.band(), delta_color="off")
        m2.metric("AI readiness", f"{rep.ai['score']}/100")
        m3.metric("Rows × columns", f"{rep.n_rows} × {rep.n_cols}")
        m4.metric("Rules assessed", f"{int(rep.coverage*100)}%", help="Share of rule weight that could be assessed. "
                  "Answer the self-assessment and connect a database to raise it.")
        st.progress(min(1.0, rep.pdpa_score / 100))
        if is_di:
            st.info("Data intermediary mode (s.4(2)): consent, purpose, access, correction and accuracy duties sit with your client (s.4(3)). "
                    "Scored on ss.24, 25 and 26C(3)(a) only. Valid only if each client has a written contract.")
        active = {k: v for k, v in rep.frameworks.items() if v["score"] is not None}
        if active:
            st.subheader("Other regimes (scored separately; never blended into the PDPA score)")
            cols = st.columns(len(active))
            for col, (name, v) in zip(cols, active.items()):
                col.metric(name, f"{v['score']}/100", f"{int(v['coverage']*100)}% of rules assessed", delta_color="off")
            st.caption("Each rule shows how well sourced it is: " + " · ".join(f"**{k}**: {v}" for k, v in CONFIDENCE_NOTE.items()))
        elif scopes:
            st.caption("Answer the AML/CFT / ACRA questions in the sidebar, or load the client CDD demo, to score those regimes.")

        st.subheader("What is costing you points")
        rows = [{"Points lost": round(c.points_lost, 1), "Regime": c.rule.framework, "Rule": c.rule.title, "Ref": c.rule.section,
                 "Source": c.rule.confidence, "Severity": c.rule.severity, "Finding": c.detail, "How to fix": c.rule.remediation}
                for c in rep.failing()]
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        else:
            st.success("No failing checks among the rules that could be assessed.")
        with st.expander("Rules not assessed (and why)"):
            st.dataframe(pd.DataFrame([{"Rule": c.rule.title, "PDPA": c.rule.section, "Reason": c.detail}
                                       for c in rep.checks if not c.applicable]), hide_index=True, width="stretch")

        st.subheader("Detected personal data (Singapore-aware)")
        if rep.findings:
            st.dataframe(pd.DataFrame([{"Column": f.column, "Class": f.data_class, "Sensitivity": f.sensitivity,
                                        "Evidence": f.evidence, "Visible (unmasked)": f"{int(f.unmasked_ratio*100)}%",
                                        "Notes": "; ".join(f.notes)} for f in rep.findings]),
                         hide_index=True, width="stretch")
        else:
            st.info("No personal data columns detected.")
        st.subheader("AI readiness")
        st.bar_chart(pd.Series(rep.ai["dimensions"], name="score"))
        with st.expander("Preview data"):
            st.dataframe(df.head(50), width="stretch")

# ----------------------------------------------------------------------------- 2. fix
with tab_fix:
    st.header("Clean, mask and govern")
    tables = st.session_state.get("tables", {})
    if not tables:
        st.info("Load data on the first tab.")
    else:
        df = tables[st.session_state.get("current_name", next(iter(tables)))]
        c1, c2, c3 = st.columns(3)
        ret = c1.number_input("Retention (days after collection)", 30, 3650, 730)
        purpose = c2.text_input("Declared purpose (must match what individuals were told, s.20)",
                                "tuition enrolment and communication")
        do_mask = c3.checkbox("Mask identifiers", True)
        if st.button("Apply governance", type="primary"):
            _p = load_policy(st.session_state.get("yaml_text", POLICY_PATH.read_text())) if not policy_errors(st.session_state.get("yaml_text", POLICY_PATH.read_text())) else None
            out, log = apply_governance(df, retention_days=int(ret), default_purpose=purpose or None, mask=do_mask,
                                        legal_hold_days=_p.settings.legal_hold_days if _p else None,
                                        legal_basis=_p.settings.legal_basis if _p else None)
            st.session_state["governed"] = (out, log)
        if "governed" in st.session_state:
            out, log = st.session_state["governed"]
            before = run_assess(df)
            after = run_assess(out)
            a, b, c = st.columns(3)
            a.metric("Before", f"{before.pdpa_score}/100")
            b.metric("After", f"{after.pdpa_score}/100", f"{after.pdpa_score - before.pdpa_score:+.1f}")
            c.metric("AI readiness", f"{after.ai['score']}/100", f"{after.ai['score'] - before.ai['score']:+.1f}")
            st.subheader("What changed")
            st.markdown("\n".join(f"- {x}" for x in log))
            remaining = [x for x in after.failing() if x.rule.kind == "data"]
            if remaining:
                st.warning("Still needs a human (the tool will not invent these): " +
                           "; ".join(f"**{x.rule.title}** - {x.rule.remediation}" for x in remaining))
            st.info("Masking here is **pseudonymisation**: partial or tokenised data can still be personal data if someone can "
                    "identify the person using other information you hold (s.2(1)). Use the re-identification check below before "
                    "calling a dataset anonymised; unauthorised re-identification is an offence (s.48F).")
            st.dataframe(out.head(50), width="stretch")
            st.session_state["current_governed"] = out
            d1, d2 = st.columns(2)
            d1.download_button("Download CSV", out.to_csv(index=False).encode(), "governed.csv", "text/csv")
            buf = io.BytesIO(); out.to_excel(buf, index=False)
            d2.download_button("Download Excel", buf.getvalue(), "governed.xlsx")
            with st.expander("Re-identification check (k-anonymity)"):
                qi = st.multiselect("Quasi-identifiers", list(out.columns), default=[c for c in out.columns if "postal" in c or "country" in c or "joined" in c][:3])
                if qi:
                    res = k_anonymity(out, qi)
                    st.json(res)

# ----------------------------------------------------------------------------- 3. policy
with tab_policy:
    st.header("Access policy as code (declarative + imperative)")
    st.markdown("**Declarative**: roles, tables, who may *view* (full / partial / token / generalise / redact / deny) and *edit*, row filters. "
                "**Imperative**: the `then:` lists - named Python actions run when a monitor rule fires. "
                "Applying compiles this to real PostgreSQL roles, masked views and grants.")
    tpl = st.selectbox("Policy template", list(POLICIES), key="tpl")
    if st.session_state.get("_tpl") != tpl:
        st.session_state["_tpl"] = tpl
        st.session_state["yaml_text"] = POLICIES[tpl].read_text()
    if "yaml_text" not in st.session_state:
        st.session_state["yaml_text"] = POLICY_PATH.read_text()
    txt = st.text_area("policy.yaml", st.session_state["yaml_text"], height=520, key=f"yaml_{tpl}")
    st.session_state["yaml_text"] = txt
    errs = policy_errors(txt)
    if errs:
        st.error("Policy is invalid:\n\n" + "\n".join(f"- {e}" for e in errs))
    else:
        pol = load_policy(txt)
        st.success(f"Valid policy '{pol.name}': {len(pol.roles)} roles, {len(pol.tables)} table(s), {len(pol.monitor)} monitor rules")
        with st.expander("Compiled PostgreSQL (preview)"):
            st.code(";\n".join(compile_policy(pol).statements) + ";", language="sql")
        who = st.columns(len(pol.roles))
        for col, (rname, r) in zip(who, pol.roles.items()):
            col.caption(f"**{rname}**\n\n{r.description}")

# ----------------------------------------------------------------------------- 4. monitoring
def get_db(dsn: str):
    from pdpa_guard.db import Database
    return Database(dsn)

with tab_mon:
    st.header("Database activity monitoring")
    dsn = st.text_input("PostgreSQL DSN", os.environ.get("PDPA_GUARD_DSN", "postgresql://postgres:postgres@localhost:5432/pdpa_demo"))
    errs = policy_errors(st.session_state.get("yaml_text", POLICY_PATH.read_text()))
    if errs:
        st.error("Fix the policy on tab 3 first.")
    else:
        pol = load_policy(st.session_state.get("yaml_text", POLICY_PATH.read_text()))
        c1, c2, c3 = st.columns(3)
        if c1.button("Connect & install audit schema"):
            try:
                db = get_db(dsn); db.install(); st.session_state["db"] = db; st.success("Connected; audit schema installed.")
            except Exception as e:  # noqa: BLE001
                st.error(f"Connection failed: {e}")
        db = st.session_state.get("db")
        if db is None:
            st.info("Connect to PostgreSQL to continue (see README for docker compose).")
        else:
            if c2.button("Load demo students table + apply policy"):
                # Always load UNMASKED source data: masking is applied by the database views, not by the data.
                kw = dict(mask=False, default_purpose=pol.settings.default_purpose,
                          retention_days=pol.settings.retention_days, legal_hold_days=pol.settings.legal_hold_days,
                          legal_basis=pol.settings.legal_basis)
                if "public.payroll" in pol.tables:
                    db.load_dataframe(apply_governance(messy_clients(), **kw)[0], "clients_cdd")
                    db.load_dataframe(apply_governance(messy_payroll(), **kw)[0], "payroll")
                    db.load_dataframe(assignments(), "assignments")
                else:
                    from pdpa_guard.db import sanitise_ident
                    need = {c for c in pol.tables["public.students"].columns if c != "id"} if "public.students" in pol.tables else set()
                    cur_df = st.session_state.get("tables", {}).get(st.session_state.get("current_name", ""))
                    if cur_df is not None and need <= {sanitise_ident(c) for c in cur_df.columns}:
                        data = apply_governance(cur_df, **kw)[0]
                    else:
                        data = apply_governance(messy_students(), **kw)[0]
                    db.load_dataframe(data, "students")
                db.apply_policy(pol, st.session_state["yaml_text"]); db.reset_audit()
                st.success("Table loaded (as UNMASKED source data) and policy applied. Staff now only see masked views.")
            if c3.button("Re-apply policy (fixes drift)"):
                db.apply_policy(pol, st.session_state["yaml_text"]); st.success("Policy re-applied.")

            state = db.policy_state(pol)
            st.session_state["policy_state"] = {k: state[k] for k in ("enforced", "drift", "audit")}
            rep = st.session_state.get("last_report")
            base_score = run_assess(st.session_state["tables"][st.session_state["current_name"]], st.session_state["policy_state"]).pdpa_score \
                if st.session_state.get("tables") else 100.0
            live = db.live_score(base_score)
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Live PDPA score", f"{band_color(live)} {live}", f"{live - base_score:+.1f} from monitoring", delta_color="inverse")
            m2.metric("Static score", base_score)
            m3.metric("Open findings", len(db.findings("open")))
            m4.metric("Permission drift", state["drift"])
            if state["drift_items"]:
                st.error("Database permissions differ from the written policy (s.24):")
                st.dataframe(pd.DataFrame(state["drift_items"]), hide_index=True, width="stretch")

            st.subheader("Staff query console (every query goes through the audit gateway)")
            from pdpa_guard.db import Gateway
            gw = Gateway(db, pol)
            q1, q2 = st.columns([1, 3])
            role = q1.selectbox("Act as role", list(pol.roles), index=1)
            staff = q1.text_input("Staff username", "amy")
            purpose = q1.text_input("Purpose", "")
            approve = q1.checkbox("I am the DPO approving a bulk read", False)
            sql = q2.text_area("SQL", "select * from students limit 5", height=120)
            if q2.button("Run as staff", type="primary"):
                res = gw.execute(staff, role, sql, purpose, approved=approve and user == DEFAULT_USER)
                if res.ok:
                    st.success(f"{res.rowcount} row(s)")
                    if res.columns:
                        st.dataframe(pd.DataFrame(res.rows, columns=res.columns), width="stretch")
                else:
                    st.error(res.error)
            st.caption("Try: base-table access, bulk export, an intern querying phones, an admin updating NRIC, running with no purpose.")
            d1, d2, d3 = st.columns(3)
            demo = [("Teacher reads base table", ("tom", "teacher", "select * from public.students limit 3", "")),
                    ("Admin exports everyone", ("amy", "admin_staff", "select * from students", "export")),
                    ("Intern asks for NRIC", ("ivy", "intern", "select nric from students", ""))]
            for col, (label, args) in zip((d1, d2, d3), demo):
                if col.button(label):
                    r = gw.execute(*args); st.write(f"{label}: {'allowed' if r.ok else 'DENIED - ' + str(r.error)}")

            if st.button("Run monitor now (evaluate rules, raise findings)"):
                st.success(f"{db.run_monitor(pol)} new finding(s)"); st.rerun()
            f1, f2 = st.columns(2)
            with f1:
                st.subheader("Open findings")
                fs = db.findings("open")
                if fs:
                    st.dataframe(pd.DataFrame(fs)[["id", "ts", "severity", "rule_id", "obligation", "app_user", "db_role", "detail"]],
                                 hide_index=True, width="stretch")
                    fid = st.number_input("Resolve finding id", 0, step=1)
                    if st.button("Mark resolved") and fid:
                        db.resolve_finding(int(fid)); st.rerun()
            with f2:
                st.subheader("Notifications to DPO")
                ns = db.notifications()
                if ns:
                    st.dataframe(pd.DataFrame(ns)[["ts", "message"]], hide_index=True, width="stretch")
            with st.expander("Raw activity log"):
                ev = db.events(200)
                if ev:
                    st.dataframe(pd.DataFrame(ev).drop(columns=["sql_text"], errors="ignore").assign(sql=[e["sql_text"] for e in ev]),
                                 hide_index=True, width="stretch")
            with st.expander("Row-level change log"):
                ch = db.changes(200)
                if ch:
                    st.dataframe(pd.DataFrame(ch)[["ts", "app_user", "db_role", "tbl", "op"]], hide_index=True, width="stretch")

# ----------------------------------------------------------------------------- 5. breach & requests
with tab_breach:
    st.header("Breach response and individual requests")
    db = st.session_state.get("db")
    if db is None:
        st.info("Connect a database on tab 4 first.")
    else:
        pol = load_policy(st.session_state["yaml_text"])
        st.subheader("Breach cases")
        st.caption(f"s.26D(1): if assessed notifiable, notify the PDPC no later than {DELEGATED_PARAMS['breach_notify_calendar_days']} "
                   "calendar days after the day of assessment. Harm classes and the 'significant scale' number come from regulations, "
                   "not the Act - verify them.")
        import json
        cases = db.cases()
        if not cases:
            st.info("No cases yet. Run a bulk read on tab 4 and click 'Run monitor now'.")
        for cs in cases[:5]:
            body = cs["body"] if isinstance(cs["body"], dict) else json.loads(cs["body"])
            with st.expander(f"Case #{cs['id']} · {body['title']} · {body['preliminary_verdict']}"):
                st.json({k: v for k, v in body.items() if k not in ("checklist",)})
                st.markdown("**Checklist**\n" + "\n".join(f"- [ ] {x}" for x in body["checklist"]))
                if is_di or pol.settings.sector == "accounting":
                    st.text_area("Draft to CLIENT first (data intermediary, s.26C(3)(a): without undue delay)",
                                 draft_client_notice(body, pol.settings.organisation), height=200, key=f"c{cs['id']}")
                st.text_area("Draft to PDPC", draft_pdpc_notification(body, pol.settings.organisation), height=220, key=f"p{cs['id']}")
                st.text_area("Draft to affected individuals", draft_individual_notice(body, pol.settings.organisation), height=160, key=f"i{cs['id']}")

        st.subheader("Access / correction request (ss.21-22)")
        ident = st.text_input("Individual's NRIC, email or phone")
        if ident:
            if pol.settings.sector == "accounting":
                st.warning("Before answering an access request in an accounting firm: do not disclose anything that could reveal a suspicious "
                           "transaction report or AML/CFT inquiry (tipping-off is prohibited under the CDSA - per a secondary source, verify). "
                           "PDPA Fifth Schedule exceptions (e.g. legal privilege, investigations) may apply. Ask counsel first.", icon="🚫")
            res = db.find_subject(pol, ident)
            if not res["records"]:
                st.warning("No record found.")
            for t, rows in res["records"].items():
                st.write(f"**{t}** - personal data held")
                st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
            if res["uses_last_year"]:
                st.write("**How the data was used/disclosed in the last year (s.21(1)(b))** - table-level access log")
                st.dataframe(pd.DataFrame(res["uses_last_year"]), hide_index=True, width="stretch")
            if res["changes_last_year"]:
                st.write("Record changes in the last year")
                st.dataframe(pd.DataFrame(res["changes_last_year"]), hide_index=True, width="stretch")
            if res["records"]:
                tname = next(iter(res["records"]))
                rec = res["records"][tname][0]
                cc1, cc2, cc3 = st.columns(3)
                col = cc1.selectbox("Correct field", [c for c in pol.tables[tname].columns if c != "id"])
                newv = cc2.text_input("New value")
                if cc3.button("Apply correction (s.22)") and newv:
                    n = db.correct_field(pol, tname, rec["id"], col, newv, user)
                    st.success(f"{n} record corrected and logged. Remember to send the correction to organisations it was disclosed to within the past year (s.22(2)(b)).")

        st.subheader("Retention sweep (s.25)")
        try:
            n = db.retention_overdue("payroll" if "public.payroll" in pol.tables else "students")
            st.metric("Records past their retention date", n)
            st.caption("Delete or de-identify these once no legal or business purpose remains.")
        except Exception:  # noqa: BLE001
            st.caption("Load the demo table (tab 4) to see retention status.")


# ----------------------------------------------------------------------------- 6. documents (NLP)
def _apply_suggestions(ids: list[str]) -> None:
    """on_click callback: runs before the rerun, so it may set the sidebar radio keys."""
    for rid in ids:
        st.session_state[f"att_{rid}"] = "Yes"


with tab_docs:
    from pdpa_guard import doc_policy, doc_scan, documents, nlp

    st.header("Documents: personal data and policy coverage")
    st.caption("PDF, Word, text. Processed in memory on this server. Rule checks always run; BERT models are optional and run locally.")
    ok_nlp, why_nlp = nlp.nlp_available()
    use_bert = st.checkbox("Use BERT models (name detection + meaning-based policy check)", False, disabled=not ok_nlp,
                           help="Needs requirements-nlp.txt. First use downloads model weights unless you point the env vars at local folders.")
    if not ok_nlp:
        st.caption(f"BERT is off: {why_nlp}. Keyword and rule checks still work.")
    ups = st.file_uploader("Documents", type=[x.lstrip(".") for x in documents.SUPPORTED], accept_multiple_files=True, key="docs_up")

    ner = enc = None
    if use_bert and ups:
        try:
            with st.spinner("Loading models (first run downloads them)..."):
                ner, enc = nlp.get_ner(), nlp.get_encoder()
        except Exception as e:  # noqa: BLE001
            st.error(f"Could not load the BERT models, using rules/keywords only: {e}")

    for up in ups or []:
        with st.expander(f"{up.name}", expanded=len(ups) == 1):
            try:
                blocks = documents.extract_blocks(up.name, up.getvalue())
            except documents.DocumentError as e:
                st.error(str(e)); continue
            t_pii, t_pol = st.tabs(["Personal data inside", "Does it cover PDPA duties?"])
            with t_pii:
                fs = doc_scan.scan_blocks(blocks, ner=ner)
                sm = doc_scan.summarise(fs)
                a, b, c = st.columns(3)
                a.metric("Items found", sm["total"]); b.metric("High sensitivity", sm["high_sensitivity"])
                c.metric("Needs human review", sm["needs_review"], help="Confidence below 0.8, e.g. NRIC-shaped values that fail the checksum.")
                if fs:
                    st.dataframe(pd.DataFrame([{"Type": f.kind, "Sensitivity": f.sensitivity, "Preview (masked)": f.preview,
                                                "Page": f.page, "Paragraph": f.block + 1, "Confidence": f.confidence, "Source": f.source,
                                                "Note": f.note} for f in fs]), hide_index=True, width="stretch")
                    st.download_button("Download redacted text", doc_scan.redact(blocks, fs).encode(), f"{Path(up.name).stem}_redacted.txt",
                                       key=f"red_{up.name}")
                    st.caption("Redaction is text-only: the original PDF/Word file is not modified. Placeholders hide the values, "
                               "but surrounding context can still identify someone (s.2(1)).")
                else:
                    st.success("No personal data found by the enabled detectors. This is not proof there is none.")
                if ner is None:
                    st.caption("Names and addresses written in free text need the BERT option; rules only catch NRIC, phone, email, card, postal.")
            with t_pol:
                res = doc_policy.check_document(blocks, encoder=enc)
                st.metric("Duties mentioned", f"{doc_policy.coverage_score(res)}/100", help="Share of the 11 topics with matching wording. "
                          "Evidence that the document mentions a topic, not that the firm does it or that the wording is adequate.")
                st.dataframe(pd.DataFrame([{"Duty": r.ob.title, "PDPA": r.ob.section, "Status": r.status, "Score": r.score,
                                            "Method": r.backend, "Best matching sentence": r.evidence} for r in res]),
                             hide_index=True, width="stretch")
                sug = [k for k in doc_policy.suggested_answers(res)]
                if sug:
                    st.button(f"Mark {len(sug)} self-assessment answer(s) as Yes (you confirm they are true)", on_click=_apply_suggestions,
                              args=(sug,), key=f"sug_{up.name}")
                st.caption("Only 'Yes' is ever suggested, and only for what the document says. A policy that exists on paper is not proof it is followed.")

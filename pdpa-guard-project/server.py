"""PDPA Guard - SaaS web app (FastAPI API + static frontend in ./web).
Run:  uvicorn server:app --port 8000      Login: PDPA_ADMIN_USER / PDPA_ADMIN_PASSWORD (default admin / rootadmin - change it!)"""
from __future__ import annotations
import hmac, io, json, os, secrets
from dataclasses import dataclass, field
from pathlib import Path
import pandas as pd
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pdpa_guard import __version__, doc_policy, doc_scan, documents, nlp
from pdpa_guard.breach import draft_client_notice, draft_individual_notice, draft_pdpc_notification
from pdpa_guard.catalogue import ATTESTATION_QUESTIONS, CONFIDENCE_NOTE, DELEGATED_PARAMS, FRAMEWORK_QUESTIONS, RULES
from pdpa_guard.masking import k_anonymity
from pdpa_guard.policy import compile_policy, load_policy, policy_errors
from pdpa_guard.remediate import apply_governance, load_table
from pdpa_guard.sample import SAMPLES, assignments, messy_clients, messy_payroll, messy_students
from pdpa_guard.scoring import assess

ROOT = Path(__file__).parent
POLICIES = {"Tuition centre": ROOT / "policies" / "tuition_centre.yaml", "Accounting firm": ROOT / "policies" / "accounting_firm.yaml"}
ADMIN_USER = os.environ.get("PDPA_ADMIN_USER", "admin")
ADMIN_PW = os.environ.get("PDPA_ADMIN_PASSWORD", "rootadmin")
app = FastAPI(title="PDPA Guard", version=__version__)
J = lambda x: JSONResponse(jsonable_encoder(x))
recs = lambda df, n=50: json.loads(df.head(n).to_json(orient="records", date_format="iso"))


@dataclass
class WS:  # one workspace per signed-in session (in memory)
    tables: dict = field(default_factory=dict); cur: str = ""; yaml: str = ""; tpl: str = "Tuition centre"
    csp: bool = False; pae: bool = False; di: bool = False; attest: dict = field(default_factory=dict)
    gov: tuple | None = None; db: object = None; ps: dict | None = None; ner: object = None; enc: object = None
    @property
    def scopes(self): return {s for s, on in (("csp", self.csp), ("pae", self.pae)) if on}


SESSIONS: dict[str, WS] = {}
def ws(request: Request) -> WS:
    w = SESSIONS.get(request.cookies.get("sid", ""))
    if not w: raise HTTPException(401, "Signed out")
    return w
def bad(e): raise HTTPException(400, str(e))
def run(w, df, ps=None): return assess(df, w.attest, ps, scopes=w.scopes, intermediary=w.di)
def pol(w):
    e = policy_errors(w.yaml)
    if e: bad("Policy is invalid: " + "; ".join(e))
    return load_policy(w.yaml)
def df_of(w):
    if w.cur not in w.tables: bad("Load data on the Scan page first.")
    return w.tables[w.cur]


class Login(BaseModel): username: str; password: str
@app.post("/api/login")
def login(b: Login, resp: Response):
    ok = hmac.compare_digest(b.username.encode(), ADMIN_USER.encode()) & hmac.compare_digest(b.password.encode(), ADMIN_PW.encode())
    if not ok: raise HTTPException(401, "Wrong username or password")
    sid = secrets.token_urlsafe(32); w = WS(); w.yaml = POLICIES[w.tpl].read_text(); SESSIONS[sid] = w
    resp.set_cookie("sid", sid, httponly=True, samesite="strict", max_age=86400)
    return {"user": ADMIN_USER}
@app.post("/api/logout")
def logout(request: Request, resp: Response):
    SESSIONS.pop(request.cookies.get("sid", ""), None); resp.delete_cookie("sid"); return {"ok": True}
@app.get("/api/me")
def me(w: WS = Depends(ws)): return {"user": ADMIN_USER, "version": __version__}


@app.get("/api/meta")
def meta(w: WS = Depends(ws)):
    ok, why = nlp.nlp_available()
    fq = [(r, t, RULES[r].framework, RULES[r].applies_to) for r, t in FRAMEWORK_QUESTIONS]
    return J({"samples": list(SAMPLES), "policies": list(POLICIES), "nlp": ok, "nlp_why": why, "confidence": CONFIDENCE_NOTE,
              "att": [(r, RULES[r].section, t) for r, t in ATTESTATION_QUESTIONS], "fw": fq, "breach_days": DELEGATED_PARAMS["breach_notify_calendar_days"]})


class Settings(BaseModel): csp: bool = False; pae: bool = False; di: bool = False; attest: dict[str, bool | None] = {}
@app.get("/api/state")
def state(w: WS = Depends(ws)):
    return J({"tables": list(w.tables), "cur": w.cur, "csp": w.csp, "pae": w.pae, "di": w.di, "attest": w.attest, "db": w.db is not None})
@app.put("/api/settings")
def settings(s: Settings, w: WS = Depends(ws)):
    w.csp, w.pae, w.di = s.csp, s.pae, s.di; w.attest.update(s.attest); return {"ok": True}


# ---------------------------------------------------------------- 1 scan
@app.post("/api/data/demo")
def demo(b: dict, w: WS = Depends(ws)):
    s = b["sample"]; w.tables = {s.split(": ")[1].replace(" ", "_"): SAMPLES[s]()}; w.cur = next(iter(w.tables)); w.gov = None
    w.tpl = "Accounting firm" if s.startswith("Accounting") else "Tuition centre"; w.yaml = POLICIES[w.tpl].read_text(); return {"ok": True}
@app.post("/api/data/upload")
async def upload(file: UploadFile = File(...), w: WS = Depends(ws)):
    try: w.tables = load_table(file.filename, await file.read())
    except Exception as e: bad(f"Could not read file: {e}")
    w.cur = next(iter(w.tables)); w.gov = None; return {"ok": True}
@app.get("/api/scan")
def scan(table: str = "", w: WS = Depends(ws)):
    if table in w.tables: w.cur = table
    df = df_of(w); r = run(w, df, w.ps)
    return J({"score": r.pdpa_score, "band": r.band(), "coverage": r.coverage, "rows": r.n_rows, "cols": r.n_cols, "ai": r.ai, "fw": r.frameworks, "di": w.di,
              "failing": [{"lost": round(c.points_lost, 1), "regime": c.rule.framework, "rule": c.rule.title, "ref": c.rule.section, "src": c.rule.confidence,
                           "sev": c.rule.severity, "finding": c.detail, "fix": c.rule.remediation} for c in r.failing()],
              "na": [{"rule": c.rule.title, "ref": c.rule.section, "why": c.detail} for c in r.checks if not c.applicable],
              "found": [{"column": f.column, "cls": f.data_class, "sens": f.sensitivity, "ev": f.evidence, "visible": f"{int(f.unmasked_ratio*100)}%", "notes": "; ".join(f.notes)} for f in r.findings],
              "preview": recs(df)})


# ---------------------------------------------------------------- 2 clean & mask
class Govern(BaseModel): retention: int = 730; purpose: str = ""; mask: bool = True
@app.post("/api/govern")
def govern(b: Govern, w: WS = Depends(ws)):
    df = df_of(w); p = load_policy(w.yaml) if not policy_errors(w.yaml) else None
    out, log = apply_governance(df, retention_days=b.retention, default_purpose=b.purpose or None, mask=b.mask,
                                legal_hold_days=p.settings.legal_hold_days if p else None, legal_basis=p.settings.legal_basis if p else None)
    w.gov = (out, log); a, c = run(w, df), run(w, out)
    return J({"before": a.pdpa_score, "after": c.pdpa_score, "ai_before": a.ai["score"], "ai_after": c.ai["score"], "log": log, "columns": list(out.columns),
              "remaining": [{"rule": x.rule.title, "fix": x.rule.remediation} for x in c.failing() if x.rule.kind == "data"], "preview": recs(out)})
@app.get("/api/govern/download")
def dl(fmt: str = "csv", w: WS = Depends(ws)):
    if not w.gov: bad("Run Apply governance first.")
    out = w.gov[0]
    if fmt == "xlsx":
        buf = io.BytesIO(); out.to_excel(buf, index=False); buf.seek(0)
        return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": "attachment; filename=governed.xlsx"})
    return StreamingResponse(io.BytesIO(out.to_csv(index=False).encode()), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=governed.csv"})
@app.post("/api/govern/kanon")
def kanon(b: dict, w: WS = Depends(ws)):
    if not w.gov: bad("Run Apply governance first.")
    return J(k_anonymity(w.gov[0], b.get("qi", [])))


# ---------------------------------------------------------------- 3 policy
@app.get("/api/policy")
def get_policy(w: WS = Depends(ws)): return {"yaml": w.yaml, "tpl": w.tpl}
@app.post("/api/policy")
def set_policy(b: dict, w: WS = Depends(ws)):
    if b.get("tpl") in POLICIES and b["tpl"] != w.tpl: w.tpl = b["tpl"]; w.yaml = POLICIES[w.tpl].read_text()
    elif "yaml" in b: w.yaml = b["yaml"]
    e = policy_errors(w.yaml)
    if e: return J({"yaml": w.yaml, "tpl": w.tpl, "errors": e})
    p = load_policy(w.yaml)
    return J({"yaml": w.yaml, "tpl": w.tpl, "errors": [], "name": p.name, "n_tables": len(p.tables), "n_monitor": len(p.monitor),
              "roles": {k: v.description for k, v in p.roles.items()}, "sql": ";\n".join(compile_policy(p).statements) + ";"})


# ---------------------------------------------------------------- 4 monitoring
def need_db(w):
    if w.db is None: bad("Connect to PostgreSQL first.")
    return w.db
@app.post("/api/db/connect")
def connect(b: dict, w: WS = Depends(ws)):
    from pdpa_guard.db import Database
    try: db = Database(b.get("dsn") or None); db.install(); w.db = db
    except Exception as e: bad(f"Connection failed: {e}")
    return {"ok": True}
@app.post("/api/db/load")
def db_load(b: dict, w: WS = Depends(ws)):
    db, p = need_db(w), pol(w)
    kw = dict(mask=False, default_purpose=p.settings.default_purpose, retention_days=p.settings.retention_days,
              legal_hold_days=p.settings.legal_hold_days, legal_basis=p.settings.legal_basis)
    if b.get("reapply"): db.apply_policy(p, w.yaml); return {"ok": True}
    if "public.payroll" in p.tables:
        db.load_dataframe(apply_governance(messy_clients(), **kw)[0], "clients_cdd"); db.load_dataframe(apply_governance(messy_payroll(), **kw)[0], "payroll"); db.load_dataframe(assignments(), "assignments")
    else:
        from pdpa_guard.db import sanitise_ident
        need = {c for c in p.tables["public.students"].columns if c != "id"} if "public.students" in p.tables else set()
        cur = w.tables.get(w.cur)
        data = apply_governance(cur if cur is not None and need <= {sanitise_ident(c) for c in cur.columns} else messy_students(), **kw)[0]
        db.load_dataframe(data, "students")
    db.apply_policy(p, w.yaml); db.reset_audit(); return {"ok": True}
@app.get("/api/db/state")
def db_state(w: WS = Depends(ws)):
    db, p = need_db(w), pol(w); st = db.policy_state(p); w.ps = {k: st[k] for k in ("enforced", "drift", "audit")}
    base = run(w, w.tables[w.cur], w.ps).pdpa_score if w.cur in w.tables else 100.0
    return J({"live": db.live_score(base), "static": base, "drift": st["drift"], "drift_items": st["drift_items"], "roles": list(p.roles),
              "findings": db.findings("open"), "notes": db.notifications(), "events": [{k: v for k, v in e.items()} for e in db.events(100)]})
@app.post("/api/db/query")
def db_query(b: dict, w: WS = Depends(ws)):
    from pdpa_guard.db import Gateway
    r = Gateway(need_db(w), pol(w)).execute(b["staff"], b["role"], b["sql"], b.get("purpose", ""), approved=bool(b.get("approve")))  # signed-in admin acts as DPO
    return J({"ok": r.ok, "columns": r.columns, "rows": r.rows, "rowcount": r.rowcount, "error": r.error})
ATTACKS = [("Teacher reads base table", ("tom", "teacher", "select * from public.students limit 3", "")),
           ("Admin exports everyone", ("amy", "admin_staff", "select * from students", "export")), ("Intern asks for NRIC", ("ivy", "intern", "select nric from students", ""))]
@app.post("/api/db/attack")
def db_attack(b: dict, w: WS = Depends(ws)):
    from pdpa_guard.db import Gateway
    label, args = ATTACKS[int(b["i"])]; r = Gateway(need_db(w), pol(w)).execute(*args)
    return J({"label": label, "ok": r.ok, "error": r.error})
@app.post("/api/db/monitor")
def db_monitor(w: WS = Depends(ws)): return {"new": need_db(w).run_monitor(pol(w))}
@app.post("/api/db/resolve")
def db_resolve(b: dict, w: WS = Depends(ws)): need_db(w).resolve_finding(int(b["id"])); return {"ok": True}


# ---------------------------------------------------------------- 5 breach & requests
@app.get("/api/breach")
def breach(w: WS = Depends(ws)):
    db, p = need_db(w), pol(w); out = []
    for cs in db.cases()[:5]:
        body = cs["body"] if isinstance(cs["body"], dict) else json.loads(cs["body"]); org = p.settings.organisation
        out.append({"id": cs["id"], "body": {k: v for k, v in body.items() if k != "checklist"}, "checklist": body["checklist"],
                    "client": draft_client_notice(body, org) if (w.di or p.settings.sector == "accounting") else None,
                    "pdpc": draft_pdpc_notification(body, org), "individual": draft_individual_notice(body, org)})
    try: ret = db.retention_overdue("payroll" if "public.payroll" in p.tables else "students")
    except Exception: ret = None
    return J({"cases": out, "retention": ret, "days": DELEGATED_PARAMS["breach_notify_calendar_days"], "accounting": p.settings.sector == "accounting"})
@app.post("/api/breach/subject")
def subject(b: dict, w: WS = Depends(ws)):
    p = pol(w); res = need_db(w).find_subject(p, b["id"]); res["columns"] = {t: [c for c in p.tables[t].columns if c != "id"] for t in res["records"]}; return J(res)
@app.post("/api/breach/correct")
def correct(b: dict, w: WS = Depends(ws)): return {"n": need_db(w).correct_field(pol(w), b["table"], b["pk"], b["column"], b["value"], ADMIN_USER)}


# ---------------------------------------------------------------- 6 documents
@app.post("/api/docs")
async def docs(files: list[UploadFile] = File(...), bert: bool = Form(False), w: WS = Depends(ws)):
    err = None
    if bert and w.ner is None:
        try: w.ner, w.enc = nlp.get_ner(), nlp.get_encoder()
        except Exception as e: err = f"Could not load BERT models, rules/keywords only: {e}"
    ner, enc = (w.ner, w.enc) if bert else (None, None); out = []
    for f in files:
        try: blocks = documents.extract_blocks(f.filename, await f.read())
        except documents.DocumentError as e: out.append({"name": f.filename, "error": str(e)}); continue
        fs = doc_scan.scan_blocks(blocks, ner=ner); res = doc_policy.check_document(blocks, encoder=enc)
        out.append({"name": f.filename, "summary": doc_scan.summarise(fs), "redacted": doc_scan.redact(blocks, fs),
                    "items": [{"kind": x.kind, "sens": x.sensitivity, "preview": x.preview, "page": x.page, "para": x.block + 1, "conf": x.confidence, "src": x.source, "note": x.note} for x in fs],
                    "coverage": doc_policy.coverage_score(res), "suggest": list(doc_policy.suggested_answers(res)),
                    "duties": [{"duty": r.ob.title, "ref": r.ob.section, "status": r.status, "score": round(r.score, 2), "method": r.backend, "evidence": r.evidence} for r in res]})
    return J({"docs": out, "error": err})


app.mount("/", StaticFiles(directory=ROOT / "web", html=True), name="web")

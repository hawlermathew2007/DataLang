"""Command line: scan a file, set up the demo database, run the monitor.

    python -m pdpa_guard scan customers.csv
    python -m pdpa_guard scan-doc policy.pdf --policy-check [--bert] [--redact]
    python -m pdpa_guard setup-demo          # needs PDPA_GUARD_DSN
    python -m pdpa_guard monitor
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .remediate import apply_governance, load_table
from .scoring import assess

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_POLICY = ROOT / "policies" / "tuition_centre.yaml"


def cmd_scan(a) -> int:
    for name, df in load_table(a.file, Path(a.file)).items():
        r = assess(df)
        print(f"\n== {name}: {r.n_rows} rows x {r.n_cols} cols")
        print(f"PDPA readiness: {r.pdpa_score}/100 ({r.band()}), assessed {int(r.coverage*100)}% of rule weight")
        print(f"AI readiness  : {r.ai['score']}/100  {r.ai['dimensions']}")
        for c in r.failing():
            print(f"  - [{c.rule.section}] {c.rule.title}: {c.detail}")
        if a.fix:
            out, log = apply_governance(df, default_purpose=a.purpose)
            r2 = assess(out)
            dest = Path(a.file).with_suffix("").as_posix() + "_governed.csv"
            out.to_csv(dest, index=False)
            print(f"\nAfter governance: {r2.pdpa_score}/100  -> {dest}")
            print("\n".join("  * " + x for x in log))
    return 0


def cmd_scan_doc(a) -> int:
    from . import doc_policy, doc_scan, documents, nlp
    blocks = documents.extract_blocks(a.file, Path(a.file))
    ner = enc = None
    if a.bert:
        ok, why = nlp.nlp_available()
        if not ok:
            print(why, file=sys.stderr); return 2
        ner, enc = nlp.get_ner(), nlp.get_encoder()
    fs = doc_scan.scan_blocks(blocks, ner=ner)
    sm = doc_scan.summarise(fs)
    print(f"\n== {a.file}: {len(blocks)} paragraphs; {sm['total']} personal-data item(s) {sm['by_kind']}, {sm['needs_review']} need review")
    for f in fs:
        print(f"  - {f.kind:8} {f.preview:20} p.{f.page or '-'} para {f.block + 1} conf {f.confidence} ({f.source})")
    if a.policy_check:
        res = doc_policy.check_document(blocks, encoder=enc)
        print(f"\nPolicy coverage: {doc_policy.coverage_score(res)}/100 (method: {res[0].backend})")
        for r in res:
            print(f"  [{r.status:9}] {r.ob.section:18} {r.ob.title}")
    if a.redact:
        dest = Path(a.file).with_suffix("").as_posix() + "_redacted.txt"
        Path(dest).write_text(doc_scan.redact(blocks, fs), encoding="utf-8")
        print(f"\nRedacted text -> {dest}")
    return 0


def cmd_setup_demo(a) -> int:
    from .db import Database
    from .policy import load_policy
    from .sample import assignments, messy_clients, messy_payroll, messy_students
    db = Database(a.dsn)
    db.install()
    text = Path(a.policy).read_text()
    pol = load_policy(text)
    s = pol.settings
    kw = dict(mask=False, default_purpose=s.default_purpose, retention_days=s.retention_days,
              legal_hold_days=s.legal_hold_days, legal_basis=s.legal_basis)
    if "public.payroll" in pol.tables:
        db.load_dataframe(apply_governance(messy_clients(), **kw)[0], "clients_cdd")
        db.load_dataframe(apply_governance(messy_payroll(), **kw)[0], "payroll")
        db.load_dataframe(assignments(), "assignments")
    else:
        db.load_dataframe(apply_governance(messy_students(), **kw)[0], "students")
    db.apply_policy(pol, text)
    db.reset_audit()
    print("Demo database ready: demo tables loaded, policy applied.")
    return 0


def cmd_monitor(a) -> int:
    from .db import Database
    from .policy import load_policy
    db = Database(a.dsn)
    pol = load_policy(Path(a.policy).read_text())
    print(f"{db.run_monitor(pol)} new finding(s)")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="pdpa_guard")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan"); s.add_argument("file"); s.add_argument("--fix", action="store_true")
    s.add_argument("--purpose", default=None); s.set_defaults(fn=cmd_scan)
    sd = sub.add_parser("scan-doc"); sd.add_argument("file")
    sd.add_argument("--bert", action="store_true", help="use BERT NER + encoder (needs requirements-nlp.txt)")
    sd.add_argument("--policy-check", action="store_true", help="also check the document against PDPA duties")
    sd.add_argument("--redact", action="store_true"); sd.set_defaults(fn=cmd_scan_doc)
    d = sub.add_parser("setup-demo"); d.add_argument("--dsn", default=None)
    d.add_argument("--policy", default=str(DEFAULT_POLICY)); d.set_defaults(fn=cmd_setup_demo)
    m = sub.add_parser("monitor"); m.add_argument("--dsn", default=None)
    m.add_argument("--policy", default=str(DEFAULT_POLICY)); m.set_defaults(fn=cmd_monitor)
    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())

"""Find personal data inside unstructured documents.

Two layers, merged:
  * deterministic (always on): NRIC/FIN with checksum, +65 phones, emails, Luhn card numbers,
    postal codes that follow the word "Singapore".
  * BERT NER (optional): person names / locations that no regex can find.

Display values are masked by default so the scan result itself does not become a new copy
of the personal data.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from .detectors import luhn, normalise_sg_phone, valid_email, valid_nric
from .documents import Block
from .masking import mask_value
from .nlp import Entity, NerBackend

# kind -> (sensitivity, placeholder, masking data-class)
KINDS = {
    "nric": ("high", "[NRIC]", "nric"),
    "card": ("high", "[CARD]", "financial"),
    "phone": ("medium", "[PHONE]", "phone"),
    "email": ("medium", "[EMAIL]", "email"),
    "name": ("medium", "[NAME]", "name"),
    "postal": ("low", "[POSTAL]", "postal"),
    "location": ("low", "[LOCATION]", "address"),
}
_PRIORITY = {"nric": 0, "card": 1, "email": 2, "phone": 3, "postal": 4, "name": 5, "location": 6}

_NRIC = re.compile(r"(?<![A-Za-z0-9])[STFGMstfgm]\d{7}[A-Za-z](?![A-Za-z0-9])")
_PHONE = re.compile(r"(?<![\d])(?:\+?65[\s-]?)?[3689]\d{3}[\s-]?\d{4}(?![\d])")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_CARD = re.compile(r"(?<![\d])(?:\d[ -]?){12,18}\d(?![\d])")
_POSTAL = re.compile(r"(?i:singapore)\s+(\d{6})(?!\d)")


@dataclass
class DocFinding:
    kind: str
    start: int            # offsets inside Block.text
    end: int
    block: int
    page: int | None
    source: str           # "rule" | "bert"
    confidence: float
    sensitivity: str
    preview: str          # masked
    note: str = ""
    _raw: str = field(default="", repr=False)   # kept in memory for redaction only


def _rule_spans(text: str) -> list[tuple[str, int, int, float, str]]:
    out: list[tuple[str, int, int, float, str]] = []
    for m in _NRIC.finditer(text):
        ok = valid_nric(m.group())
        out.append(("nric", m.start(), m.end(), 0.99 if ok else 0.6,
                    "checksum valid" if ok else "NRIC-shaped but checksum fails (may be a typo or a fake)"))
    for m in _EMAIL.finditer(text):
        if valid_email(m.group()):
            out.append(("email", m.start(), m.end(), 0.98, ""))
    for m in _CARD.finditer(text):
        if luhn(m.group()):
            out.append(("card", m.start(), m.end(), 0.9, "Luhn check passes"))
    for m in _PHONE.finditer(text):
        if normalise_sg_phone(m.group()):
            out.append(("phone", m.start(), m.end(), 0.85, "Singapore number format"))
    for m in _POSTAL.finditer(text):
        out.append(("postal", m.start(1), m.end(1), 0.8, "6 digits after 'Singapore'"))
    return out


def _bert_spans(text: str, ner: NerBackend, min_score: float) -> list[tuple[str, int, int, float, str]]:
    out = []
    for e in ner.entities(text):
        if e.score < min_score:
            continue
        if e.label == "PER" and len(e.text.strip()) > 2:
            out.append(("name", e.start, e.end, e.score, f"BERT NER ({ner.name})"))
        elif e.label == "LOC":
            out.append(("location", e.start, e.end, e.score, f"BERT NER ({ner.name}); may be an address or just a place name"))
    return out


def _resolve(spans: list[tuple[str, int, int, float, str]]) -> list[tuple[str, int, int, float, str]]:
    """Drop overlapping spans, keeping the higher-priority (then longer) one."""
    keep: list[tuple[str, int, int, float, str]] = []
    for s in sorted(spans, key=lambda s: (_PRIORITY[s[0]], -(s[2] - s[1]))):
        if all(s[2] <= k[1] or s[1] >= k[2] for k in keep):
            keep.append(s)
    return sorted(keep, key=lambda s: s[1])


def scan_blocks(blocks: list[Block], ner: NerBackend | None = None, min_score: float = 0.85) -> list[DocFinding]:
    findings: list[DocFinding] = []
    for b in blocks:
        spans = _rule_spans(b.text)
        if ner is not None:
            spans += _bert_spans(b.text, ner, min_score)
        for kind, s, e, conf, note in _resolve(spans):
            raw = b.text[s:e]
            sens, _, cls = KINDS[kind]
            mode = "partial" if cls in ("nric", "phone", "email") else "redact"
            prev = str(mask_value(raw, cls, mode)) if kind not in ("name", "location") else raw[:1] + "…"
            findings.append(DocFinding(kind, s, e, b.index, b.page, "bert" if "BERT" in note else "rule",
                                       round(conf, 2), sens, prev, note, raw))
    return findings


def redact(blocks: list[Block], findings: list[DocFinding]) -> str:
    """Return the document text with every finding replaced by a placeholder."""
    by_block: dict[int, list[DocFinding]] = {}
    for f in findings:
        by_block.setdefault(f.block, []).append(f)
    parts = []
    for b in blocks:
        t = b.text
        for f in sorted(by_block.get(b.index, []), key=lambda f: -f.start):
            t = t[:f.start] + KINDS[f.kind][1] + t[f.end:]
        parts.append(t)
    return "\n\n".join(parts)


def summarise(findings: list[DocFinding]) -> dict:
    c = Counter(f.kind for f in findings)
    high = sum(1 for f in findings if f.sensitivity == "high")
    return {"total": len(findings), "by_kind": dict(c), "high_sensitivity": high,
            "needs_review": sum(1 for f in findings if f.confidence < 0.8)}

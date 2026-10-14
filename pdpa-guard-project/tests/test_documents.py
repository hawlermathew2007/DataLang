"""Document scanning + policy-document check. No model downloads: BERT backends are replaced by fakes."""
import io

import pytest

from pdpa_guard.doc_policy import COVERED, MISSING, OBLIGATIONS, check_document, coverage_score, suggested_answers
from pdpa_guard.doc_scan import redact, scan_blocks, summarise
from pdpa_guard.documents import DocumentError, extract_blocks, sentences
from pdpa_guard.nlp import Entity

TEXT = """Student: Aung Ko, NRIC S1234567D, phone +65 9123 4567, email aung@example.com.

Card 4539 1488 0343 6467. Address: 12 Bedok Road, Singapore 469001. Ref S1234567A.

Order id 91234567891 should not be flagged."""


def blocks(text=TEXT):
    return extract_blocks("x.txt", text.encode())


def test_rule_layer_finds_and_validates():
    fs = scan_blocks(blocks())
    kinds = [f.kind for f in fs]
    assert kinds.count("nric") == 2 and {"phone", "email", "card", "postal"} <= set(kinds)
    nrics = sorted((f for f in fs if f.kind == "nric"), key=lambda f: -f.confidence)
    assert nrics[0].confidence > 0.9 and nrics[1].confidence < 0.7      # checksum fail -> review
    assert not any("91234567891" in f._raw for f in fs)


def test_preview_is_masked_and_redaction_removes_everything():
    b = blocks()
    fs = scan_blocks(b)
    assert all("S1234567D" not in f.preview for f in fs)
    out = redact(b, fs)
    for secret in ("S1234567D", "9123 4567", "aung@example.com", "4539", "469001"):
        assert secret not in out
    assert "[NRIC]" in out and "Order id 91234567891" in out


class FakeNer:
    name = "fake-ner"
    def entities(self, text):
        i = text.find("Aung Ko")
        j = text.find("Bedok")
        out = []
        if i >= 0: out.append(Entity("PER", "Aung Ko", i, i + 7, 0.97))
        if j >= 0: out.append(Entity("LOC", "Bedok", j, j + 5, 0.9))
        out.append(Entity("PER", "Low", 0, 3, 0.3))            # below threshold
        return out


def test_ner_adds_names_and_respects_threshold():
    fs = scan_blocks(blocks(), ner=FakeNer())
    names = [f for f in fs if f.kind == "name"]
    assert len(names) == 1 and names[0].source == "bert"
    assert "Aung Ko" not in names[0].preview
    assert "Aung Ko" not in redact(blocks(), fs)


def test_overlap_prefers_deterministic_span():
    class Greedy:
        name = "g"
        def entities(self, text):
            i = text.find("S1234567D")
            return [Entity("PER", "S1234567D", i, i + 9, 0.99)]
    fs = scan_blocks(blocks(), ner=Greedy())
    assert [f.kind for f in fs if f._raw == "S1234567D"] == ["nric"]


def test_docx_extraction_includes_tables():
    docx = pytest.importorskip("docx")
    d = docx.Document()
    d.add_paragraph("We collect your personal data for enrolment purposes.")
    t = d.add_table(rows=1, cols=2)
    t.rows[0].cells[0].text, t.rows[0].cells[1].text = "Ms Tan", "S1234567D"
    buf = io.BytesIO(); d.save(buf)
    bl = extract_blocks("a.docx", buf.getvalue())
    assert any("S1234567D" in b.text for b in bl)


def _tiny_pdf(text: str) -> bytes:
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>"]
    st = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET"
    objs += [f"<< /Length {len(st)} >>\nstream\n{st}\nendstream", "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offs = "%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out)); out += f"{i} 0 obj\n{o}\nendobj\n"
    x = len(out); out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n" + "".join(f"{o:010d} 00000 n \n" for o in offs)
    return (out + f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{x}\n%%EOF").encode()


def test_pdf_extraction_keeps_page_numbers():
    pytest.importorskip("pypdf")
    bl = extract_blocks("a.pdf", _tiny_pdf("Contact Ms Tan NRIC S1234567D"))
    assert bl[0].page == 1 and "S1234567D" in bl[0].text
    assert scan_blocks(bl)[0].page == 1


def test_errors_are_readable():
    with pytest.raises(DocumentError):
        extract_blocks("a.exe", b"x")
    with pytest.raises(DocumentError):
        extract_blocks("empty.txt", b"   \n ")
    with pytest.raises(DocumentError):
        extract_blocks("bad.pdf", b"not a pdf")


def test_sentence_splitter_handles_burmese_terminator():
    assert len(sentences("ကျွန်ုပ်တို့ ဒေတာကို ကာကွယ်ပါသည်။ ကျွန်ုပ်တို့ ဒေတာကို ဖျက်ပါသည်။")) == 2


POLICY = """We have appointed a Data Protection Officer who is responsible for PDPA compliance.

We collect your personal data for the following purposes: enrolment and billing.

You may request access to your personal data and ask us to correct it at any time.

We retain records for seven years and then delete them. Staff access is limited and data is encrypted.

Our canteen serves lunch from twelve o'clock every weekday."""


def test_keyword_backend_finds_covered_and_missing():
    res = {r.ob.id: r for r in check_document(blocks(POLICY))}
    assert res["O-DPO"].status == COVERED and "Data Protection Officer" in res["O-DPO"].evidence
    assert res["O-RETENTION"].status == COVERED
    assert res["O-BREACH"].status == MISSING and res["O-BREACH"].evidence == ""
    assert res["O-DPO"].backend == "keyword"


class FakeEncoder:
    """Bag-of-words vectors: deterministic stand-in for a BERT sentence encoder."""
    name = "fake-encoder"
    VOCAB = sorted({w for o in OBLIGATIONS for h in o.hypotheses for w in h.lower().replace(".", "").split()}
                   | {"canteen", "lunch"})
    def encode(self, texts):
        out = []
        for t in texts:
            ws = set(t.lower().replace(".", "").replace(",", "").split())
            v = [1.0 if w in ws else 0.0 for w in self.VOCAB]
            n = sum(x * x for x in v) ** 0.5 or 1.0
            out.append([x / n for x in v])
        return out


def test_encoder_backend_flags_relevant_sentences_not_noise():
    res = {r.ob.id: r for r in check_document(blocks(POLICY), encoder=FakeEncoder(), covered_at=0.5, weak_at=0.3)}
    assert res["O-DPO"].status != MISSING and "Data Protection Officer" in res["O-DPO"].evidence
    assert "canteen" not in " ".join(r.evidence for r in res.values())
    assert res["O-DPO"].backend == "fake-encoder"


def test_suggestions_only_ever_say_yes_and_map_to_real_rules():
    sug = suggested_answers(check_document(blocks(POLICY)))
    assert sug.get("A-DPO") is True and all(v is True for v in sug.values())
    assert "A-BREACH" not in sug
    assert 0 < coverage_score(check_document(blocks(POLICY))) < 100


def test_summary_counts():
    s = summarise(scan_blocks(blocks()))
    assert s["total"] >= 6 and s["high_sensitivity"] == 3 and s["needs_review"] == 1

"""Check whether a policy / notice / consent document *states* what the PDPA expects.

Each obligation is described by a few hypothesis sentences. Every sentence of the uploaded
document is compared with them and the best match is shown as evidence.

Backends
  * keyword  - always available, no ML, English phrases. Used as a fallback and as a cross-check.
  * encoder  - BERT-family sentence encoder (multilingual by default). Cosine similarity.

This produces EVIDENCE that a document mentions a topic. It does not show the organisation
follows what the document says, nor that the wording is legally adequate. Results can
pre-fill the self-assessment, but a person has to confirm them (same rule as the rest of
the tool: it never invents facts only the organisation can confirm).
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

from .catalogue import RULES
from .documents import Block, sentences
from .nlp import EncoderBackend


@dataclass(frozen=True)
class Obligation:
    id: str                       # catalogue rule id when it maps to one
    title: str
    section: str
    hypotheses: tuple[str, ...]   # what a covering sentence would say
    keywords: tuple[str, ...]     # regex fragments for the keyword backend
    attest_rule: str | None = None


OBLIGATIONS: tuple[Obligation, ...] = (
    Obligation("O-DPO", "Designated person responsible for data protection", "s.11(3)-(5)",
               ("We have appointed a Data Protection Officer responsible for PDPA compliance.",
                "Contact our data protection officer at the email address below."),
               (r"data protection officer", r"\bDPO\b", r"responsible for (?:PDPA|data protection)"), "A-DPO"),
    Obligation("O-NOTICE", "Purposes of collection, use and disclosure are stated", "s.18, s.20",
               ("We collect your personal data for the following purposes.",
                "Your personal data will be used only for the purposes notified to you."),
               (r"purposes?", r"we (?:collect|use) your (?:personal )?(?:data|information)"), "A-NOTICE"),
    Obligation("O-CONSENT", "Consent is obtained and can be withdrawn", "s.13, s.14, s.16",
               ("We collect your personal data only with your consent.",
                "You may withdraw your consent at any time by contacting us."),
               (r"consent", r"withdraw"), None),
    Obligation("O-ACCESS", "Access and correction requests", "s.21, s.22",
               ("You may request access to the personal data we hold about you.",
                "You may ask us to correct an error in your personal data."),
               (r"access (?:to )?(?:your )?(?:personal )?(?:data|information)", r"correct(?:ion)?\b", r"request"), "A-ACCESS-PROC"),
    Obligation("O-RETENTION", "Retention period / when data is deleted", "s.25",
               ("We keep your personal data only as long as necessary and then delete or anonymise it.",
                "Records are retained for a period of seven years."),
               (r"retain", r"retention", r"delete", r"destroy", r"anonymi[sz]e", r"no longer (?:needed|necessary)"), None),
    Obligation("O-PROTECT", "Security arrangements", "s.24",
               ("We protect personal data with reasonable security arrangements such as access control and encryption.",
                "Only authorised staff may access personal data."),
               (r"security", r"encrypt", r"access control", r"authori[sz]ed (?:staff|personnel)", r"safeguard"), None),
    Obligation("O-TRANSFER", "Transfers outside Singapore", "s.26",
               ("Your personal data may be transferred outside Singapore with comparable protection.",
                "We store data on servers located overseas."),
               (r"outside singapore", r"overseas", r"transfer(?:red)?", r"cross-border"), None),
    Obligation("O-BREACH", "Data breach response and notification", "Part 6A (s.26A-26E)",
               ("We will notify the PDPC and affected individuals of a notifiable data breach.",
                "We have a data breach response plan to assess and contain incidents."),
               (r"data breach", r"breach (?:response|notification|plan)", r"notify the (?:PDPC|commission)"), "A-BREACH"),
    Obligation("O-COMPLAINT", "Complaints handling", "s.12(b)",
               ("You may contact us to raise a complaint about how we handle personal data.",
                "We have a process to receive and respond to complaints."),
               (r"complaint", r"grievance"), "A-COMPLAINT"),
    Obligation("O-VENDOR", "Data intermediaries are bound by contract", "s.4(2)-(3), s.24",
               ("Service providers that process personal data for us are bound by written contracts.",
                "Third parties handling data on our behalf must protect it."),
               (r"(?:service provider|vendor|third part(?:y|ies)|data intermediar(?:y|ies)|processor)", r"contract"), "A-DI"),
    Obligation("O-DNC", "Marketing messages and Do Not Call registers", "Part 9 (s.36-48)",
               ("We check the Do Not Call Registry before sending marketing messages.",
                "You can opt out of marketing communications at any time."),
               (r"do not call", r"\bDNC\b", r"opt[- ]out", r"unsubscribe", r"marketing"), None),
)

COVERED, WEAK, MISSING = "covered", "weak", "not found"


@dataclass
class ObligationResult:
    ob: Obligation
    status: str
    score: float                 # 0..1 best similarity / keyword strength
    evidence: str                # best matching sentence
    block: int | None
    page: int | None
    backend: str
    suggests_yes: bool           # evidence the doc states it (to pre-fill, never to assert)


def _cos(a: list[float], b: list[float]) -> float:
    d = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)); nb = math.sqrt(sum(y * y for y in b))
    return d / (na * nb) if na and nb else 0.0


def _keyword_score(sentence: str, ob: Obligation) -> float:
    hits = sum(1 for k in ob.keywords if re.search(k, sentence, re.I))
    return min(1.0, hits / 2)       # two distinct cues = full strength


def _all_sentences(blocks: list[Block]) -> list[tuple[str, int, int | None]]:
    out = []
    for b in blocks:
        for s in sentences(b.text):
            if len(s) >= 15:
                out.append((s[:600], b.index, b.page))
    return out


def check_document(blocks: list[Block], encoder: EncoderBackend | None = None,
                   covered_at: float = 0.55, weak_at: float = 0.40) -> list[ObligationResult]:
    """Score every obligation. With an encoder: cosine similarity; otherwise keyword cues.

    Thresholds are starting points, not calibrated values - tune them on your own documents.
    """
    sents = _all_sentences(blocks)
    results: list[ObligationResult] = []
    if not sents:
        return [ObligationResult(o, MISSING, 0.0, "", None, None, "none", False) for o in OBLIGATIONS]

    kw_best = {}
    for o in OBLIGATIONS:
        scored = [(_keyword_score(s, o), s, bi, pg) for s, bi, pg in sents]
        kw_best[o.id] = max(scored, key=lambda t: t[0])

    if encoder is None:
        for o in OBLIGATIONS:
            sc, s, bi, pg = kw_best[o.id]
            status = COVERED if sc >= 1.0 else WEAK if sc > 0 else MISSING
            results.append(ObligationResult(o, status, round(sc, 2), s if sc > 0 else "", bi if sc > 0 else None,
                                            pg if sc > 0 else None, "keyword", status == COVERED))
        return results

    s_vecs = encoder.encode([s for s, _, _ in sents])
    for o in OBLIGATIONS:
        h_vecs = encoder.encode(list(o.hypotheses))
        best, bi_ = 0.0, 0
        for i, sv in enumerate(s_vecs):
            sim = max(_cos(sv, hv) for hv in h_vecs)
            if sim > best:
                best, bi_ = sim, i
        s, bi, pg = sents[bi_]
        kw = kw_best[o.id][0]
        # a sentence the encoder likes AND that has a keyword cue is stronger evidence than either alone
        status = COVERED if best >= covered_at else WEAK if best >= weak_at else MISSING
        if status == COVERED and kw == 0 and best < covered_at + 0.1:
            status = WEAK
        results.append(ObligationResult(o, status, round(best, 2), s if status != MISSING else "",
                                        bi if status != MISSING else None, pg if status != MISSING else None,
                                        getattr(encoder, "name", "encoder"), status == COVERED))
    return results


def suggested_answers(results: list[ObligationResult]) -> dict[str, bool]:
    """Self-assessment ids that the document supports with a 'covered' sentence. Only 'Yes' is ever suggested."""
    return {r.ob.attest_rule: True for r in results if r.ob.attest_rule and r.suggests_yes and r.ob.attest_rule in RULES}


def coverage_score(results: list[ObligationResult]) -> float:
    pts = sum(1.0 if r.status == COVERED else 0.5 if r.status == WEAK else 0.0 for r in results)
    return round(100 * pts / len(results), 1) if results else 0.0

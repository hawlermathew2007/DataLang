"""Optional BERT-family models, loaded lazily.

Nothing here is imported unless the person turns the NLP option on, so the base install
(and every deterministic score) works without torch/transformers. Models run locally; the
first use downloads weights from the Hugging Face Hub unless you point the env vars at a
local folder (recommended for sensitive environments: pre-download, then set HF_HUB_OFFLINE=1).

Env vars
  PDPA_GUARD_NER_MODEL     token-classification model   (default: dslim/bert-base-NER, English, BERT-base)
  PDPA_GUARD_ENCODER_MODEL sentence-embedding model     (default: sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2)
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

NER_MODEL = os.environ.get("PDPA_GUARD_NER_MODEL", "dslim/bert-base-NER")
ENCODER_MODEL = os.environ.get("PDPA_GUARD_ENCODER_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")


@dataclass
class Entity:
    label: str      # PER | ORG | LOC | MISC
    text: str
    start: int
    end: int
    score: float


class NerBackend(Protocol):
    name: str
    def entities(self, text: str) -> list[Entity]: ...


class EncoderBackend(Protocol):
    name: str
    def encode(self, texts: list[str]) -> list[list[float]]: ...


def nlp_available() -> tuple[bool, str]:
    """(ok, reason). Cheap check - does not load any weights."""
    try:
        import transformers  # noqa: F401
        import torch  # noqa: F401
    except ImportError:
        return False, "Install the optional NLP extras: pip install -r requirements-nlp.txt"
    return True, "ok"


class HfNer:
    """Token-classification pipeline (e.g. BERT fine-tuned on CoNLL-03)."""

    def __init__(self, model: str = NER_MODEL):
        from transformers import pipeline
        self.name = model
        self._pipe = pipeline("token-classification", model=model, aggregation_strategy="simple")

    def entities(self, text: str) -> list[Entity]:
        out: list[Entity] = []
        # BERT has a 512-token window: feed it in overlapping character windows.
        step, size = 1200, 1500
        seen: set[tuple[int, int]] = set()
        for off in range(0, max(len(text), 1), step):
            chunk = text[off:off + size]
            if not chunk.strip():
                continue
            for e in self._pipe(chunk):
                s, t = off + int(e["start"]), off + int(e["end"])
                if (s, t) in seen:
                    continue
                seen.add((s, t))
                out.append(Entity(str(e["entity_group"]).upper(), text[s:t], s, t, float(e["score"])))
            if off + size >= len(text):
                break
        return sorted(out, key=lambda e: e.start)


class HfEncoder:
    """Sentence encoder (BERT-family) via sentence-transformers; L2-normalised vectors."""

    def __init__(self, model: str = ENCODER_MODEL):
        from sentence_transformers import SentenceTransformer
        self.name = model
        self._m = SentenceTransformer(model)

    def encode(self, texts: list[str]) -> list[list[float]]:
        return self._m.encode(texts, normalize_embeddings=True, show_progress_bar=False).tolist()


@lru_cache(maxsize=2)
def get_ner(model: str = NER_MODEL) -> HfNer:
    return HfNer(model)


@lru_cache(maxsize=2)
def get_encoder(model: str = ENCODER_MODEL) -> HfEncoder:
    return HfEncoder(model)

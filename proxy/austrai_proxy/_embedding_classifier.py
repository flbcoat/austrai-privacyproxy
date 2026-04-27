"""Stage 2 intent classifier via sentence-transformers.

Loaded lazily only when the [routing] optional dependency is installed.
Install: pip install austrai[routing]

Privacy: operates ONLY on already-anonymized text passed by router.py.
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("austrai.router.embeddings")

_MODEL = None
_ANCHOR_EMBS: dict = {}
_ANCHORS_SIGNATURE: Optional[int] = None


def _model_name() -> str:
    # Multilingual, compact (~500 MB). Works well for DE + EN; we keep it
    # hardcoded for now — power users who want a different model can
    # override via env var AUSTRAI_ROUTING_MODEL (documented in README).
    import os
    return os.environ.get(
        "AUSTRAI_ROUTING_MODEL",
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    )


def _ensure_loaded(anchors: dict[str, list[str]]) -> None:
    """Load model + precompute anchor embeddings lazily.

    Re-precompute if anchors dict differs from last call (power-user edit).
    """
    global _MODEL, _ANCHOR_EMBS, _ANCHORS_SIGNATURE
    sig = hash(tuple(sorted((k, tuple(v)) for k, v in anchors.items())))

    if _MODEL is None:
        from sentence_transformers import SentenceTransformer

        logger.info("Loading sentence-transformers model for Auto-Router…")
        _MODEL = SentenceTransformer(_model_name())

    if sig != _ANCHORS_SIGNATURE:
        _ANCHOR_EMBS = {
            label: _MODEL.encode(prompts, convert_to_tensor=True)
            for label, prompts in anchors.items()
            if prompts
        }
        _ANCHORS_SIGNATURE = sig


def classify_via_embeddings(
    anonymized_text: str, anchors: dict[str, list[str]]
) -> Optional[str]:
    """Return the task label whose anchor prompts have highest mean cosine
    similarity to the input.

    Returns None on any failure; caller cascades to keyword rules.
    """
    from sentence_transformers import util

    if not anonymized_text.strip() or not anchors:
        return None

    _ensure_loaded(anchors)
    if _MODEL is None or not _ANCHOR_EMBS:
        return None

    text_emb = _MODEL.encode(anonymized_text, convert_to_tensor=True)
    scores = {
        label: float(util.cos_sim(text_emb, embs).mean())
        for label, embs in _ANCHOR_EMBS.items()
    }
    if not scores:
        return None
    return max(scores, key=scores.get)

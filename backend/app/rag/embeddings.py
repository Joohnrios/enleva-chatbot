"""Embeddings locais compartilhados (Chroma EF / pgvector)."""

from __future__ import annotations

from functools import lru_cache

import numpy as np


@lru_cache
def get_embedding_model(model_name: str):
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name)


def embed_texts(texts: list[str], *, model_name: str) -> list[list[float]]:
    if not texts:
        return []
    model = get_embedding_model(model_name)
    vectors = model.encode(
        texts,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    arr = np.asarray(vectors, dtype=np.float32)
    if arr.ndim == 1:
        return [arr.tolist()]
    return [row.tolist() for row in arr]


def embed_query(text: str, *, model_name: str) -> list[float]:
    return embed_texts([text], model_name=model_name)[0]

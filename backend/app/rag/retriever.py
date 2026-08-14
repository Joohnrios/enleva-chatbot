"""Retrieval com threshold de score."""

from __future__ import annotations

from backend.app.config import Settings, get_settings
from backend.app.rag.store import KnowledgeStore, RetrievedChunk, get_store


def retrieve(
    query: str,
    *,
    settings: Settings | None = None,
    store: KnowledgeStore | None = None,
) -> list[RetrievedChunk]:
    settings = settings or get_settings()
    store = store or get_store()
    chunks = store.query(query, top_k=settings.retrieval_top_k)
    return [c for c in chunks if c.score >= settings.retrieval_min_score]

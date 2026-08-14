"""Factory do vector store — Chroma (rollback) ou pgvector (padrão no Compose)."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from backend.app.config import Settings, get_settings
from backend.app.rag.chroma_store import ChromaKnowledgeStore
from backend.app.rag.pgvector_store import PgvectorKnowledgeStore
from backend.app.rag.types import RetrievedChunk

__all__ = [
    "RetrievedChunk",
    "ChromaKnowledgeStore",
    "PgvectorKnowledgeStore",
    "KnowledgeStore",
    "create_store",
    "get_store",
    "reset_store_cache",
]

# Alias para testes unitários locais sem Postgres
KnowledgeStore = ChromaKnowledgeStore


def create_store(settings: Settings | None = None) -> Any:
    settings = settings or get_settings()
    backend = (settings.vector_store or "chroma").strip().lower()
    if backend == "pgvector":
        return PgvectorKnowledgeStore(settings)
    return ChromaKnowledgeStore(settings)


@lru_cache
def get_store() -> Any:
    return create_store(get_settings())


def reset_store_cache() -> None:
    get_store.cache_clear()

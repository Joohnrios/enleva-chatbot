"""Vector store Chroma (fallback / testes / rollback)."""

from __future__ import annotations

import logging
from typing import Any

import chromadb
from chromadb.api.models.Collection import Collection
from chromadb.utils import embedding_functions

from backend.app.config import Settings, get_settings
from backend.app.rag.types import RetrievedChunk

logger = logging.getLogger(__name__)

COLLECTION_NAME = "enleva_knowledge"
ANCHORS_COLLECTION = "enleva_scope_anchors"


class ChromaKnowledgeStore:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.settings.chroma_path.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(self.settings.chroma_path))
        self._ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=self.settings.embedding_model
        )
        self._collection = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=self._ef,
            metadata={"hnsw:space": "cosine"},
        )
        self._anchors = self._client.get_or_create_collection(
            name=ANCHORS_COLLECTION,
            embedding_function=self._ef,
            metadata={"hnsw:space": "cosine"},
        )

    @property
    def collection(self) -> Collection:
        return self._collection

    def count(self) -> int:
        return self._collection.count()

    def anchors_count(self) -> int:
        return self._anchors.count()

    def reset(self) -> None:
        for name in (COLLECTION_NAME, ANCHORS_COLLECTION):
            try:
                self._client.delete_collection(name)
            except Exception:
                logger.debug("Coleção inexistente ao resetar: %s", name, exc_info=True)
        self._collection = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=self._ef,
            metadata={"hnsw:space": "cosine"},
        )
        self._anchors = self._client.get_or_create_collection(
            name=ANCHORS_COLLECTION,
            embedding_function=self._ef,
            metadata={"hnsw:space": "cosine"},
        )

    def upsert_chunks(
        self,
        *,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        if not ids:
            return
        self._collection.upsert(ids=ids, documents=documents, metadatas=metadatas)

    def upsert_anchors(
        self,
        *,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        if not ids:
            return
        self._anchors.upsert(ids=ids, documents=documents, metadatas=metadatas)

    def source_hashes(self) -> dict[str, str]:
        if self.count() == 0:
            return {}
        result = self._collection.get(include=["metadatas"])
        hashes: dict[str, str] = {}
        for meta in result.get("metadatas") or []:
            if not meta:
                continue
            source = meta.get("source")
            file_hash = meta.get("file_hash")
            if source and file_hash:
                hashes[str(source)] = str(file_hash)
        return hashes

    def content_hashes(self) -> dict[str, str]:
        return self.source_hashes()

    def delete_by_source(self, source: str) -> None:
        if not source:
            return
        try:
            self._collection.delete(where={"source": source})
        except Exception:
            logger.debug("Falha ao apagar chunks de %s", source, exc_info=True)
        try:
            self._anchors.delete(where={"source": source})
        except Exception:
            logger.debug("Falha ao apagar âncoras de %s", source, exc_info=True)

    def max_anchor_similarity(self, text: str) -> float:
        if self.anchors_count() == 0:
            return 0.0
        result = self._anchors.query(
            query_texts=[text],
            n_results=min(3, self.anchors_count()),
            include=["distances"],
        )
        dists = (result.get("distances") or [[]])[0]
        if not dists:
            return 0.0
        return max(0.0, 1.0 - float(min(dists)))

    def nearest_anchor_domain(self, text: str) -> str | None:
        if self.anchors_count() == 0:
            return None
        result = self._anchors.query(
            query_texts=[text],
            n_results=min(3, self.anchors_count()),
            include=["distances", "metadatas"],
        )
        dists = (result.get("distances") or [[]])[0]
        metas = (result.get("metadatas") or [[]])[0]
        if not dists or not metas:
            return None
        best_i = min(range(len(dists)), key=lambda i: float(dists[i]))
        meta = metas[best_i] or {}
        domain = str(meta.get("domain") or "").strip()
        return domain or None

    def query(self, text: str, top_k: int) -> list[RetrievedChunk]:
        if self.count() == 0:
            return []
        result = self._collection.query(
            query_texts=[text],
            n_results=min(top_k, max(self.count(), 1)),
            include=["documents", "metadatas", "distances"],
        )
        docs = (result.get("documents") or [[]])[0]
        metas = (result.get("metadatas") or [[]])[0]
        dists = (result.get("distances") or [[]])[0]
        chunks: list[RetrievedChunk] = []
        for doc, meta, dist in zip(docs, metas, dists):
            score = max(0.0, 1.0 - float(dist))
            meta = meta or {}
            chunks.append(
                RetrievedChunk(
                    text=doc or "",
                    title=str(meta.get("title", "")),
                    source=str(meta.get("source", "")),
                    domain=str(meta.get("domain", "")),
                    classification=str(meta.get("classification", "")),
                    score=score,
                )
            )
        return chunks

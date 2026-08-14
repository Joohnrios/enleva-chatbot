"""Vector store Postgres + pgvector (mesma API pública do ChromaKnowledgeStore)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from backend.app.config import Settings, get_settings
from backend.app.db.engine import build_database_url, get_engine, reset_engine_cache
from backend.app.rag.embeddings import embed_query, embed_texts
from backend.app.rag.types import RetrievedChunk


def _vector_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{float(x):.8f}" for x in vec) + "]"


class PgvectorKnowledgeStore:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._model = self.settings.embedding_model
        reset_engine_cache()
        engine = get_engine()
        if engine is None:
            from sqlalchemy import create_engine

            url = build_database_url(self.settings)
            engine = create_engine(url, pool_pre_ping=True, pool_size=2, max_overflow=2)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        self._engine = engine

    def count(self) -> int:
        with self._engine.connect() as conn:
            return int(conn.execute(text("SELECT COUNT(*) FROM kb_chunk")).scalar_one())

    def anchors_count(self) -> int:
        with self._engine.connect() as conn:
            return int(conn.execute(text("SELECT COUNT(*) FROM kb_anchor")).scalar_one())

    def reset(self) -> None:
        with self._engine.begin() as conn:
            conn.execute(text("TRUNCATE kb_chunk"))
            conn.execute(text("TRUNCATE kb_anchor"))

    def upsert_chunks(
        self,
        *,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        if not ids:
            return
        vectors = embed_texts(documents, model_name=self._model)
        sql = text(
            """
            INSERT INTO kb_chunk
                (id, body, source, title, domain, classification, file_hash, embedding)
            VALUES
                (:id, :body, :source, :title, :domain, :classification, :file_hash,
                 CAST(:embedding AS vector))
            ON CONFLICT (id) DO UPDATE SET
                body = EXCLUDED.body,
                source = EXCLUDED.source,
                title = EXCLUDED.title,
                domain = EXCLUDED.domain,
                classification = EXCLUDED.classification,
                file_hash = EXCLUDED.file_hash,
                embedding = EXCLUDED.embedding
            """
        )
        rows = []
        for i, doc, meta, vec in zip(ids, documents, metadatas, vectors):
            meta = meta or {}
            rows.append(
                {
                    "id": i,
                    "body": doc,
                    "source": str(meta.get("source") or ""),
                    "title": str(meta.get("title") or ""),
                    "domain": str(meta.get("domain") or ""),
                    "classification": str(meta.get("classification") or ""),
                    "file_hash": str(meta.get("file_hash") or ""),
                    "embedding": _vector_literal(vec),
                }
            )
        with self._engine.begin() as conn:
            conn.execute(sql, rows)

    def upsert_anchors(
        self,
        *,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        if not ids:
            return
        vectors = embed_texts(documents, model_name=self._model)
        sql = text(
            """
            INSERT INTO kb_anchor
                (id, body, domain, kind, title, source, embedding)
            VALUES
                (:id, :body, :domain, :kind, :title, :source, CAST(:embedding AS vector))
            ON CONFLICT (id) DO UPDATE SET
                body = EXCLUDED.body,
                domain = EXCLUDED.domain,
                kind = EXCLUDED.kind,
                title = EXCLUDED.title,
                source = EXCLUDED.source,
                embedding = EXCLUDED.embedding
            """
        )
        rows = []
        for i, doc, meta, vec in zip(ids, documents, metadatas, vectors):
            meta = meta or {}
            rows.append(
                {
                    "id": i,
                    "body": doc,
                    "domain": str(meta.get("domain") or ""),
                    "kind": str(meta.get("kind") or ""),
                    "title": str(meta.get("title") or ""),
                    "source": str(meta.get("source") or ""),
                    "embedding": _vector_literal(vec),
                }
            )
        with self._engine.begin() as conn:
            conn.execute(sql, rows)

    def source_hashes(self) -> dict[str, str]:
        with self._engine.connect() as conn:
            result = conn.execute(
                text(
                    """
                    SELECT DISTINCT ON (source) source, file_hash
                    FROM kb_chunk
                    WHERE source <> '' AND file_hash <> ''
                    ORDER BY source, file_hash
                    """
                )
            )
            return {str(row.source): str(row.file_hash) for row in result}

    def content_hashes(self) -> dict[str, str]:
        return self.source_hashes()

    def delete_by_source(self, source: str) -> None:
        if not source:
            return
        with self._engine.begin() as conn:
            conn.execute(
                text("DELETE FROM kb_chunk WHERE source = :source"),
                {"source": source},
            )
            conn.execute(
                text("DELETE FROM kb_anchor WHERE source = :source"),
                {"source": source},
            )

    def max_anchor_similarity(self, text: str) -> float:
        if self.anchors_count() == 0:
            return 0.0
        vec = _vector_literal(embed_query(text, model_name=self._model))
        with self._engine.connect() as conn:
            dist = conn.execute(
                text(
                    """
                    SELECT embedding <=> CAST(:embedding AS vector) AS dist
                    FROM kb_anchor
                    ORDER BY embedding <=> CAST(:embedding AS vector)
                    LIMIT 1
                    """
                ),
                {"embedding": vec},
            ).scalar()
        if dist is None:
            return 0.0
        return max(0.0, 1.0 - float(dist))

    def nearest_anchor_domain(self, text: str) -> str | None:
        if self.anchors_count() == 0:
            return None
        vec = _vector_literal(embed_query(text, model_name=self._model))
        with self._engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT domain
                    FROM kb_anchor
                    ORDER BY embedding <=> CAST(:embedding AS vector)
                    LIMIT 1
                    """
                ),
                {"embedding": vec},
            ).first()
        if not row:
            return None
        domain = str(row.domain or "").strip()
        return domain or None

    def query(self, query_text: str, top_k: int) -> list[RetrievedChunk]:
        if self.count() == 0:
            return []
        vec = _vector_literal(embed_query(query_text, model_name=self._model))
        n = max(1, min(top_k, self.count()))
        with self._engine.connect() as conn:
            rows = (
                conn.execute(
                    text(
                        """
                        SELECT body, title, source, domain, classification,
                               embedding <=> CAST(:embedding AS vector) AS dist
                        FROM kb_chunk
                        ORDER BY embedding <=> CAST(:embedding AS vector)
                        LIMIT :lim
                        """
                    ),
                    {"embedding": vec, "lim": n},
                )
                .mappings()
                .all()
            )
        chunks: list[RetrievedChunk] = []
        for row in rows:
            score = max(0.0, 1.0 - float(row["dist"]))
            chunks.append(
                RetrievedChunk(
                    text=row["body"] or "",
                    title=str(row["title"] or ""),
                    source=str(row["source"] or ""),
                    domain=str(row["domain"] or ""),
                    classification=str(row["classification"] or ""),
                    score=score,
                )
            )
        return chunks

"""Testes unitários do PgvectorKnowledgeStore (SQL mockado)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from backend.app.config import Settings
from backend.app.rag.pgvector_store import PgvectorKnowledgeStore, _vector_literal
from backend.app.rag.store import create_store


def test_vector_literal_format():
    assert _vector_literal([0.1, -0.2]) == "[0.10000000,-0.20000000]"


def test_create_store_selects_backend(tmp_path):
    chroma = Settings(
        VECTOR_STORE="chroma",
        CHROMA_DIR=str(tmp_path / "c"),
        KNOWLEDGE_DIR=str(tmp_path / "k"),
        LOG_DIR=str(tmp_path / "l"),
        KB_SQL_ENABLED=False,
    )
    store = create_store(chroma)
    from backend.app.rag.chroma_store import ChromaKnowledgeStore

    assert isinstance(store, ChromaKnowledgeStore)


def test_pgvector_query_maps_rows():
    settings = Settings(
        VECTOR_STORE="pgvector",
        CHROMA_DIR="./data/chroma",
        KNOWLEDGE_DIR="./knowledge",
        LOG_DIR="./data/logs",
        KB_SQL_ENABLED=False,
        EMBEDDING_MODEL="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    )
    engine = MagicMock()
    conn = MagicMock()
    engine.connect.return_value.__enter__.return_value = conn
    engine.begin.return_value.__enter__.return_value = conn

    count_result = MagicMock()
    count_result.scalar_one.return_value = 1

    query_rows = MagicMock()
    query_rows.mappings.return_value.all.return_value = [
        {
            "body": "VPN",
            "title": "Acesso",
            "source": "faq-ti.md",
            "domain": "TI",
            "classification": "Interno",
            "dist": 0.2,
        }
    ]

    def execute_side_effect(stmt, params=None):
        sql = str(stmt)
        if "COUNT(*)" in sql:
            return count_result
        return query_rows

    conn.execute.side_effect = execute_side_effect

    with (
        patch("backend.app.rag.pgvector_store.get_engine", return_value=engine),
        patch(
            "backend.app.rag.pgvector_store.embed_query",
            return_value=[0.0] * 8,
        ),
    ):
        store = PgvectorKnowledgeStore(settings)
        store._engine = engine
        chunks = store.query("vpn", top_k=3)
        assert len(chunks) == 1
        assert chunks[0].domain == "TI"
        assert abs(chunks[0].score - 0.8) < 1e-6

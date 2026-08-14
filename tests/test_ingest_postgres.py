"""Ingest a partir de DocumentInfo (Postgres) com store Chroma."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from backend.app.config import Settings
from backend.app.db.repository import DocumentInfo
from backend.app.rag.ingest import document_source_key, ingest_knowledge
from backend.app.rag.store import KnowledgeStore


@pytest.fixture()
def pg_settings(tmp_path: Path) -> Settings:
    return Settings(
        BOT_NAME="AssistenteTeste",
        KNOWLEDGE_DIR=str(tmp_path / "knowledge"),
        CHROMA_DIR=str(tmp_path / "chroma"),
        LOG_DIR=str(tmp_path / "logs"),
        KNOWLEDGE_WATCH_ENABLED=False,
        INGEST_SOURCE="postgres",
        KB_SQL_ENABLED=True,
        LLM_PROVIDER="anthropic",
        ANTHROPIC_API_KEY="",
    )


def _doc(slug: str, body: str, content_hash: str) -> DocumentInfo:
    return DocumentInfo(
        id="00000000-0000-0000-0000-000000000001",
        slug=slug,
        title=f"Title {slug}",
        domain_slug="ti",
        domain_name="TI",
        classification="Interno",
        sensitive=False,
        owner="TI",
        body=body,
        content_hash=content_hash,
        version=1,
    )


def test_postgres_full_and_incremental(pg_settings: Settings) -> None:
    docs = [_doc("faq-vpn", "Texto sobre VPN corporativa.", "hash111111111111")]
    store = KnowledgeStore(pg_settings)

    with (
        patch("backend.app.rag.ingest.list_indexable_documents", return_value=docs),
        patch("backend.app.rag.ingest.list_active_domains", return_value=[]),
    ):
        first = ingest_knowledge(settings=pg_settings, store=store, full=True)
        assert first.source_mode == "postgres"
        assert first.indexed_files == 1
        assert store.count() > 0
        assert document_source_key("faq-vpn") in store.source_hashes()

        second = ingest_knowledge(settings=pg_settings, store=store, full=False)
        assert second.indexed_files == 0
        assert second.unchanged_files == 1


def test_postgres_updates_on_hash_change(pg_settings: Settings) -> None:
    store = KnowledgeStore(pg_settings)
    docs_v1 = [_doc("faq-vpn", "Versão 1 VPN.", "hashaaaaaaaaaaaa")]
    docs_v2 = [_doc("faq-vpn", "Versão 2 VPN com detalhe.", "hashbbbbbbbbbbbb")]

    with (
        patch("backend.app.rag.ingest.list_indexable_documents", return_value=docs_v1),
        patch("backend.app.rag.ingest.list_active_domains", return_value=[]),
    ):
        ingest_knowledge(settings=pg_settings, store=store, full=True)

    with (
        patch("backend.app.rag.ingest.list_indexable_documents", return_value=docs_v2),
        patch("backend.app.rag.ingest.list_active_domains", return_value=[]),
    ):
        updated = ingest_knowledge(settings=pg_settings, store=store, full=False)
        assert updated.indexed_files == 1
        assert store.source_hashes()[document_source_key("faq-vpn")] == "hashbbbbbbbbbbbb"


def test_postgres_fallback_to_files_when_empty(pg_settings: Settings, tmp_path: Path) -> None:
    knowledge = pg_settings.knowledge_path
    knowledge.mkdir(parents=True, exist_ok=True)
    (knowledge / "faq-local.md").write_text(
        "---\ntitle: Local\nclassification: Interno\ndomain: TI\n"
        "owner: t\nsensitive: false\n---\n\nConteúdo local VPN.\n",
        encoding="utf-8",
    )
    store = KnowledgeStore(pg_settings)
    with (
        patch("backend.app.rag.ingest.list_indexable_documents", return_value=[]),
        patch("backend.app.rag.ingest.list_active_domains", return_value=[]),
    ):
        result = ingest_knowledge(settings=pg_settings, store=store, full=True)
        assert result.source_mode == "files"
        assert result.indexed_files == 1

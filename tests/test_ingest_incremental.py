"""Testes de ingestão incremental por file_hash."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.config import Settings
from backend.app.rag.ingest import ingest_knowledge
from backend.app.rag.store import KnowledgeStore


@pytest.fixture()
def kb_settings(tmp_path: Path) -> Settings:
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    chroma = tmp_path / "chroma"
    logs = tmp_path / "logs"
    return Settings(
        BOT_NAME="AssistenteTeste",
        KNOWLEDGE_DIR=str(knowledge),
        CHROMA_DIR=str(chroma),
        LOG_DIR=str(logs),
        KNOWLEDGE_WATCH_ENABLED=False,
        INGEST_SOURCE="files",
        KB_SQL_ENABLED=False,
        LLM_PROVIDER="anthropic",
        ANTHROPIC_API_KEY="",
    )


def _write_md(path: Path, title: str, body: str) -> None:
    path.write_text(
        f"---\ntitle: {title}\nclassification: Interno\ndomain: TI\n"
        f"owner: teste\nsensitive: false\n---\n\n{body}\n",
        encoding="utf-8",
    )


def test_incremental_skips_unchanged(kb_settings: Settings) -> None:
    knowledge = kb_settings.knowledge_path
    _write_md(knowledge / "faq-a.md", "FAQ A", "Conteúdo sobre VPN e senha.")
    store = KnowledgeStore(kb_settings)

    first = ingest_knowledge(settings=kb_settings, store=store, full=True)
    assert first.indexed_files == 1
    assert first.indexed_chunks > 0
    count_after_first = store.count()

    second = ingest_knowledge(settings=kb_settings, store=store, full=False)
    assert second.indexed_files == 0
    assert second.unchanged_files == 1
    assert second.indexed_chunks == 0
    assert store.count() == count_after_first


def test_incremental_updates_changed_file(kb_settings: Settings) -> None:
    knowledge = kb_settings.knowledge_path
    path = knowledge / "faq-b.md"
    _write_md(path, "FAQ B", "Texto original do procedimento.")
    store = KnowledgeStore(kb_settings)
    ingest_knowledge(settings=kb_settings, store=store, full=True)

    _write_md(path, "FAQ B", "Texto alterado do procedimento com detalhe novo.")
    updated = ingest_knowledge(settings=kb_settings, store=store, full=False)
    assert updated.indexed_files == 1
    assert updated.unchanged_files == 0
    hashes = store.source_hashes()
    assert "faq-b.md" in hashes


def test_incremental_removes_deleted_file(kb_settings: Settings) -> None:
    knowledge = kb_settings.knowledge_path
    keep = knowledge / "keep.md"
    gone = knowledge / "gone.md"
    _write_md(keep, "Keep", "Documento que permanece.")
    _write_md(gone, "Gone", "Documento que será apagado.")
    store = KnowledgeStore(kb_settings)
    ingest_knowledge(settings=kb_settings, store=store, full=True)
    assert "gone.md" in store.source_hashes()

    gone.unlink()
    result = ingest_knowledge(settings=kb_settings, store=store, full=False)
    assert result.removed_files == 1
    assert result.unchanged_files == 1
    assert "gone.md" not in store.source_hashes()
    assert "keep.md" in store.source_hashes()

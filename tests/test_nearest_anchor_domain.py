"""Testes de nearest_anchor_domain no KnowledgeStore (mock da collection)."""

from __future__ import annotations

from unittest.mock import MagicMock

from backend.app.rag.chroma_store import ChromaKnowledgeStore


def test_nearest_anchor_domain_returns_best_meta():
    store = ChromaKnowledgeStore.__new__(ChromaKnowledgeStore)
    anchors = MagicMock()
    anchors.count.return_value = 2
    anchors.query.return_value = {
        "distances": [[0.4, 0.1]],
        "metadatas": [[{"domain": "RH"}, {"domain": "TI"}]],
    }
    store._anchors = anchors  # noqa: SLF001

    assert store.nearest_anchor_domain("vpn senha") == "TI"


def test_nearest_anchor_domain_empty():
    store = ChromaKnowledgeStore.__new__(ChromaKnowledgeStore)
    anchors = MagicMock()
    anchors.count.return_value = 0
    store._anchors = anchors  # noqa: SLF001
    assert store.nearest_anchor_domain("qualquer") is None

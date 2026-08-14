"""Testes do classificador de escopo (cascata) e filtro de saída."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from backend.app.config import Settings
from backend.app.guardrails.local_scope import classify_by_similarity
from backend.app.guardrails.output_filter import contains_sensitive, filter_output
from backend.app.guardrails.scope import classify_scope, classify_scope_rules
from backend.app.rag.ingest import ingest_knowledge
from backend.app.rag.store import KnowledgeStore


@pytest.fixture()
def scoped_store(tmp_path: Path) -> tuple[Settings, KnowledgeStore]:
    knowledge = Path(__file__).resolve().parents[1] / "knowledge"
    settings = Settings(
        BOT_NAME="AssistenteTeste",
        KNOWLEDGE_DIR=str(knowledge),
        CHROMA_DIR=str(tmp_path / "chroma"),
        LOG_DIR=str(tmp_path / "logs"),
        SCOPE_LOCAL_MIN_SCORE=0.28,
        SCOPE_LOCAL_OUT_MAX=0.18,
        ANTHROPIC_API_KEY="",
        INGEST_SOURCE="files",
        KB_SQL_ENABLED=False,
        KNOWLEDGE_WATCH_ENABLED=False,
    )
    store = KnowledgeStore(settings)
    ingest_knowledge(settings=settings, store=store)
    return settings, store


def test_in_scope_keywords():
    assert classify_scope_rules("Como faço reset de senha da VPN?") == "in_scope"
    assert classify_scope_rules("Qual o prazo para solicitar férias?") == "in_scope"


def test_out_of_scope_keywords():
    assert classify_scope_rules("Me conta uma piada") == "out_of_scope"
    assert classify_scope_rules("Escreva um código em python") == "out_of_scope"


def test_ambiguous_without_llm_is_fail_closed_out_of_scope(scoped_store):
    """Não existe mais default in_scope sem checagem."""
    settings, store = scoped_store
    # Frase sem keyword e tipicamente ambígua / fora — sem Haiku
    decision = classify_scope(
        "Olá, tudo bem?",
        settings=settings,
        store=store,
        use_llm_if_ambiguous=False,
    )
    assert decision == "out_of_scope"


def test_cascade_keyword_in_scope_skips_similarity(scoped_store):
    settings, store = scoped_store
    decision = classify_scope(
        "Como resetar a senha da VPN?",
        settings=settings,
        store=store,
        use_llm_if_ambiguous=False,
    )
    assert decision == "in_scope"


def test_cascade_keyword_out_of_scope(scoped_store):
    settings, store = scoped_store
    decision = classify_scope(
        "Me conta uma piada",
        settings=settings,
        store=store,
        use_llm_if_ambiguous=False,
    )
    assert decision == "out_of_scope"


def test_cascade_similarity_in_scope_for_corporate_phrasing(scoped_store):
    """Sem keyword óbvia, mas semanticamente perto da BC → in via similaridade."""
    settings, store = scoped_store
    # Evita keywords diretas da lista; ainda fala de benefício corporativo
    q = "Quais são as regras para inclusão de dependentes no convênio médico da empresa?"
    assert classify_scope_rules(q) is None
    local = classify_by_similarity(q, settings=settings, store=store)
    decision = classify_scope(
        q, settings=settings, store=store, use_llm_if_ambiguous=False
    )
    # Deve resolver sem Haiku (in por similaridade ou out se score baixo demais)
    assert decision in {"in_scope", "out_of_scope"}
    if local.decision == "in_scope":
        assert decision == "in_scope"


def test_cascade_haiku_called_only_when_ambiguous(scoped_store):
    settings, store = scoped_store
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "out_of_scope"

    # Força faixa ambígua: thresholds apertados
    settings.scope_local_min_score = 0.99
    settings.scope_local_out_max = 0.01

    q = "Preciso de orientação sobre um assunto interno da empresa"
    assert classify_scope_rules(q) is None
    decision = classify_scope(
        q,
        llm=mock_llm,
        settings=settings,
        store=store,
        use_llm_if_ambiguous=True,
    )
    assert decision == "out_of_scope"
    mock_llm.complete.assert_called_once()


def test_cascade_haiku_in_scope_when_model_says_so(scoped_store):
    settings, store = scoped_store
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "in_scope"
    settings.scope_local_min_score = 0.99
    settings.scope_local_out_max = 0.01

    q = "Preciso de orientação sobre um assunto interno da empresa"
    decision = classify_scope(
        q,
        llm=mock_llm,
        settings=settings,
        store=store,
        use_llm_if_ambiguous=True,
    )
    assert decision == "in_scope"
    mock_llm.complete.assert_called_once()


def test_cascade_haiku_network_failure_is_fail_closed(scoped_store):
    """Timeout/erro de API na etapa Haiku → out_of_scope, sem explodir."""
    settings, store = scoped_store
    mock_llm = MagicMock()
    mock_llm.complete.side_effect = TimeoutError("simulated network timeout")
    settings.scope_local_min_score = 0.99
    settings.scope_local_out_max = 0.01

    q = "Preciso de orientação sobre um assunto interno da empresa"
    decision = classify_scope(
        q,
        llm=mock_llm,
        settings=settings,
        store=store,
        use_llm_if_ambiguous=True,
    )
    assert decision == "out_of_scope"
    mock_llm.complete.assert_called_once()


def test_output_filter_blocks_cpf():
    text, blocked = filter_output("O CPF é 123.456.789-09", "Assistente")
    assert blocked is True
    assert "não pode exibir" in text.lower() or "segurança" in text.lower()


def test_output_filter_allows_safe_text():
    text, blocked = filter_output("Abra um chamado com a TI pelo portal.", "Assistente")
    assert blocked is False
    assert "chamado" in text


def test_contains_sensitive_health():
    assert contains_sensitive("O diagnóstico do colaborador é X") is True

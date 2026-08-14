"""Testes de ingestão, frontmatter e golden set de recusas."""

from pathlib import Path

import pytest

from backend.app.config import Settings
from backend.app.guardrails.prompts import refusal_out_of_scope
from backend.app.guardrails.scope import classify_scope
from backend.app.rag.ingest import ingest_knowledge, is_indexable, parse_markdown_file
from backend.app.rag.orchestrator import answer_question
from backend.app.rag.store import KnowledgeStore


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture()
def demo_settings(tmp_path: Path) -> Settings:
    knowledge = Path(__file__).resolve().parents[1] / "knowledge"
    chroma = tmp_path / "chroma"
    logs = tmp_path / "logs"
    return Settings(
        BOT_NAME="AssistenteTeste",
        KNOWLEDGE_DIR=str(knowledge),
        CHROMA_DIR=str(chroma),
        LOG_DIR=str(logs),
        RETRIEVAL_MIN_SCORE=0.2,
        LLM_PROVIDER="anthropic",
        ANTHROPIC_API_KEY="",
        INGEST_SOURCE="files",
        KB_SQL_ENABLED=False,
        KNOWLEDGE_WATCH_ENABLED=False,
    )


def test_parse_and_gate_classification():
    path = Path(__file__).resolve().parents[1] / "knowledge" / "faq-ti-acesso.md"
    parsed = parse_markdown_file(path)
    assert parsed is not None
    meta, body = parsed
    assert is_indexable(meta) is True
    assert "senha" in body.lower()


def test_confidential_not_indexable():
    path = Path(__file__).resolve().parents[1] / "knowledge" / "SKIP-confidencial-exemplo.md"
    parsed = parse_markdown_file(path)
    assert parsed is not None
    meta, _ = parsed
    assert is_indexable(meta) is False


def test_ingest_skips_confidential(demo_settings: Settings, tmp_path: Path):
    store = KnowledgeStore(demo_settings)
    result = ingest_knowledge(settings=demo_settings, store=store)
    assert result.indexed_files >= 3
    assert result.indexed_chunks > 0
    assert any("SKIP-confidencial" in s or "Confidencial" in s for s in result.skipped_files)


def test_golden_out_of_scope_refusals():
    questions = [
        "Me conta uma piada",
        "Escreva um código em python para ordenar lista",
        "Qual a previsão do tempo amanhã?",
        "Qual a capital da França?",
        "Recomenda um filme de ação",
    ]
    for q in questions:
        assert classify_scope(q) == "out_of_scope"


def test_golden_in_scope_signals():
    questions = [
        "Como resetar a senha da VPN?",
        "Qual o prazo para pedir férias?",
        "Como solicitar notebook?",
        "Esqueci de bater o ponto, o que faço?",
        "Como abrir chamado de impressora?",
        "Qual o prazo de adesão ao plano de saúde?",
        "Como funciona o primeiro acesso à intranet?",
        "Onde solicito ajuste de ponto?",
    ]
    for q in questions:
        assert classify_scope(q) == "in_scope"


def test_out_of_scope_chat_refuses_without_llm(demo_settings: Settings):
    result = answer_question(
        "Me conta uma piada",
        settings=demo_settings,
        llm=None,
        use_llm_if_ambiguous=False,
    )
    assert result.refused is True
    assert result.refusal_reason == "out_of_scope"
    assert "escopo" in result.reply.lower() or "base de conhecimento" in result.reply.lower()
    assert result.bot_name == "AssistenteTeste"


def test_no_context_or_retrieval_path(demo_settings: Settings, tmp_path: Path):
    """Pergunta corporativa sem docs relevantes deve recusar por falta de contexto."""
    store = KnowledgeStore(demo_settings)
    ingest_knowledge(settings=demo_settings, store=store)

    class FakeLLM:
        name = "fake"

        def complete(self, *, system, messages, temperature=0.2):
            raise AssertionError("LLM não deveria ser chamado sem contexto útil")

    demo_settings.retrieval_min_score = 0.99
    result = answer_question(
        "Qual a política secreta de bônus executivo XYZ inexistente?",
        settings=demo_settings,
        llm=FakeLLM(),
        use_llm_if_ambiguous=False,
    )
    assert result.refused is True
    assert result.refusal_reason == "no_context"
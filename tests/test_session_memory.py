"""Testes de memória de sessão multi-turno."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.routes_chat import router as chat_router
from backend.app.config import get_settings
from backend.app.guardrails.scope import (
    build_scope_text,
    classify_scope,
    classify_scope_rules,
)
from backend.app.rag.orchestrator import ChatResult, answer_question
from backend.app.rag.session_memory import SessionMemory, session_memory
from backend.app.security.rate_limit import chat_limiter


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "")
    monkeypatch.setenv("WIDGET_API_TOKEN", "test-widget-token")
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://127.0.0.1:8000")
    monkeypatch.setattr(
        "backend.app.security.rate_limit.get_redis", lambda: None
    )
    monkeypatch.setattr(
        "backend.app.rag.session_memory.get_redis", lambda: None
    )
    from backend.app.redis_client import reset_redis_cache

    reset_redis_cache()
    session_memory.reset()
    chat_limiter.reset()
    get_settings.cache_clear()
    yield
    session_memory.reset()
    chat_limiter.reset()
    get_settings.cache_clear()
    reset_redis_cache()


CHAT_HEADERS = {
    "X-Widget-Token": "test-widget-token",
    "Origin": "http://127.0.0.1:8000",
}


def test_session_memory_ttl_lazy_expiry():
    mem = SessionMemory()
    mem.append_exchange(
        "s1",
        user_message="oi",
        assistant_message="olá",
        ttl_minutes=60,
        max_turns=6,
    )
    mem._sessions["s1"].last_access = time.monotonic() - 3700
    assert mem.get_history("s1", ttl_minutes=60, max_turns=6) == []
    assert "s1" not in mem._sessions


def test_session_memory_truncates_to_max_turns():
    mem = SessionMemory()
    for i in range(10):
        mem.append_exchange(
            "s1",
            user_message=f"u{i}",
            assistant_message=f"a{i}",
            ttl_minutes=60,
            max_turns=2,
        )
    hist = mem.get_history("s1", ttl_minutes=60, max_turns=2)
    assert len(hist) == 4
    assert hist[0]["content"] == "u8"
    assert hist[-1]["content"] == "a9"


def test_chat_generates_session_id_when_missing():
    app = FastAPI()
    app.include_router(chat_router)
    client = TestClient(app)

    with patch("backend.app.api.routes_chat.answer_question") as mock_answer:
        mock_answer.return_value = ChatResult(
            reply="ok",
            sources=[],
            refused=False,
            bot_name="Assistente",
            session_id="generated-by-orch",
        )
        r = client.post(
            "/chat",
            json={"message": "Me conta uma piada"},
            headers=CHAT_HEADERS,
        )
        assert r.status_code == 200
        assert mock_answer.call_args.kwargs["session_id"]
        assert r.json()["session_id"]


def test_followup_scope_uses_history_not_isolated_text():
    """Follow-up isolado seria ambíguo; com histórico de VPN fica in_scope via keyword."""
    history = [
        {"role": "user", "content": "Como resetar a senha da VPN?"},
        {"role": "assistant", "content": "Abra um chamado na categoria Acesso/Senha."},
    ]
    followup = "e quanto tempo demora?"

    assert classify_scope_rules(followup) is None

    scope_text = build_scope_text(followup, history)
    assert "VPN" in scope_text or "senha" in scope_text.lower()

    decision = classify_scope(
        followup,
        history=history,
        use_llm_if_ambiguous=False,
    )
    assert decision == "in_scope"


def test_current_out_of_scope_not_rescued_by_history():
    """Mesmo após VPN, 'me conta uma piada' continua fora (mensagem atual manda)."""
    history = [
        {"role": "user", "content": "Como resetar a senha da VPN?"},
        {"role": "assistant", "content": "Abra um chamado."},
    ]
    decision = classify_scope(
        "Me conta uma piada",
        history=history,
        use_llm_if_ambiguous=False,
    )
    assert decision == "out_of_scope"


def test_followup_sends_prior_history_and_passes_real_scope():
    """Follow-up passa pela cascata real (sem mock de escopo) e histórico vai ao LLM."""
    captured: list[list[dict]] = []

    class CapturingLLM:
        name = "fake"

        def complete(self, *, system, messages, temperature=0.2):
            captured.append(list(messages))
            return "O prazo é de até 4 horas úteis."

    with patch("backend.app.rag.orchestrator.retrieve") as mock_retrieve:
        from backend.app.rag.store import RetrievedChunk

        mock_retrieve.return_value = [
            RetrievedChunk(
                text="O Service Desk responde reset de senha em até 4 horas úteis.",
                title="Acesso",
                source="faq-ti-acesso.md",
                domain="TI",
                classification="Interno",
                score=0.9,
            )
        ]
        sid = "sess-followup"
        r1 = answer_question(
            "Como resetar a senha da VPN?",
            session_id=sid,
            llm=CapturingLLM(),
            use_llm_if_ambiguous=False,
        )
        assert r1.refused is False

        r2 = answer_question(
            "e quanto tempo demora?",
            session_id=sid,
            llm=CapturingLLM(),
            use_llm_if_ambiguous=False,
        )
        assert r2.refused is False, (
            "Follow-up não deve ser recusado por escopo quando há histórico de VPN"
        )
        assert len(captured) == 2
        assert any(
            "senha" in m["content"].lower() or "VPN" in m["content"] for m in captured[1]
        )
        assert "quanto tempo" in captured[1][-1]["content"].lower()
        second_query = mock_retrieve.call_args_list[1].args[0]
        assert "VPN" in second_query or "senha" in second_query.lower()

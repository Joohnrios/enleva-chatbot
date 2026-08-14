"""Guards provisórios do /chat: token + Origin/Referer (401 antes do RAG/LLM)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.routes_chat import router as chat_router
from backend.app.config import get_settings
from backend.app.security.rate_limit import chat_limiter


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("WIDGET_API_TOKEN", "segredo-teste")
    monkeypatch.setenv(
        "ALLOWED_ORIGINS",
        "http://127.0.0.1:8000,https://intranet.enlevasaude.com",
    )
    monkeypatch.setenv("RATE_LIMIT_CHAT", "100/minute")
    monkeypatch.setenv("RATE_LIMIT_CHAT_SESSION", "100/minute")
    chat_limiter.reset()
    get_settings.cache_clear()
    yield
    chat_limiter.reset()
    get_settings.cache_clear()


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(chat_router)
    return TestClient(app)


def _mock_answer():
    from backend.app.rag.orchestrator import ChatResult

    return patch(
        "backend.app.api.routes_chat.answer_question",
        return_value=ChatResult(
            reply="ok",
            sources=[],
            refused=False,
            bot_name="Assistente",
            session_id="s",
        ),
    )


def test_chat_401_without_token(client: TestClient):
    with _mock_answer() as mock_answer:
        r = client.post(
            "/chat",
            json={"message": "oi"},
            headers={"Origin": "http://127.0.0.1:8000"},
        )
        assert r.status_code == 401
        assert mock_answer.call_count == 0


def test_chat_401_wrong_token(client: TestClient):
    with _mock_answer() as mock_answer:
        r = client.post(
            "/chat",
            json={"message": "oi"},
            headers={
                "X-Widget-Token": "errado",
                "Origin": "http://127.0.0.1:8000",
            },
        )
        assert r.status_code == 401
        assert mock_answer.call_count == 0


def test_chat_401_without_origin_or_referer(client: TestClient):
    with _mock_answer() as mock_answer:
        r = client.post(
            "/chat",
            json={"message": "oi"},
            headers={"X-Widget-Token": "segredo-teste"},
        )
        assert r.status_code == 401
        assert "origem" in r.json()["detail"].lower()
        assert mock_answer.call_count == 0


def test_chat_401_foreign_origin(client: TestClient):
    with _mock_answer() as mock_answer:
        r = client.post(
            "/chat",
            json={"message": "oi"},
            headers={
                "X-Widget-Token": "segredo-teste",
                "Origin": "https://evil.example",
            },
        )
        assert r.status_code == 401
        assert mock_answer.call_count == 0


def test_chat_ok_with_token_and_origin(client: TestClient):
    with _mock_answer() as mock_answer:
        r = client.post(
            "/chat",
            json={"message": "oi", "session_id": "s1"},
            headers={
                "X-Widget-Token": "segredo-teste",
                "Origin": "https://intranet.enlevasaude.com",
            },
        )
        assert r.status_code == 200, r.text
        assert mock_answer.call_count == 1


def test_chat_ok_with_referer_fallback(client: TestClient):
    with _mock_answer() as mock_answer:
        r = client.post(
            "/chat",
            json={"message": "oi", "session_id": "s2"},
            headers={
                "X-Widget-Token": "segredo-teste",
                "Referer": "https://intranet.enlevasaude.com/pagina",
            },
        )
        assert r.status_code == 200, r.text
        assert mock_answer.call_count == 1

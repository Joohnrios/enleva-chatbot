"""Testes de rate limiting do /chat."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.routes_chat import router as chat_router
from backend.app.config import get_settings
from backend.app.security.rate_limit import (
    chat_limiter,
    parse_limit,
    rate_limit_exceeded_message,
)

CHAT_HEADERS = {
    "X-Widget-Token": "test-widget-token",
    "Origin": "http://127.0.0.1:8000",
}


@pytest.fixture(autouse=True)
def _reset_limiter(monkeypatch):
    monkeypatch.setenv("WIDGET_API_TOKEN", "test-widget-token")
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://127.0.0.1:8000")
    monkeypatch.setenv("REDIS_URL", "")
    monkeypatch.setattr(
        "backend.app.security.rate_limit.get_redis", lambda: None
    )
    from backend.app.redis_client import reset_redis_cache

    reset_redis_cache()
    chat_limiter.reset()
    get_settings.cache_clear()
    yield
    chat_limiter.reset()
    get_settings.cache_clear()
    reset_redis_cache()


def _post(client: TestClient, payload: dict):
    return client.post("/chat", json=payload, headers=CHAT_HEADERS)


def test_parse_limit_minute():
    parsed = parse_limit("20/minute")
    assert parsed.max_calls == 20
    assert parsed.window_seconds == 60


def test_parse_limit_invalid():
    with pytest.raises(ValueError):
        parse_limit("muito")


def test_friendly_429_message_uses_bot_name():
    msg = rate_limit_exceeded_message("Vita")
    assert "Vita" in msg
    assert "pausa" in msg.lower() or "instantes" in msg.lower()


def test_chat_returns_429_when_ip_quota_exceeded(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_CHAT", "3/minute")
    monkeypatch.setenv("RATE_LIMIT_CHAT_SESSION", "100/minute")
    monkeypatch.setenv("BOT_NAME", "AssistenteTeste")
    get_settings.cache_clear()

    app = FastAPI()
    app.include_router(chat_router)
    client = TestClient(app)

    with patch("backend.app.api.routes_chat.answer_question") as mock_answer:
        from backend.app.rag.orchestrator import ChatResult

        mock_answer.return_value = ChatResult(
            reply="ok",
            sources=[],
            refused=False,
            bot_name="AssistenteTeste",
            session_id="s1",
        )

        for i in range(3):
            r = _post(client, {"message": f"pergunta {i}", "session_id": f"s-{i}"})
            assert r.status_code == 200, r.text

        blocked = _post(client, {"message": "estoura", "session_id": "s-new"})
        assert blocked.status_code == 429
        detail = blocked.json()["detail"]
        assert "AssistenteTeste" in detail
        assert mock_answer.call_count == 3


def test_chat_returns_429_when_session_quota_exceeded(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_CHAT", "100/minute")
    monkeypatch.setenv("RATE_LIMIT_CHAT_SESSION", "2/minute")
    monkeypatch.setenv("BOT_NAME", "AssistenteTeste")
    get_settings.cache_clear()

    app = FastAPI()
    app.include_router(chat_router)
    client = TestClient(app)

    with patch("backend.app.api.routes_chat.answer_question") as mock_answer:
        from backend.app.rag.orchestrator import ChatResult

        mock_answer.return_value = ChatResult(
            reply="ok",
            sources=[],
            refused=False,
            bot_name="AssistenteTeste",
            session_id="same-session",
        )

        assert _post(client, {"message": "a", "session_id": "same-session"}).status_code == 200
        assert _post(client, {"message": "b", "session_id": "same-session"}).status_code == 200
        blocked = _post(client, {"message": "c", "session_id": "same-session"})
        assert blocked.status_code == 429
        assert "AssistenteTeste" in blocked.json()["detail"]
        assert mock_answer.call_count == 2


def test_most_restrictive_wins_session_blocks_while_ip_still_has_quota(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_CHAT", "5/minute")
    monkeypatch.setenv("RATE_LIMIT_CHAT_SESSION", "2/minute")
    monkeypatch.setenv("BOT_NAME", "AssistenteTeste")
    get_settings.cache_clear()

    app = FastAPI()
    app.include_router(chat_router)
    client = TestClient(app)

    with patch("backend.app.api.routes_chat.answer_question") as mock_answer:
        from backend.app.rag.orchestrator import ChatResult

        mock_answer.return_value = ChatResult(
            reply="ok",
            sources=[],
            refused=False,
            bot_name="AssistenteTeste",
            session_id="s",
        )

        assert _post(client, {"message": "1", "session_id": "sess-A"}).status_code == 200
        assert _post(client, {"message": "2", "session_id": "sess-A"}).status_code == 200
        blocked_a = _post(client, {"message": "3", "session_id": "sess-A"})
        assert blocked_a.status_code == 429

        other = _post(client, {"message": "4", "session_id": "sess-B"})
        assert other.status_code == 200
        assert mock_answer.call_count == 3


def test_most_restrictive_wins_ip_blocks_even_with_fresh_sessions(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_CHAT", "2/minute")
    monkeypatch.setenv("RATE_LIMIT_CHAT_SESSION", "10/minute")
    monkeypatch.setenv("BOT_NAME", "AssistenteTeste")
    get_settings.cache_clear()

    app = FastAPI()
    app.include_router(chat_router)
    client = TestClient(app)

    with patch("backend.app.api.routes_chat.answer_question") as mock_answer:
        from backend.app.rag.orchestrator import ChatResult

        mock_answer.return_value = ChatResult(
            reply="ok",
            sources=[],
            refused=False,
            bot_name="AssistenteTeste",
            session_id="x",
        )

        assert _post(client, {"message": "1", "session_id": "s1"}).status_code == 200
        assert _post(client, {"message": "2", "session_id": "s2"}).status_code == 200
        blocked = _post(client, {"message": "3", "session_id": "s3"})
        assert blocked.status_code == 429
        assert mock_answer.call_count == 2

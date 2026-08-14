"""Testes Redis rate limit / sessão (mock do cliente)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from backend.app.rag.session_memory import RedisSessionMemory
from backend.app.security.rate_limit import ParsedLimit, RedisSlidingWindowLimiter


def test_redis_limiter_allow_uses_script():
    client = MagicMock()
    script = MagicMock(return_value=1)
    client.register_script.return_value = script
    limiter = RedisSlidingWindowLimiter(client)
    assert limiter.allow("ip:1.2.3.4", ParsedLimit(5, 60)) is True
    script.assert_called_once()
    assert script.call_args.kwargs["keys"][0] == "rl:ip:1.2.3.4"


def test_redis_limiter_blocks_when_script_returns_zero():
    client = MagicMock()
    client.register_script.return_value = MagicMock(return_value=0)
    limiter = RedisSlidingWindowLimiter(client)
    assert limiter.allow("session:abc", ParsedLimit(2, 60)) is False


def test_redis_session_roundtrip():
    client = MagicMock()
    client.get.return_value = None
    mem = RedisSessionMemory(client)
    mem.append_exchange(
        "s1",
        user_message="oi",
        assistant_message="olá",
        ttl_minutes=60,
        max_turns=6,
    )
    assert client.set.called
    args, kwargs = client.set.call_args
    assert args[0] == "chat:session:s1"
    assert "oi" in args[1]
    assert kwargs.get("ex") == 3600

    client.get.return_value = args[1]
    hist = mem.get_history("s1", ttl_minutes=60, max_turns=6)
    assert hist[0]["content"] == "oi"
    assert hist[1]["content"] == "olá"


def test_proxy_uses_memory_without_redis():
    with patch("backend.app.security.rate_limit.get_redis", return_value=None):
        from backend.app.security.rate_limit import chat_limiter

        chat_limiter.reset()
        assert chat_limiter.allow("ip:x", ParsedLimit(1, 60)) is True
        assert chat_limiter.allow("ip:x", ParsedLimit(1, 60)) is False

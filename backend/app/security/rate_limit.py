"""Rate limiting para /chat (por IP e por session_id).

Backend: Redis (compartilhado entre réplicas) ou memória de processo (fallback).
"""

from __future__ import annotations

import logging
import re
import threading
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass

from fastapi import HTTPException, Request

from backend.app.redis_client import get_redis

logger = logging.getLogger(__name__)

_LIMIT_RE = re.compile(r"^(\d+)\s*/\s*(second|minute|hour|day)s?$", re.IGNORECASE)

_WINDOW_SECONDS = {
    "second": 1,
    "minute": 60,
    "hour": 3600,
    "day": 86400,
}

# Lua: janela deslizante atômica (ZSET score = timestamp)
_ALLOW_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local max_calls = tonumber(ARGV[3])
local member = ARGV[4]
redis.call('ZREMRANGEBYSCORE', key, '-inf', now - window)
local count = redis.call('ZCARD', key)
if count >= max_calls then
  return 0
end
redis.call('ZADD', key, now, member)
redis.call('EXPIRE', key, math.ceil(window) + 1)
return 1
"""


@dataclass(frozen=True)
class ParsedLimit:
    max_calls: int
    window_seconds: int


def parse_limit(value: str) -> ParsedLimit:
    """Converte '20/minute' em ParsedLimit."""
    raw = (value or "").strip()
    match = _LIMIT_RE.match(raw)
    if not match:
        raise ValueError(
            f"RATE_LIMIT inválido: {value!r}. Use formatos como '20/minute'."
        )
    count = int(match.group(1))
    unit = match.group(2).lower().rstrip("s")
    return ParsedLimit(max_calls=count, window_seconds=_WINDOW_SECONDS[unit])


class MemorySlidingWindowLimiter:
    """Contador thread-safe por chave com janela deslizante (processo local)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()

    def allow(self, key: str, limit: ParsedLimit) -> bool:
        now = time.monotonic()
        cutoff = now - limit.window_seconds
        with self._lock:
            bucket = self._hits[key]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= limit.max_calls:
                return False
            bucket.append(now)
            return True


class RedisSlidingWindowLimiter:
    """Janela deslizante compartilhada via Redis ZSET."""

    def __init__(self, client) -> None:
        self._client = client
        self._script = client.register_script(_ALLOW_SCRIPT)

    def reset(self) -> None:
        for pattern in ("rl:ip:*", "rl:session:*"):
            cursor = 0
            while True:
                cursor, keys = self._client.scan(cursor=cursor, match=pattern, count=100)
                if keys:
                    self._client.delete(*keys)
                if cursor == 0:
                    break

    def allow(self, key: str, limit: ParsedLimit) -> bool:
        redis_key = f"rl:{key}"
        member = f"{time.time_ns()}:{uuid.uuid4().hex[:8]}"
        try:
            allowed = self._script(
                keys=[redis_key],
                args=[time.time(), limit.window_seconds, limit.max_calls, member],
            )
            return bool(int(allowed))
        except Exception:
            logger.warning("Falha no rate limit Redis — negando com cuidado", exc_info=True)
            # Fail-open conservador para o piloto: se Redis cai mid-flight, não derruba o chat
            # (réplica local ainda tem Memory se get_redis falhou no boot). Aqui já estamos no Redis.
            return True


class _LimiterProxy:
    """Escolhe Redis ou memória a cada chamada (após settings/redis cache)."""

    def __init__(self) -> None:
        self._memory = MemorySlidingWindowLimiter()

    def _backend(self):
        client = get_redis()
        if client is not None:
            return RedisSlidingWindowLimiter(client)
        return self._memory

    def reset(self) -> None:
        self._memory.reset()
        client = get_redis()
        if client is not None:
            try:
                RedisSlidingWindowLimiter(client).reset()
            except Exception:
                logger.debug("reset Redis limiter falhou", exc_info=True)

    def allow(self, key: str, limit: ParsedLimit) -> bool:
        return self._backend().allow(key, limit)


# Proxy de processo — Redis se REDIS_URL ok, senão memória
chat_limiter = _LimiterProxy()

# Alias compatível com código/testes antigos
SlidingWindowLimiter = MemorySlidingWindowLimiter


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def rate_limit_exceeded_message(bot_name: str) -> str:
    return (
        f"Muitas mensagens em pouco tempo. "
        f"{bot_name} pediu uma pausa — tente novamente em instantes "
        "ou abra um chamado com RH/TI se for urgente."
    )


def enforce_chat_rate_limits(
    request: Request,
    *,
    session_id: str | None,
    bot_name: str,
    limit_ip: str,
    limit_session: str,
) -> None:
    """Aplica limite por IP e por session_id. Qualquer um estourando → 429."""
    ip_limit = parse_limit(limit_ip)
    session_limit = parse_limit(limit_session)

    ip = client_ip(request)
    if not chat_limiter.allow(f"ip:{ip}", ip_limit):
        raise HTTPException(
            status_code=429,
            detail=rate_limit_exceeded_message(bot_name),
        )

    sid = (session_id or "").strip() or "anonymous"
    if not chat_limiter.allow(f"session:{sid}", session_limit):
        raise HTTPException(
            status_code=429,
            detail=rate_limit_exceeded_message(bot_name),
        )

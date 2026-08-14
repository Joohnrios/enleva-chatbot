"""Histórico multi-turno — Redis (compartilhado) ou memória de processo (fallback).

Logs de auditoria em JSONL NÃO são afetados por este módulo.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from backend.app.redis_client import get_redis

logger = logging.getLogger(__name__)


@dataclass
class SessionState:
    messages: list[dict[str, str]] = field(default_factory=list)
    last_access: float = field(default_factory=time.monotonic)


class MemorySessionMemory:
    """Dict session_id → mensagens, thread-safe, com TTL e limite de turnos."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, SessionState] = {}

    def reset(self) -> None:
        with self._lock:
            self._sessions.clear()

    def get_history(
        self,
        session_id: str,
        *,
        ttl_minutes: int,
        max_turns: int,
    ) -> list[dict[str, str]]:
        now = time.monotonic()
        ttl_seconds = max(1, ttl_minutes) * 60
        with self._lock:
            state = self._sessions.get(session_id)
            if state is None:
                return []
            if now - state.last_access > ttl_seconds:
                del self._sessions[session_id]
                return []
            state.last_access = now
            limit = max(1, max_turns) * 2
            return list(state.messages[-limit:])

    def append_exchange(
        self,
        session_id: str,
        *,
        user_message: str,
        assistant_message: str,
        ttl_minutes: int,
        max_turns: int,
    ) -> None:
        now = time.monotonic()
        ttl_seconds = max(1, ttl_minutes) * 60
        with self._lock:
            state = self._sessions.get(session_id)
            if state is not None and now - state.last_access > ttl_seconds:
                del self._sessions[session_id]
                state = None
            if state is None:
                state = SessionState()
                self._sessions[session_id] = state
            state.messages.append({"role": "user", "content": user_message})
            state.messages.append({"role": "assistant", "content": assistant_message})
            limit = max(1, max_turns) * 2
            if len(state.messages) > limit:
                state.messages = state.messages[-limit:]
            state.last_access = now

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {"active_sessions": len(self._sessions), "backend": "memory"}


class RedisSessionMemory:
    """Histórico em Redis: chave chat:session:{id} = JSON, com EXPIRE = TTL."""

    def __init__(self, client) -> None:
        self._client = client

    def _key(self, session_id: str) -> str:
        return f"chat:session:{session_id}"

    def reset(self) -> None:
        cursor = 0
        while True:
            cursor, keys = self._client.scan(
                cursor=cursor, match="chat:session:*", count=100
            )
            if keys:
                self._client.delete(*keys)
            if cursor == 0:
                break

    def get_history(
        self,
        session_id: str,
        *,
        ttl_minutes: int,
        max_turns: int,
    ) -> list[dict[str, str]]:
        key = self._key(session_id)
        ttl_seconds = max(1, ttl_minutes) * 60
        try:
            raw = self._client.get(key)
            if not raw:
                return []
            messages = json.loads(raw)
            if not isinstance(messages, list):
                return []
            self._client.expire(key, ttl_seconds)
            limit = max(1, max_turns) * 2
            return list(messages[-limit:])
        except Exception:
            logger.warning("Falha ao ler sessão Redis %s", session_id, exc_info=True)
            return []

    def append_exchange(
        self,
        session_id: str,
        *,
        user_message: str,
        assistant_message: str,
        ttl_minutes: int,
        max_turns: int,
    ) -> None:
        key = self._key(session_id)
        ttl_seconds = max(1, ttl_minutes) * 60
        limit = max(1, max_turns) * 2
        try:
            raw = self._client.get(key)
            messages: list[dict[str, str]] = []
            if raw:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    messages = parsed
            messages.append({"role": "user", "content": user_message})
            messages.append({"role": "assistant", "content": assistant_message})
            if len(messages) > limit:
                messages = messages[-limit:]
            self._client.set(key, json.dumps(messages, ensure_ascii=False), ex=ttl_seconds)
        except Exception:
            logger.warning("Falha ao gravar sessão Redis %s", session_id, exc_info=True)

    def stats(self) -> dict[str, Any]:
        try:
            n = 0
            cursor = 0
            while True:
                cursor, keys = self._client.scan(
                    cursor=cursor, match="chat:session:*", count=100
                )
                n += len(keys)
                if cursor == 0:
                    break
            return {"active_sessions": n, "backend": "redis"}
        except Exception:
            return {"active_sessions": 0, "backend": "redis", "error": True}


class _SessionMemoryProxy:
    def __init__(self) -> None:
        self._memory = MemorySessionMemory()

    def _impl(self):
        client = get_redis()
        if client is not None:
            return RedisSessionMemory(client)
        return self._memory

    def reset(self) -> None:
        self._memory.reset()
        client = get_redis()
        if client is not None:
            try:
                RedisSessionMemory(client).reset()
            except Exception:
                logger.debug("reset Redis session falhou", exc_info=True)

    def get_history(self, session_id: str, *, ttl_minutes: int, max_turns: int):
        return self._impl().get_history(
            session_id, ttl_minutes=ttl_minutes, max_turns=max_turns
        )

    def append_exchange(
        self,
        session_id: str,
        *,
        user_message: str,
        assistant_message: str,
        ttl_minutes: int,
        max_turns: int,
    ) -> None:
        self._impl().append_exchange(
            session_id,
            user_message=user_message,
            assistant_message=assistant_message,
            ttl_minutes=ttl_minutes,
            max_turns=max_turns,
        )

    def stats(self) -> dict[str, Any]:
        return self._impl().stats()

    # Acesso interno usado por testes de TTL na implementação memória
    @property
    def _sessions(self):
        return self._memory._sessions


# Alias: testes que instanciam SessionMemory() usam a implementação em memória
SessionMemory = MemorySessionMemory

session_memory = _SessionMemoryProxy()

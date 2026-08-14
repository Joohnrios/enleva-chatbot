"""Protocolo comum para provedores de LLM."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    name: str

    def complete(
        self,
        *,
        system: str,
        messages: list[dict],
        temperature: float = 0.2,
    ) -> str:
        """Gera texto a partir de system prompt + mensagens [{role, content}]."""
        ...

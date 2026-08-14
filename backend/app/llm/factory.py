"""Factory de provedores LLM."""

from backend.app.config import Settings, get_settings
from backend.app.llm.anthropic_provider import AnthropicProvider
from backend.app.llm.base import LLMProvider
from backend.app.llm.gemini_provider import GeminiProvider
from backend.app.llm.openai_provider import OpenAIProvider


def get_provider(settings: Settings | None = None) -> LLMProvider:
    """Provider para geração RAG (ANTHROPIC_MODEL / equivalente)."""
    settings = settings or get_settings()
    provider = settings.llm_provider.strip().lower()

    if provider == "anthropic":
        return AnthropicProvider(settings.anthropic_api_key, settings.anthropic_model)
    if provider == "openai":
        return OpenAIProvider(settings.openai_api_key, settings.openai_model)
    if provider == "gemini":
        return GeminiProvider(settings.gemini_api_key, settings.gemini_model)

    raise ValueError(
        f"LLM_PROVIDER inválido: {settings.llm_provider!r}. "
        "Use anthropic, openai ou gemini."
    )


def get_scope_provider(settings: Settings | None = None) -> LLMProvider:
    """Provider barato/rápido só para classificador de escopo (Haiku).

    Reaproveita AnthropicProvider com ANTHROPIC_SCOPE_MODEL.
    Se o LLM_PROVIDER não for anthropic, usa o mesmo provider de geração
    (fallback até haver modelos de escopo dedicados nos outros provedores).
    """
    settings = settings or get_settings()
    provider = settings.llm_provider.strip().lower()

    if provider == "anthropic":
        return AnthropicProvider(
            settings.anthropic_api_key,
            settings.anthropic_scope_model,
        )
    return get_provider(settings)

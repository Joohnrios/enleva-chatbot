"""Classificador de escopo corporativo — cascata: keywords → similaridade → Haiku."""

from __future__ import annotations

import logging
import re

from backend.app.config import Settings, get_settings
from backend.app.guardrails.local_scope import classify_by_similarity
from backend.app.guardrails.prompts import scope_classifier_prompt
from backend.app.llm.base import LLMProvider
from backend.app.llm.factory import get_scope_provider
from backend.app.rag.store import KnowledgeStore

logger = logging.getLogger(__name__)

IN_SCOPE_KEYWORDS = [
    "senha",
    "vpn",
    "chamado",
    "intranet",
    "rh",
    "benefício",
    "beneficio",
    "férias",
    "ferias",
    "atestado",
    "vale",
    "plano de saúde",
    "plano de saude",
    "ponto",
    "jornada",
    "notebook",
    "impressora",
    "equipamento",
    "ti",
    "service desk",
    "acesso",
    "login",
    "política",
    "politica",
    "procedimento",
    "folha",
    "admissão",
    "admissao",
    "colaborador",
    "enleva",
]

OUT_OF_SCOPE_KEYWORDS = [
    "receita de bolo",
    "piada",
    "filme",
    "série",
    "serie",
    "futebol",
    "bitcoin",
    "python",
    "javascript",
    "escreva um código",
    "escreva um codigo",
    "previsão do tempo",
    "previsao do tempo",
    "capital da",
    "traduz",
    "namoro",
]


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def build_scope_text(
    message: str,
    history: list[dict[str, str]] | None = None,
    *,
    max_prior_user_turns: int = 2,
) -> str:
    """Monta texto para escopo/retrieval: últimas perguntas do usuário + mensagem atual.

    Follow-ups curtos ("e quanto tempo demora?") herdam sinal de domínio do histórico.
    """
    message = (message or "").strip()
    if not history:
        return message
    prior_users = [
        (m.get("content") or "").strip()
        for m in history
        if m.get("role") == "user" and (m.get("content") or "").strip()
    ]
    recent = prior_users[-max_prior_user_turns:]
    if not recent:
        return message
    return "\n".join([*recent, message])


def classify_scope_rules(message: str) -> str | None:
    """Retorna in_scope, out_of_scope ou None se inconclusivo."""
    text = _normalize(message)
    if any(k in text for k in OUT_OF_SCOPE_KEYWORDS):
        return "out_of_scope"
    if any(k in text for k in IN_SCOPE_KEYWORDS):
        return "in_scope"
    return None


def _classify_with_haiku(message: str, llm: LLMProvider) -> str:
    raw = llm.complete(
        system=scope_classifier_prompt(),
        messages=[{"role": "user", "content": message}],
        temperature=0.0,
    )
    cleaned = _normalize(raw).replace(" ", "_")
    if "out_of_scope" in cleaned or cleaned.startswith("out"):
        return "out_of_scope"
    if "in_scope" in cleaned or cleaned.startswith("in"):
        return "in_scope"
    logger.warning("Classificador Haiku retornou valor inesperado: %r", raw)
    return "out_of_scope"


def classify_scope(
    message: str,
    *,
    history: list[dict[str, str]] | None = None,
    llm: LLMProvider | None = None,
    settings: Settings | None = None,
    store: KnowledgeStore | None = None,
    use_llm_if_ambiguous: bool = True,
) -> str:
    """Cascata: keywords → similaridade local → Haiku (só se ambíguo).

    A mensagem atual é checada isolada primeiro (OUT/IN claros).
    Se inconclusiva, usa texto contextual (histórico curto + mensagem) para
    keywords, similaridade e Haiku — evita recusar follow-ups legítimos.

    Nunca assume in_scope por padrão sem checagem.
    Se ambíguo e LLM indisponível/falha → out_of_scope (fail-closed).
    """
    settings = settings or get_settings()

    # 1a) Keywords na mensagem atual isolada (não deixa histórico "salvar" fora de escopo)
    ruled_current = classify_scope_rules(message)
    if ruled_current:
        logger.debug("Escopo por keyword (mensagem atual): %s", ruled_current)
        return ruled_current

    scope_text = build_scope_text(message, history)

    # 1b) Keywords com histórico (ex.: follow-up após pergunta sobre VPN/senha)
    if scope_text != message:
        ruled_ctx = classify_scope_rules(scope_text)
        if ruled_ctx:
            logger.debug("Escopo por keyword (com histórico): %s", ruled_ctx)
            return ruled_ctx

    # 2) Similaridade vs âncoras (texto contextual)
    local = classify_by_similarity(scope_text, settings=settings, store=store)
    logger.debug("Escopo por similaridade: %s (%s)", local.decision, local.reason)
    if local.decision in {"in_scope", "out_of_scope"}:
        return local.decision

    # 3) Ambíguo → Haiku (ANTHROPIC_SCOPE_MODEL), também com contexto
    if not use_llm_if_ambiguous:
        logger.info("Escopo ambíguo sem LLM — fail-closed out_of_scope")
        return "out_of_scope"

    try:
        scope_llm = llm or get_scope_provider(settings)
        decision = _classify_with_haiku(scope_text, scope_llm)
        logger.debug("Escopo por Haiku: %s", decision)
        return decision
    except Exception:
        logger.exception("Falha no classificador Haiku — fail-closed out_of_scope")
        return "out_of_scope"

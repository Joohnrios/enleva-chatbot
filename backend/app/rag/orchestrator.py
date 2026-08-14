"""Orquestração RAG: escopo → retrieval → LLM (com histórico) → filtro de saída."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

from backend.app.config import Settings, get_settings
from backend.app.db.repository import get_domain_contact
from backend.app.guardrails.output_filter import filter_output
from backend.app.guardrails.prompts import (
    refusal_no_context,
    refusal_out_of_scope,
    system_prompt,
)
from backend.app.guardrails.scope import build_scope_text, classify_scope
from backend.app.llm.base import LLMProvider
from backend.app.llm.factory import get_provider
from backend.app.rag.retriever import retrieve
from backend.app.rag.session_memory import session_memory
from backend.app.rag.store import RetrievedChunk, get_store
from backend.app.schemas import SourceRef
from backend.app.security.retention import append_chat_log


@dataclass
class ChatResult:
    reply: str
    sources: list[SourceRef] = field(default_factory=list)
    refused: bool = False
    refusal_reason: str | None = None  # out_of_scope | no_context | sensitive
    bot_name: str = ""
    session_id: str = ""


def _format_context(chunks: list[RetrievedChunk]) -> str:
    blocks: list[str] = []
    for i, chunk in enumerate(chunks, start=1):
        blocks.append(
            f"[{i}] Título: {chunk.title}\n"
            f"Fonte: {chunk.source}\n"
            f"Domínio: {chunk.domain}\n"
            f"Trecho:\n{chunk.text}"
        )
    return "\n\n".join(blocks)


def answer_question(
    message: str,
    *,
    session_id: str | None = None,
    history: list[dict[str, str]] | None = None,
    settings: Settings | None = None,
    llm: LLMProvider | None = None,
    scope_llm: LLMProvider | None = None,
    use_llm_if_ambiguous: bool = True,
    persist_session: bool = True,
) -> ChatResult:
    settings = settings or get_settings()
    bot_name = settings.bot_name
    sid = (session_id or "").strip() or str(uuid4())

    prior = history
    if prior is None:
        prior = session_memory.get_history(
            sid,
            ttl_minutes=settings.session_ttl_minutes,
            max_turns=settings.session_max_turns,
        )

    scope = classify_scope(
        message,
        history=prior,
        llm=scope_llm,
        settings=settings,
        use_llm_if_ambiguous=use_llm_if_ambiguous,
    )
    if scope == "out_of_scope":
        reply = refusal_out_of_scope(bot_name)
        result = ChatResult(
            reply=reply,
            sources=[],
            refused=True,
            refusal_reason="out_of_scope",
            bot_name=bot_name,
            session_id=sid,
        )
        if persist_session:
            session_memory.append_exchange(
                sid,
                user_message=message,
                assistant_message=reply,
                ttl_minutes=settings.session_ttl_minutes,
                max_turns=settings.session_max_turns,
            )
        _log(settings, result, message)
        return result

    # Retrieval também usa texto contextual para follow-ups curtos
    retrieval_query = build_scope_text(message, prior)
    chunks = retrieve(retrieval_query, settings=settings)
    if not chunks:
        nearest = get_store().nearest_anchor_domain(retrieval_query)
        domain_info = get_domain_contact(nearest) if nearest else None
        # Fallback de canais conhecidos se SQL ainda não populou Domain
        channel = domain_info.contact_channel if domain_info else None
        domain_label = domain_info.name if domain_info else nearest
        if not channel and nearest:
            key = nearest.strip().lower()
            if key in {"ti", "tecnologia"}:
                channel = "GLPI"
                domain_label = domain_label or "TI"
            elif key in {"rh", "recursos-humanos", "recursos humanos"}:
                channel = "Atendimento ao Colaborador"
                domain_label = domain_label or "RH"
            elif key in {"admin", "administrativo"}:
                channel = "Atendimento ao Colaborador"
                domain_label = domain_label or "Admin"
        reply = refusal_no_context(
            bot_name,
            contact_channel=channel,
            domain_name=domain_label,
        )
        result = ChatResult(
            reply=reply,
            sources=[],
            refused=True,
            refusal_reason="no_context",
            bot_name=bot_name,
            session_id=sid,
        )
        if persist_session:
            session_memory.append_exchange(
                sid,
                user_message=message,
                assistant_message=reply,
                ttl_minutes=settings.session_ttl_minutes,
                max_turns=settings.session_max_turns,
            )
        _log(settings, result, message)
        return result

    provider = llm or get_provider(settings)
    context = _format_context(chunks)
    messages: list[dict[str, str]] = []
    for turn in prior:
        role = turn.get("role")
        content = turn.get("content")
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})

    messages.append(
        {
            "role": "user",
            "content": (
                f"Pergunta do colaborador:\n{message}\n\n"
                f"Contexto da base de conhecimento:\n{context}\n\n"
                "Responda usando apenas o contexto acima. "
                "Se a pergunta for de acompanhamento, use o histórico da conversa "
                "para interpretar a referência, sem inventar fatos fora do contexto."
            ),
        }
    )
    raw = provider.complete(
        system=system_prompt(bot_name),
        messages=messages,
        temperature=0.2,
    )
    safe, blocked = filter_output(raw, bot_name)
    sources = [
        SourceRef(
            title=c.title,
            source=c.source,
            domain=c.domain,
            score=round(c.score, 4),
        )
        for c in chunks
    ]
    result = ChatResult(
        reply=safe,
        sources=[] if blocked else sources,
        refused=blocked,
        refusal_reason="sensitive" if blocked else None,
        bot_name=bot_name,
        session_id=sid,
    )
    if persist_session:
        session_memory.append_exchange(
            sid,
            user_message=message,
            assistant_message=safe,
            ttl_minutes=settings.session_ttl_minutes,
            max_turns=settings.session_max_turns,
        )
    _log(settings, result, message)
    return result


def _log(settings: Settings, result: ChatResult, message: str) -> None:
    append_chat_log(
        settings.log_path,
        session_id=result.session_id,
        message=message,
        reply=result.reply,
        refused=result.refused,
        sources=[s.source for s in result.sources],
    )

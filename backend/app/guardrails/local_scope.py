"""Filtro local de escopo por similaridade de embedding vs âncoras de domínio."""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.config import Settings, get_settings
from backend.app.rag.store import KnowledgeStore, get_store


@dataclass
class LocalScopeResult:
    decision: str  # in_scope | out_of_scope | ambiguous
    score: float
    reason: str


def score_against_anchors(
    message: str,
    *,
    settings: Settings | None = None,
    store: KnowledgeStore | None = None,
) -> float:
    """Retorna a maior similaridade (0–1) entre a pergunta e as âncoras indexadas."""
    settings = settings or get_settings()
    store = store or get_store()
    return store.max_anchor_similarity(message)


def classify_by_similarity(
    message: str,
    *,
    settings: Settings | None = None,
    store: KnowledgeStore | None = None,
) -> LocalScopeResult:
    """Decide in/out/ambiguous com base em SCOPE_LOCAL_MIN_SCORE e SCOPE_LOCAL_OUT_MAX.

    - score >= MIN → claramente relacionado à BC (in_scope)
    - score < OUT_MAX → claramente fora (out_of_scope)
    - entre OUT_MAX e MIN → ambíguo (escala para Haiku)
    """
    settings = settings or get_settings()
    score = score_against_anchors(message, settings=settings, store=store)
    min_in = settings.scope_local_min_score
    max_out = settings.scope_local_out_max

    if score >= min_in:
        return LocalScopeResult(
            decision="in_scope",
            score=score,
            reason=f"similaridade {score:.3f} >= {min_in}",
        )
    if score < max_out:
        return LocalScopeResult(
            decision="out_of_scope",
            score=score,
            reason=f"similaridade {score:.3f} < {max_out}",
        )
    return LocalScopeResult(
        decision="ambiguous",
        score=score,
        reason=f"similaridade {score:.3f} entre {max_out} e {min_in}",
    )


# Textos base por domínio (sempre indexados como âncoras, além dos títulos dos docs)
DOMAIN_SEED_ANCHORS: dict[str, str] = {
    "RH": (
        "Recursos Humanos RH benefícios plano de saúde vale-refeição férias "
        "atestado médico admissão colaborador política interna"
    ),
    "TI": (
        "Tecnologia da Informação TI senha VPN acesso intranet notebook "
        "impressora equipamento service desk chamado software"
    ),
    "Admin": (
        "Administrativo ponto eletrônico jornada banco de horas ajuste de ponto "
        "procedimentos administrativos unidade"
    ),
}


def build_doc_anchor(title: str, domain: str, body: str, max_chars: int = 400) -> str:
    excerpt = " ".join(body.split())[:max_chars]
    return f"Domínio {domain}. Título: {title}. Resumo: {excerpt}"

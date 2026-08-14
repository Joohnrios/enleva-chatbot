"""Consultas de leitura da BC no Postgres (sem ORM Django)."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select

from backend.app.db.engine import get_session
from backend.app.db.models import KbDocument, KbDomain

logger = logging.getLogger(__name__)

INDEXABLE_CLASSIFICATION = "Interno"


@dataclass(frozen=True)
class DomainInfo:
    id: str
    slug: str
    name: str
    scope_seed: str
    contact_channel: str
    contact_hint: str


@dataclass(frozen=True)
class DocumentInfo:
    id: str
    slug: str
    title: str
    domain_slug: str
    domain_name: str
    classification: str
    sensitive: bool
    owner: str
    body: str
    content_hash: str
    version: int


def _domain_key_matches(domain: KbDomain, key: str) -> bool:
    k = key.strip().lower()
    return domain.slug.lower() == k or domain.name.lower() == k


def list_active_domains() -> list[DomainInfo]:
    session = get_session()
    if session is None:
        return []
    try:
        rows = session.scalars(
            select(KbDomain).where(KbDomain.is_active.is_(True)).order_by(KbDomain.name)
        ).all()
        return [
            DomainInfo(
                id=str(r.id),
                slug=r.slug,
                name=r.name,
                scope_seed=r.scope_seed,
                contact_channel=r.contact_channel,
                contact_hint=r.contact_hint or "",
            )
            for r in rows
        ]
    except Exception:
        logger.warning("Falha ao listar kb_domain", exc_info=True)
        return []
    finally:
        session.close()


def get_domain_contact(domain_key: str | None) -> DomainInfo | None:
    """Resolve por slug ou name (case-insensitive)."""
    if not domain_key or not str(domain_key).strip():
        return None
    session = get_session()
    if session is None:
        return None
    try:
        rows = session.scalars(
            select(KbDomain).where(KbDomain.is_active.is_(True))
        ).all()
        for row in rows:
            if _domain_key_matches(row, domain_key):
                return DomainInfo(
                    id=str(row.id),
                    slug=row.slug,
                    name=row.name,
                    scope_seed=row.scope_seed,
                    contact_channel=row.contact_channel,
                    contact_hint=row.contact_hint or "",
                )
        return None
    except Exception:
        logger.warning("Falha ao buscar domínio %s", domain_key, exc_info=True)
        return None
    finally:
        session.close()


def list_indexable_documents() -> list[DocumentInfo]:
    """Publicados, Interno, não sensíveis, domínio ativo — prontos para reindex futuro."""
    session = get_session()
    if session is None:
        return []
    try:
        stmt = (
            select(KbDocument)
            .join(KbDomain, KbDocument.domain_id == KbDomain.id)
            .where(
                KbDocument.is_published.is_(True),
                KbDocument.classification == INDEXABLE_CLASSIFICATION,
                KbDocument.sensitive.is_(False),
                KbDomain.is_active.is_(True),
            )
            .order_by(KbDocument.slug)
        )
        rows = session.scalars(stmt).unique().all()
        out: list[DocumentInfo] = []
        for r in rows:
            domain = r.domain
            out.append(
                DocumentInfo(
                    id=str(r.id),
                    slug=r.slug,
                    title=r.title,
                    domain_slug=domain.slug if domain else "",
                    domain_name=domain.name if domain else "",
                    classification=r.classification,
                    sensitive=r.sensitive,
                    owner=r.owner or "",
                    body=r.body,
                    content_hash=r.content_hash or "",
                    version=r.version,
                )
            )
        return out
    except Exception:
        logger.warning("Falha ao listar kb_document indexáveis", exc_info=True)
        return []
    finally:
        session.close()

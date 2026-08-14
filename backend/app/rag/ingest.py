"""Pipeline de ingestão: Postgres (Document) ou Markdown em knowledge/ + Chroma."""

from __future__ import annotations

import hashlib
import logging
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

from backend.app.config import Settings, get_settings
from backend.app.db.repository import DocumentInfo, list_active_domains, list_indexable_documents
from backend.app.guardrails.local_scope import DOMAIN_SEED_ANCHORS, build_doc_anchor
from backend.app.rag.chunking import chunk_markdown
from backend.app.rag.store import KnowledgeStore, get_store, reset_store_cache

logger = logging.getLogger(__name__)

ALLOWED_CLASSIFICATION = {"interno"}
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)

_ingest_lock = threading.Lock()

IngestMode = Literal["postgres", "files"]


@dataclass
class IngestResult:
    indexed_files: int = 0
    indexed_chunks: int = 0
    indexed_anchors: int = 0
    unchanged_files: int = 0
    removed_files: int = 0
    skipped_files: list[str] = field(default_factory=list)
    message: str = ""
    source_mode: str = ""


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def parse_markdown_file(path: Path) -> tuple[dict[str, Any], str] | None:
    raw = path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(raw)
    if not match:
        logger.warning("Sem frontmatter YAML: %s", path.name)
        return None
    meta = yaml.safe_load(match.group(1)) or {}
    body = match.group(2).strip()
    if not isinstance(meta, dict):
        return None
    return meta, body


def is_indexable(meta: dict[str, Any]) -> bool:
    classification = str(meta.get("classification", "")).strip().lower()
    sensitive = bool(meta.get("sensitive", False))
    if classification not in ALLOWED_CLASSIFICATION:
        return False
    if sensitive:
        return False
    return True


def document_source_key(slug: str) -> str:
    """Chave estável no Chroma (compatível com .md histórico)."""
    return f"{slug}.md" if not slug.endswith(".md") else slug


def _prepare_payload(
    *,
    source: str,
    stem: str,
    title: str,
    domain: str,
    classification: str,
    body: str,
    content_hash: str,
) -> tuple[list[str], list[str], list[dict[str, Any]], str, str, dict[str, Any]]:
    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict[str, Any]] = []
    for chunk in chunk_markdown(body):
        chunk_id = f"{stem}-{content_hash}-{chunk.chunk_index}"
        ids.append(chunk_id)
        documents.append(chunk.text)
        metadatas.append(
            {
                "source": source,
                "title": title,
                "domain": domain,
                "classification": classification,
                "chunk_id": chunk_id,
                "file_hash": content_hash,
            }
        )
    anchor_id = f"doc-{stem}-{content_hash}"
    anchor_doc = build_doc_anchor(title, domain, body)
    anchor_meta = {
        "domain": domain,
        "kind": "document",
        "title": title,
        "source": source,
    }
    return ids, documents, metadatas, anchor_id, anchor_doc, anchor_meta


def _prepare_file_payload(
    path: Path,
    meta: dict[str, Any],
    body: str,
    file_hash: str,
) -> tuple[list[str], list[str], list[dict[str, Any]], str, str, dict[str, Any]]:
    title = str(meta.get("title") or path.stem)
    domain = str(meta.get("domain") or "Geral")
    classification = str(meta.get("classification") or "")
    return _prepare_payload(
        source=path.name,
        stem=path.stem,
        title=title,
        domain=domain,
        classification=classification,
        body=body,
        content_hash=file_hash,
    )


def _prepare_document_payload(
    doc: DocumentInfo,
) -> tuple[list[str], list[str], list[dict[str, Any]], str, str, dict[str, Any]]:
    source = document_source_key(doc.slug)
    content_hash = doc.content_hash or hashlib.sha256(doc.body.encode("utf-8")).hexdigest()[:16]
    return _prepare_payload(
        source=source,
        stem=doc.slug,
        title=doc.title,
        domain=doc.domain_name or doc.domain_slug or "Geral",
        classification=doc.classification,
        body=doc.body,
        content_hash=content_hash,
    )


def _seed_anchor_map() -> dict[str, str]:
    """Seeds de domínio: Postgres (kb_domain) com fallback ao dict Python."""
    domains = list_active_domains()
    if domains:
        return {d.name: d.scope_seed for d in domains if d.scope_seed.strip()}
    return dict(DOMAIN_SEED_ANCHORS)


def _upsert_seed_anchors(store: KnowledgeStore) -> int:
    seeds = _seed_anchor_map()
    anchor_ids: list[str] = []
    anchor_docs: list[str] = []
    anchor_metas: list[dict[str, Any]] = []
    for domain, text in seeds.items():
        anchor_ids.append(f"seed-{domain.lower()}")
        anchor_docs.append(text)
        anchor_metas.append(
            {"domain": domain, "kind": "seed", "title": f"Âncora {domain}"}
        )
    store.upsert_anchors(ids=anchor_ids, documents=anchor_docs, metadatas=anchor_metas)
    return len(anchor_ids)


def _flush_batches(
    store: KnowledgeStore,
    ids: list[str],
    documents: list[str],
    metadatas: list[dict[str, Any]],
    anchor_ids: list[str],
    anchor_docs: list[str],
    anchor_metas: list[dict[str, Any]],
) -> None:
    batch = 64
    for i in range(0, len(ids), batch):
        store.upsert_chunks(
            ids=ids[i : i + batch],
            documents=documents[i : i + batch],
            metadatas=metadatas[i : i + batch],
        )
    for i in range(0, len(anchor_ids), batch):
        store.upsert_anchors(
            ids=anchor_ids[i : i + batch],
            documents=anchor_docs[i : i + batch],
            metadatas=anchor_metas[i : i + batch],
        )


def resolve_ingest_mode(settings: Settings) -> tuple[IngestMode, list[DocumentInfo] | None]:
    """postgres se configurado e houver docs indexáveis; senão files."""
    mode = (settings.ingest_source or "auto").strip().lower()
    if mode == "files":
        return "files", None

    docs = list_indexable_documents() if settings.kb_sql_enabled else []
    if mode == "postgres":
        if docs:
            return "postgres", docs
        logger.warning(
            "INGEST_SOURCE=postgres sem documentos indexáveis — fallback para knowledge/"
        )
        return "files", None

    # auto
    if docs:
        return "postgres", docs
    return "files", None


def _ingest_full_documents(
    store: KnowledgeStore, docs: list[DocumentInfo]
) -> IngestResult:
    store.reset()
    result = IngestResult(source_mode="postgres")
    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict[str, Any]] = []
    anchor_ids: list[str] = []
    anchor_docs: list[str] = []
    anchor_metas: list[dict[str, Any]] = []

    for domain, text in _seed_anchor_map().items():
        anchor_ids.append(f"seed-{domain.lower()}")
        anchor_docs.append(text)
        anchor_metas.append(
            {"domain": domain, "kind": "seed", "title": f"Âncora {domain}"}
        )

    for doc in docs:
        c_ids, c_docs, c_metas, a_id, a_doc, a_meta = _prepare_document_payload(doc)
        ids.extend(c_ids)
        documents.extend(c_docs)
        metadatas.extend(c_metas)
        anchor_ids.append(a_id)
        anchor_docs.append(a_doc)
        anchor_metas.append(a_meta)
        result.indexed_files += 1

    _flush_batches(
        store, ids, documents, metadatas, anchor_ids, anchor_docs, anchor_metas
    )
    result.indexed_chunks = len(ids)
    result.indexed_anchors = len(anchor_ids)
    result.message = (
        f"Reindex completo (Postgres): {result.indexed_files} documento(s), "
        f"{result.indexed_chunks} chunk(s), "
        f"{result.indexed_anchors} âncora(s)."
    )
    return result


def _ingest_incremental_documents(
    store: KnowledgeStore, docs: list[DocumentInfo]
) -> IngestResult:
    result = IngestResult(source_mode="postgres")
    existing = store.source_hashes()
    seen_sources: set[str] = set()
    seed_count = _upsert_seed_anchors(store)

    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict[str, Any]] = []
    anchor_ids: list[str] = []
    anchor_docs: list[str] = []
    anchor_metas: list[dict[str, Any]] = []

    for doc in docs:
        source = document_source_key(doc.slug)
        seen_sources.add(source)
        content_hash = (
            doc.content_hash
            or hashlib.sha256(doc.body.encode("utf-8")).hexdigest()[:16]
        )
        if existing.get(source) == content_hash:
            result.unchanged_files += 1
            continue
        if source in existing:
            store.delete_by_source(source)
        c_ids, c_docs, c_metas, a_id, a_doc, a_meta = _prepare_document_payload(doc)
        ids.extend(c_ids)
        documents.extend(c_docs)
        metadatas.extend(c_metas)
        anchor_ids.append(a_id)
        anchor_docs.append(a_doc)
        anchor_metas.append(a_meta)
        result.indexed_files += 1

    for source in set(existing) - seen_sources:
        store.delete_by_source(source)
        result.removed_files += 1
        logger.info("Removido do índice (doc ausente/não indexável): %s", source)

    _flush_batches(
        store, ids, documents, metadatas, anchor_ids, anchor_docs, anchor_metas
    )
    result.indexed_chunks = len(ids)
    result.indexed_anchors = len(anchor_ids) + seed_count
    result.message = (
        f"Ingest incremental (Postgres): {result.indexed_files} atualizado(s), "
        f"{result.unchanged_files} inalterado(s), "
        f"{result.removed_files} removido(s); "
        f"{result.indexed_chunks} chunk(s) reescritos."
    )
    return result


def _ingest_full_files(store: KnowledgeStore, knowledge_dir: Path) -> IngestResult:
    store.reset()
    result = IngestResult(source_mode="files")
    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict[str, Any]] = []
    anchor_ids: list[str] = []
    anchor_docs: list[str] = []
    anchor_metas: list[dict[str, Any]] = []

    for domain, text in _seed_anchor_map().items():
        anchor_ids.append(f"seed-{domain.lower()}")
        anchor_docs.append(text)
        anchor_metas.append(
            {"domain": domain, "kind": "seed", "title": f"Âncora {domain}"}
        )

    for path in sorted(knowledge_dir.glob("*.md")):
        if path.name.startswith("_"):
            continue
        parsed = parse_markdown_file(path)
        if parsed is None:
            result.skipped_files.append(f"{path.name}: frontmatter inválido")
            continue
        meta, body = parsed
        if not is_indexable(meta):
            reason = (
                f"{path.name}: classification={meta.get('classification')!r} "
                f"sensitive={meta.get('sensitive')!r} (fora do MVP)"
            )
            logger.info("Ignorado no índice: %s", reason)
            result.skipped_files.append(reason)
            continue

        file_hash = _file_hash(path)
        c_ids, c_docs, c_metas, a_id, a_doc, a_meta = _prepare_file_payload(
            path, meta, body, file_hash
        )
        ids.extend(c_ids)
        documents.extend(c_docs)
        metadatas.extend(c_metas)
        anchor_ids.append(a_id)
        anchor_docs.append(a_doc)
        anchor_metas.append(a_meta)
        result.indexed_files += 1

    _flush_batches(
        store, ids, documents, metadatas, anchor_ids, anchor_docs, anchor_metas
    )
    result.indexed_chunks = len(ids)
    result.indexed_anchors = len(anchor_ids)
    result.message = (
        f"Reindex completo (files): {result.indexed_files} arquivo(s), "
        f"{result.indexed_chunks} chunk(s), "
        f"{result.indexed_anchors} âncora(s) de escopo."
    )
    return result


def _ingest_incremental_files(
    store: KnowledgeStore, knowledge_dir: Path
) -> IngestResult:
    result = IngestResult(source_mode="files")
    existing = store.source_hashes()
    seen_sources: set[str] = set()
    seed_count = _upsert_seed_anchors(store)

    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict[str, Any]] = []
    anchor_ids: list[str] = []
    anchor_docs: list[str] = []
    anchor_metas: list[dict[str, Any]] = []

    for path in sorted(knowledge_dir.glob("*.md")):
        if path.name.startswith("_"):
            continue
        parsed = parse_markdown_file(path)
        if parsed is None:
            result.skipped_files.append(f"{path.name}: frontmatter inválido")
            if path.name in existing:
                store.delete_by_source(path.name)
                result.removed_files += 1
            continue
        meta, body = parsed
        if not is_indexable(meta):
            reason = (
                f"{path.name}: classification={meta.get('classification')!r} "
                f"sensitive={meta.get('sensitive')!r} (fora do MVP)"
            )
            logger.info("Ignorado no índice: %s", reason)
            result.skipped_files.append(reason)
            if path.name in existing:
                store.delete_by_source(path.name)
                result.removed_files += 1
            continue

        seen_sources.add(path.name)
        file_hash = _file_hash(path)
        if existing.get(path.name) == file_hash:
            result.unchanged_files += 1
            continue

        if path.name in existing:
            store.delete_by_source(path.name)

        c_ids, c_docs, c_metas, a_id, a_doc, a_meta = _prepare_file_payload(
            path, meta, body, file_hash
        )
        ids.extend(c_ids)
        documents.extend(c_docs)
        metadatas.extend(c_metas)
        anchor_ids.append(a_id)
        anchor_docs.append(a_doc)
        anchor_metas.append(a_meta)
        result.indexed_files += 1

    for source in set(existing) - seen_sources:
        store.delete_by_source(source)
        result.removed_files += 1
        logger.info("Removido do índice (arquivo ausente): %s", source)

    _flush_batches(
        store, ids, documents, metadatas, anchor_ids, anchor_docs, anchor_metas
    )
    result.indexed_chunks = len(ids)
    result.indexed_anchors = len(anchor_ids) + seed_count
    result.message = (
        f"Ingest incremental (files): {result.indexed_files} atualizado(s), "
        f"{result.unchanged_files} inalterado(s), "
        f"{result.removed_files} removido(s); "
        f"{result.indexed_chunks} chunk(s) reescritos."
    )
    return result


def ingest_knowledge(
    settings: Settings | None = None,
    store: KnowledgeStore | None = None,
    *,
    full: bool = False,
) -> IngestResult:
    settings = settings or get_settings()
    mode, docs = resolve_ingest_mode(settings)

    if mode == "files":
        knowledge_dir = settings.knowledge_path
        if not knowledge_dir.exists():
            return IngestResult(
                message=f"Pasta não encontrada: {knowledge_dir}",
                source_mode="files",
            )

    force_full = full or settings.ingest_force_full

    with _ingest_lock:
        if store is None:
            reset_store_cache()
            store = get_store()

        if mode == "postgres" and docs is not None:
            if force_full or store.count() == 0:
                result = _ingest_full_documents(store, docs)
            else:
                result = _ingest_incremental_documents(store, docs)
        else:
            knowledge_dir = settings.knowledge_path
            if force_full or store.count() == 0:
                result = _ingest_full_files(store, knowledge_dir)
            else:
                result = _ingest_incremental_files(store, knowledge_dir)

        logger.info(result.message)
        return result

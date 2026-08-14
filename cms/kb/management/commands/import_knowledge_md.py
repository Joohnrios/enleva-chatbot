"""Importa knowledge/*.md → Domain + Document (idempotente por slug).

Uso:
  set CMS_USE_SQLITE=true
  python cms/manage.py import_knowledge_md
  python cms/manage.py import_knowledge_md --dry-run
  python cms/manage.py import_knowledge_md --knowledge-dir C:\\path\\knowledge
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from cms.kb.domain_defaults import DOMAIN_DEFAULTS
from cms.kb.models import Classification, Document, Domain

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)

CLASSIFICATION_ALIASES: dict[str, str] = {
    "publica": Classification.PUBLICA,
    "pública": Classification.PUBLICA,
    "interno": Classification.INTERNO,
    "restrita": Classification.RESTRITA,
    "confidencial": Classification.CONFIDENCIAL,
}


def parse_markdown_file(path: Path) -> tuple[dict[str, Any], str] | None:
    raw = path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(raw)
    if not match:
        return None
    meta = yaml.safe_load(match.group(1)) or {}
    body = match.group(2).strip()
    if not isinstance(meta, dict):
        return None
    return meta, body


def normalize_classification(raw: Any) -> str:
    key = str(raw or Classification.INTERNO).strip().lower()
    if key in CLASSIFICATION_ALIASES:
        return CLASSIFICATION_ALIASES[key]
    for choice in Classification.values:
        if choice.lower() == key or choice == raw:
            return choice
    return Classification.INTERNO


def domain_slug_from_meta(domain_raw: Any) -> str:
    name = str(domain_raw or "Geral").strip() or "Geral"
    return slugify(name, allow_unicode=False) or "geral"


def should_publish(classification: str, sensitive: bool) -> bool:
    return classification == Classification.INTERNO and not sensitive


def resolve_domain(domain_raw: Any, *, dry_run: bool) -> Domain:
    slug = domain_slug_from_meta(domain_raw)
    display_name = str(domain_raw or "Geral").strip() or "Geral"
    defaults = DOMAIN_DEFAULTS.get(slug, {})
    fields = {
        "name": defaults.get("name") or display_name,
        "scope_seed": defaults.get(
            "scope_seed",
            f"Documentos e procedimentos do domínio {display_name}.",
        ),
        "contact_channel": defaults.get("contact_channel", "Central de Atendimento"),
        "contact_hint": defaults.get("contact_hint", ""),
        "is_active": True,
    }
    if dry_run:
        existing = Domain.objects.filter(slug=slug).first()
        if existing:
            return existing
        return Domain(slug=slug, **fields)

    domain, _created = Domain.objects.update_or_create(slug=slug, defaults=fields)
    return domain


class Command(BaseCommand):
    help = "Importa Markdown de knowledge/ para Domain/Document (idempotente por slug)."

    def add_arguments(self, parser):
        default_dir = Path(settings.PROJECT_ROOT) / "knowledge"
        parser.add_argument(
            "--knowledge-dir",
            type=Path,
            default=default_dir,
            help=f"Diretório dos .md (default: {default_dir})",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Só reporta o que seria feito, sem gravar.",
        )

    def handle(self, *args, **options):
        knowledge_dir: Path = options["knowledge_dir"].resolve()
        dry_run: bool = options["dry_run"]

        if not knowledge_dir.is_dir():
            raise CommandError(f"Diretório não encontrado: {knowledge_dir}")

        paths = sorted(
            p for p in knowledge_dir.glob("*.md") if not p.name.startswith("_")
        )
        if not paths:
            self.stdout.write(self.style.WARNING(f"Nenhum .md em {knowledge_dir}"))
            return

        created_docs = 0
        updated_docs = 0
        skipped: list[str] = []
        domains_touched: set[str] = set()

        for path in paths:
            parsed = parse_markdown_file(path)
            if parsed is None:
                skipped.append(f"{path.name}: frontmatter inválido")
                continue

            meta, body = parsed
            slug = path.stem
            title = str(meta.get("title") or slug).strip()
            classification = normalize_classification(meta.get("classification"))
            sensitive = bool(meta.get("sensitive", False))
            owner = str(meta.get("owner") or "").strip()
            published = should_publish(classification, sensitive)

            try:
                with transaction.atomic():
                    domain = resolve_domain(meta.get("domain"), dry_run=dry_run)
                    domains_touched.add(domain.slug)

                    if dry_run:
                        exists = Document.objects.filter(slug=slug).exists()
                        action = "update" if exists else "create"
                        self.stdout.write(
                            f"  [dry-run] {action} Document slug={slug} "
                            f"domain={domain.slug} published={published}"
                        )
                        if exists:
                            updated_docs += 1
                        else:
                            created_docs += 1
                        continue

                    defaults = {
                        "title": title,
                        "domain": domain,
                        "classification": classification,
                        "sensitive": sensitive,
                        "owner": owner,
                        "body": body,
                        "is_published": published,
                    }
                    doc, created = Document.objects.update_or_create(
                        slug=slug,
                        defaults=defaults,
                    )
                    if created:
                        created_docs += 1
                        self.stdout.write(f"  + {slug} → {domain.slug}")
                    else:
                        updated_docs += 1
                        self.stdout.write(
                            f"  ~ {slug} → {domain.slug} (v{doc.version})"
                        )
            except Exception as exc:  # noqa: BLE001 — reportar arquivo e seguir
                skipped.append(f"{path.name}: {exc}")

        summary = (
            f"Domínios: {len(domains_touched)}. "
            f"Docs criados: {created_docs}, atualizados: {updated_docs}. "
            f"Ignorados: {len(skipped)}."
        )
        if dry_run:
            self.stdout.write(self.style.WARNING(f"[dry-run] {summary}"))
        else:
            self.stdout.write(self.style.SUCCESS(summary))
        for item in skipped:
            self.stdout.write(self.style.WARNING(f"  skip: {item}"))

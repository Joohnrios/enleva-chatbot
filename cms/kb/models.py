"""Domain / Document / DomainMembership — contrato em docs/ARCHITECTURE_DJANGO_CMS.md."""

from __future__ import annotations

import hashlib

from django.conf import settings
from django.db import models

from cms.core.models import AuditedModel


class Classification(models.TextChoices):
    PUBLICA = "Publica", "Pública"
    INTERNO = "Interno", "Interno"
    RESTRITA = "Restrita", "Restrita"
    CONFIDENCIAL = "Confidencial", "Confidencial"


class Domain(AuditedModel):
    slug = models.SlugField("slug", max_length=64, unique=True)
    name = models.CharField("nome", max_length=120)
    description = models.TextField("descrição", blank=True, default="")
    scope_seed = models.TextField(
        "texto-semente de escopo",
        help_text="Indexado como âncora de domínio (substitui DOMAIN_SEED_ANCHORS).",
    )
    contact_channel = models.CharField(
        "canal de contato",
        max_length=120,
        help_text="Ex.: GLPI, Atendimento ao Colaborador.",
    )
    contact_hint = models.CharField(
        "dica do canal",
        max_length=255,
        blank=True,
        default="",
    )
    is_active = models.BooleanField("ativo", default=True)

    class Meta:
        db_table = "kb_domain"
        ordering = ("name",)
        verbose_name = "domínio"
        verbose_name_plural = "domínios"

    def __str__(self) -> str:
        return self.name


class Document(AuditedModel):
    slug = models.SlugField("slug", max_length=120, unique=True)
    title = models.CharField("título", max_length=255)
    domain = models.ForeignKey(
        Domain,
        on_delete=models.PROTECT,
        related_name="documents",
        verbose_name="domínio",
    )
    classification = models.CharField(
        "classificação",
        max_length=32,
        choices=Classification.choices,
        default=Classification.INTERNO,
    )
    sensitive = models.BooleanField("sensível", default=False)
    owner = models.CharField("responsável", max_length=120, blank=True, default="")
    body = models.TextField("corpo (Markdown)")
    content_hash = models.CharField("hash do conteúdo", max_length=64, blank=True, default="")
    is_published = models.BooleanField(
        "publicado",
        default=False,
        help_text="Só publicados (+ gate Interno/sensitive) entram no índice.",
    )
    version = models.PositiveIntegerField("versão", default=1)

    class Meta:
        db_table = "kb_document"
        ordering = ("title",)
        verbose_name = "documento"
        verbose_name_plural = "documentos"
        indexes = [
            models.Index(fields=["is_published", "classification", "sensitive"]),
            models.Index(fields=["domain", "is_published"]),
        ]

    def __str__(self) -> str:
        return self.title

    def compute_content_hash(self) -> str:
        payload = (
            f"{self.slug}|{self.title}|{self.domain_id}|{self.classification}|"
            f"{self.sensitive}|{self.owner}|{self.body}"
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()[:16]

    def save(self, *args, **kwargs):
        self.content_hash = self.compute_content_hash()
        # Django 5.2+ update_or_create passa update_fields=defaults; garantir
        # que hash/versão calculados aqui entrem no UPDATE.
        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            update_fields = set(update_fields)
            update_fields.update({"content_hash", "version"})
            kwargs["update_fields"] = update_fields

        if not self._state.adding:
            previous = (
                Document.objects.filter(pk=self.pk)
                .only("content_hash", "version")
                .first()
            )
            if (
                previous
                and previous.content_hash
                and previous.content_hash != self.content_hash
            ):
                self.version = previous.version + 1
        super().save(*args, **kwargs)

    @property
    def is_indexable(self) -> bool:
        return (
            self.is_published
            and self.classification == Classification.INTERNO
            and not self.sensitive
            and self.domain_id is not None
            and self.domain.is_active
        )


class DomainMembership(AuditedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="domain_memberships",
        verbose_name="usuário",
    )
    domain = models.ForeignKey(
        Domain,
        on_delete=models.CASCADE,
        related_name="memberships",
        verbose_name="domínio",
    )
    can_add = models.BooleanField("pode criar", default=True)
    can_change = models.BooleanField("pode editar", default=True)
    can_delete = models.BooleanField("pode excluir", default=False)
    can_publish = models.BooleanField(
        "pode publicar",
        default=False,
        help_text="Publicar e alterar classification/sensitive que afetam o índice.",
    )

    class Meta:
        db_table = "kb_domain_membership"
        verbose_name = "vínculo usuário–domínio"
        verbose_name_plural = "vínculos usuário–domínio"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "domain"],
                name="kb_membership_user_domain_uniq",
            )
        ]

    def __str__(self) -> str:
        return f"{self.user} @ {self.domain}"

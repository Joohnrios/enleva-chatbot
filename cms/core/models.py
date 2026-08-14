"""BaseModel enxuto: UUID PK + auditoria (sem portar BaseModel gigante de outros produtos)."""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class UUIDModel(models.Model):
    """PK UUID — reduz enumeração e alinha FKs do FastAPI ao mesmo tipo."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        verbose_name="id",
    )

    class Meta:
        abstract = True


class AuditedModel(UUIDModel):
    """Timestamps + quem/de onde (IP) criou/alterou — complementar ao LogEntry do Admin."""

    created_at = models.DateTimeField("criado em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizado em", auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_created",
        verbose_name="criado por",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_updated",
        verbose_name="atualizado por",
    )
    created_from = models.CharField(
        "criado de (IP)",
        max_length=64,
        blank=True,
        default="",
    )
    updated_from = models.CharField(
        "atualizado de (IP)",
        max_length=64,
        blank=True,
        default="",
    )

    class Meta:
        abstract = True

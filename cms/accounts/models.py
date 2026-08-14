"""User com PK UUID — evita FK int misturado com Domain/Document UUID."""

from __future__ import annotations

import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        db_table = "accounts_user"
        verbose_name = "usuário"
        verbose_name_plural = "usuários"

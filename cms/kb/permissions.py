"""Regras de permissão por domínio — docs/ARCHITECTURE_DJANGO_CMS.md §1.3."""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth import get_user_model

from cms.kb.models import Domain, DomainMembership

User = get_user_model()


def client_ip(request) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return (request.META.get("REMOTE_ADDR") or "")[:64]


def is_kb_supereditor(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    group = getattr(settings, "KB_SUPEREDITOR_GROUP", "kb_supereditor")
    return user.groups.filter(name=group).exists()


def user_domain_ids(user, *, flag: str | None = None):
    """IDs de Domain do usuário. Se `flag` (ex. can_publish), exige esse boolean."""
    if not user or not user.is_authenticated:
        return Domain.objects.none().values_list("id", flat=True)
    if is_kb_supereditor(user):
        return Domain.objects.all().values_list("id", flat=True)
    qs = DomainMembership.objects.filter(user=user)
    if flag:
        qs = qs.filter(**{flag: True})
    return qs.values_list("domain_id", flat=True)


def membership_for(user, domain_id) -> DomainMembership | None:
    if not user or not domain_id:
        return None
    if is_kb_supereditor(user):
        # Supereditor: permissão total sintética (não precisa de linha)
        return None
    return DomainMembership.objects.filter(user=user, domain_id=domain_id).first()


def user_can_add(user, domain_id) -> bool:
    if is_kb_supereditor(user):
        return True
    m = membership_for(user, domain_id)
    return bool(m and m.can_add)


def user_can_change(user, domain_id) -> bool:
    if is_kb_supereditor(user):
        return True
    m = membership_for(user, domain_id)
    return bool(m and m.can_change)


def user_can_delete(user, domain_id) -> bool:
    if is_kb_supereditor(user):
        return True
    m = membership_for(user, domain_id)
    return bool(m and m.can_delete)


def user_can_publish(user, domain_id) -> bool:
    if is_kb_supereditor(user):
        return True
    m = membership_for(user, domain_id)
    return bool(m and m.can_publish)


def user_has_any_kb_access(user) -> bool:
    if not user or not user.is_authenticated or not user.is_staff:
        return False
    if is_kb_supereditor(user):
        return True
    return DomainMembership.objects.filter(user=user).exists()

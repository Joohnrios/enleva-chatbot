"""Admin KB com permissão por DomainMembership + can_publish (anti-bypass POST)."""

from __future__ import annotations

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied

from cms.kb.forms import DocumentAdminForm
from cms.kb.models import Document, Domain, DomainMembership
from cms.kb.permissions import (
    client_ip,
    is_kb_supereditor,
    user_can_add,
    user_can_change,
    user_can_delete,
    user_can_publish,
    user_domain_ids,
    user_has_any_kb_access,
)

PUBLISH_FIELDS = ("is_published", "classification", "sensitive")


class AuditedAdminMixin:
    """Carimba created_by/updated_by e IP a partir do request."""

    def save_model(self, request, obj, form, change):
        ip = client_ip(request)
        if not change:
            obj.created_by = request.user
            obj.created_from = ip
        obj.updated_by = request.user
        obj.updated_from = ip
        super().save_model(request, obj, form, change)


@admin.register(Domain)
class DomainAdmin(AuditedAdminMixin, admin.ModelAdmin):
    list_display = ("name", "slug", "contact_channel", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug", "contact_channel")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
        "created_from",
        "updated_from",
    )

    def has_module_permission(self, request):
        return is_kb_supereditor(request.user)

    def has_view_permission(self, request, obj=None):
        return is_kb_supereditor(request.user)

    def has_add_permission(self, request):
        return is_kb_supereditor(request.user)

    def has_change_permission(self, request, obj=None):
        return is_kb_supereditor(request.user)

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(Document)
class DocumentAdmin(AuditedAdminMixin, admin.ModelAdmin):
    form = DocumentAdminForm
    list_display = (
        "title",
        "slug",
        "domain",
        "classification",
        "sensitive",
        "is_published",
        "version",
        "updated_at",
    )
    list_filter = ("domain", "classification", "sensitive", "is_published")
    search_fields = ("title", "slug", "owner", "body")
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = (
        "id",
        "content_hash",
        "version",
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
        "created_from",
        "updated_from",
    )
    actions = ("action_publish", "action_unpublish")

    def get_form(self, request, obj=None, **kwargs):
        Form = super().get_form(request, obj, **kwargs)

        class RequestForm(Form):
            def __init__(self, *args, **kw):
                kw.setdefault("user", request.user)
                super().__init__(*args, **kw)

        return RequestForm

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if is_kb_supereditor(request.user):
            return qs
        return qs.filter(domain_id__in=user_domain_ids(request.user))

    def get_readonly_fields(self, request, obj=None):
        ro = list(super().get_readonly_fields(request, obj))
        domain_id = obj.domain_id if obj else None
        # Na criação ainda não há obj.domain; campos ficam editáveis no form e
        # o clean() força valores seguros sem can_publish.
        if obj and not user_can_publish(request.user, domain_id):
            for field in PUBLISH_FIELDS:
                if field not in ro:
                    ro.append(field)
        return ro

    def has_module_permission(self, request):
        return user_has_any_kb_access(request.user)

    def has_view_permission(self, request, obj=None):
        if not user_has_any_kb_access(request.user):
            return False
        if obj is None or is_kb_supereditor(request.user):
            return True
        return obj.domain_id in set(user_domain_ids(request.user))

    def has_add_permission(self, request):
        if is_kb_supereditor(request.user):
            return True
        return user_domain_ids(request.user, flag="can_add").exists()

    def has_change_permission(self, request, obj=None):
        if not request.user.is_staff:
            return False
        if obj is None:
            return user_has_any_kb_access(request.user)
        return user_can_change(request.user, obj.domain_id)

    def has_delete_permission(self, request, obj=None):
        if obj is None:
            return is_kb_supereditor(request.user) or user_domain_ids(
                request.user, flag="can_delete"
            ).exists()
        return user_can_delete(request.user, obj.domain_id)

    def save_model(self, request, obj, form, change):
        # Segunda linha de defesa além do form.clean (POST direto / race)
        previous = None
        if change and obj.pk:
            previous = Document.objects.filter(pk=obj.pk).first()
        domain_id = obj.domain_id
        if change and previous and not user_can_change(request.user, domain_id):
            raise PermissionDenied("Sem permissão para editar este domínio.")
        if not change and not user_can_add(request.user, domain_id):
            raise PermissionDenied("Sem permissão para criar neste domínio.")

        if not user_can_publish(request.user, domain_id):
            if previous:
                obj.is_published = previous.is_published
                obj.classification = previous.classification
                obj.sensitive = previous.sensitive
            else:
                obj.is_published = False

        super().save_model(request, obj, form, change)

    @admin.action(description="Publicar selecionados")
    def action_publish(self, request, queryset):
        updated = 0
        skipped = 0
        for doc in queryset:
            if not user_can_publish(request.user, doc.domain_id):
                skipped += 1
                continue
            if not doc.is_published:
                doc.is_published = True
                doc.updated_by = request.user
                doc.updated_from = client_ip(request)
                doc.save(update_fields=["is_published", "updated_by", "updated_from", "updated_at", "content_hash", "version"])
                updated += 1
        self.message_user(
            request,
            f"Publicados: {updated}. Ignorados (sem can_publish): {skipped}.",
            messages.INFO if updated else messages.WARNING,
        )

    @admin.action(description="Despublicar selecionados")
    def action_unpublish(self, request, queryset):
        updated = 0
        skipped = 0
        for doc in queryset:
            if not user_can_publish(request.user, doc.domain_id):
                skipped += 1
                continue
            if doc.is_published:
                doc.is_published = False
                doc.updated_by = request.user
                doc.updated_from = client_ip(request)
                doc.save(update_fields=["is_published", "updated_by", "updated_from", "updated_at", "content_hash", "version"])
                updated += 1
        self.message_user(
            request,
            f"Despublicados: {updated}. Ignorados (sem can_publish): {skipped}.",
            messages.INFO if updated else messages.WARNING,
        )


@admin.register(DomainMembership)
class DomainMembershipAdmin(AuditedAdminMixin, admin.ModelAdmin):
    list_display = (
        "user",
        "domain",
        "can_add",
        "can_change",
        "can_delete",
        "can_publish",
    )
    list_filter = ("domain", "can_publish", "can_delete")
    search_fields = ("user__username", "user__email", "domain__slug")
    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
        "created_from",
        "updated_from",
    )
    autocomplete_fields = ("user", "domain")

    def has_module_permission(self, request):
        return is_kb_supereditor(request.user)

    def has_view_permission(self, request, obj=None):
        return is_kb_supereditor(request.user)

    def has_add_permission(self, request):
        return is_kb_supereditor(request.user)

    def has_change_permission(self, request, obj=None):
        return is_kb_supereditor(request.user)

    def has_delete_permission(self, request, obj=None):
        return is_kb_supereditor(request.user)

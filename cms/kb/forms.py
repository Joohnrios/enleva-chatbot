"""Forms do Admin KB — anti-bypass de classification/sensitive/is_published."""

from __future__ import annotations

from django import forms
from django.core.exceptions import ValidationError

from cms.kb.models import Classification, Document, Domain
from cms.kb.permissions import (
    is_kb_supereditor,
    user_can_add,
    user_can_change,
    user_can_publish,
    user_domain_ids,
)


class DocumentAdminForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = "__all__"

    def __init__(self, *args, user=None, **kwargs):
        self._user = user
        super().__init__(*args, **kwargs)
        if user is None:
            return
        if is_kb_supereditor(user):
            return
        # Domínios permitidos: add na criação, change na edição
        if self.instance and self.instance.pk:
            allowed = user_domain_ids(user, flag="can_change")
        else:
            allowed = user_domain_ids(user, flag="can_add")
        self.fields["domain"].queryset = Domain.objects.filter(id__in=allowed)

    def clean(self):
        cleaned = super().clean()
        user = self._user
        if user is None:
            return cleaned

        domain = cleaned.get("domain") or getattr(self.instance, "domain", None)
        domain_id = getattr(domain, "id", None) or cleaned.get("domain_id")

        if self.instance and self.instance.pk:
            if not user_can_change(user, domain_id):
                raise ValidationError("Sem permissão para editar documentos deste domínio.")
            # Troca de domínio: precisa poder editar no destino
            if domain_id != self.instance.domain_id and not user_can_change(user, domain_id):
                raise ValidationError("Sem permissão no domínio de destino.")
        else:
            if not user_can_add(user, domain_id):
                raise ValidationError("Sem permissão para criar documentos neste domínio.")

        # Guardrail can_publish — também cobre POST forçando campos readonly
        if not user_can_publish(user, domain_id):
            if self.instance and self.instance.pk:
                cleaned["is_published"] = self.instance.is_published
                cleaned["classification"] = self.instance.classification
                cleaned["sensitive"] = self.instance.sensitive
            else:
                cleaned["is_published"] = False
                cleaned["classification"] = Classification.INTERNO
                cleaned["sensitive"] = False
            # Reaplica no instance para save()
            self.instance.is_published = cleaned["is_published"]
            self.instance.classification = cleaned["classification"]
            self.instance.sensitive = cleaned["sensitive"]

        return cleaned

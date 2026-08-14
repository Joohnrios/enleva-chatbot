"""Testes das regras DomainMembership / can_publish no Admin."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, TestCase
from django.urls import reverse

from cms.kb.forms import DocumentAdminForm
from cms.kb.models import Classification, Document, Domain, DomainMembership
from cms.kb.permissions import (
    is_kb_supereditor,
    user_can_publish,
    user_has_any_kb_access,
)

User = get_user_model()


class KbPermissionTests(TestCase):
    def setUp(self):
        self.rh = Domain.objects.create(
            slug="rh",
            name="RH",
            scope_seed="Recursos humanos férias ponto benefícios",
            contact_channel="Atendimento ao Colaborador",
        )
        self.ti = Domain.objects.create(
            slug="ti",
            name="TI",
            scope_seed="VPN senha notebook impressora",
            contact_channel="GLPI",
        )
        self.editor_rh = User.objects.create_user(
            username="editor_rh",
            password="pass-test-123",
            is_staff=True,
        )
        DomainMembership.objects.create(
            user=self.editor_rh,
            domain=self.rh,
            can_add=True,
            can_change=True,
            can_delete=False,
            can_publish=False,
        )
        self.publisher_rh = User.objects.create_user(
            username="publisher_rh",
            password="pass-test-123",
            is_staff=True,
        )
        DomainMembership.objects.create(
            user=self.publisher_rh,
            domain=self.rh,
            can_add=True,
            can_change=True,
            can_delete=True,
            can_publish=True,
        )
        self.doc_rh = Document.objects.create(
            slug="faq-rh-teste",
            title="FAQ RH",
            domain=self.rh,
            body="Conteúdo RH",
            is_published=False,
        )
        self.doc_ti = Document.objects.create(
            slug="faq-ti-teste",
            title="FAQ TI",
            domain=self.ti,
            body="Conteúdo TI",
            is_published=False,
        )

    def test_editor_only_sees_own_domain_in_admin_changelist(self):
        client = Client()
        client.force_login(self.editor_rh)
        url = reverse("admin:kb_document_changelist")
        resp = client.get(url)
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn("FAQ RH", content)
        self.assertNotIn("FAQ TI", content)

    def test_editor_cannot_publish_via_form_clean(self):
        form = DocumentAdminForm(
            data={
                "slug": "faq-rh-novo",
                "title": "Novo",
                "domain": str(self.rh.id),
                "classification": Classification.INTERNO,
                "sensitive": False,
                "owner": "RH",
                "body": "texto",
                "is_published": True,
                "version": 1,
            },
            user=self.editor_rh,
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertFalse(form.cleaned_data["is_published"])

    def test_publisher_can_publish(self):
        self.assertTrue(user_can_publish(self.publisher_rh, self.rh.id))
        form = DocumentAdminForm(
            instance=self.doc_rh,
            data={
                "slug": self.doc_rh.slug,
                "title": self.doc_rh.title,
                "domain": str(self.rh.id),
                "classification": Classification.INTERNO,
                "sensitive": False,
                "owner": "",
                "body": self.doc_rh.body,
                "is_published": True,
                "version": self.doc_rh.version,
            },
            user=self.publisher_rh,
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(form.cleaned_data["is_published"])

    def test_editor_post_cannot_force_publish_on_change(self):
        client = Client()
        client.force_login(self.editor_rh)
        url = reverse("admin:kb_document_change", args=[self.doc_rh.pk])
        resp = client.post(
            url,
            {
                "slug": self.doc_rh.slug,
                "title": self.doc_rh.title,
                "domain": str(self.rh.id),
                "classification": Classification.CONFIDENCIAL,
                "sensitive": "on",
                "owner": "",
                "body": self.doc_rh.body,
                "is_published": "on",
                "version": self.doc_rh.version,
                "_save": "Save",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.doc_rh.refresh_from_db()
        self.assertFalse(self.doc_rh.is_published)
        self.assertEqual(self.doc_rh.classification, Classification.INTERNO)
        self.assertFalse(self.doc_rh.sensitive)

    def test_supereditor_group(self):
        user = User.objects.create_user(
            username="supered",
            password="pass-test-123",
            is_staff=True,
        )
        group, _ = Group.objects.get_or_create(name="kb_supereditor")
        user.groups.add(group)
        self.assertTrue(is_kb_supereditor(user))
        self.assertTrue(user_has_any_kb_access(user))
        self.assertTrue(user_can_publish(user, self.ti.id))

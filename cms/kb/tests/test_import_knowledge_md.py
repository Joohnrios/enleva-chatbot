"""Testes do import knowledge/*.md → Domain/Document."""

from __future__ import annotations

from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from cms.kb.models import Classification, Document, Domain

SAMPLE_TI = """---
title: Acesso teste
classification: Interno
domain: TI
owner: Service Desk
sensitive: false
---

# Acesso teste

Corpo TI.
"""

SAMPLE_SKIP = """---
title: Confidencial
classification: Confidencial
domain: RH
owner: RH
sensitive: true
---

# Segredo

Não indexar.
"""

SAMPLE_RH = """---
title: Benefícios
classification: Interno
domain: RH
owner: RH
sensitive: false
---

# Benefícios

Texto RH.
"""


class ImportKnowledgeMdTests(TestCase):
    def setUp(self):
        self.kb = Path(self._test_dir())
        self.kb.mkdir(parents=True, exist_ok=True)
        (self.kb / "_TEMPLATE.md").write_text("# ignore\n", encoding="utf-8")
        (self.kb / "faq-ti-acesso.md").write_text(SAMPLE_TI, encoding="utf-8")
        (self.kb / "faq-rh-beneficios.md").write_text(SAMPLE_RH, encoding="utf-8")
        (self.kb / "SKIP-confidencial-exemplo.md").write_text(
            SAMPLE_SKIP, encoding="utf-8"
        )

    def _test_dir(self) -> str:
        # Diretório temporário por teste (Django TestCase)
        import tempfile

        if not hasattr(self, "_tmpdir"):
            self._tmpdir = tempfile.mkdtemp(prefix="kb_import_")
        return self._tmpdir

    def test_import_creates_domains_and_documents(self):
        call_command("import_knowledge_md", knowledge_dir=self.kb)
        self.assertEqual(Domain.objects.count(), 2)
        self.assertTrue(Domain.objects.filter(slug="ti").exists())
        self.assertTrue(Domain.objects.filter(slug="rh").exists())
        ti = Domain.objects.get(slug="ti")
        self.assertEqual(ti.contact_channel, "GLPI")
        self.assertIn("VPN", ti.scope_seed)

        self.assertEqual(Document.objects.count(), 3)
        doc_ti = Document.objects.get(slug="faq-ti-acesso")
        self.assertTrue(doc_ti.is_published)
        self.assertEqual(doc_ti.domain_id, ti.id)
        self.assertIn("Corpo TI", doc_ti.body)

        skip = Document.objects.get(slug="SKIP-confidencial-exemplo")
        self.assertFalse(skip.is_published)
        self.assertTrue(skip.sensitive)
        self.assertEqual(skip.classification, Classification.CONFIDENCIAL)

        self.assertFalse(Document.objects.filter(slug="_TEMPLATE").exists())

    def test_import_is_idempotent(self):
        call_command("import_knowledge_md", knowledge_dir=self.kb)
        call_command("import_knowledge_md", knowledge_dir=self.kb)
        self.assertEqual(Document.objects.count(), 3)
        self.assertEqual(Domain.objects.count(), 2)

    def test_dry_run_does_not_write(self):
        call_command("import_knowledge_md", knowledge_dir=self.kb, dry_run=True)
        self.assertEqual(Document.objects.count(), 0)
        self.assertEqual(Domain.objects.count(), 0)

    def test_reimport_updates_body(self):
        call_command("import_knowledge_md", knowledge_dir=self.kb)
        path = self.kb / "faq-ti-acesso.md"
        path.write_text(
            SAMPLE_TI.replace("Corpo TI.", "Corpo TI atualizado."),
            encoding="utf-8",
        )
        call_command("import_knowledge_md", knowledge_dir=self.kb)
        doc = Document.objects.get(slug="faq-ti-acesso")
        self.assertIn("atualizado", doc.body)
        self.assertGreaterEqual(doc.version, 2)

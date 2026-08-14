"""Testes da camada de leitura kb_* (repository) com mocks."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

from backend.app.db.repository import (
    DomainInfo,
    get_domain_contact,
    list_active_domains,
    list_indexable_documents,
)


def test_list_active_domains_empty_without_session():
    with patch("backend.app.db.repository.get_session", return_value=None):
        assert list_active_domains() == []


def test_get_domain_contact_matches_slug_or_name():
    domain = MagicMock()
    domain.id = uuid4()
    domain.slug = "ti"
    domain.name = "TI"
    domain.scope_seed = "senha VPN"
    domain.contact_channel = "GLPI"
    domain.contact_hint = "chamado TI"

    session = MagicMock()
    session.scalars.return_value.all.return_value = [domain]

    with patch("backend.app.db.repository.get_session", return_value=session):
        info = get_domain_contact("TI")
        assert info is not None
        assert info.contact_channel == "GLPI"
        assert info.slug == "ti"

        info2 = get_domain_contact("ti")
        assert info2 is not None

        assert get_domain_contact("rh") is None

    session.close.assert_called()


def test_list_indexable_documents_maps_rows():
    domain = MagicMock()
    domain.slug = "rh"
    domain.name = "RH"

    doc = MagicMock()
    doc.id = uuid4()
    doc.slug = "faq-rh"
    doc.title = "Benefícios"
    doc.classification = "Interno"
    doc.sensitive = False
    doc.owner = "RH"
    doc.body = "texto"
    doc.content_hash = "abc"
    doc.version = 1
    doc.domain = domain

    session = MagicMock()
    session.scalars.return_value.unique.return_value.all.return_value = [doc]

    with patch("backend.app.db.repository.get_session", return_value=session):
        rows = list_indexable_documents()
        assert len(rows) == 1
        assert rows[0].slug == "faq-rh"
        assert rows[0].domain_slug == "rh"


def test_domain_info_dataclass():
    d = DomainInfo(
        id="1",
        slug="ti",
        name="TI",
        scope_seed="x",
        contact_channel="GLPI",
        contact_hint="",
    )
    assert d.contact_channel == "GLPI"

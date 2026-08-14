# CMS Django — base de conhecimento Enleva

Dono do **schema Postgres** (`kb_domain`, `kb_document`, `kb_domain_membership`).  
Arquitetura: [`docs/ARCHITECTURE_DJANGO_CMS.md`](../docs/ARCHITECTURE_DJANGO_CMS.md).

## Princípios

- PK **UUID** em User, Domain, Document, DomainMembership
- `cms.core.AuditedModel`: created/updated + by + from (IP)
- FastAPI **não** migra estas tabelas; lê Domain/Document via SQLAlchemy (`backend/app/db/`)
- Admin com filtro por domínio e `can_publish` (anti-bypass POST)

## Docker Compose (recomendado)

```bash
docker compose up -d --build
# Admin: http://127.0.0.1:8001/admin/
docker compose exec cms python cms/manage.py createsuperuser
```

O serviço `cms` roda migrate (+ `import_knowledge_md` se `CMS_IMPORT_ON_START=true`) e gunicorn na porta **8001**.

## Permissões no Admin

| Papel | Como configurar | Efeito |
|-------|-----------------|--------|
| Superusuário / grupo `kb_supereditor` | `is_superuser` ou grupo criado na migração `0002` | Vê todos os domínios; Domain + Membership; pode publicar |
| Editor de domínio | `DomainMembership` com `can_add`/`can_change` | Só documentos do domínio; sem `can_publish` |
| Publicador | Membership com `can_publish=True` | Pode alterar `is_published`, `classification`, `sensitive` |

Sem `can_publish`, o Admin deixa esses campos readonly (edição) e o `DocumentAdminForm.clean` + `save_model` ignoram valores forçados no POST.

```bash
set CMS_USE_SQLITE=true
python cms/manage.py test kb.tests.test_admin_permissions
python cms/manage.py test kb.tests.test_import_knowledge_md
```

## Import dos Markdown (`knowledge/`)

Idempotente por `slug` (= nome do arquivo sem `.md`). Ignora `_TEMPLATE.md`.  
`Interno` + `sensitive: false` → `is_published=True`; SKIP/Confidencial entram não publicados.

```bash
set CMS_USE_SQLITE=true
python cms/manage.py import_knowledge_md --dry-run
python cms/manage.py import_knowledge_md
# equivalente: python -m scripts.import_knowledge_md
```

Domínios conhecidos (`ti`, `rh`, `admin`) recebem `scope_seed` e `contact_channel` de `cms/kb/domain_defaults.py`.

## Setup rápido (SQLite)

```bash
pip install -r cms/requirements.txt
set CMS_USE_SQLITE=true
python cms/manage.py migrate
python cms/manage.py createsuperuser
python cms/manage.py runserver 127.0.0.1:8001
```

Admin: http://127.0.0.1:8001/admin/

## Apps

| App | Papel |
|-----|--------|
| `accounts` | `User` UUID |
| `core` | `UUIDModel` / `AuditedModel` (abstratos) |
| `kb` | Domain, Document, DomainMembership |

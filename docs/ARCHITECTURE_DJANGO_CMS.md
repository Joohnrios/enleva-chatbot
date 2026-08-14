# Arquitetura — CMS Django Admin para a base de conhecimento

**Status:** implementação em andamento (CMS + ingest + pgvector + Redis feitos; SSO pendente)  
**Decisão de produto:** CMS da BC = **Django Admin**, não WordPress  
**Substitui:** [`docs/archive/WORDPRESS_KB_SYNC.md`](archive/WORDPRESS_KB_SYNC.md) (descartado)  
**PK:** todas as entidades de conteúdo usam **UUID** (`id` UUID v4), não inteiros sequenciais — reduz enumeração e alinha ao padrão de BaseModel auditável.

## Objetivo

Permitir que RH, TI e outras áreas **criem, editem e excluam** documentos da base com:

- permissão **granular por domínio/departamento**;
- trilha de **auditoria** (quem alterou o quê e quando);
- FastAPI continuando como **único** serviço no caminho do colaborador (chat, guardrails, RAG), lendo do Postgres (e, depois, pgvector) em vez de editar arquivos `.md`.

```text
Editor RH/TI  →  Django Admin (CMS)  →  Postgres
                                      ↘ (job/sinal) reindex → embeddings/pgvector
Colaborador   →  FastAPI (chat)      →  leitura Postgres/pgvector + Redis
```

Ordem de implementação:

1. Schema Domain/Document + permissões no Django (**feito** — app `cms/`)  
2. Import dos `.md` existentes (**feito** — `manage.py import_knowledge_md`)  
3. FastAPI leitura SQL + canal por domínio nas recusas (**feito** — `backend/app/db/` + Compose `cms`)  
4. Ingest a partir de `Document` publicados (**feito** — `INGEST_SOURCE=auto`)  
5. Migração de vetores Chroma → pgvector (**feito** — `VECTOR_STORE=pgvector`, tabelas `kb_chunk`/`kb_anchor`)  
6. Redis sessão/rate limit (**feito** — `REDIS_URL`, fallback memória)  
7. SSO Google Workspace no Admin (pendente)

---

## 0. BaseModel e UUID (segurança / consistência)

Código em `cms/core/models.py` (abstrato) e `cms/accounts/models.py` (User com UUID).

| Camada | Campos |
|--------|--------|
| `UUIDModel` | `id` UUID PK (`default=uuid4`, não editável) |
| `AuditedModel` | `created_at`, `updated_at`, `created_by`, `updated_by`, `created_from`, `updated_from` (IP, opcional) |

- **User** do CMS também é UUID (`AUTH_USER_MODEL = accounts.User`) — evita misturar PK int com FK UUID.  
- **Não** portamos o BaseModel “gigante” de outros produtos (pgbulk, template resolver, etc.): só UUID + auditoria. Extensões só quando o chatbot precisar.  
- FastAPI trata `id` / `domain_id` / `user_id` como **UUID string** no contrato SQL.

---

## 1. Schema mínimo

### 1.1 `Domain`

| Campo | Tipo | Uso |
|-------|------|-----|
| `id` | **UUID** PK | |
| `slug` | unique, ex. `ti`, `rh`, `operacoes` | Estável para APIs e permissões |
| `name` | string | Exibição (TI, RH, …) |
| `description` | text | Texto humano |
| `scope_seed` | text | Texto indexado como âncora de escopo (substitui `DOMAIN_SEED_ANCHORS` em Python) |
| `contact_channel` | string | Ex. `GLPI`, `Atendimento ao Colaborador` — resolve o TODO em `refusal_no_context` |
| `contact_hint` | string opcional | Frase curta para a mensagem de recusa |
| `is_active` | bool | Domínio desativado não entra em seeds/escopo |
| auditoria | herdada de `AuditedModel` | |

Seeds iniciais alinhados ao código atual: **RH**, **TI**, **Admin** (ver `backend/app/guardrails/local_scope.py`).

### 1.2 `Document`

Espelho do frontmatter em [`knowledge/_TEMPLATE.md`](../knowledge/_TEMPLATE.md):

| Campo | Tipo | Uso |
|-------|------|-----|
| `id` | **UUID** PK | |
| `slug` | unique | Ex. `faq-ti-acesso` (estável no import) |
| `title` | string | |
| `domain` | FK → Domain (UUID) | |
| `classification` | enum/string | `Interno` no MVP indexável; gate igual ao ingest atual |
| `sensitive` | bool | `false` para indexar no MVP |
| `owner` | string | Responsável textual |
| `body` | text | Markdown |
| `content_hash` | string | SHA-256 truncado do corpo+metadados relevantes (equiv. `_file_hash`) |
| `is_published` | bool | Só publicados elegíveis ao índice (além do gate) |
| `version` | int | Incrementa a cada save publicado |
| auditoria | herdada de `AuditedModel` | LogEntry + created_by/updated_by |

**Gate de indexação (inalterado em espírito):** só entra no índice se `classification` ∈ permitido (MVP: Interno), `sensitive=false`, `is_published=true`, domínio `is_active`.

Editores comuns trabalham em **rascunho** (`is_published=false`). Publicar (e alterar classificação/`sensitive` de forma que afete o índice) exige permissão `can_publish` — ver §1.3.

### 1.3 Permissão por domínio (não nativa no Admin)

Django Groups/Permissions padrão são **por modelo**, não por linha (`Document` do domínio RH vs TI). Por isso o desenho exige:

**`DomainMembership`**

| Campo | Uso |
|-------|-----|
| `user` | FK User |
| `domain` | FK Domain |
| `can_change` | bool (default true) — editar rascunho / metadados permitidos ao editor |
| `can_add` | bool — criar documento (nasce como rascunho) |
| `can_delete` | bool |
| `can_publish` | bool (default **false**) — marcar `is_published=true`, e alterar `classification` / `sensitive` quando isso afeta elegibilidade ao índice |

Mais um Group opcional `kb_supereditor` (staff que vê todos os domínios e, em regra, tem `can_publish`).

**Por que separar editar de publicar (recomendado já no schema MVP):**  
Sem `can_publish`, qualquer editor com `can_change` pode sozinho pôr `sensitive=false`, classificação indexável e publicar — o próximo reindex manda o trecho à Anthropic sem segunda checagem. Incluir o flag **agora** é barato; acrescentar depois que o fluxo já estiver em uso é caro (hábitos + dados já publicados).

**Comportamento no `ModelAdmin` (a implementar depois):**

1. `get_queryset(request)` — se não for superuser/`kb_supereditor`, filtrar `Document` com `domain_id ∈ memberships do user`.
2. `has_module_permission` / `has_view_permission` — staff com pelo menos um membership.
3. `has_add_permission` — membership com `can_add` no domínio escolhido no form; documento novo com `is_published=false`.
4. `has_change_permission` / `has_delete_permission` — membership no `obj.domain` com flag correspondente.
5. Campos `is_published`, `classification`, `sensitive`: read-only no form se o usuário **não** tiver `can_publish` naquele domínio (exceto supereditor). Tentativa de bypass via POST rejeitada no `save_model` / `clean`.
6. Form de `Document`: campo `domain` limitado aos domínios do usuário (exceto supereditor).
7. `Domain` Admin: criação/edição de domínios restrita a superuser/TI plataforma (não a cada editor de FAQ).
8. Ação “Publicar” / “Despublicar” no Admin só para quem tem `can_publish`; despublicar remove do índice no próximo reindex (ou job imediato).

Isso é o mecanismo documentado para “RH só edita RH” **e** “nem todo editor publica sozinho”; sem o filtro por membership, Groups globais em `Document` **não** bastam.

### 1.4 Auditoria (POL / seção 5.9–5.11) — decisão do CG-SI

**`django.contrib.admin.models.LogEntry`** (nativo): registra add/change/delete no Admin com usuário, timestamp, `object_id`, `object_repr`, `change_message` (quais campos mudaram — **não** o diff completo do `body`).

| Necessidade | LogEntry | Complemento se CG-SI exigir |
|-------------|----------|-----------------------------|
| Quem criou/alterou/removeu e quando | Sim | — |
| Qual documento (id/repr) | Sim | Manter `slug`/`title` estáveis no repr |
| Saber que `classification` / `sensitive` / `body` mudaram | Parcial (`change_message`) | — |
| Diff completo do corpo / valor anterior de classificação | **Não** | `django-simple-history` ou `DocumentRevision` desde o dia 1 |
| Ações fora do Admin (script import, reindex) | Não | Log de aplicação / job com user de serviço |
| Retenção | Não automática | Job de purge no prazo que a POL/CG-SI definir |

**Pergunta explícita ao CG-SI (não fechar só em engenharia):**

> Para a BC editável no Django Admin, **LogEntry + usuário + timestamp + lista de campos alterados + retenção** basta para POL 5.9/5.11, ou vocês exigem **histórico de conteúdo completo** (texto anterior do `body` e valores anteriores de `classification`/`sensitive`) desde o primeiro dia de uso?

**Motivo da pergunta:** classificação/`sensitive` decidem se o trecho entra no índice e é enviado à Anthropic. Só “o campo mudou” sem “de que para quê / qual era o texto” pode ser insuficiente para investigação.  
**Postura de engenharia até a resposta:** schema MVP inclui LogEntry + `created_by`/`updated_by` + retenção; se CG-SI pedir histórico completo, acrescentar `DocumentRevision` (ou equivalent) **antes** do go-live do Admin — não depois de meses de edição sem trilha.

---

## 2. Dono do schema

| Responsável | Escopo |
|-------------|--------|
| **Django** | Dono das **migrations** de `Domain`, `Document`, `DomainMembership`, e (quando existirem) tabelas de chunks/âncoras/pgvector criadas pelo app CMS |
| **FastAPI** | **Sem** migrations nessas tabelas; leitura (e depois upsert de embeddings) via SQLAlchemy/asyncpg |

### Contrato de leitura FastAPI (estável)

Mudanças de coluna no Django que quebrem estes nomes/semânticas exigem versão coordenada do FastAPI:

**Tabela `kb_domain`:**

- `id` (UUID), `slug`, `name`, `scope_seed`, `contact_channel`, `contact_hint`, `is_active`

**Tabela `kb_document`:**

- `id` (UUID), `slug`, `title`, `domain_id` (UUID), `classification`, `sensitive`, `owner`, `body`, `content_hash`, `is_published`, `version`, `updated_at`

**Regra:** publicar contrato em comentário/migration inicial + este doc. FastAPI mapeia só o necessário ao RAG; não espelha o ORM Django.

Reindex após publish: sinal Django / webhook autenticado → endpoint admin do FastAPI (mesmo espírito do `ADMIN_TOKEN` atual), **sem** o Django chamar o LLM.

---

## 3. Plano Chroma → Postgres/pgvector

### 3.1 Encapsulamento

Hoje `chromadb` aparece **somente** em [`backend/app/rag/store.py`](../backend/app/rag/store.py). Callers usam `KnowledgeStore` / `get_store()`:

- `retriever.py`, `local_scope.py`, `ingest.py`, `routes_health.py`

**Regra de migração:** nova implementação (ex. `PgvectorKnowledgeStore`) atrás da **mesma API** (`query`, `upsert_chunks`, `upsert_anchors`, `delete_by_source`/`delete_by_document_id`, `source_hashes`→`content_hashes`, `max_anchor_similarity`, `count`, `reset`). Nenhum SQL de vetor em orchestrator/guardrails/routes.

Ingest deixa de varrer `./knowledge/*.md` e passa a ler documentos publicados no Postgres; o gate de classificação permanece no pipeline (e espelhado no Admin).

### 3.2 Estratégia de corte (recomendação)

**Cutover direto com janela de teste em staging** — não dual-write prolongado.

| Motivo | |
|--------|--|
| Volume atual | Poucos documentos; reindex completo é barato |
| Dual-write | Dobra complexidade (dois stores, dois caminhos de delete/hash, risco de divergência) |
| Encapsulamento | Troca concentrada em `store.py` + ingest |

Procedimento:

1. Staging: Postgres+pgvector populado (import + reindex).  
2. Golden tests + amostra RH/TI.  
3. Cutover produção: apontar FastAPI para pgvector; manter volume Chroma **somente backup** por N dias; rollback = reapontar + reindex Chroma se necessário.  
4. Remover dependência `chromadb` quando estável.

Dual-write só como plano B se o cutover em staging falhar por regressão difícil de isolar.

### 3.3 `DOMAIN_SEED_ANCHORS` → dados

Hoje seeds RH/TI/Admin estão hardcoded em `local_scope.py`.

Após Domain no banco:

1. Import cria/atualiza `Domain` com `scope_seed` = texto atual das âncoras.  
2. Pipeline de reindex monta âncoras `kind=seed` a partir de `Domain.objects.filter(is_active=True)`.  
3. Remover (ou deixar fallback de emergência) o dict Python — **domínio novo só no Admin deve gerar seed no próximo reindex**, senão o classificador local fica cego (risco já identificado).

`contact_channel` do Domain alimenta `refusal_no_context(domain=...)` (TODO atual em `prompts.py`).

---

## 4. Import inicial dos `.md`

Script único (ex. `python -m scripts.import_knowledge_md`), uma vez:

1. Ler `knowledge/*.md` (ignorar `_TEMPLATE`, respeitar SKIP/confidencial como não publicados ou `sensitive=true`).  
2. Frontmatter → colunas; body → `body`; hash arquivo → `content_hash`; nome do arquivo → `slug`.  
3. Resolver/criar `Domain` pelo campo `domain`.  
4. Idempotente por `slug` (re-rodar não duplica).

### Depois do cutover: o que fazer com `./knowledge`

**Recomendação:** manter por um período como **export/backup gerado pelo Admin** (job “exportar Markdown”), não como fonte editável.

| Fase | `./knowledge` |
|------|----------------|
| Pré-cutover | Fonte canônica (hoje) |
| Pós-import estável | Somente export opcional + cópia em Git se desejado |
| Longo prazo | Descontinuar volume de escrita no compose; watcher de arquivos desligado |

**Não** manter edição dual (arquivo **e** Admin) — duas fontes de verdade.

---

## 5. Hospedagem e exposição

### 5.1 Servidor

**Recomendação confirmada:** stack do chatbot (**FastAPI + Postgres [+ Redis depois] + Django Admin**) em **host separado** do VPS do WordPress.

Motivos: RAM do modelo de embeddings no FastAPI; blast radius; operação independente do WP. Postgres/Redis/Django são modestos; o que aperta o VPS compartilhado é **WP + torch/embeddings juntos**.

### 5.2 Exposição do Django Admin

O Admin **não** fica aberto na internet como o widget/demo.

Opções (da mais restritiva à mais prática para RH/TI remoto):

| Opção | Prós | Contras |
|-------|------|---------|
| A. Só VPN / rede corporativa | Superfície mínima | RH/TI fora da rede precisam VPN |
| B. URL pública atrás de **SSO + MFA** + allowlist opcional | Acesso de qualquer lugar com controle | Precisa de IdP (ver abaixo — na Enleva provavelmente já existe) |
| C. Só senha Django na internet | Inaceitável para este risco | — |

#### IdP na Rede Enleva (Google Workspace)

A intranet já usa **Google Workspace** (Gmail, Calendar, Drive, Meet). Isso é um **IdP OIDC/OAuth maduro** e, na prática, remove o maior “contra” da Opção B (“exige IdP do zero”).

Caminho técnico previsto (quando implementar, não neste doc):

- Login do Admin via **Google OAuth** (ex. `django-allauth` provider Google), restrito ao domínio Workspace da Enleva (`hd=` / allowlist de e-mails).
- Contas Django `is_staff` provisionadas ou vinculadas ao e-mail Google; **sem** cadastro aberto.
- MFA: preferir a do **Google** (já exigida/corporativa) e/ou camada no proxy (Cloudflare Access com IdP Google). Não depender só de senha local Django.
- Confirmar com TI: OAuth client no Google Cloud, usuários do domínio que podem ser editores, e se há política de bloquear apps OAuth de terceiros.

**Recomendação atualizada:** preferir **Opção B com Google Workspace como IdP**, salvo se a política interna exigir VPN obrigatória para qualquer ferramenta de conteúdo — aí **A**, ou **A+B** (VPN + SSO). Em todos os casos: HTTPS, staff only, rate limit no proxy, cookie de sessão do Admin **separado** do chat.

FastAPI `/chat` continua no desenho de auth de **colaborador** (prompt de arquitetura separado). Django Admin = identidade de **editor de conteúdo** (conta Google corporativa + membership por domínio).

---

## 6. O que NÃO fazer

Documentado para não reabrir sem nova decisão formal:

1. **Não** implementar UI de CMS dentro do FastAPI.  
2. **Não** manter [`WORDPRESS_KB_SYNC.md`](archive/WORDPRESS_KB_SYNC.md) como plano B ativo — está **DESCARTADO**; CMS = Django Admin.  
3. **Não** misturar autenticação de sessão do colaborador (chat) com autenticação de editores no Django Admin — públicos, riscos e ciclos de vida diferentes.  
4. **Não** usar Groups globais em `Document` sem filtro por `DomainMembership` e achar que “permissão por departamento” está resolvida.  
5. **Não** permitir que editor com só `can_change` publique ou altere sozinho `classification`/`sensitive` de forma indexável — isso exige `can_publish`.  
6. **Não** cadastrar domínio novo sem `scope_seed` + reindex de âncoras.  
7. **Não** expor Django Admin só com senha local na internet aberta (sem SSO/VPN).  
8. **Não** colocar Redis como pré-requisito do CMS (fase posterior).  
9. **Não** editar em paralelo `.md` no volume e Admin após o cutover.  
10. **Não** assumir sozinho que LogEntry basta para POL 5.9/5.11 — pergunta formal ao CG-SI (§1.4).

---

## Relação com o código atual (referência)

| Peça atual | Destino |
|------------|---------|
| `knowledge/*.md` + frontmatter | `Document` + import |
| `DOMAIN_SEED_ANCHORS` | `Domain.scope_seed` |
| `refusal_no_context` hardcoded GLPI/RH | `Domain.contact_channel` |
| `KnowledgeStore` / Chroma | Mesma interface, backend pgvector |
| `ingest_knowledge` / watcher / `POST /admin/reindex` | Reindex a partir do Postgres |
| Rate limit / sessão em memória | Redis (fase posterior; ver README) |

---

## Checklist de aprovação deste documento

| Item | Status engenharia | Pendência |
|------|-------------------|-----------|
| Schema Domain/Document/Membership | Aprovado | — |
| `can_publish` separado de editar (rascunho vs índice) | **Incluído no schema MVP** (§1.3) | Confirmar papéis: quem na RH/TI terá publish |
| Cutover (não dual-write) | Aprovado | — |
| WordPress sync descartado | Feito | — |
| Host separado do WP | Recomendado | Dimensionar host na implantação |
| Acesso Admin: VPN vs SSO+MFA | Preferir **B + Google Workspace** (§5.2) | TI confirma OAuth/`hd` do domínio |
| LogEntry vs histórico completo de conteúdo | **Pergunta ao CG-SI** (§1.4) | Resposta formal antes do go-live do Admin |

Só após checklist fechado (incluindo CG-SI em auditoria): implementação na ordem schema → import → permissões Admin (incl. publish) → leitura FastAPI / canais → migração vetorial.

**Progresso código:** schema, import, permissões, SQL/canais, Compose `cms`, ingest Postgres, pgvector, **Redis** — **feitos**. Restam SSO Admin e checklist SI/host. Rollback vetorial: `VECTOR_STORE=chroma` + reindex.

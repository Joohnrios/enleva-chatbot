# Chatbot Interno RAG — Rede Enleva

Assistente interno baseado em RAG (Retrieval-Augmented Generation) para reduzir chamados repetitivos de **RH** e **TI**.

O nome do bot é configurável via `BOT_NAME` no `.env` (sem alteração de código).

## Stack

- Python + FastAPI (chat / RAG)
- Django Admin (CMS da BC) + Postgres + **pgvector**
- Embeddings locais (`sentence-transformers`)
- LLM desacoplado: Anthropic Claude (padrão), OpenAI, Gemini
- Widget flutuante embutível (`frontend/`)
- Redis (rate limit + sessão); Chroma como **rollback** (`VECTOR_STORE=chroma`)

## Estrutura do repositório

```text
backend/          # FastAPI, RAG, guardrails, SQL read-only
cms/              # Django Admin (dono do schema kb_*)
frontend/         # Widget embutível
knowledge/        # Seed Markdown (import → Postgres)
scripts/
  ops/            # ingest, import, purge, métricas
  archive/        # one-shots históricos (planilha de custos)
tests/            # Pytest da API
docs/             # Arquitetura, SI, custos
  archive/        # Docs descartados / supersedidos
data/             # Volumes runtime (gitignored; só .gitkeep)
```

## Setup rápido (local / bare-metal)

```bash
cd enleva-chatbot
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux/macOS
# source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env   # ou cp .env.example .env
```

Edite `.env` e preencha pelo menos:

- `BOT_NAME`
- `ANTHROPIC_API_KEY` (se `LLM_PROVIDER=anthropic`)
- `ADMIN_TOKEN`

### Indexar a base

```bash
python -m scripts.ingest
```

### Subir a API

```bash
uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

- Health: http://127.0.0.1:8000/health  
- Docs: http://127.0.0.1:8000/docs  
- Demo widget: http://127.0.0.1:8000/demo.html  

### Testar chat (Postman/curl)

```bash
curl -X POST http://127.0.0.1:8000/chat ^
  -H "Content-Type: application/json" ^
  -d "{\"message\":\"Como resetar a senha da VPN?\"}"
```

### Reindexar via API

```bash
curl -X POST http://127.0.0.1:8000/admin/reindex ^
  -H "X-Admin-Token: SEU_ADMIN_TOKEN"
```

### Testes

```bash
pytest -q
```

## Rodando com Docker

Infraestrutura pronta para o piloto (Etapa 4). Segredos entram só via `.env` em runtime (`env_file`) — **nunca** são copiados para a imagem.

### 1. Preparar `.env`

```bash
copy .env.example .env   # ou cp .env.example .env
```

Preencha pelo menos `ANTHROPIC_API_KEY` (ou o provedor escolhido) e `ADMIN_TOKEN`.

### 2. Build e subir

```bash
docker compose build
docker compose up -d
```

Sobe **postgres** (pgvector) + **redis** + **cms** (:8001) + **enleva-chatbot** (:8000).  

Se você já tinha volume `./data/postgres` com a imagem `postgres:16-alpine` antiga, apague o volume uma vez (`docker compose down` + remover `data/postgres`) antes do primeiro start com pgvector — a extensão `vector` exige a imagem nova.
Aguarde o healthcheck do chatbot (primeiro start pode levar ~1–2 min enquanto carrega o modelo já bakeado na imagem).

Superuser do Admin (uma vez):

```bash
docker compose exec cms python cms/manage.py createsuperuser
```

### 3. Verificar health

```bash
curl http://localhost:8000/health
```

Esperado: JSON com `"status":"ok"` e `index_ready: true` após a ingestão inicial.

Demo: http://localhost:8000/demo.html

### 4. Reindexar a base

Via API (recomendado) — **sem rebuild da imagem**:

```bash
curl -X POST http://localhost:8000/admin/reindex ^
  -H "X-Admin-Token: SEU_ADMIN_TOKEN"
```

Ou dentro do container:

```bash
docker compose exec enleva-chatbot python -m scripts.ingest
```

Ver também a seção **Atualizar a base sem deploy** abaixo.

### Volumes

| Host | Container | Motivo |
|------|-----------|--------|
| `./knowledge` | `/app/knowledge` | BC atualizável sem rebuild da imagem |
| `./data/chroma` | `/app/data/chroma` | Persistência do índice entre restarts |
| `./data/logs` | `/app/data/logs` | Logs para retenção/purge |

### Reindex no start e por mudança

No startup o serviço executa `ingest_knowledge` em modo **incremental**:

- Com `INGEST_SOURCE=auto` (padrão), se houver documentos publicados no Postgres, indexa a partir do CMS (`content_hash`); senão usa `./knowledge/*.md`.
- Vector store padrão no Compose: **`VECTOR_STORE=pgvector`** (tabelas `kb_chunk` / `kb_anchor`). Rollback: `VECTOR_STORE=chroma` + `POST /admin/reindex?full=true`.
- Compara hash com o índice — se nada mudou, o boot não re-embeda a base inteira.
- `full=true` no `/admin/reindex` (ou `INGEST_FORCE_FULL=true`) força `reset` + reindex completo.

Com ingest via Postgres, o watcher de `./knowledge` fica **desligado**; após publicar no Admin, use `POST /admin/reindex`. Com fonte em arquivos e `KNOWLEDGE_WATCH_ENABLED=true`, mudanças em `./knowledge` disparam reindex após debounce.

### Réplicas e Redis

Com `REDIS_URL` (padrão no Compose: `redis://redis:6379/0`), **rate limit** e **histórico multi-turno** são compartilhados entre workers/réplicas.

Sem Redis (`REDIS_URL` vazio), ambos ficam em memória de um processo — nesse caso **não** escale `enleva-chatbot`.

### Parar / logs

```bash
docker compose logs -f enleva-chatbot
docker compose down
```

## Base de conhecimento

**Fonte canônica (Compose):** documentos no Postgres via Django Admin (`cms`).  
`INGEST_SOURCE=auto` indexa publicados (`Interno`, não sensíveis). O diretório `knowledge/` permanece para import inicial / fallback.

Frontmatter legado (import / fallback arquivos):

```yaml
---
title: ...
classification: Interno
domain: TI
owner: ...
sensitive: false
---
```

No MVP só indexa `classification: Interno` e `sensitive: false`. Modelo: [`knowledge/_TEMPLATE.md`](knowledge/_TEMPLATE.md).

### Atualizar a base **sem deploy** (runbook do piloto)

**Preferido:** editar/publicar no Admin (`:8001`) e chamar `POST /admin/reindex` no chatbot.

**Fallback arquivos:** editar `./knowledge` (volume montado) com `INGEST_SOURCE=files` — o índice atualiza via watcher ou reindex.

1. Edite, adicione ou remova arquivos `.md` em `./knowledge` no **host** (respeitando o frontmatter e a classificação).
2. Reindexe (ingestão incremental por hash — só reprocessa o que mudou):

```bash
curl -X POST http://localhost:8000/admin/reindex ^
  -H "X-Admin-Token: SEU_ADMIN_TOKEN"
```

Forçar rebuild completo do índice (raro):

```bash
curl -X POST "http://localhost:8000/admin/reindex?full=true" ^
  -H "X-Admin-Token: SEU_ADMIN_TOKEN"
```

3. Confira a resposta (`indexed_files`, `unchanged_files`, `removed_files`, `skipped_files`) e, se quiser, `GET /health` (`index_ready`, `indexed_chunks`).

Com `KNOWLEDGE_WATCH_ENABLED=true` (padrão), alterações em `knowledge/` também disparam reindex automático após um debounce — o `POST /admin/reindex` continua disponível para force manual.

**Permissões:** restrinja escrita em `./knowledge` a TI (ou grupo dono). Não exponha a pasta anonimamente.

### CMS Django (schema Postgres + Admin)

Arquitetura: [`docs/ARCHITECTURE_DJANGO_CMS.md`](docs/ARCHITECTURE_DJANGO_CMS.md).  
Django é dono das tabelas `kb_*`. O FastAPI **lê** Domain (canais/seeds) via SQL; o ingest RAG ainda usa `./knowledge` + Chroma nesta fase.

**Com Docker Compose** (recomendado): sobe `postgres` + `cms` (:8001) + `enleva-chatbot` (:8000).

```bash
docker compose up -d --build
# Admin: http://127.0.0.1:8001/admin/
docker compose exec cms python cms/manage.py createsuperuser
```

No primeiro start, com `CMS_IMPORT_ON_START=true` (padrão no compose), o CMS importa `knowledge/*.md` para o Postgres.

**Dev local sem Docker:**

```bash
pip install -r cms/requirements.txt
set CMS_USE_SQLITE=true
python cms/manage.py migrate
python cms/manage.py createsuperuser
python cms/manage.py runserver 127.0.0.1:8001
```

## Segurança (POL RBD TI 001)

Antes de sair do localhost, seguir `docs/SEGURANCA_REVISAO_SI.md` (aprovação de fornecedor + revisão SI).

### Proteção provisória do `/chat` (intranet pública)

A intranet é alcançável pela internet; CORS **não** bloqueia `curl`/clientes diretos. Enquanto não houver autenticação de sessão real:

1. **`WIDGET_API_TOKEN` (obrigatório)** — toda chamada a `/chat` exige o header `X-Widget-Token` igual ao valor do `.env` (comparação em tempo constante). Sem token ou token errado → **401** antes de RAG/LLM. O widget obtém o valor em `/config/public` (ou `EnlevaChatConfig.apiToken`).
2. **`ALLOWED_ORIGINS`** (fallback: `CORS_ORIGINS`) — `/chat` exige `Origin` ou `Referer` compatível. Origem ausente/estranha → **401**.
3. **Rate limit mais baixo** no piloto controlado (`10/minute` IP, `15/minute` sessão) — revisar para cima quando a auth real existir.

**Isto NÃO é autenticação.** O token é visível no JavaScript do navegador e Origin/Referer são forjáveis. Serve só como barreira contra descoberta casual e scanners automatizados. Autenticação de colaborador logado (token de sessão emitido pelo WordPress) fica como próximo desenho de arquitetura — não implementada neste MVP.

### Rate limiting

O endpoint `/chat` limita por **IP** (`RATE_LIMIT_CHAT`) e por **`session_id`** (`RATE_LIMIT_CHAT_SESSION`). O mais restritivo vence; ao estourar → **HTTP 429**.

Com `REDIS_URL`, contadores ficam no Redis (janela deslizante). Sem Redis, usam memória de processo (adequado a 1 worker).

### Contexto multi-turno

Histórico curto por `session_id` (`SESSION_MAX_TURNS`, `SESSION_TTL_MINUTES`). Com Redis, sobrevive a restart/réplica; sem Redis, reinício zera o contexto. Logs JSONL em `data/logs/` não são afetados.

Tematização do widget: ver [`frontend/THEMING.md`](frontend/THEMING.md).

## Widget na intranet

```html
<script>
  window.EnlevaChatConfig = {
    apiUrl: "https://SERVIDOR-INTERNO/chat",
    position: "right"
    // apiToken opcional: se omitido, o widget usa widget_api_token de /config/public
  };
</script>
<script src="https://SERVIDOR-INTERNO/static/widget.js" defer></script>
```

## Scripts úteis

| Comando | Função |
|---------|--------|
| `python -m scripts.ingest` | Reindexa BC |
| `python -m scripts.purge_logs` | Descarta logs expirados (`LOG_RETENTION_DAYS`, default 90) |
| `python -m scripts.pilot_metrics` | Conta métricas do piloto |

### Agendamento do purge de logs

O processo FastAPI:

1. Executa `purge_expired_logs` no **startup** (`lifespan`) — rede de segurança em todo restart.
2. Mantém um **agendador interno** (asyncio) que roda o purge diariamente em `LOG_PURGE_HOUR_UTC` (default `3` = 03:00 UTC).

Isso vale para **Docker e bare-metal** quando a API sobe via `uvicorn` / `docker compose`. Não é necessário configurar cron dentro do container.

#### Só para deploys fora de container (bare-metal / VM) sem o processo da API 24×7

Se a API não fica sempre ligada, o agendador interno não cobre o intervalo offline. Nesse caso, agende o script no SO:

**Linux / cron** (exemplo: todo dia às 03:00):

```bash
0 3 * * * cd /caminho/para/enleva-chatbot && .venv/bin/python -m scripts.purge_logs >> /var/log/enleva-purge.log 2>&1
```

**Windows / Task Scheduler** (resumo):

1. Abra o Agendador de Tarefas → Criar Tarefa Básica.
2. Disparador: Diariamente (ex. 03:00).
3. Ação: Iniciar um programa.
4. Programa/script: `C:\Users\...\enleva-chatbot\.venv\Scripts\python.exe`
5. Argumentos: `-m scripts.purge_logs`
6. Iniciar em: `C:\Users\...\enleva-chatbot`
7. Confirme e teste com “Executar” uma vez; o stdout indica quantos arquivos foram removidos.

Manual a qualquer momento:

```bash
python -m scripts.purge_logs
```

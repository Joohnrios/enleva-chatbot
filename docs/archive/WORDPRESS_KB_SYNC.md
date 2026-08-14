---
STATUS: DESCARTADO
Decisão formal: CMS da BC = Django Admin, não WordPress.
Documento vigente: docs/ARCHITECTURE_DJANGO_CMS.md
---

# Sincronização da base de conhecimento via WordPress (Fase 2) — ARQUIVO HISTÓRICO

> **Não implementar.** Mantido só como histórico. Qualquer trabalho de CMS deve seguir `docs/ARCHITECTURE_DJANGO_CMS.md`.

O bot continua sendo **consumidor** de Markdown em `./knowledge` + reindex.
O WordPress (intranet Enleva) permanece o lugar onde RH/TI já edita conteúdo.
Não implementar CMS dentro do FastAPI.

## Visão geral (obsoleta)

```text
Dono RH/TI → CPT/página WP → export .md (frontmatter) → volume knowledge/
                         ↘ webhook autenticado → POST /admin/reindex → Chroma
```

## Peças

### 1. CPT ou páginas no WordPress

Campos sugeridos (espelham `knowledge/_TEMPLATE.md`):

| Campo WP | Frontmatter / uso |
|----------|-------------------|
| Título | `title` |
| Domínio (RH / TI) | `domain` |
| Classificação | `classification` — no MVP só **Interno** |
| Sensível | `sensitive` — deve ser `false` para indexar |
| Owner / responsável | `owner` |
| Corpo | Markdown ou HTML→MD |

O gate de classificação no ingest **não muda**: Restrito/Confidencial ou `sensitive=true` não entram no índice sem decisão formal.

### 2. Export para `./knowledge`

Job ou plugin que, ao publicar/atualizar/apagar:

1. Gera (ou remove) um `.md` no volume montado pelo container (`./knowledge` no host → `/app/knowledge`).
2. Nome estável por slug (ex.: `faq-ti-vpn.md`) para o ingest incremental por `file_hash` funcionar bem.
3. Inclui o YAML frontmatter completo.

Alternativa: API do bot recebendo o Markdown (futuro) — o volume + arquivo continua sendo a fonte canônica mais simples no piloto.

### 3. Webhook de reindex

Após gravar o arquivo:

```http
POST /admin/reindex
X-Admin-Token: <ADMIN_TOKEN>
```

- Use o mesmo `ADMIN_TOKEN` do `.env` (segredo de servidor — **não** embutir no JS público).
- Opcional: `?full=true` só se precisar reconstruir o índice do zero.
- Resposta: `indexed_files`, `unchanged_files`, `removed_files`, `skipped_files`.

Com `KNOWLEDGE_WATCH_ENABLED=true`, o watcher no container também reindexa ao detectar mudança no volume; o webhook continua útil para sync imediato e para ambientes sem watcher.

### 4. Auth de sessão WordPress (pré-requisito de produto)

A edição na intranet e o uso do chat por colaborador autenticado fazem parte da conversa de arquitetura de auth. Este documento cobre só o **fluxo de conteúdo** (CPT → MD → reindex). Não misturar “login do bot” com “CMS no FastAPI”.

## O que não fazer

- UI de CMS no FastAPI (duplica o WP).
- Sync SharePoint/Drive como segunda fonte de verdade antes de validar o fluxo WP.
- Expor escrita anônima em `knowledge/` ou o `ADMIN_TOKEN` no widget.

## Checklist de implementação (quando sair do piloto)

- [ ] CPT (ou páginas) com campos de classificação + domínio
- [ ] Export Markdown + frontmatter para o volume
- [ ] Webhook autenticado → `POST /admin/reindex`
- [ ] Permissões: só papéis RH/TI donos publicam no CPT
- [ ] Teste: editar no WP → arquivo no host → chunks atualizados sem `docker compose build`

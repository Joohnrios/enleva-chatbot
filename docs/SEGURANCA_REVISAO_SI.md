# Dossiê de Segurança — Chatbot Interno RAG (Rede Enleva)

Documento para revisão com **TI / CG-SI** antes de qualquer deploy além de teste controlado, alinhado à **POL RBD TI 001**.

Versão espelho do arquivo `DOS ENLEVA IA 001` (Word). Em caso de divergência com o `.docx` oficial em tramitação, prevalece o Word — mantenha este Markdown sincronizado após cada revisão.

## 1. Resumo do sistema

- **Finalidade**: otimizar o trabalho de RH/TI (foco inicial), reduzir carga de FAQ repetitivo e aproximar o colaborador dos procedimentos oficiais **dentro da plataforma da Rede Enleva**. A arquitetura é extensível a outros domínios internos via base Markdown.
- **Ambiente**: MVP + Docker; testes controlados. Intranet alcançável pela internet — CORS sozinho não basta.
- **Provedor LLM padrão**: Anthropic Claude (`LLM_PROVIDER=anthropic`).
- **Alternativas técnicas**: OpenAI e Google Gemini (mesma abstração; requerem aprovação própria).

## 2. Aprovação de fornecedor (obrigatória)

| Item | Conteúdo |
|------|----------|
| Fornecedor | Anthropic, PBC |
| Serviço | API Messages (Claude) |
| Dados enviados | System prompt + pergunta do colaborador + trechos recuperados da BC classificada como Interno (+ histórico curto em memória) |
| Dados NÃO enviados (MVP) | Base completa; Restrito/Confidencial; nome/matrícula/e-mail/IP do colaborador; embeddings (gerados localmente) |
| Retenção no fornecedor | Verificar política / zero-data-retention / DPA vigente no momento da homologação |
| DPA / contrato | **Pendente** — obter sob titularidade jurídica da Rede Enleva |
| Homologação SI | **Pendente** — CG-SI / Coordenação de TI |

**Status**: ⏳ Aguardando aprovação formal de fornecedor externo.

## 3. Classificação do conteúdo indexado

| Nível (POL 5.6) | Indexado no MVP? |
|-----------------|------------------|
| Pública | Não |
| Interna (não sensível) | Sim — `classification: Interno`, `sensitive: false` |
| Restrita | Não |
| Confidencial | Não |

Frontmatter obrigatório em cada `.md`. Arquivos com `sensitive: true` ou classificação fora de Interno são ignorados.

**Fora do índice até DPA / decisão formal**: folha, salários, dados de saúde de colaboradores, prontuários, avaliações individuais, demais Restrito/Confidencial.

## 4. Controles técnicos implementados

- Credenciais apenas em `.env` / secret manager (nunca no código).
- Gate de classificação na ingestão.
- Cascata de escopo (local → Haiku se ambíguo) + system prompt + threshold de retrieval; **fail-closed**.
- Filtro de saída (CPF, padrões de salário, termos de saúde/diagnóstico).
- Logs de conversa em `data/logs/` com retenção configurável (`LOG_RETENTION_DAYS`, default 90); purge no **startup** + **agendador interno** (`LOG_PURGE_HOUR_UTC`); cron/Task Scheduler só como complemento bare-metal sem API 24×7.
- `ADMIN_TOKEN` para reindexação.
- `WIDGET_API_TOKEN` **obrigatório** no `/chat` (`X-Widget-Token`, `hmac.compare_digest`). Visível no JS via `/config/public` — **mitigação anti-scanner, não autenticação de sessão**.
- Checagem de `Origin`/`Referer` (`ALLOWED_ORIGINS`, fallback `CORS_ORIGINS`).
- CORS restrito; rate limit conservador no piloto (`10/minute` IP, `15/minute` sessão) — revisar após auth real.
- Docker: usuário não-root; volumes `knowledge` / `chroma` / `logs`; reindex completo a cada start (intencional).

## 5. O que apresentar na reunião de revisão SI

1. Este dossiê / Word oficial preenchido (fornecedor + DPA).
2. Exemplos de payload enviado à API (sem PII).
3. Lista dos documentos indexados e classificação.
4. Política de retenção de logs internos e do fornecedor.
5. Plano de incidente (revogar chave, desligar endpoint, purge).
6. Esclarecimento: intranet pública na internet + camadas provisórias até auth WordPress.

## 6. Checklist de go-live (além de teste controlado)

- [ ] Aprovação de fornecedor Anthropic (ou outro escolhido)
- [ ] DPA assinado sob titularidade da Rede Enleva
- [ ] Conteúdo real triado por donos RH/TI
- [ ] `WIDGET_API_TOKEN` forte ativo + `ALLOWED_ORIGINS` com hosts da intranet
- [ ] CORS limitado aos hosts da intranet
- [ ] Deploy Docker (ou equivalente) aprovado pela TI
- [ ] Purge/retenção confirmados nos logs do container
- [ ] Canal de escalonamento humano comunicado aos usuários
- [ ] (Futuro) autenticação real via sessão WordPress

## 7. Contato

Preencher: responsável produto, responsável TI, responsável CG-SI, data da revisão.

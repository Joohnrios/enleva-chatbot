# Levantamento de custos — APIs Anthropic, OpenAI e Gemini

Estimativa de gasto com LLM para o chatbot interno RAG da Rede Enleva (ago/2026).

| Artefato | Uso |
|----------|-----|
| Planilha gestores | [`docs/estimativa-custo-api-bot-enleva.xlsx`](estimativa-custo-api-bot-enleva.xlsx) |
| Este doc | Hipóteses técnicas + bakeoff para opção barata |

## Fontes de preço

| Provedor | Documentação |
|----------|----------------|
| Anthropic | https://platform.claude.com/docs/en/about-claude/pricing |
| OpenAI | https://openai.com/api/pricing/ |
| Google Gemini | https://ai.google.dev/gemini-api/docs/pricing |

Preços usados (USD / 1M tokens, tier pago, sem Batch/caching):

| Modelo | Input | Output | Papel |
|--------|-------|--------|-------|
| Claude Sonnet 5 | **$2.00** | **$10.00** | Geração (padrão / produção) — preço permanente vigente |
| Claude Haiku 4.5 | $1.00 | $5.00 | Escopo ambíguo no stack atual; candidata a gerador no bakeoff |
| GPT-4o mini | $0.15 | $0.60 | Candidata bakeoff (`LLM_PROVIDER=openai`) |
| Gemini 3.1 Flash-Lite | $0.25 | $1.50 | Candidata bakeoff (barata) |
| Gemini 3.6 Flash | $1.50 | $7.50 | Candidata bakeoff (qualidade Google) |

**Não usar** `$3/$15` para Sonnet 5 (previsão antiga de set/2026 — cancelada).  
**Não usar** Gemini free tier / AI Studio gratuito em teste com dados internos (pode treinar produtos Google — incompatível com o dossiê). Só API paga.

Embeddings locais (`sentence-transformers` + Chroma) = **USD 0**.

## Duas lentes de volume

### A) Piloto técnico (este doc / canvas)

Público: **20–40** colaboradores ([`PILOTO_METRICAS.md`](PILOTO_METRICAS.md)).

Mix operacional: ~50% mensagens sem LLM (recusa/sem contexto), ~40% só geração, ~10% escopo+geração.

| Stack | Conservador 50/dia | Base 150/dia | Alto 400/dia |
|-------|--------------------|--------------|--------------|
| Anthropic Sonnet+Haiku | ~$6.64 | ~$19.92 | ~$53.13 |
| OpenAI GPT-4o mini | ~$0.47 | ~$1.40 | ~$3.74 |
| Gemini Flash-Lite* | ~$0.31–1† | ~$0.9–3† | ~$2.5–8† |

\*† Ordem de grandeza; planilha gestores usa preços Gemini 3.x da aba Comparativo.

### B) Planilha gestores (600 colaboradores + intensidade com pico editável)

Câmbio referência **R$ 5,30**. Tom Amigável.

**Origem do “350”:** estimativa informada pelo solicitante na discussão de custo com o Cursor — **não** é dado formal de RH/TI nem invenção do modelo. Confirmar antes de cravar na apresentação. Célula editável na aba `Intensidade 350`.

**Preços Sonnet 5 — apresentar FAIXA:**

| Cenário de preço | Input/Output | Uso na planilha |
|------------------|--------------|-----------------|
| Vigente / permanente | **$2 / $10** | Base (Anthropic confirmou em **10/08/2026** que o introdutório virou padrão; aumento a $3/$15 em 01/09 foi **cancelado**) |
| Estresse | **$3 / $15** | Sensibilidade orçamentária / material antigo — **não** rotular como “preço pós-31/08” |

Revalidar [pricing Anthropic](https://platform.claude.com/docs/en/about-claude/pricing) na semana do contrato.

Stack atual (Sonnet + Haiku escopo) — **350 usuários ativos**, 5 intensidades (R$/mês):

| Nível | Msgs/mês | @ $2/$10 | @ $3/$15 (estresse) |
|-------|----------|----------|---------------------|
| Leve (2×2,5) | 1.750 | ~R$ 57 | ~R$ 85 |
| Moderada (3×3) | 3.150 | ~R$ 102 | ~R$ 152 |
| Forte (4×3,5) | 4.900 | ~R$ 158 | ~R$ 237 |
| Intensa (1 msg/dia útil) | 7.700 | ~R$ 249 | ~R$ 373 |
| Muito intensa (2 msgs/dia) | 15.400 | ~R$ 498 | ~R$ 745 |

Moderado clássico (600 colab., 30% ativos): ver abas Resumo/Cenários da planilha (~R$ 52 @ $2/$10).

Arquivo: [`docs/estimativa-custo-api-bot-enleva.xlsx`](estimativa-custo-api-bot-enleva.xlsx) (abas `Intensidade 350` e **`TCO Infra+API`**).

### TCO = infra + API (para a conversa com gestão)

Aba **`TCO Infra+API`**: placeholders editáveis de host (default R$ 450 + R$ 50 misc) + API Sonnet ($2/$10) vs Gemini Flash-Lite / 3.6 Flash nos 5 níveis de intensidade.

- Infra é **fixa** (igual com qualquer LLM).
- Gemini reduz só a **variável**; no Moderada, a economia típica é da ordem de **~R$ 90–100/mês** frente ao Sonnet — útil, mas **não paga o VPS sozinha**.
- Piloto continua Sonnet; Gemini = trilho paralelo (lab + mini-dossiê SI).

## Como o projeto consome tokens hoje

`POST /chat` → guards → escopo (local → Haiku se ambíguo) → retrieve → Sonnet se in-scope com chunks.

Defaults: [`backend/app/config.py`](../backend/app/config.py).

## Candidatas baratas sob avaliação

Não são recomendação de troca ainda. Default de produção = **Anthropic Sonnet**.

| Candidata | Por que considerar | Risco |
|-----------|--------------------|-------|
| GPT-4o mini | Muito barato; já no código | Qualidade/guardrails PT |
| Gemini 3.1 Flash-Lite | Mais barato Google | Instrução fraca; só API paga |
| Gemini 3.6 Flash | Meio-termo Google | Reabre DPA/SI |
| Haiku como gerador | Economia sem trocar fornecedor | Pode perder qualidade vs Sonnet |

## Protocolo de bakeoff (qualidade antes de custo)

Objetivo: achar a stack **mais barata que empatar** o Sonnet nos guardrails. Sem mudar default até passar.

```text
Golden set → Sonnet (baseline)
           → GPT-4o mini
           → Gemini 3.6 Flash
           → Gemini Flash-Lite
           → Haiku como gerador
                ↓
         Score: recusa / fontes / tom
                ↓
    Só troca default se empatar (1)–(3)
```

### Critérios de aceite

1. Recusas fora de escopo / sensível (fail-closed) — [`tests/test_scope.py`](../tests/test_scope.py), golden em [`tests/test_rag_answers.py`](../tests/test_rag_answers.py)
2. Respostas in-scope com fonte quando a BC tem trecho
3. Tom estável (amigável) sem inventar política — amostra manual RH/TI
4. Gemini: **somente API paga** (nunca AI Studio free)

### Regra de decisão

**Barato só ganha se empatar (1)–(3).** Senão permanece Sonnet.  
Troca de produção = `LLM_PROVIDER` + chave + **revisão SI/DPA** (não só `.env` de lab).

### Como rodar um round (lab)

1. Backup do `.env`
2. `LLM_PROVIDER=openai` (ou `gemini`) + model id da candidata + API key **paga**
3. Rodar a bateria de testes + 15–20 perguntas reais da BC
4. Registrar score; restaurar Sonnet no `.env` de produção/piloto

## Recomendação atual

1. **Piloto/produção:** Anthropic Sonnet (~**R$ 52/mês** no Moderado gestores; ~**USD 20/mês** no Base piloto).
2. **Economia:** aberta — bakeoff com as candidatas acima; não fechar por preço sozinho.
3. Após piloto: recalibrar com `python -m scripts.pilot_metrics` + usage real dos consoles.

## O que não entra neste levantamento

- Infra VM/Docker/CPU de embeddings
- Free tier / créditos promocionais
- ROI inventado por “preço de chamado”

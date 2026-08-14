# Métricas e operação do piloto

## Público-alvo piloto

20–40 colaboradores (RH + TI + áreas administrativas).

## Métricas sugeridas

| Métrica | Como obter | Meta inicial |
|---------|------------|--------------|
| Volume de perguntas / dia | Contagem em `data/logs/chat-*.jsonl` | Baseline |
| Taxa de recusa (`refused=true`) | Logs | Monitorar; alta pode indicar gap de conteúdo ou abuso fora de escopo |
| % com fontes citadas | Campo `sources` nos logs | Preferência por respostas com fonte |
| Chamados RH/TI no período | Sistema de chamados (baseline vs piloto) | Redução em FAQs repetidos |
| Feedback qualitativo | Formulário curto pós-piloto | Satisfação > baseline acordado |

## Script rápido de contagem

```bash
python -m scripts.pilot_metrics
```

## Deploy interno (Docker)

Ver `docker-compose.yml` na raiz. **Não** publicar na internet sem revisão SI.

## Conteúdo real

1. Triar FAQs/procedimentos com donos RH/TI.
2. Classificar cada arquivo (`Interno` + `sensitive: false`).
3. Copiar para `knowledge/` (não misturar com docs Confidenciais).
4. Rodar `python -m scripts.ingest` ou `POST /admin/reindex`.

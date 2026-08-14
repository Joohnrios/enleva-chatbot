# Tematização do widget Enleva

O widget aplica CSS custom properties **somente** em `#enleva-chat-root` (não no `:root` da página hospedeira), para não colidir com variáveis da intranet (`--theme-color-*`, etc.).

## Defaults (medidos na intranet)

Inspecionado em `https://intranet.enlevasaude.com/` via DevTools:

| Papel | Valor | Evidência |
|-------|-------|-----------|
| Primary (CTAs / chrome) | `#1c51a0` | Token `--lp-secondary-color`; botões `.bbw-btn` Parabenizar/Enviar ≈ `#1e4076` |
| Accent (marca / destaque) | `#F05B78` | Token `--lp-primary-color`; nav ativa, badge, FAB scroll |
| Fundo página/painel msgs | `#EEF6F7` | `body` + `--wp--preset--color--bg-color` |
| Superfície (bolha bot) | `#FFFFFF` | `--wp--preset--color--content-bg` |
| Texto corpo | `#707276` | `--theme-color-text` / `body` |
| Texto muted | `#7A7E83` | `--wp--preset--color--text-light` |
| Texto sobre primary | `#FCFCFC` | badge/contador |
| Borda | `#D9E0E3` | `--wp--preset--color--bd-color` |
| Bolha usuário | `#1c51a0` | mesmo azul primary/CTA dos botões; texto `#FCFCFC` |

**Nota:** na marca, `--lp-primary-color` é o coral; nos botões de ação principais da home (Parabenizar/Enviar) o fundo computado é azul. O widget usa azul no chrome (header/launcher/Enviar) e coral no accent/gradiente.

## Exemplo

```html
<script>
  window.EnlevaChatConfig = {
    apiUrl: "/chat",
    position: "right",
    primaryColor: "#1c51a0",
    accentColor: "#F05B78",
    bgColor: "#EEF6F7",
    textColor: "#707276",
    icon: "💬"
  };
</script>
<script src="/static/widget.js" defer></script>
```

## Variáveis CSS (em `#enleva-chat-root`)

| Variável CSS | Config JS |
|--------------|-----------|
| `--enleva-chat-primary-color` | `primaryColor` / `primary` |
| `--enleva-chat-accent-color` | `accentColor` / `accent` |
| `--enleva-chat-bg` | `bgColor` / `backgroundColor` |
| `--enleva-chat-text-color` | `textColor` |
| `--enleva-chat-muted-color` | `mutedColor` |
| `--enleva-chat-border-color` | `borderColor` |
| `--enleva-chat-user-bg` | `userBubbleColor` (default = primary `#1c51a0`) |
| `--enleva-chat-surface` | (só CSS / set via JS interno) |
| `--enleva-chat-on-primary` | (texto sobre primary, default `#FCFCFC`) |

Posição: `position: "left" | "right"` no JS (classe `.enleva-left`), não CSS var.

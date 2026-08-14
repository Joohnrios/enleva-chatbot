"""Adiciona aba TCO (infra + API Sonnet vs Gemini) na planilha de custos."""

from __future__ import annotations

from pathlib import Path

from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

V2 = Path(r"C:\Users\John-Rios\Documents\enleva-chatbot\docs\estimativa-custo-api-bot-enleva-v2.xlsx")
V1 = Path(r"C:\Users\John-Rios\Documents\enleva-chatbot\docs\estimativa-custo-api-bot-enleva.xlsx")
DOWNLOADS = Path(r"c:\Users\John-Rios\Downloads\estimativa-custo-api-bot-enleva.xlsx")

YELLOW = PatternFill("solid", fgColor="FFF2CC")
BOLD = Font(bold=True)
WRAP = Alignment(wrap_text=True, vertical="top")
THIN = Border(
    left=Side(style="thin"),
    right=Side(style="thin"),
    top=Side(style="thin"),
    bottom=Side(style="thin"),
)


def main() -> None:
    wb = load_workbook(V2)

    if "TCO Infra+API" in wb.sheetnames:
        del wb["TCO Infra+API"]
    # após Intensidade 350
    idx = wb.sheetnames.index("Intensidade 350") + 1
    tco = wb.create_sheet("TCO Infra+API", idx)

    tco["A1"] = "TCO mensal — Infraestrutura + API (Sonnet vs Gemini)"
    tco["A1"].font = Font(bold=True, size=14)
    tco["A2"] = (
        "Mesma infra para qualquer fornecedor de LLM. A economia do Gemini reduz só a parte "
        "variável (API) — não elimina o custo do host. Células amarelas = editáveis. "
        "Msgs/mês vêm da aba Intensidade 350 (usuários em B4 lá)."
    )
    tco["A2"].alignment = WRAP
    tco.row_dimensions[2].height = 48

    # --- Premissas de infra ---
    tco["A4"] = "Custo de infraestrutura (R$/mês) — PLACEHOLDERS"
    tco["A4"].font = BOLD
    tco["A5"] = "Host dedicado bot (FastAPI + embeddings + Postgres + Django Admin)"
    tco["B5"] = 450
    tco["B5"].fill = YELLOW
    tco["C5"] = "Ajustar com cotação real de VPS/cloud Enleva"
    tco["A6"] = "Redis (quando entrar) — opcional / fase posterior"
    tco["B6"] = 0
    tco["B6"].fill = YELLOW
    tco["C6"] = "0 se ainda não provisionado; ex. +30–80 se managed"
    tco["A7"] = "Observabilidade / backup / misc"
    tco["B7"] = 50
    tco["B7"].fill = YELLOW
    tco["A8"] = "Total infra (R$/mês)"
    tco["B8"] = "=B5+B6+B7"
    tco["A8"].font = BOLD
    tco["B8"].font = BOLD

    tco["A10"] = "Câmbio"
    tco["B10"] = "=Premissas!B6"
    tco["A11"] = "Usuários (ref. Intensidade 350)"
    tco["B11"] = "='Intensidade 350'!B4"

    # --- Tabela principal ---
    headers = [
        "Nível",
        "Msgs/mês",
        "API Sonnet R$ ($2/$10)",
        "API Gemini Flash-Lite R$",
        "API Gemini 3.6 Flash R$",
        "Economia Lite vs Sonnet",
        "TCO Sonnet (infra+API)",
        "TCO Gemini Lite",
        "TCO Gemini Flash",
        "Lite economiza quanto do TCO Sonnet?",
    ]
    for c, h in enumerate(headers, start=1):
        cell = tco.cell(13, c, h)
        cell.font = BOLD
        cell.alignment = Alignment(wrap_text=True, vertical="center")
        cell.border = THIN
    tco.row_dimensions[13].height = 36

    # Row refs Intensidade 350: C9:C13 msgs, levels A9:A13
    # Sonnet R$: Intensidade D9:D13 (= msgs * Cálculo C19)
    # Gemini Lite: msgs * Comparativo!B15 * câmbio
    # Gemini Flash: msgs * Comparativo!B16 * câmbio
    for i in range(5):
        r = 14 + i
        src = 9 + i
        tco[f"A{r}"] = f"='Intensidade 350'!A{src}"
        tco[f"B{r}"] = f"='Intensidade 350'!C{src}"
        tco[f"C{r}"] = f"='Intensidade 350'!D{src}"
        tco[f"D{r}"] = f"=B{r}*'Comparativo Provedores'!$B$15*$B$10"
        tco[f"E{r}"] = f"=B{r}*'Comparativo Provedores'!$B$16*$B$10"
        tco[f"F{r}"] = f"=C{r}-D{r}"
        tco[f"G{r}"] = f"=$B$8+C{r}"
        tco[f"H{r}"] = f"=$B$8+D{r}"
        tco[f"I{r}"] = f"=$B$8+E{r}"
        tco[f"J{r}"] = f"=IF(G{r}=0,\"-\",F{r}/G{r})"
        for c in range(1, 11):
            tco.cell(r, c).border = THIN

    # Format percent column hint
    for r in range(14, 19):
        tco[f"J{r}"].number_format = "0.0%"

    tco["A20"] = "Leitura para a conversa com gestão"
    tco["A20"].font = BOLD
    bullets = [
        "•  Infra é custo FIXO do produto (host do bot + CMS + banco). Trocar Anthropic por Gemini "
        "não remove essa linha — só reduz a variável API.",
        "•  No nível Moderada/Forte, a economia Lite vs Sonnet costuma ser dezenas a ~R$ 150/mês: "
        "relevante na fatura de API, pequena frente a um host de centenas de R$.",
        "•  Narrativa recomendada: piloto em Sonnet (dossiê pronto); trilho Gemini em paralelo "
        "(lab + mini-dossiê SI) para quando o volume/teto apertar — sem atrasar o CG-SI atual.",
        "•  Ajuste B5–B7 com a cotação real do provedor Enleva antes da apresentação. "
        "Defaults (450+50) são PLACEHOLDERS, não proposta comercial.",
        "•  Gemini na tabela = preço Comparativo (Flash-Lite / 3.6 Flash), tom Amigável, "
        "API paga only — nunca free tier / AI Studio gratuito.",
    ]
    for i, text in enumerate(bullets):
        row = 21 + i
        tco[f"A{row}"] = text
        tco[f"A{row}"].alignment = WRAP
        tco.row_dimensions[row].height = 40

    tco["A27"] = "Exemplo numérico (com placeholders atuais de infra)"
    tco["A27"].font = BOLD
    tco["A28"] = (
        "Se infra ≈ R$ 500 e Moderada (~3.150 msgs): TCO Sonnet ≈ 500+102 ≈ R$ 602; "
        "TCO Lite ≈ 500+~7 ≈ R$ 507 — economia ~R$ 95 (~16% do TCO), não 'metade da conta'."
    )
    tco["A28"].alignment = WRAP
    tco.row_dimensions[28].height = 40

    widths = [22, 12, 18, 18, 18, 16, 16, 14, 14, 18]
    for i, w in enumerate(widths, start=1):
        tco.column_dimensions[get_column_letter(i)].width = w
    tco.column_dimensions["A"].width = 56

    # Resumo pointer
    res = wb["Resumo"]
    res["A15"] = (
        "•  TCO (infra + API Sonnet vs Gemini): ver aba 'TCO Infra+API'. "
        "Ajuste os placeholders de host antes de apresentar."
    )
    res["A15"].alignment = WRAP

    inten = wb["Intensidade 350"]
    inten["A20"] = (
        "•  Para infra + API na mesma página: aba 'TCO Infra+API' "
        "(economia Gemini não elimina o custo do servidor)."
    )
    inten["A20"].alignment = WRAP

    saved = []
    for path in (V2, V1, DOWNLOADS):
        try:
            wb.save(path)
            saved.append(str(path))
        except PermissionError:
            print("locked:", path)
    print("saved:", saved)


if __name__ == "__main__":
    main()

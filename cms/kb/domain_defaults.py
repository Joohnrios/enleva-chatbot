"""Defaults de Domain alinhados a DOMAIN_SEED_ANCHORS (backend) e canais de contato."""

from __future__ import annotations

# Espelho de backend.app.guardrails.local_scope.DOMAIN_SEED_ANCHORS
# (evita importar o backend no processo Django).
DOMAIN_DEFAULTS: dict[str, dict[str, str]] = {
    "rh": {
        "name": "RH",
        "scope_seed": (
            "Recursos Humanos RH benefícios plano de saúde vale-refeição férias "
            "atestado médico admissão colaborador política interna"
        ),
        "contact_channel": "Atendimento ao Colaborador",
        "contact_hint": "Abra chamado em Atendimento ao Colaborador (RH).",
    },
    "ti": {
        "name": "TI",
        "scope_seed": (
            "Tecnologia da Informação TI senha VPN acesso intranet notebook "
            "impressora equipamento service desk chamado software"
        ),
        "contact_channel": "GLPI",
        "contact_hint": "Abra chamado no GLPI (TI).",
    },
    "admin": {
        "name": "Admin",
        "scope_seed": (
            "Administrativo ponto eletrônico jornada banco de horas ajuste de ponto "
            "procedimentos administrativos unidade"
        ),
        "contact_channel": "Atendimento ao Colaborador",
        "contact_hint": "Ajuste de ponto e jornada: intranet ou RH / Administração.",
    },
}

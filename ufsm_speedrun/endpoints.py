"""Registro dos endpoints conhecidos do SIE.

A documentação completa (params, semântica, exemplos) está em docs/ufsm-api.md.
"""

from __future__ import annotations

from . import config

# --- curso (dados curriculares) --------------------------------------------
CURSO_ESTRUTURA = "curso/estrutura.json"
CURSO_DISCIPLINAS_PERIODO = "curso/disciplinasPeriodo.json"
CURSO_PREREQUISITOS = "curso/preRequisitosAgrupados.json"
CURSO_EQUIVALENCIAS = "curso/equivalenciasAgrupadas.json"

# --- disciplina (catálogo global) ------------------------------------------
DISCIPLINA_DETALHE = "disciplina/disciplina.json"
DISCIPLINA_BUSCA = "disciplina/busca.json"
DISCIPLINA_CURRICULOS = "disciplina/curriculos.json"


def url_for(endpoint: str) -> str:
    return f"{config.BASE_URL}/{endpoint}"


def slug_for(endpoint: str) -> str:
    """Nome de pasta seguro para gravar o raw: 'curso/estrutura.json' -> 'curso_estrutura'."""
    return endpoint.replace(".json", "").replace("/", "_")


# Enums documentados em docs/ufsm-api.md
TIPO_DISCIPLINA_CURRICULO = {
    1: "Obrigatória",
    2: "Optativa",
    3: "Eletiva",
    4: "Atividade Complementar",
    5: "Disciplina Complementar de Graduação",
    6: "Inativa",
    7: "Disciplina Complementar de Pós-Graduação",
    8: "Atividade Complementar de Pós-Graduação",
}

TIPO_PREREQUISITO = {
    1: "Disciplinas vencidas",
    2: "Correquisito",
    3: "Carga horária vencida",
    4: "Créditos vencidos",
    5: "Período vencido",
}

TIPO_CONTEUDO_PROGRAMA = {
    1: "Bibliografia",
    2: "Programa da Disciplina",
}

SITUACAO_VERSAO = {"C": "Corrente", "A": "Ativa", "I": "Inativa"}

"""Fase 5 — validação e relatório de qualidade.

Roda 100% offline, em cima do que já está no SQLite. Serve de checkpoint antes
de construir o otimizador e a dashboard: se estes números estiverem estranhos,
o problema é de dados, não de algoritmo.

Gera `docs/relatorio-qualidade.md`.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import config


@dataclass
class Achado:
    titulo: str
    severidade: str  # ok | atencao | problema
    detalhe: str
    amostra: list[str] = field(default_factory=list)


def _escalar(conn: sqlite3.Connection, sql: str) -> int:
    return conn.execute(sql).fetchone()[0]


def checar_fk(conn: sqlite3.Connection) -> Achado:
    violacoes = conn.execute("PRAGMA foreign_key_check").fetchall()
    return Achado(
        "Integridade referencial",
        "ok" if not violacoes else "problema",
        f"{len(violacoes)} violação(ões) de chave estrangeira",
        [f"{v[0]} (rowid={v[1]}) -> {v[2]}" for v in violacoes[:10]],
    )


def checar_cursos(conn: sqlite3.Connection) -> list[Achado]:
    achados: list[Achado] = []

    sem_versao = conn.execute(
        "SELECT c.id, c.nome FROM curso c "
        "WHERE NOT EXISTS (SELECT 1 FROM versao_curriculo v WHERE v.curso_id = c.id)"
    ).fetchall()
    achados.append(Achado(
        "Cursos sem nenhuma versão de currículo",
        "problema" if sem_versao else "ok",
        f"{len(sem_versao)} curso(s)",
        [f"{r[0]} {r[1]}" for r in sem_versao[:10]],
    ))

    sem_selecionada = conn.execute(
        "SELECT c.id, c.nome FROM curso c WHERE NOT EXISTS ("
        "  SELECT 1 FROM versao_curriculo v WHERE v.curso_id = c.id AND v.selecionada = 1)"
    ).fetchall()
    achados.append(Achado(
        "Cursos sem versão selecionada",
        "problema" if sem_selecionada else "ok",
        f"{len(sem_selecionada)} curso(s)",
        [f"{r[0]} {r[1]}" for r in sem_selecionada[:10]],
    ))

    sem_estrutura = conn.execute(
        "SELECT c.nome, v.numero FROM versao_curriculo v "
        "JOIN curso c ON c.id = v.curso_id "
        "WHERE v.selecionada = 1 AND NOT EXISTS "
        "(SELECT 1 FROM estrutura e WHERE e.versao_id = v.id)"
    ).fetchall()
    achados.append(Achado(
        "Versões selecionadas sem árvore curricular (Fase 2 falhou?)",
        "problema" if sem_estrutura else "ok",
        f"{len(sem_estrutura)} versão(ões)",
        [f"{r[0]} ({r[1]})" for r in sem_estrutura[:10]],
    ))
    return achados


def checar_ementas(conn: sqlite3.Connection) -> Achado:
    total = _escalar(conn, "SELECT COUNT(*) FROM disciplina")
    baixadas = _escalar(conn, "SELECT COUNT(*) FROM disciplina WHERE raw_file IS NOT NULL")
    com_texto = _escalar(
        conn,
        "SELECT COUNT(*) FROM disciplina WHERE programa_texto IS NOT NULL AND programa_texto <> ''",
    )
    faltando = total - baixadas
    severidade = "ok" if faltando == 0 else "atencao"
    return Achado(
        "Ementas (Fase 4)",
        severidade,
        f"{baixadas}/{total} baixadas · {com_texto} com programa · "
        f"{faltando} pendentes · {baixadas - com_texto} sem programa no SIE",
    )


def checar_grafo(conn: sqlite3.Connection) -> Achado:
    """Procura ciclos no grafo global de pré-requisitos."""
    arestas = conn.execute(
        "SELECT DISTINCT pi.disciplina_req_id, dc.disciplina_id "
        "FROM prereq_item pi "
        "JOIN prereq_bloco pb ON pb.id = pi.bloco_id "
        "JOIN disciplina_curriculo dc ON dc.id = pb.disciplina_curriculo_id "
        "WHERE pi.tipo_item IN (1, 2) AND pi.disciplina_req_id IS NOT NULL"
    ).fetchall()

    grafo: dict[int, set[int]] = {}
    for origem, destino in arestas:
        grafo.setdefault(origem, set()).add(destino)

    BRANCO, CINZA, PRETO = 0, 1, 2
    cor: dict[int, int] = {}
    ciclos: list[str] = []

    codigos = dict(conn.execute("SELECT id, codigo FROM disciplina"))

    def dfs(no: int, caminho: list[int]) -> None:
        cor[no] = CINZA
        for vizinho in grafo.get(no, ()):
            if cor.get(vizinho, BRANCO) == CINZA:
                i = caminho.index(vizinho) if vizinho in caminho else 0
                ciclo = caminho[i:] + [vizinho]
                ciclos.append(" -> ".join(codigos.get(n, str(n)) for n in ciclo))
            elif cor.get(vizinho, BRANCO) == BRANCO:
                dfs(vizinho, caminho + [vizinho])
        cor[no] = PRETO

    for no in list(grafo):
        if cor.get(no, BRANCO) == BRANCO:
            dfs(no, [no])

    return Achado(
        "Ciclos no grafo de pré-requisitos",
        "ok" if not ciclos else "problema",
        f"{len(arestas)} arestas · {len(ciclos)} ciclo(s) detectado(s)",
        ciclos[:10],
    )


def checar_carga_horaria(conn: sqlite3.Connection) -> Achado:
    """Quanto da CH total da versão está coberto por disciplina obrigatória."""
    linhas = conn.execute(
        """
        SELECT c.nome, v.numero, v.ch_total,
               COALESCE(SUM(DISTINCT_CH.ch), 0) AS ch_obrig
        FROM versao_curriculo v
        JOIN curso c ON c.id = v.curso_id
        LEFT JOIN (
            SELECT dc.versao_id, dc.disciplina_id, MAX(d.ch_total) AS ch
            FROM disciplina_curriculo dc
            JOIN disciplina d ON d.id = dc.disciplina_id
            WHERE dc.tipo_item = 1
            GROUP BY dc.versao_id, dc.disciplina_id
        ) DISTINCT_CH ON DISTINCT_CH.versao_id = v.id
        WHERE v.selecionada = 1 AND v.ch_total IS NOT NULL
        GROUP BY v.id
        """
    ).fetchall()

    estouradas = [(n, num, total, ob) for n, num, total, ob in linhas if ob > total]
    amostra = [f"{n} ({num}): obrigatórias {ob}h > total {total}h" for n, num, total, ob in estouradas[:10]]
    return Achado(
        "Coerência de carga horária",
        "ok" if not estouradas else "atencao",
        f"{len(linhas)} versões conferidas · {len(estouradas)} com obrigatórias acima do total",
        amostra,
    )


def checar_buckets(conn: sqlite3.Connection) -> Achado:
    abertos = conn.execute(
        """
        SELECT c.nome, v.numero, e.descricao, e.ch_minima
        FROM estrutura e
        JOIN versao_curriculo v ON v.id = e.versao_id
        JOIN curso c ON c.id = v.curso_id
        WHERE v.selecionada = 1 AND e.ch_minima > 0
          AND NOT EXISTS (SELECT 1 FROM disciplina_curriculo dc WHERE dc.estrutura_id = e.id)
          AND NOT EXISTS (SELECT 1 FROM estrutura f WHERE f.pai_id = e.id)
          AND NOT EXISTS (SELECT 1 FROM estrutura_atividade a WHERE a.estrutura_id = e.id)
        ORDER BY e.ch_minima DESC
        """
    ).fetchall()
    return Achado(
        "Cotas abertas (sem disciplinas e sem atividades)",
        "atencao" if abertos else "ok",
        f"{len(abertos)} cota(s) — precisam de tratamento explícito no otimizador",
        [f"{ch}h · {nome} ({numero}) · {desc[:40]}" for nome, numero, desc, ch in abertos[:15]],
    )


def checar_densidade_relacoes(conn: sqlite3.Connection) -> Achado:
    total = _escalar(conn, "SELECT COUNT(*) FROM disciplina_curriculo")
    com_flag = _escalar(
        conn, "SELECT COUNT(*) FROM disciplina_curriculo WHERE tem_prereq = 1 OR tem_equiv = 1"
    )
    com_bloco = _escalar(
        conn,
        "SELECT COUNT(*) FROM (SELECT disciplina_curriculo_id FROM prereq_bloco "
        "UNION SELECT disciplina_curriculo_id FROM equivalencia_bloco)",
    )
    pre = _escalar(conn, "SELECT COUNT(*) FROM prereq_item WHERE tipo_item IN (1, 2)")
    eqv = _escalar(conn, "SELECT COUNT(*) FROM equivalencia_item")
    pendentes = com_flag - com_bloco
    return Achado(
        "Pré-requisitos e equivalências (Fase 3)",
        "ok" if pendentes == 0 else "atencao",
        f"{com_flag}/{total} ofertas com flag · {com_bloco} com relação gravada · "
        f"{pendentes} pendentes · {pre} arestas de prereq · {eqv} itens de equivalência",
    )


# --------------------------------------------------------------------- relatório
def gerar(conn: sqlite3.Connection, destino: Path | None = None) -> Path:
    destino = destino or (config.PROJECT_ROOT / "docs" / "relatorio-qualidade.md")

    achados = [checar_fk(conn)] + checar_cursos(conn) + [
        checar_ementas(conn),
        checar_grafo(conn),
        checar_carga_horaria(conn),
        checar_densidade_relacoes(conn),
        checar_buckets(conn),
    ]

    icone = {"ok": "✅", "atencao": "⚠️", "problema": "❌"}
    agora = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    linhas = [
        "# Relatório de qualidade dos dados",
        "",
        f"Gerado em {agora} por `python -m ufsm_speedrun validar`.",
        "",
        "| | verificação | situação |",
        "|---|---|---|",
    ]
    for a in achados:
        linhas.append(f"| {icone[a.severidade]} | {a.titulo} | {a.detalhe} |")

    for a in achados:
        linhas += ["", f"## {icone[a.severidade]} {a.titulo}", "", a.detalhe]
        if a.amostra:
            linhas += [""] + [f"- `{item}`" for item in a.amostra]

    linhas += [
        "",
        "---",
        "",
        "## Contagens",
        "",
        "```",
    ]
    for tabela in ("curso", "versao_curriculo", "estrutura", "disciplina",
                   "disciplina_curriculo", "prereq_item", "equivalencia_item"):
        linhas.append(f"{tabela:<24} {_escalar(conn, f'SELECT COUNT(*) FROM {tabela}'):>7}")
    linhas += ["```", ""]

    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text("\n".join(linhas), encoding="utf-8")

    problemas = sum(1 for a in achados if a.severidade == "problema")
    atencoes = sum(1 for a in achados if a.severidade == "atencao")
    print(f"\nrelatório escrito em {destino}")
    print(f"  {len(achados) - problemas - atencoes} ok · {atencoes} atenção · {problemas} problema(s)")
    for a in achados:
        print(f"  {icone[a.severidade]} {a.titulo}: {a.detalhe}")
    return destino

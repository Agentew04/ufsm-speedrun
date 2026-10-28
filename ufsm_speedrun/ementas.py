"""Fase 4 — ementas / programa das disciplinas.

O campo `ementa` do SIE é sempre null; o conteúdo real está em
`programaDisciplina` (tipoConteudo 2 = programa, 1 = bibliografia) + `objetivos`.
Ver docs/ufsm-api.md §3.

É a fase mais longa (milhares de requests) e por isso é retomável: pula quem já
tem `raw_file` preenchido.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field

from bs4 import BeautifulSoup

from . import config, endpoints
from .http import UfsmClient
from .recorder import utc_now

TIPO_BIBLIOGRAFIA = 1
TIPO_PROGRAMA = 2


@dataclass
class Coleta:
    processadas: int = 0
    com_programa: int = 0
    sem_programa: int = 0
    sem_resposta: int = 0
    erros: list[str] = field(default_factory=list)


def html_to_text(valor: str | None) -> str:
    """HTML do SIE -> texto limpo (sem <span style=...>, sem espaços duplicados)."""
    if not valor:
        return ""
    soup = BeautifulSoup(valor, "html.parser")
    texto = soup.get_text("\n")
    texto = texto.replace("\u00a0", " ")
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r"\n\s*\n+", "\n", texto)
    return texto.strip()


def extrair_conteudo(itens: list[dict] | None, tipo_item: int) -> str:
    """Concatena descrição + texto de todos os itens de um tipo, recursivamente."""
    partes: list[str] = []

    def walk(lista: list[dict] | None) -> None:
        for item in lista or []:
            if (item.get("tipoConteudo") or {}).get("item") == tipo_item:
                descricao = (item.get("descricao") or "").strip()
                if descricao:
                    partes.append(descricao)
                texto = html_to_text(item.get("texto"))
                if texto:
                    partes.append(texto)
            walk(item.get("filhos"))

    walk(itens)
    return "\n".join(partes).strip()


def run(client: UfsmClient, conn: sqlite3.Connection, *, limit: int | None = None,
        refazer: bool = False) -> Coleta:
    sql = "SELECT id, codigo, nome FROM disciplina"
    if not refazer:
        sql += " WHERE raw_file IS NULL"
    sql += " ORDER BY codigo"
    if limit:
        sql += f" LIMIT {int(limit)}"
    alvos = conn.execute(sql).fetchall()
    total = len(alvos)

    print(f"\n{total} disciplinas para buscar ementa"
          f"{'' if refazer else ' (pulando as já baixadas)'}\n", flush=True)

    coleta = Coleta()
    for i, (disc_id, codigo, nome) in enumerate(alvos, 1):
        try:
            resp = client.call(endpoints.DISCIPLINA_DETALHE, {"codigo": codigo})
            d = resp.data or {}
            if not d:
                coleta.sem_resposta += 1

            programa = extrair_conteudo(d.get("programaDisciplina"), TIPO_PROGRAMA)
            bibliografia = extrair_conteudo(d.get("programaDisciplina"), TIPO_BIBLIOGRAFIA)

            caminho = client.recorder.raw_path(endpoints.DISCIPLINA_DETALHE, resp.meta["key"])
            try:
                raw_rel = str(caminho.relative_to(config.DATA_DIR))
            except ValueError:
                raw_rel = str(caminho)

            conn.execute(
                """
                UPDATE disciplina SET
                    codigo = ?, nome = ?, nome_ingles = ?, creditos = ?, ch_total = ?,
                    ch_extensao = ?, ch_encargo = ?, departamento_id = ?, departamento_nome = ?,
                    situacao_codigo = ?, situacao = ?, tipo = ?, tipo_disciplina = ?,
                    objetivos_html = ?, programa_texto = ?, bibliografia_texto = ?,
                    documento_programa = ?, raw_file = ?, atualizado_em = ?
                WHERE id = ?
                """,
                (
                    d.get("codigo") or codigo,
                    d.get("descricao") or nome,
                    d.get("nomeIngles"),
                    d.get("creditos"),
                    d.get("cargaHoraria"),
                    d.get("cargaHorariaExtensao"),
                    d.get("encargoDidatico"),
                    (d.get("departamento") or {}).get("id"),
                    (d.get("departamento") or {}).get("descricao"),
                    (d.get("situacao") or {}).get("codigo"),
                    (d.get("situacao") or {}).get("descricao"),
                    (d.get("tipo") or {}).get("descricao"),
                    (d.get("tipoDisciplina") or {}).get("descricao"),
                    d.get("objetivos"),
                    programa,
                    bibliografia,
                    d.get("documentoPrograma"),
                    raw_rel,
                    utc_now(),
                    disc_id,
                ),
            )

            conn.execute("DELETE FROM disciplina_ch WHERE disciplina_id = ?", (disc_id,))
            for carga in d.get("cargasHorarias") or []:
                conn.execute(
                    "INSERT OR REPLACE INTO disciplina_ch (disciplina_id, tipo_aula, horas) "
                    "VALUES (?, ?, ?)",
                    (disc_id, (carga.get("tipoAula") or {}).get("descricao") or "?",
                     carga.get("horasAula") or 0),
                )

            conn.commit()
            coleta.processadas += 1
            if programa:
                coleta.com_programa += 1
            elif d:
                coleta.sem_programa += 1

            if client.verbose and (i % 50 == 0 or i == total):
                pct = 100 * i / total
                print(f"  {i:>5}/{total} ({pct:4.0f}%) {codigo:<12} {nome[:40]}", flush=True)
        except Exception as exc:  # noqa: BLE001
            conn.rollback()
            coleta.erros.append(f"{codigo}: {exc}")
            if client.verbose and len(coleta.erros) <= 20:
                print(f"  !! {codigo}: {exc}", flush=True)

    return coleta


def relatorio(conn: sqlite3.Connection, coleta: Coleta) -> None:
    escalar = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731

    print("\n" + "=" * 72)
    print("RELATÓRIO — FASE 4")
    print("=" * 72)
    print(f"  disciplinas processadas .... {coleta.processadas}")
    print(f"  com programa (ementa) ...... {coleta.com_programa}")
    print(f"  sem programa cadastrado .... {coleta.sem_programa}")
    print(f"  resposta vazia (código inexistente) {coleta.sem_resposta}")
    print(f"  total no banco com ementa .. "
          f"{escalar('SELECT COUNT(*) FROM disciplina WHERE programa_texto IS NOT NULL AND programa_texto <> \"\"')}")
    print(f"  total de disciplinas ....... {escalar('SELECT COUNT(*) FROM disciplina')}")

    tamanho = escalar(
        "SELECT COALESCE(SUM(LENGTH(programa_texto)), 0) FROM disciplina"
    )
    print(f"  texto de ementa acumulado .. {tamanho / 1024 / 1024:.1f} MB")

    if coleta.erros:
        print(f"\n  erros: {len(coleta.erros)} (rode de novo; o que falhou não tem raw_file)")
        for erro in coleta.erros[:10]:
            print(f"    - {erro}")
    print()

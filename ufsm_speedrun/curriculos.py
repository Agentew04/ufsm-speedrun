"""Fase 2 — coleta das árvores curriculares.

Para cada versão de currículo, busca `curso/estrutura.json` e materializa:

    estrutura            <- os nós ("NÚCLEO DE FORMAÇÃO BÁSICA", "DCG", ...)
    estrutura_atividade  <- requisitos que não são disciplina (horas de extensão)
    disciplina           <- stub (o detalhe/ementa vem na Fase 4)
    disciplina_curriculo <- a oferta: disciplina X, neste núcleo, neste papel

Por padrão processa apenas as versões `selecionada = 1` (abaixo de 1/4 da
árvore inteira). Use `--todas` para o histórico completo.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from dataclasses import dataclass, field

from . import endpoints
from .http import UfsmClient
from .persist import upsert_disciplina


@dataclass
class Coleta:
    versoes_ok: int = 0
    estruturas: int = 0
    atividades: int = 0
    ofertas: int = 0
    erros: list[str] = field(default_factory=list)


def persist_versao(conn: sqlite3.Connection, versao_id: int, itens: list[dict]) -> tuple[int, int, int]:
    """Grava a árvore de uma versão. Retorna (estruturas, atividades, ofertas)."""
    n_estruturas = n_atividades = n_ofertas = 0

    def walk(node: dict, pai_id: int | None, ordem: int) -> None:
        nonlocal n_estruturas, n_atividades, n_ofertas

        conn.execute(
            """
            INSERT INTO estrutura (id, versao_id, pai_id, descricao, ch_minima, ch_maxima,
                                   min_creditos, max_creditos, ordem)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                versao_id = excluded.versao_id, pai_id = excluded.pai_id,
                descricao = excluded.descricao, ch_minima = excluded.ch_minima,
                ch_maxima = excluded.ch_maxima, min_creditos = excluded.min_creditos,
                max_creditos = excluded.max_creditos, ordem = excluded.ordem
            """,
            (node["id"], versao_id, pai_id, node.get("descricao") or "",
             node.get("cargaHorariaMinima"), node.get("cargaHorariaMaxima"),
             node.get("minimoCreditos"), node.get("maximoCreditos"), ordem),
        )
        n_estruturas += 1

        for atividade in node.get("atividades") or []:
            conn.execute(
                "INSERT INTO estrutura_atividade (estrutura_id, sie_id, descricao) VALUES (?, ?, ?)",
                (node["id"], atividade.get("id"), atividade.get("descricao")),
            )
            n_atividades += 1

        for dc in node.get("disciplinas") or []:
            d = dc["disciplina"]
            upsert_disciplina(conn, d)
            tipo_item = (dc.get("tipo") or {}).get("item")
            conn.execute(
                """
                INSERT INTO disciplina_curriculo
                    (id, versao_id, estrutura_id, disciplina_id, tipo_item, tipo,
                     periodo_ideal, ch_ead, nota_minima, nota_maxima, tem_prereq, tem_equiv)
                VALUES (:id, :versao_id, :estrutura_id, :disciplina_id, :tipo_item, :tipo,
                        :periodo_ideal, :ch_ead, :nota_minima, :nota_maxima, :tem_prereq, :tem_equiv)
                ON CONFLICT(id) DO UPDATE SET
                    versao_id = excluded.versao_id, estrutura_id = excluded.estrutura_id,
                    disciplina_id = excluded.disciplina_id, tipo_item = excluded.tipo_item,
                    tipo = excluded.tipo, periodo_ideal = excluded.periodo_ideal,
                    ch_ead = excluded.ch_ead, nota_minima = excluded.nota_minima,
                    nota_maxima = excluded.nota_maxima,
                    tem_prereq = excluded.tem_prereq, tem_equiv = excluded.tem_equiv
                """,
                {
                    "id": dc["id"],
                    "versao_id": versao_id,
                    "estrutura_id": node["id"],
                    "disciplina_id": d["id"],
                    "tipo_item": tipo_item,
                    "tipo": endpoints.TIPO_DISCIPLINA_CURRICULO.get(tipo_item)
                            or (dc.get("tipo") or {}).get("descricao"),
                    "periodo_ideal": dc.get("periodoIdeal"),
                    "ch_ead": dc.get("cargaHorariaEad"),
                    "nota_minima": dc.get("notaMinima"),
                    "nota_maxima": dc.get("notaMaxima"),
                    "tem_prereq": 1 if dc.get("temPreRequisitos") else 0,
                    "tem_equiv": 1 if dc.get("temEquivalencias") else 0,
                },
            )
            n_ofertas += 1

        # o webservice ordena as filhas alfabeticamente; o SIE ordena por id
        filhas = sorted(node.get("filhas") or [], key=lambda f: f["id"])
        for i, filha in enumerate(filhas):
            walk(filha, node["id"], i)

    for i, raiz in enumerate(itens):
        walk(raiz, None, i)

    return n_estruturas, n_atividades, n_ofertas


def run(client: UfsmClient, conn: sqlite3.Connection, *, todas: bool = False,
        limit: int | None = None) -> Coleta:
    sql = ("SELECT v.id, c.nome, v.numero FROM versao_curriculo v "
           "JOIN curso c ON c.id = v.curso_id ")
    if not todas:
        sql += "WHERE v.selecionada = 1 "
    sql += "ORDER BY c.nome, v.numero"
    if limit:
        sql += f" LIMIT {int(limit)}"

    alvos = conn.execute(sql).fetchall()
    total = len(alvos)
    print(f"\n{total} versões para coletar"
          f"{'' if todas else ' (apenas as selecionadas; use --todas para o histórico)'}\n",
          flush=True)

    coleta = Coleta()
    for i, row in enumerate(alvos, 1):
        versao_id, nome, numero = row[0], row[1], row[2]
        try:
            resp = client.call(endpoints.CURSO_ESTRUTURA,
                               {"versao": str(versao_id), "disciplinas": "true"})
            itens = resp.data.get("itens") or []
            if not itens:
                coleta.erros.append(f"versão {versao_id} ({nome} {numero}): árvore vazia")
                continue
            est, ativ, ofe = persist_versao(conn, versao_id, itens)
            conn.commit()
            coleta.versoes_ok += 1
            coleta.estruturas += est
            coleta.atividades += ativ
            coleta.ofertas += ofe
            if client.verbose:
                print(f"  {i:>3}/{total} {nome[:38]:<38} {numero:<8} "
                      f"estruturas={est:<3} ofertas={ofe}", flush=True)
        except Exception as exc:  # noqa: BLE001
            conn.rollback()
            coleta.erros.append(f"versão {versao_id} ({nome} {numero}): {exc}")
            print(f"  !! {nome} {numero}: {exc}", flush=True)

    return coleta


# --------------------------------------------------------------------- relatório
def relatorio(conn: sqlite3.Connection, coleta: Coleta) -> None:
    escalar = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731

    print("\n" + "=" * 72)
    print("RELATÓRIO — FASE 2")
    print("=" * 72)
    print(f"  versões coletadas .......... {coleta.versoes_ok}")
    print(f"  nós de estrutura ........... {coleta.estruturas}")
    print(f"  atividades (não-disciplina)  {coleta.atividades}")
    print(f"  ofertas de disciplina ...... {coleta.ofertas}")
    print(f"  disciplinas distintas ...... {escalar('SELECT COUNT(*) FROM disciplina')}")

    print("\n  ofertas por papel (tipo_item):")
    for tipo_item, tipo, n in conn.execute(
        "SELECT tipo_item, tipo, COUNT(*) FROM disciplina_curriculo "
        "GROUP BY tipo_item ORDER BY COUNT(*) DESC"
    ):
        print(f"    [{tipo_item}] {tipo or '?':<42} {n:>6}")

    # --- o checkpoint que importa: cotas de horas sem lista de disciplinas
    # (a) com atividades cadastradas: legítimo, fecha por atividades
    so_atividades = conn.execute(
        """
        SELECT COUNT(*) FROM estrutura e
        JOIN versao_curriculo v ON v.id = e.versao_id
        WHERE v.selecionada = 1 AND e.ch_minima > 0
          AND NOT EXISTS (SELECT 1 FROM disciplina_curriculo dc WHERE dc.estrutura_id = e.id)
          AND NOT EXISTS (SELECT 1 FROM estrutura f WHERE f.pai_id = e.id)
          AND EXISTS (SELECT 1 FROM estrutura_atividade a WHERE a.estrutura_id = e.id)
        """
    ).fetchone()[0]

    # (b) sem disciplinas E sem atividades: não há como cumprir pela lista -> aberto de fato
    abertos = conn.execute(
        """
        SELECT c.nome, v.numero, e.descricao, e.ch_minima
        FROM estrutura e
        JOIN versao_curriculo v ON v.id = e.versao_id
        JOIN curso c ON c.id = v.curso_id
        WHERE v.selecionada = 1
          AND e.ch_minima > 0
          AND NOT EXISTS (SELECT 1 FROM disciplina_curriculo dc WHERE dc.estrutura_id = e.id)
          AND NOT EXISTS (SELECT 1 FROM estrutura f WHERE f.pai_id = e.id)
          AND NOT EXISTS (SELECT 1 FROM estrutura_atividade a WHERE a.estrutura_id = e.id)
        ORDER BY e.ch_minima DESC
        """
    ).fetchall()

    print(f"\n  cotas fechadas por atividades complementares: {so_atividades}")
    print(f"  BUCKETS ABERTOS (cota de horas, sem disciplinas e sem atividades): {len(abertos)}")
    for nome, numero, descricao, ch in abertos[:25]:
        print(f"    {ch:>5}h  {nome[:40]:<40} {numero:<8} {descricao[:34]}")
    if len(abertos) > 25:
        print(f"    ... e mais {len(abertos) - 25}")

    if coleta.erros:
        print(f"\n  erros: {len(coleta.erros)}")
        for erro in coleta.erros[:10]:
            print(f"    - {erro}")
    print()

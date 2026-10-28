"""Fase 3 — pré-requisitos e equivalências.

Ambos vêm em blocos com a mesma semântica:
    OR entre blocos · AND dentro do bloco

Os endpoints são por `DisciplinaCurriculo.id` (a oferta), não pelo id global da
disciplina. Ver docs/ufsm-api.md §5 e §6.
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
    ofertas: int = 0
    blocos: int = 0
    itens: int = 0
    sem_relacao: int = 0
    erros: list[str] = field(default_factory=list)


def _persistir_blocos(conn: sqlite3.Connection, dc_id: int, blocos: list[dict],
                      tipo_bloco: str) -> tuple[int, int]:
    """Grava blocos+itens de pré-requisito (`pre`) ou equivalência (`eqv`)."""
    tabela_bloco = "prereq_bloco" if tipo_bloco == "pre" else "equivalencia_bloco"
    tabela_item = "prereq_item" if tipo_bloco == "pre" else "equivalencia_item"

    conn.execute(f"DELETE FROM {tabela_bloco} WHERE disciplina_curriculo_id = ?", (dc_id,))

    n_blocos = n_itens = 0
    for bloco in blocos:
        b = bloco.get("bloco") or {}
        bloco_id = conn.execute(
            f"INSERT INTO {tabela_bloco} (disciplina_curriculo_id, sie_item, sie_descricao) "
            "VALUES (?, ?, ?)",
            (dc_id, b.get("item"), b.get("descricao")),
        ).lastrowid
        n_blocos += 1

        for tipo in bloco.get("tipos") or []:
            t = tipo.get("tipo") or {}
            tipo_item = t.get("item")
            for item in tipo.get("itens") or []:
                req = item.get("disciplinaRequisito") or {}
                if req.get("id") and req.get("codigo"):
                    upsert_disciplina(conn, req)

                if tipo_bloco == "pre":
                    estrutura = item.get("estruturaCurricular") or {}
                    conn.execute(
                        f"INSERT INTO {tabela_item} (bloco_id, tipo_item, tipo, disciplina_req_id, "
                        "disciplina_req_codigo, numero_referencia, estrutura_ref) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (bloco_id, tipo_item, t.get("descricao"), req.get("id"),
                         req.get("codigo"), item.get("numeroReferencia"),
                         estrutura.get("descricao")),
                    )
                else:
                    ref = item.get("disciplinaCurriculoRef")
                    contexto = None
                    if isinstance(ref, dict):
                        versao = (ref.get("estrutura") or {}).get("versaoCurso") or {}
                        curso = versao.get("curso") or {}
                        if curso.get("descricao"):
                            contexto = f"{curso['descricao']} - {versao.get('numero')}"
                    conn.execute(
                        f"INSERT INTO {tabela_item} (bloco_id, disciplina_req_id, "
                        "disciplina_req_codigo, tipo_item, tipo, curriculo_ref) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (bloco_id, req.get("id"), req.get("codigo"), tipo_item,
                         t.get("descricao"), contexto),
                    )
                n_itens += 1

    return n_blocos, n_itens


def run(client: UfsmClient, conn: sqlite3.Connection, *, limit: int | None = None) -> Coleta:
    sql = """
        SELECT dc.id, dc.tem_prereq, dc.tem_equiv, c.nome, d.codigo, d.nome
        FROM disciplina_curriculo dc
        JOIN versao_curriculo v ON v.id = dc.versao_id
        JOIN curso c ON c.id = v.curso_id
        JOIN disciplina d ON d.id = dc.disciplina_id
        WHERE dc.tem_prereq = 1 OR dc.tem_equiv = 1
        ORDER BY c.nome, d.codigo
    """
    if limit:
        sql += f" LIMIT {int(limit)}"
    alvos = conn.execute(sql).fetchall()
    total = len(alvos)

    print(f"\n{total} ofertas com pré-requisito e/ou equivalência\n", flush=True)

    coleta = Coleta()
    for i, (dc_id, tem_pre, tem_eqv, curso, codigo, nome) in enumerate(alvos, 1):
        try:
            if tem_pre:
                resp = client.call(endpoints.CURSO_PREREQUISITOS, {"disciplina": str(dc_id)})
                blocos = resp.data or []
                if blocos:
                    b, it = _persistir_blocos(conn, dc_id, blocos, "pre")
                    coleta.blocos += b
                    coleta.itens += it
            if tem_eqv:
                resp = client.call(endpoints.CURSO_EQUIVALENCIAS, {"disciplina": str(dc_id)})
                blocos = resp.data or []
                if blocos:
                    b, it = _persistir_blocos(conn, dc_id, blocos, "eqv")
                    coleta.blocos += b
                    coleta.itens += it

            conn.commit()
            coleta.ofertas += 1
            if client.verbose and i % 25 == 0:
                print(f"  {i:>4}/{total} {codigo:<12} {nome[:42]}", flush=True)
        except Exception as exc:  # noqa: BLE001
            conn.rollback()
            coleta.erros.append(f"oferta {dc_id} ({codigo}): {exc}")

    return coleta


def relatorio(conn: sqlite3.Connection, coleta: Coleta) -> None:
    escalar = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731

    print("\n" + "=" * 72)
    print("RELATÓRIO — FASE 3")
    print("=" * 72)
    print(f"  ofertas processadas ........ {coleta.ofertas}")
    print(f"  blocos de pré-requisito .... {escalar('SELECT COUNT(*) FROM prereq_bloco')}")
    print(f"  itens de pré-requisito ..... {escalar('SELECT COUNT(*) FROM prereq_item')}")
    print(f"  blocos de equivalência ..... {escalar('SELECT COUNT(*) FROM equivalencia_bloco')}")
    print(f"  itens de equivalência ...... {escalar('SELECT COUNT(*) FROM equivalencia_item')}")

    print("\n  pré-requisitos por tipo:")
    for tipo_item, tipo, n in conn.execute(
        "SELECT tipo_item, tipo, COUNT(*) FROM prereq_item GROUP BY tipo_item ORDER BY COUNT(*) DESC"
    ):
        rotulo = tipo or endpoints.TIPO_PREREQUISITO.get(tipo_item, "?")
        print(f"    [{tipo_item}] {rotulo:<28} {n:>5}")

    print("\n  ofertas com pré-requisito de disciplina (tipo 1/2):")
    n = escalar("SELECT COUNT(DISTINCT bloco_id) FROM prereq_item WHERE tipo_item IN (1, 2)")
    print(f"    {n} blocos")

    print("\n  disciplinas que mais aparecem como pré-requisito:")
    for codigo, nome, n in conn.execute(
        """
        SELECT pi.disciplina_req_codigo, d.nome, COUNT(*) AS n
        FROM prereq_item pi LEFT JOIN disciplina d ON d.id = pi.disciplina_req_id
        WHERE pi.disciplina_req_id IS NOT NULL
        GROUP BY pi.disciplina_req_id ORDER BY n DESC LIMIT 10
        """
    ):
        print(f"    {n:>4}x  {codigo:<12} {(nome or '?')[:44]}")

    if coleta.erros:
        print(f"\n  erros: {len(coleta.erros)}")
        for erro in coleta.erros[:10]:
            print(f"    - {erro}")
    print()

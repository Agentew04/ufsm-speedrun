"""Materializa os pré-requisitos "fracos" (tipos 3 e 5).

O SIE registra quatro tipos de condição de matrícula:

    1  disciplinas vencidas         -> grafo (já tratado)
    2  correquisito                 -> grafo (já tratado)
    3  carga horária numa estrutura -> requisito_ch  (era ignorado)
    4  créditos vencidos            -> 0 ocorrências no banco
    5  período vencido              -> periodo_minimo (era ignorado)

Sem isso, a agenda semestral adianta disciplina que o aluno não poderia cursar.

    periodo_minimo = N   -> só pode cursar a partir do período N+1
    requisito_ch         -> uma linha por estrutura exigida; estrutura_id NULL
                            significa "GERAL" (total do curso), que aceita
                            somatório de qualquer estrutura
"""

from __future__ import annotations

import sqlite3


def aplicar(conn: sqlite3.Connection) -> dict:
    from . import db as _db

    _db.migrar(conn)

    conn.execute(
        "UPDATE disciplina_curriculo SET periodo_minimo = NULL WHERE periodo_minimo IS NOT NULL"
    )
    conn.execute("DELETE FROM requisito_ch")

    itens = conn.execute(
        """
        SELECT pb.disciplina_curriculo_id AS dc_id, pi.tipo_item,
               pi.numero_referencia AS referencia, pi.estrutura_ref
        FROM prereq_item pi
        JOIN prereq_bloco pb ON pb.id = pi.bloco_id
        WHERE pi.tipo_item IN (3, 4, 5)
        ORDER BY pb.disciplina_curriculo_id, pi.id
        """
    ).fetchall()

    mapa_estruturas = {
        (r[0], r[1]): r[2]
        for r in conn.execute("SELECT versao_id, descricao, id FROM estrutura")
    }
    versao_por_oferta = {
        r[0]: r[1] for r in conn.execute("SELECT id, versao_id FROM disciplina_curriculo")
    }

    periodos: dict[int, int] = {}
    cargas: list[tuple] = []
    creditos = 0

    for dc_id, tipo, referencia, estrutura_ref in itens:
        if referencia is None:
            continue
        if tipo == 5:
            periodos[dc_id] = max(periodos.get(dc_id, 0), referencia)
        elif tipo == 3:
            ref_id = mapa_estruturas.get((versao_por_oferta.get(dc_id), estrutura_ref))
            cargas.append((dc_id, ref_id, estrutura_ref, referencia))
        elif tipo == 4:
            creditos += 1

    conn.executemany(
        "INSERT INTO requisito_ch (disciplina_curriculo_id, estrutura_id, estrutura_texto, horas) "
        "VALUES (?, ?, ?, ?)",
        cargas,
    )
    conn.executemany(
        "UPDATE disciplina_curriculo SET periodo_minimo = ? WHERE id = ?",
        [(p, dc_id) for dc_id, p in periodos.items()],
    )
    conn.commit()

    resolvidas = sum(1 for _, ref_id, texto, _ in cargas if ref_id or not texto)
    print(f"  período vencido (tipo 5) ..... {len(periodos)} ofertas")
    print(f"  carga horária (tipo 3) ....... {len(cargas)} exigências em "
          f"{len({c[0] for c in cargas})} ofertas ({resolvidas} com estrutura resolvida)")
    print(f"  créditos vencidos (tipo 4) ... {creditos} itens no banco")

    return {"periodo": len(periodos), "carga": len(cargas), "creditos": creditos}


def relatorio(conn: sqlite3.Connection) -> None:
    print("\n  distribuição de período mínimo:")
    for periodo, n in conn.execute(
        "SELECT periodo_minimo, COUNT(*) FROM disciplina_curriculo "
        "WHERE periodo_minimo IS NOT NULL GROUP BY 1 ORDER BY 1"
    ):
        print(f"    vencido o {periodo}º -> cursar a partir do {periodo + 1}º: {n} ofertas")

    print("\n  exigências de carga horária (top 6):")
    for horas, texto, n in conn.execute(
        """
        SELECT horas, COALESCE(estrutura_texto, 'GERAL (total do curso)'), COUNT(*)
        FROM requisito_ch GROUP BY horas, estrutura_texto ORDER BY horas DESC LIMIT 6
        """
    ):
        print(f"    {horas:>5}h em {texto[:44]:<44} {n} exigência(s)")

"""Quais disciplinas podem preencher cada cota de DCG.

Problema que isto resolve: o SIE lista, para cada currículo, o **menu** de
Disciplinas Complementares de Graduação (DCG). O otimizador ignorava o menu e
tratava toda cota como "qualquer disciplina do catálogo" — o que produz sugestões
que nenhum colegiado aprovaria (TCC de outro curso como DCG, música em CC).

Aqui o menu vira dado materializado em `dcg_elegivel`, com duas origens:

    menu    -> a lista explícita do currículo (129 estruturas)
    aberta  -> cota de DCG sem lista (ex.: SI/2026, 420 h) — qualquer disciplina

Exceção de domínio: disciplinas **terminais** (TCC/TCG/TG, estágio, monografia)
nunca entram. Elas são amarradas ao curso; "TCC de SI como DCG de CC" não existe.
"""

from __future__ import annotations

import re
import sqlite3

DCG_NO_NOME = re.compile(r"disciplinas?\s+complementares?|\bdcg\b", re.I)
TIPOS_MENU = (2, 3, 5, 7)   # optativa, eletiva, DCG graduação, DCG pós
TIPO_OBRIGATORIA = 1
TIPO_DCG = (5, 7)


def construir(conn: sqlite3.Connection) -> dict:
    from . import db as _db

    _db.migrar(conn)

    versoes = conn.execute(
        """
        SELECT v.id, v.curso_id, v.ch_total
        FROM versao_curriculo v
        WHERE v.selecionada = 1
        """
    ).fetchall()

    conn.execute("DELETE FROM dcg_elegivel")
    linhas: list[tuple] = []
    n_menu = n_aberta = n_excluidas = 0

    for versao_id, curso_id, _ch_total in versoes:
        estruturas = conn.execute(
            "SELECT id, pai_id, descricao, ch_minima FROM estrutura WHERE versao_id = ? ORDER BY id",
            (versao_id,),
        ).fetchall()
        por_id = {e["id"]: e for e in estruturas}

        ofertas = conn.execute(
            """
            SELECT dc.estrutura_id, dc.disciplina_id, dc.tipo_item, d.ch_total
            FROM disciplina_curriculo dc
            JOIN disciplina d ON d.id = dc.disciplina_id
            WHERE dc.versao_id = ?
            """,
            (versao_id,),
        ).fetchall()

        por_estrutura: dict[int, list[sqlite3.Row]] = {}
        ch_obrigatoria: dict[int, int] = {}
        vistos: set[int] = set()
        for o in ofertas:
            por_estrutura.setdefault(o["estrutura_id"], []).append(o)
            if o["tipo_item"] == TIPO_OBRIGATORIA and o["disciplina_id"] not in vistos:
                vistos.add(o["disciplina_id"])
                ch_obrigatoria[o["estrutura_id"]] = (
                    ch_obrigatoria.get(o["estrutura_id"], 0) + (o["ch_total"] or 0)
                )

        def tem_ancestral_com_cota(est) -> bool:
            pai = por_id.get(est["pai_id"]) if est["pai_id"] else None
            guarda = 0
            while pai and guarda < 32:
                guarda += 1
                if (pai["ch_minima"] or 0) > 0:
                    return True
                pai = por_id.get(pai["pai_id"]) if pai["pai_id"] else None
            return False

        for est in estruturas:
            minima = est["ch_minima"] or 0
            if minima <= 0 or tem_ancestral_com_cota(est):
                continue
            deficit = minima - ch_obrigatoria.get(est["id"], 0)
            if deficit <= 0:
                continue

            da_estrutura = por_estrutura.get(est["id"], [])
            candidatos = [o["disciplina_id"] for o in da_estrutura if o["tipo_item"] in TIPOS_MENU]
            tem_dcg = any(o["tipo_item"] in TIPO_DCG for o in da_estrutura)
            eh_dcg = tem_dcg or bool(DCG_NO_NOME.search(est["descricao"] or ""))
            if not eh_dcg:
                continue

            if candidatos:
                # menu explícito do currículo
                elegiveis = conn.execute(
                    f"""
                    SELECT id FROM disciplina
                    WHERE id IN ({",".join("?" * len(candidatos))})
                      AND eh_terminal = 0
                    """,
                    candidatos,
                ).fetchall()
                ids = [r[0] for r in elegiveis]
                n_excluidas += len(set(candidatos)) - len(ids)
                linhas.extend((curso_id, est["id"], did, "menu", deficit) for did in ids)
                n_menu += 1
            else:
                # cota de DCG sem lista: qualquer disciplina não-terminal e ativa
                elegiveis = conn.execute(
                    "SELECT id FROM disciplina "
                    "WHERE eh_terminal = 0 AND COALESCE(situacao_codigo, 'A') = 'A'"
                ).fetchall()
                ids = [r[0] for r in elegiveis]
                linhas.extend((curso_id, est["id"], did, "aberta", deficit) for did in ids)
                n_aberta += 1

    conn.executemany(
        "INSERT INTO dcg_elegivel (curso_id, estrutura_id, disciplina_id, fonte, horas_cota) "
        "VALUES (?, ?, ?, ?, ?)",
        linhas,
    )
    conn.commit()

    total_estruturas = n_menu + n_aberta
    print(f"  estruturas de DCG ........ {total_estruturas}")
    print(f"    com menu listado ....... {n_menu}")
    print(f"    cota aberta ............ {n_aberta}")
    print(f"  linhas de elegibilidade .. {len(linhas)}")
    print(f"  terminais excluídas ...... {n_excluidas} entradas de menu")

    return {"estruturas": total_estruturas, "menu": n_menu, "aberta": n_aberta,
            "linhas": len(linhas)}


def relatorio(conn: sqlite3.Connection) -> None:
    print("\n  maiores menus de DCG:")
    for curso, ch, n in conn.execute(
        """
        SELECT c.nome, de.horas_cota, COUNT(*)
        FROM dcg_elegivel de
        JOIN curso c ON c.id = de.curso_id
        WHERE de.fonte = 'menu'
        GROUP BY de.curso_id, de.estrutura_id
        ORDER BY COUNT(*) DESC LIMIT 8
        """
    ):
        print(f"    {n:>3} disciplinas · {ch:>4}h  {curso[:52]}")

    print("\n  terminais que estavam em menu e foram barradas:")
    for codigo, nome, categoria in conn.execute(
        """
        SELECT DISTINCT d.codigo, d.nome, d.terminal_categoria
        FROM disciplina_curriculo dc
        JOIN disciplina d ON d.id = dc.disciplina_id
        JOIN versao_curriculo v ON v.id = dc.versao_id
        WHERE v.selecionada = 1 AND dc.tipo_item = 5 AND d.eh_terminal = 1
        ORDER BY d.codigo LIMIT 12
        """
    ):
        print(f"    {codigo:<12} {nome[:48]:<48} [{categoria}]")

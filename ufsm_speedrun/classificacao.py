"""Classificação dos cursos — propriedade do DADO, não da tela.

O SIE tem registros que **não são cursos completos**: são a porta de entrada
(ABI — Área Básica de Ingresso / "núcleo comum"). Ex.: `Artes Cênicas -
Bacharelado` tem 960 h, enquanto a habilitação irmã tem 2.756 h. Quem "fecha" o
ABI não recebe diploma de bacharel.

Essa classificação era feita no front (`web/src/db/load.ts:247`), recalculada a
cada carregamento. Aqui ela vira coluna do banco — mesma regra, fonte única.
"""

from __future__ import annotations

import re
import sqlite3
import unicodedata


def _normalizar(texto: str | None) -> str:
    t = unicodedata.normalize("NFKD", (texto or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c))


PADROES_TERMINAL = [
    ("tcc", r"\b(tcc|tcg|tccg|tg)\b|trabalho de (conclus|gradua)|trabalho final|trabalho de fim"),
    ("estagio", r"\best[áa]gio\b|relat[óo]rio de est[áa]gio"),
    ("monografia", r"monografia|disserta"),
]


def marcar_terminais(conn: sqlite3.Connection) -> dict:
    """Marca disciplinas que não são transferíveis entre cursos.

    TCC/TCG/TG, estágio e monografia são amarrados ao curso (o aluno escreve o
    trabalho *daquele* curso). Aceitá-los como DCG de outro curso é erro de
    domínio: "TCC de SI como DCG de CC" não existe.
    """
    disciplinas = conn.execute("SELECT id, nome FROM disciplina").fetchall()

    contagem: dict[str, int] = {}
    conn.execute("UPDATE disciplina SET eh_terminal = 0, terminal_categoria = NULL, "
                 "terminal_motivo = NULL")
    for disc_id, nome in disciplinas:
        for categoria, padrao in PADROES_TERMINAL:
            achado = re.search(padrao, nome or "", re.I)
            if achado:
                contagem[categoria] = contagem.get(categoria, 0) + 1
                conn.execute(
                    "UPDATE disciplina SET eh_terminal = 1, terminal_categoria = ?, "
                    "terminal_motivo = ? WHERE id = ?",
                    (categoria, f"nome contém '{achado.group(0)}'", disc_id),
                )
                break
    conn.commit()

    total = sum(contagem.values())
    print(f"  disciplinas terminais ..... {total} de {len(disciplinas)}")
    for categoria, n in sorted(contagem.items(), key=lambda x: -x[1]):
        print(f"    {categoria:<12} {n:>4}")
    return contagem


def classificar(conn: sqlite3.Connection) -> dict:
    from . import db as _db

    _db.migrar(conn)

    linhas = conn.execute(
        """
        SELECT c.id, c.nome, c.nome_lista, v.ch_total
        FROM curso c
        JOIN versao_curriculo v ON v.curso_id = c.id AND v.selecionada = 1
        """
    ).fetchall()

    # maior CH entre os cursos que compartilham o mesmo nome na lista
    por_lista: dict[str, int] = {}
    for _, _, nome_lista, ch_total in linhas:
        if not nome_lista:
            continue
        por_lista[nome_lista] = max(por_lista.get(nome_lista, 0), ch_total or 0)

    marcados = 0
    for curso_id, nome, nome_lista, ch_total in linhas:
        motivo = None

        if "nucleo comum" in _normalizar(nome):
            motivo = "nome contém 'núcleo comum'"
        elif nome_lista and ch_total:
            irmao = por_lista.get(nome_lista, 0)
            if irmao >= ch_total * 2 and ch_total < 2000:
                motivo = f"ABI: irmão com {irmao} h ({irmao / ch_total:.1f}× a CH deste)"

        eh = 1 if motivo else 0
        marcados += eh
        conn.execute(
            "UPDATE curso SET eh_nucleo_comum = ?, nucleo_comum_motivo = ? WHERE id = ?",
            (eh, motivo, curso_id),
        )

    conn.commit()

    print(f"  cursos classificados ..... {len(linhas)}")
    print(f"  núcleo comum / ABI ....... {marcados}")
    for curso_id, nome, _, ch_total in linhas:
        motivo = conn.execute(
            "SELECT nucleo_comum_motivo FROM curso WHERE id = ?", (curso_id,)
        ).fetchone()[0]
        if motivo:
            print(f"    {ch_total:>5} h  {nome[:52]:<52} — {motivo}")

    marcar_terminais(conn)
    return {"total": len(linhas), "nucleo_comum": marcados}

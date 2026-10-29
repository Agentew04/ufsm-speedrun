"""Fechamento transitivo das equivalências.

O SIE troca códigos de disciplina a cada reforma curricular: a mesma cadeira pode
aparecer como `ELC1086` num currículo antigo e `UFSM01310` num novo, com uma
terceira (`ELC1077`) fazendo a ponte. Sem transitividade, quem cursou a antiga
não "vê" a nova.

    ELC1086 ≡ ELC1077   (0,84)
    ELC1077 ≡ UFSM01310 (0,59)
    --------------------------------
    ELC1086 ≡ UFSM01310 (transitiva, 2 saltos)

Regras:
  * só arestas **equivalentes** propagam (oficial, julgada `equivalente`,
    heurística `equivalente`); `parcial` fica de fora — não é decisão, é dúvida;
  * disciplinas **terminais** nunca entram (TCC não se equivale a TCC);
  * profundidade limitada (padrão 3) para não transformar a cadeia em borracha;
  * a confiança da aresta fechada é o **mínimo** do caminho.
"""

from __future__ import annotations

import sqlite3
from collections import deque


def _arestas(conn: sqlite3.Connection) -> dict[int, list[tuple[int, float]]]:
    """Arestas dirigidas com confiança, sem terminais e sem `parcial`."""
    grafo: dict[int, list[tuple[int, float]]] = {}
    consulta = """
        SELECT x.alvo_id, x.substituta_id, x.confianca
        FROM v_equivalencia_efetiva x
        JOIN disciplina a ON a.id = x.alvo_id
        JOIN disciplina b ON b.id = x.substituta_id
        WHERE a.eh_terminal = 0 AND b.eh_terminal = 0
          AND x.origem <> 'transitiva'
          AND x.veredito = 'equivalente'
    """
    for alvo, sub, conf in conn.execute(consulta):
        grafo.setdefault(alvo, []).append((sub, conf if conf is not None else 1.0))
    return grafo


def construir(conn: sqlite3.Connection, profundidade: int = 3) -> dict:
    from . import db as _db

    _db.migrar(conn)
    grafo = _arestas(conn)

    diretas = {(a, b) for a, lista in grafo.items() for b, _ in lista}
    fechadas: dict[tuple[int, int], tuple[int, float, int]] = {}

    for origem in grafo:
        visto = {origem}
        fila = deque()
        for destino, conf in grafo[origem]:
            if destino != origem:
                fila.append((destino, conf, 1, destino))
                visto.add(destino)

        while fila:
            no, conf, saltos, via = fila.popleft()
            if saltos >= 2 and (origem, no) not in diretas:
                atual = fechadas.get((origem, no))
                if atual is None or conf > atual[1]:
                    fechadas[(origem, no)] = (saltos, conf, via)
            if saltos >= profundidade:
                continue
            for proximo, conf2 in grafo.get(no, ()):
                if proximo in visto:
                    continue
                visto.add(proximo)
                fila.append((proximo, min(conf, conf2), saltos + 1, via))

    conn.execute("DELETE FROM equivalencia_fechada")
    conn.executemany(
        "INSERT INTO equivalencia_fechada (alvo_id, substituta_id, saltos, confianca, via_id) "
        "VALUES (?, ?, ?, ?, ?)",
        [(a, b, s, c, v) for (a, b), (s, c, v) in fechadas.items()],
    )
    conn.commit()

    print(f"  arestas de entrada ........ {len(diretas)}")
    print(f"  pares fechados ............ {len(fechadas)} (profundidade <= {profundidade})")

    return {"diretas": len(diretas), "fechadas": len(fechadas)}


def relatorio(conn: sqlite3.Connection) -> None:
    print("\n  distribuição por número de saltos:")
    for saltos, n in conn.execute(
        "SELECT saltos, COUNT(*) FROM equivalencia_fechada GROUP BY saltos ORDER BY saltos"
    ):
        print(f"    {saltos} saltos: {n} pares")

#!/usr/bin/env python3
"""Copia data/ufsm.db para web/public/ufsm.db com o WAL já aplicado.

Por que não copiar o arquivo na mão: o coletor usa WAL, então os últimos commits
podem estar em `ufsm.db-wal`. O backup API do sqlite resolve isso e produz um
arquivo único consistente — é esse que o frontend (sql.js) carrega.

Uso:
    python web/scripts/snapshot-db.py
    python web/scripts/snapshot-db.py --src data/ufsm.db --dst web/public/ufsm.db
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", default=str(RAIZ / "data" / "ufsm.db"))
    parser.add_argument("--dst", default=str(RAIZ / "web" / "public" / "ufsm.db"))
    args = parser.parse_args()

    src = Path(args.src)
    dst = Path(args.dst)
    if not src.exists():
        print(f"erro: {src} não existe (rode as fases de coleta primeiro)", file=sys.stderr)
        return 1

    dst.parent.mkdir(parents=True, exist_ok=True)
    origem = sqlite3.connect(f"file:{src.as_posix()}?mode=ro", uri=True)
    destino = sqlite3.connect(dst)
    try:
        origem.backup(destino)
        destino.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        destino.commit()
    finally:
        destino.close()
        origem.close()

    check = sqlite3.connect(f"file:{dst.as_posix()}?mode=ro", uri=True)
    try:
        contar = lambda sql: check.execute(sql).fetchone()[0]
        print(f"ok: {dst}  ({dst.stat().st_size / 1_048_576:.1f} MB)")
        print(f"    cursos          {contar('SELECT COUNT(*) FROM curso')}")
        print(f"    ofertas         {contar('SELECT COUNT(*) FROM disciplina_curriculo')}")
        print(f"    disciplinas     {contar('SELECT COUNT(*) FROM disciplina')}")
        print(f"    pre-req itens   {contar('SELECT COUNT(*) FROM prereq_item')}")
        print(f"    com ementa      {contar('SELECT COUNT(*) FROM disciplina WHERE programa_texto IS NOT NULL')}")
    finally:
        check.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

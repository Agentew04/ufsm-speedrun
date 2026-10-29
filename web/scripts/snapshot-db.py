#!/usr/bin/env python3
"""Copia o banco para web/public/ufsm.db com o WAL já aplicado.

Por padrão usa o **núcleo publicado** (`data/public/ufsm-web.db`, ~8 MB), que já
vem sem as ementas — o front não usa ementas. Se ele não existir (ou com
`--src data/ufsm.db`), copia o banco de trabalho completo.

Por que não copiar o arquivo na mão: o coletor usa WAL, então os últimos commits
podem estar em `ufsm.db-wal`. O backup API do sqlite resolve isso e produz um
arquivo único consistente — é esse que o frontend (sql.js) carrega.

Uso:
    python web/scripts/snapshot-db.py
    python web/scripts/snapshot-db.py --src data/ufsm.db
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", default=None)
    parser.add_argument("--dst", default=str(RAIZ / "web" / "public" / "ufsm.db"))
    args = parser.parse_args()

    if args.src:
        src = Path(args.src)
    else:
        publicado = RAIZ / "data" / "public" / "ufsm-web.db"
        src = publicado if publicado.exists() else RAIZ / "data" / "ufsm.db"
    dst = Path(args.dst)
    if not src.exists():
        print(f"erro: {src} não existe (rode as fases de coleta/publicar)", file=sys.stderr)
        return 1

    dst.parent.mkdir(parents=True, exist_ok=True)
    origem = sqlite3.connect(f"file:{src.as_posix()}?mode=ro", uri=True)
    destino = sqlite3.connect(dst)
    try:
        origem.backup(destino)
        destino.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        destino.execute("PRAGMA journal_mode=DELETE")
        destino.commit()
    finally:
        destino.close()
        origem.close()

    # se o artefato publicado comprimido existir, ele é o que o front baixa
    # (2,1 MB em vez de 7,9 MB); o .db fica como fallback
    gz = src.parent / f"{src.name}.gz"
    if gz.exists():
        shutil.copyfile(gz, dst.parent / f"{dst.name}.gz")
        print(f"     + {dst.name}.gz  ({gz.stat().st_size / 1_048_576:.1f} MB)")

    # conteúdo sob demanda: ementas e bibliografias (não entram no boot)
    publicados = RAIZ / "data" / "public"
    for nome in ("ementas.db.gz", "bibliografias.db.gz"):
        artefato = publicados / nome
        if artefato.exists():
            shutil.copyfile(artefato, dst.parent / nome)
            print(f"     + {nome}  ({artefato.stat().st_size / 1_048_576:.1f} MB)")

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

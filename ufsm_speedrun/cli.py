"""Interface de linha de comando.

Uso:
    python -m ufsm_speedrun init-db [--recreate]
    python -m ufsm_speedrun smoke [--refresh]
    python -m ufsm_speedrun stats
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from . import config, db, endpoints
from .http import UfsmClient

VERSAO_DEMO = "104760"  # Ciência da Computação, currículo 2024


# --------------------------------------------------------------------- helpers
def _human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _walk(estrutura: dict, depth: int = 0) -> list[tuple[int, dict]]:
    out = [(depth, estrutura)]
    for filha in estrutura.get("filhas") or []:
        out.extend(_walk(filha, depth + 1))
    return out


# -------------------------------------------------------------------- comandos
def cmd_init_db(args: argparse.Namespace) -> int:
    path = db.init_db(recreate=args.recreate)
    print(f"banco criado: {path}")
    for tabela, n in db.counts(path).items():
        print(f"  {tabela:<24} {n:>6}")
    return 0


def cmd_smoke(args: argparse.Namespace) -> int:
    print(f"cliente: {config.BASE_URL}")
    print(f"raw:     {config.RAW_DIR}")
    print(f"log:     {config.REQUESTS_LOG}\n")

    client = UfsmClient(min_interval=args.delay, refresh=args.refresh,
                        verbose=not args.quiet)

    print(f"[1/2] estrutura da versao {VERSAO_DEMO} (rede ou cache)")
    res = client.call(endpoints.CURSO_ESTRUTURA,
                      {"versao": VERSAO_DEMO, "disciplinas": "true"})
    itens = res.data.get("itens") or []

    total_disc = 0
    tipos: Counter[str] = Counter()
    for raiz in itens:
        for depth, node in _walk(raiz):
            disc = node.get("disciplinas") or []
            ativ = node.get("atividades") or []
            total_disc += len(disc)
            for d in disc:
                tipos[d["tipo"]["descricao"]] += 1
            marcador = f"disc={len(disc):>2}" if disc else "      "
            if ativ:
                marcador = f"ativ={len(ativ):>2}"
            print(f"  {'  ' * depth}- {node['descricao']:<50} {marcador}"
                  f"  chMin={node.get('cargaHorariaMinima')}")

    print(f"\n  total de ofertas de disciplina: {total_disc}")
    for k, v in tipos.most_common():
        print(f"    {k:<40} {v}")
    print(f"  origem: {'cache local' if res.from_cache else 'rede'}")

    print("\n[2/2] mesma chamada de novo — deve vir do cache, sem tocar na rede")
    res2 = client.call(endpoints.CURSO_ESTRUTURA,
                       {"versao": VERSAO_DEMO, "disciplinas": "true"})
    if not res2.from_cache:
        print("  AVISO: esperava cache hit e houve chamada de rede.")
        return 1
    print("  ok: cache hit confirmado")

    print(f"\nestatisticas: {client.stats.summary()}")
    print("fase 0 validada.")
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    from .recorder import Recorder

    rec = Recorder()
    n_raw = rec.count_raw()
    n_log = rec.count_log()
    raw_bytes = sum(p.stat().st_size for p in rec.raw_dir.rglob("*.json")) if rec.raw_dir.exists() else 0

    print("== disco ==")
    print(f"  respostas cruas : {n_raw} arquivos ({_human(raw_bytes)})")
    print(f"  linhas de log   : {n_log}")

    db_path = Path(config.DB_PATH)
    if db_path.exists():
        print(f"\n== banco ({db_path.name}, {_human(db_path.stat().st_size)}) ==")
        for tabela, n in db.counts(db_path).items():
            print(f"  {tabela:<24} {n:>6}")
    else:
        print(f"\n  banco ainda não existe ({db_path}) — rode: init-db")
    return 0


# ----------------------------------------------------------------------- main
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ufsm-speedrun",
        description="Coletor de dados curriculares da UFSM (respeitoso, com cache em disco).",
    )
    sub = parser.add_subparsers(dest="comando", required=True)

    p = sub.add_parser("init-db", help="cria o SQLite a partir de schema.sql")
    p.add_argument("--recreate", action="store_true", help="apaga e recria o banco")
    p.set_defaults(func=cmd_init_db)

    p = sub.add_parser("smoke", help="testa o pipeline (1 request) e o cache")
    p.add_argument("--refresh", action="store_true", help="ignora o cache e refaz a chamada")
    p.add_argument("--delay", type=float, default=config.MIN_INTERVAL,
                   help=f"intervalo minimo entre requests (padrao {config.MIN_INTERVAL}s)")
    p.add_argument("--quiet", action="store_true")
    p.set_defaults(func=cmd_smoke)

    p = sub.add_parser("stats", help="mostra o que já foi coletado")
    p.set_defaults(func=cmd_stats)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

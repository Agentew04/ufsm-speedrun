"""Interface de linha de comando.

Uso:
    python -m ufsm_speedrun init-db [--recreate]
    python -m ufsm_speedrun smoke [--refresh]
    python -m ufsm_speedrun stats
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from pathlib import Path

from . import (config, curriculos, db, discover, ementas, endpoints,
               equivalencia, julgamento, relacoes, validacao)
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


def cmd_discover(args: argparse.Namespace) -> int:
    from .recorder import utc_now

    if not Path(config.DB_PATH).exists():
        print(f"banco não existe em {config.DB_PATH} — rode: init-db")
        return 1

    client = UfsmClient(min_interval=args.delay, refresh=args.refresh,
                        verbose=not args.quiet)

    conn = db.connect()
    cur = conn.execute(
        "INSERT INTO ingest_run (fase, iniciado_em, raw_dir) VALUES (?, ?, ?)",
        ("discover", utc_now(), str(config.RAW_DIR)),
    )
    run_id = cur.lastrowid
    conn.commit()

    inicio = time.monotonic()
    try:
        descoberta = discover.discover(client, limit=args.limit)
        por_curso = discover.persist(conn, descoberta)
        discover.relatorio(conn, descoberta, por_curso)
        duracao = time.monotonic() - inicio
        conn.execute(
            "UPDATE ingest_run SET finalizado_em = ?, observacoes = ? WHERE id = ?",
            (utc_now(), f"{client.stats.summary()} em {duracao:.0f}s", run_id),
        )
        conn.commit()
        print(f"  estatísticas: {client.stats.summary()} em {duracao:.0f}s\n")
        return 0 if not descoberta.erros else 2
    finally:
        conn.close()


def cmd_curriculos(args: argparse.Namespace) -> int:
    from .recorder import utc_now

    if not Path(config.DB_PATH).exists():
        print(f"banco não existe em {config.DB_PATH} — rode: init-db")
        return 1

    conn = db.connect()
    client = UfsmClient(min_interval=args.delay, refresh=args.refresh,
                        verbose=not args.quiet)

    run_id = conn.execute(
        "INSERT INTO ingest_run (fase, iniciado_em, raw_dir) VALUES (?, ?, ?)",
        ("curriculos", utc_now(), str(config.RAW_DIR)),
    ).lastrowid
    conn.commit()

    inicio = time.monotonic()
    try:
        coleta = curriculos.run(client, conn, todas=args.todas, limit=args.limit)
        curriculos.relatorio(conn, coleta)
        duracao = time.monotonic() - inicio
        conn.execute(
            "UPDATE ingest_run SET finalizado_em = ?, observacoes = ? WHERE id = ?",
            (utc_now(), f"{client.stats.summary()} em {duracao:.0f}s", run_id),
        )
        conn.commit()
        print(f"  estatísticas: {client.stats.summary()} em {duracao:.0f}s\n")
        return 0 if not coleta.erros else 2
    finally:
        conn.close()


def cmd_relacoes(args: argparse.Namespace) -> int:
    from .recorder import utc_now

    if not Path(config.DB_PATH).exists():
        print(f"banco não existe em {config.DB_PATH} — rode: init-db")
        return 1

    conn = db.connect()
    client = UfsmClient(min_interval=args.delay, refresh=args.refresh,
                        verbose=not args.quiet)
    run_id = conn.execute(
        "INSERT INTO ingest_run (fase, iniciado_em, raw_dir) VALUES (?, ?, ?)",
        ("relacoes", utc_now(), str(config.RAW_DIR)),
    ).lastrowid
    conn.commit()

    inicio = time.monotonic()
    try:
        coleta = relacoes.run(client, conn, limit=args.limit)
        relacoes.relatorio(conn, coleta)
        duracao = time.monotonic() - inicio
        conn.execute(
            "UPDATE ingest_run SET finalizado_em = ?, observacoes = ? WHERE id = ?",
            (utc_now(), f"{client.stats.summary()} em {duracao:.0f}s", run_id),
        )
        conn.commit()
        print(f"  estatísticas: {client.stats.summary()} em {duracao:.0f}s\n")
        return 0 if not coleta.erros else 2
    finally:
        conn.close()


def cmd_ementas(args: argparse.Namespace) -> int:
    from .recorder import utc_now

    if not Path(config.DB_PATH).exists():
        print(f"banco não existe em {config.DB_PATH} — rode: init-db")
        return 1

    conn = db.connect()
    client = UfsmClient(min_interval=args.delay, refresh=args.refresh,
                        verbose=not args.quiet)
    run_id = conn.execute(
        "INSERT INTO ingest_run (fase, iniciado_em, raw_dir) VALUES (?, ?, ?)",
        ("ementas", utc_now(), str(config.RAW_DIR)),
    ).lastrowid
    conn.commit()

    inicio = time.monotonic()
    try:
        coleta = ementas.run(client, conn, limit=args.limit, refazer=args.refazer)
        ementas.relatorio(conn, coleta)
        duracao = time.monotonic() - inicio
        conn.execute(
            "UPDATE ingest_run SET finalizado_em = ?, observacoes = ? WHERE id = ?",
            (utc_now(), f"{client.stats.summary()} em {duracao:.0f}s", run_id),
        )
        conn.commit()
        print(f"  estatísticas: {client.stats.summary()} em {duracao:.0f}s\n")
        return 0 if not coleta.erros else 2
    finally:
        conn.close()


def cmd_tudo(args: argparse.Namespace) -> int:
    """Roda o pipeline inteiro em sequência (retomável: o cache evita refazer)."""
    etapas = [
        ("discover", cmd_discover),
        ("curriculos", cmd_curriculos),
        ("relacoes", cmd_relacoes),
        ("ementas", cmd_ementas),
    ]
    pior = 0
    for nome, funcao in etapas:
        print(f"\n{'#' * 72}\n# {nome.upper()}\n{'#' * 72}")
        codigo = funcao(args)
        if codigo == 1:  # erro fatal (ex.: banco ausente)
            return codigo
        pior = max(pior, codigo)
    return pior


def cmd_validar(args: argparse.Namespace) -> int:
    if not Path(config.DB_PATH).exists():
        print(f"banco não existe em {config.DB_PATH} — rode: init-db")
        return 1
    conn = db.connect()
    try:
        validacao.gerar(conn, Path(args.out) if args.out else None)
    finally:
        conn.close()
    return 0


def cmd_equivalencia(args: argparse.Namespace) -> int:
    if not Path(config.DB_PATH).exists():
        print(f"banco não existe em {config.DB_PATH} — rode: init-db")
        return 1

    cfg = equivalencia.Config(top_k=args.top_k,
                              limiar_equivalente=args.limiar,
                              limiar_nao=args.limiar_nao)
    conn = db.connect()
    inicio = time.monotonic()
    try:
        resultado = equivalencia.run(conn, cfg, exportar=not args.sem_export)
        equivalencia.relatorio(conn, resultado)
        print(f"  tempo: {time.monotonic() - inicio:.0f}s\n")
    finally:
        conn.close()
    return 0


def cmd_julgar_exportar(args: argparse.Namespace) -> int:
    if not Path(config.DB_PATH).exists():
        print(f"banco não existe em {config.DB_PATH} — rode: init-db")
        return 1
    conn = db.connect()
    try:
        destino = Path(args.dir) if args.dir else config.DATA_DIR / "exports" / "lotes"
        caminhos = julgamento.exportar_lotes(conn, destino, lotes=args.lotes)
        if not caminhos:
            print("nada a julgar: rode 'equivalencia' antes")
            return 0
        for c in caminhos:
            print(f"    {c.name}")
    finally:
        conn.close()
    return 0


def cmd_julgar_aplicar(args: argparse.Namespace) -> int:
    if not Path(config.DB_PATH).exists():
        print(f"banco não existe em {config.DB_PATH} — rode: init-db")
        return 1
    conn = db.connect()
    try:
        origem = Path(args.dir) if args.dir else config.DATA_DIR / "exports" / "lotes"
        julgamento.aplicar(conn, origem, julgador=args.julgador)
        julgamento.relatorio(conn)
    finally:
        conn.close()
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

        conn = db.connect(db_path)
        try:
            sem_ementa = conn.execute(
                "SELECT COUNT(*) FROM disciplina WHERE raw_file IS NULL"
            ).fetchone()[0]
            total_disc = conn.execute("SELECT COUNT(*) FROM disciplina").fetchone()[0]
            ofertas_rel = conn.execute(
                "SELECT COUNT(*) FROM disciplina_curriculo WHERE tem_prereq = 1 OR tem_equiv = 1"
            ).fetchone()[0]
            com_blocos = conn.execute(
                """
                SELECT COUNT(*) FROM (
                    SELECT disciplina_curriculo_id FROM prereq_bloco
                    UNION SELECT disciplina_curriculo_id FROM equivalencia_bloco
                )
                """
            ).fetchone()[0]
            print("\n== faltando para concluir a coleta ==")
            print(f"  fase 3: {ofertas_rel - com_blocos} ofertas sem relação gravada "
                  f"(de {ofertas_rel}; reprocessar usa cache, não rede)")
            print(f"  fase 4: {sem_ementa} disciplinas sem ementa baixada "
                  f"(de {total_disc})")
        finally:
            conn.close()
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

    p = sub.add_parser("discover", help="fase 1: descobre cursos e versões de currículo")
    p.add_argument("--limit", type=int, default=None, help="limita o nº de páginas (teste)")
    p.add_argument("--refresh", action="store_true", help="ignora o cache e refaz as chamadas")
    p.add_argument("--delay", type=float, default=config.MIN_INTERVAL,
                   help=f"intervalo minimo entre requests (padrao {config.MIN_INTERVAL}s)")
    p.add_argument("--quiet", action="store_true")
    p.set_defaults(func=cmd_discover)

    p = sub.add_parser("curriculos", help="fase 2: coleta as árvores curriculares")
    p.add_argument("--todas", action="store_true",
                   help="inclui versões históricas (Ativa/Inativa), não só as selecionadas")
    p.add_argument("--limit", type=int, default=None, help="limita o nº de versões (teste)")
    p.add_argument("--refresh", action="store_true", help="ignora o cache e refaz as chamadas")
    p.add_argument("--delay", type=float, default=config.MIN_INTERVAL,
                   help=f"intervalo minimo entre requests (padrao {config.MIN_INTERVAL}s)")
    p.add_argument("--quiet", action="store_true")
    p.set_defaults(func=cmd_curriculos)

    p = sub.add_parser("relacoes", help="fase 3: pré-requisitos e equivalências")
    p.add_argument("--limit", type=int, default=None, help="limita o nº de ofertas (teste)")
    p.add_argument("--refresh", action="store_true")
    p.add_argument("--delay", type=float, default=config.MIN_INTERVAL)
    p.add_argument("--quiet", action="store_true")
    p.set_defaults(func=cmd_relacoes)

    p = sub.add_parser("ementas", help="fase 4: baixa o programa/ementa de cada disciplina")
    p.add_argument("--limit", type=int, default=None, help="limita o nº de disciplinas (teste)")
    p.add_argument("--refazer", action="store_true", help="refaz mesmo as já baixadas")
    p.add_argument("--refresh", action="store_true")
    p.add_argument("--delay", type=float, default=config.MIN_INTERVAL)
    p.add_argument("--quiet", action="store_true")
    p.set_defaults(func=cmd_ementas)

    p = sub.add_parser("tudo", help="roda o pipeline completo (retomável)")
    p.add_argument("--limit", type=int, default=None, help="limita cada fase (teste rápido)")
    p.add_argument("--todas", action="store_true", help="fase 2 inclui versões históricas")
    p.add_argument("--refazer", action="store_true", help="fase 4 refaz mesmo as já baixadas")
    p.add_argument("--refresh", action="store_true")
    p.add_argument("--delay", type=float, default=config.MIN_INTERVAL)
    p.add_argument("--quiet", action="store_true")
    p.set_defaults(func=cmd_tudo)

    p = sub.add_parser("validar", help="fase 5: confere o banco e gera docs/relatorio-qualidade.md")
    p.add_argument("--out", default=None, help="caminho do relatório (padrão: docs/relatorio-qualidade.md)")
    p.set_defaults(func=cmd_validar)

    p = sub.add_parser("equivalencia", help="fase 6a: equivalência heurística entre disciplinas")
    p.add_argument("--top-k", type=int, default=12, help="vizinhos por disciplina no bloqueio")
    p.add_argument("--limiar", type=float, default=0.55, help="score mínimo para 'equivalente'")
    p.add_argument("--limiar-nao", type=float, default=0.22, help="score máximo para 'nao_equivalente'")
    p.add_argument("--sem-export", action="store_true", help="não exportar a banda de revisão")
    p.set_defaults(func=cmd_equivalencia)

    p = sub.add_parser("julgar-exportar", help="fase 6b: exporta a banda prioritária em lotes para julgamento")
    p.add_argument("--lotes", type=int, default=10, help="em quantos lotes dividir")
    p.add_argument("--dir", default=None, help="pasta de saída (padrão: data/exports/lotes)")
    p.set_defaults(func=cmd_julgar_exportar)

    p = sub.add_parser("julgar-aplicar", help="fase 6b: grava os vereditos julgados no banco")
    p.add_argument("--dir", default=None, help="pasta dos vereditos (padrão: data/exports/lotes)")
    p.add_argument("--julgador", default="llm", help="rótulo de quem julgou")
    p.set_defaults(func=cmd_julgar_aplicar)

    p = sub.add_parser("stats", help="mostra o que já foi coletado")
    p.set_defaults(func=cmd_stats)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

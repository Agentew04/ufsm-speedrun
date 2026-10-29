"""Publicação: gera os artefatos que o front consome.

O banco de trabalho (`data/ufsm.db`) tem tudo — inclusive 25 MB de texto de
ementa e as 90 mil linhas do palpite heurístico. Isso não pode ir pro browser.

Saída (padrão `data/public/`):

    ufsm-web.db        núcleo enxuto, carregado no boot
    ufsm-web.db.gz     idem, comprimido
    ementas.db         textos de ementa, carregado SOB DEMANDA (clique na cadeira)
    ementas.db.gz      idem
    manifest.json      tamanhos, contagens e versão

Por que separar: 51 MB de banco viram 7,4 MB de núcleo + 8 MB de ementas que só
baixam quando o usuário pede. Quem navega o ranking nunca paga pelo texto.

Uso:
    python -m ufsm_speedrun publicar
"""

from __future__ import annotations

import gzip
import json
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from . import config

COLUNAS_TEXTO = ("programa_texto", "bibliografia_texto", "objetivos_html")

# Tabelas que só existem para o ETL/auditoria e não têm uso no cliente.
TABELAS_SO_ETL = ("rota_benchmark", "rota_gulosa", "ingest_run")


def _mb(caminho: Path) -> float:
    return caminho.stat().st_size / 1024 / 1024


def vacuum(caminho: Path) -> None:
    """Devolve ao sistema as páginas livres (SQLite não faz sozinho após DELETE)."""
    conn = sqlite3.connect(caminho, isolation_level=None)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("VACUUM")
        conn.execute("ANALYZE")
    finally:
        conn.close()


def _gzip(origem: Path, destino: Path) -> None:
    with origem.open("rb") as src, gzip.open(destino, "wb", compresslevel=9) as dst:
        shutil.copyfileobj(src, dst)


def exportar_nucleo(origem: Path, destino: Path, *, manter_palpite: bool = True) -> None:
    """Copia o banco e remove o que é pesado e não serve ao cliente."""
    if destino.exists():
        destino.unlink()
    shutil.copy2(origem, destino)

    conn = sqlite3.connect(destino, isolation_level=None)
    try:
        # 1. tira o texto de ementa (vai no outro arquivo)
        sets = ", ".join(f"{c} = NULL" for c in COLUNAS_TEXTO)
        conn.execute(f"UPDATE disciplina SET {sets}")

        # 2. do palpite heurístico, só interessa o que foi confirmado
        if manter_palpite:
            conn.execute("DELETE FROM similaridade_ementa WHERE veredito <> 'equivalente'")
        else:
            conn.execute("DROP TABLE IF EXISTS similaridade_ementa")

        # 3. fora o que só serve ao ETL
        for tabela in TABELAS_SO_ETL:
            conn.execute(f"DROP TABLE IF EXISTS {tabela}")

        conn.execute("VACUUM")
        conn.execute("ANALYZE")
    finally:
        conn.close()


def exportar_ementas(origem: Path, destino: Path, *,
                     com_bibliografia: bool = False) -> int:
    """Banco separado com o texto de cada disciplina, para carga sob demanda.

    Por padrão leva `programa` + `objetivos` (o conteúdo que responde "o que é
    essa cadeira"). A bibliografia é o maior campo (~13 MB de texto) e o menos
    consultado: fica de fora salvo com `--com-bibliografia`.
    """
    if destino.exists():
        destino.unlink()

    src = sqlite3.connect(origem)
    dst = sqlite3.connect(destino, isolation_level=None)
    try:
        dst.executescript(
            """
            CREATE TABLE ementa (
                disciplina_id  INTEGER PRIMARY KEY,
                codigo         TEXT,
                programa       TEXT,
                bibliografia   TEXT,
                objetivos_html TEXT
            );
            CREATE INDEX idx_ementa_codigo ON ementa(codigo);
            """
        )
        coluna_bib = "bibliografia_texto" if com_bibliografia else "NULL"
        filtro = ("COALESCE(programa_texto, '') <> '' OR COALESCE(objetivos_html, '') <> ''")
        if com_bibliografia:
            filtro += " OR COALESCE(bibliografia_texto, '') <> ''"
        linhas = src.execute(
            f"""
            SELECT id, codigo, programa_texto, {coluna_bib}, objetivos_html
            FROM disciplina
            WHERE {filtro}
            """
        ).fetchall()
        dst.executemany("INSERT INTO ementa VALUES (?, ?, ?, ?, ?)", linhas)
        dst.execute("VACUUM")
        dst.execute("ANALYZE")
    finally:
        src.close()
        dst.close()
    return len(linhas)


def publicar(origem: Path | None = None, destino_dir: Path | None = None,
             *, comprimir: bool = True, com_bibliografia: bool = False) -> dict:
    origem = Path(origem or config.DB_PATH)
    if not origem.exists():
        raise FileNotFoundError(f"banco não encontrado: {origem}")

    destino_dir = Path(destino_dir or (config.DATA_DIR / "public"))
    destino_dir.mkdir(parents=True, exist_ok=True)

    print(f"  origem ................... {origem} ({_mb(origem):.1f} MB)")
    print("  compactando o banco de trabalho…", flush=True)
    vacuum(origem)
    print(f"    após VACUUM ............ {_mb(origem):.1f} MB")

    nucleo = destino_dir / "ufsm-web.db"
    ementas = destino_dir / "ementas.db"

    print("  gerando núcleo…", flush=True)
    exportar_nucleo(origem, nucleo)

    print("  extraindo ementas…", flush=True)
    n_ementas = exportar_ementas(origem, ementas, com_bibliografia=com_bibliografia)

    artefatos = {
        "ufsm-web.db": nucleo,
        "ementas.db": ementas,
    }
    if comprimir:
        for nome, caminho in list(artefatos.items()):
            gz = caminho.with_suffix(caminho.suffix + ".gz")
            _gzip(caminho, gz)
            artefatos[gz.name] = gz

    manifest = {
        "gerado_em": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "nucleo": "ufsm-web.db",
        "ementas": "ementas.db",
        "ementas_carregar": "on_demand",
        "ementas_com_bibliografia": com_bibliografia,
        "disciplinas_com_ementa": n_ementas,
        "artefatos": {
            nome: round(_mb(caminho), 2) for nome, caminho in sorted(artefatos.items())
        },
    }
    (destino_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    print("\n  artefatos:")
    for nome, caminho in sorted(artefatos.items()):
        print(f"    {nome:<20} {_mb(caminho):>7.1f} MB")

    return manifest

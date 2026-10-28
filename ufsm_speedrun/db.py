"""Acesso ao SQLite: conexão, criação do esquema e consultas de verificação."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from . import config

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

TABELAS = [
    "ingest_run",
    "disciplina",
    "disciplina_ch",
    "curso",
    "versao_curriculo",
    "estrutura",
    "estrutura_atividade",
    "disciplina_curriculo",
    "prereq_bloco",
    "prereq_item",
    "equivalencia_bloco",
    "equivalencia_item",
    "similaridade_ementa",
    "cobertura_curso",
]


def connect(db_path: Path = config.DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # Durabilidade: com WAL, synchronous=NORMAL pode perder os últimos commits
    # num corte de energia. FULL fsync-a o WAL a cada commit — e como commitamos
    # por item (1 request), o custo é irrelevante.
    conn.execute("PRAGMA synchronous = FULL")
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


def migrar(conn: sqlite3.Connection) -> None:
    """Ajustes de schema em bancos já existentes (CREATE IF NOT EXISTS não altera)."""
    colunas = {r[1] for r in conn.execute("PRAGMA table_info(similaridade_ementa)")}
    if colunas and "score_final" not in colunas:
        conn.execute("ALTER TABLE similaridade_ementa ADD COLUMN score_final REAL")
    if colunas and "motivo" not in colunas:
        conn.execute("ALTER TABLE similaridade_ementa ADD COLUMN motivo TEXT")
    conn.commit()


def init_db(db_path: Path = config.DB_PATH, *, recreate: bool = False) -> Path:
    """Cria o banco aplicando schema.sql. Idempotente."""
    if recreate and db_path.exists():
        db_path.unlink()
    conn = connect(db_path)
    try:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        conn.commit()
        migrar(conn)
    finally:
        conn.close()
    return db_path


def counts(db_path: Path = config.DB_PATH) -> dict[str, int]:
    """Contagem de linhas por tabela (para relatório de status)."""
    conn = connect(db_path)
    try:
        existing = {
            r["name"]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        out: dict[str, int] = {}
        for tabela in TABELAS:
            if tabela in existing:
                out[tabela] = conn.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]
        return out
    finally:
        conn.close()

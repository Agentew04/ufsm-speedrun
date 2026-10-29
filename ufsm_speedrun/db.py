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


VIEW_EQUIVALENCIA = """
DROP VIEW IF EXISTS v_equivalencia_efetiva;
CREATE VIEW v_equivalencia_efetiva AS
SELECT dc.disciplina_id  AS alvo_id,
       ei.disciplina_req_id AS substituta_id,
       'oficial'         AS origem,
       1.0               AS confianca,
       'equivalente'     AS veredito
FROM equivalencia_item ei
JOIN equivalencia_bloco eb      ON eb.id = ei.bloco_id
JOIN disciplina_curriculo dc    ON dc.id = eb.disciplina_curriculo_id
WHERE ei.disciplina_req_id IS NOT NULL
  AND ei.disciplina_req_id <> dc.disciplina_id
UNION ALL
SELECT ej.disciplina_a, ej.disciplina_b, 'julgada', ej.confianca, ej.veredito
FROM equivalencia_julgada ej
WHERE ej.veredito IN ('equivalente', 'parcial')
UNION ALL
SELECT ej.disciplina_b, ej.disciplina_a, 'julgada', ej.confianca, ej.veredito
FROM equivalencia_julgada ej
WHERE ej.veredito IN ('equivalente', 'parcial');
"""


def migrar(conn: sqlite3.Connection) -> None:
    """Ajustes incrementais para bancos já existentes.

    `CREATE TABLE IF NOT EXISTS` não adiciona coluna nem atualiza view, então
    cada mudança de schema precisa vir parar aqui também.
    """
    # tabela de julgamento (a view depende dela)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS equivalencia_julgada (
            disciplina_a  INTEGER NOT NULL REFERENCES disciplina(id) ON DELETE CASCADE,
            disciplina_b  INTEGER NOT NULL REFERENCES disciplina(id) ON DELETE CASCADE,
            veredito      TEXT NOT NULL,
            confianca     REAL,
            justificativa TEXT,
            julgador      TEXT,
            julgado_em    TEXT,
            PRIMARY KEY (disciplina_a, disciplina_b)
        );
        CREATE TABLE IF NOT EXISTS rota_gulosa (
            ordem        INTEGER PRIMARY KEY,
            curso_id     INTEGER NOT NULL REFERENCES curso(id) ON DELETE CASCADE,
            horas_passo  INTEGER NOT NULL,
            horas_acum   INTEGER NOT NULL,
            semestre     INTEGER NOT NULL,
            disciplinas_novas INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS rota_benchmark (
            base_curso_id  INTEGER NOT NULL REFERENCES curso(id) ON DELETE CASCADE,
            alvo_curso_id  INTEGER NOT NULL REFERENCES curso(id) ON DELETE CASCADE,
            horas          INTEGER NOT NULL,
            disciplinas    INTEGER NOT NULL,
            semestres      INTEGER NOT NULL,
            calculado_em   TEXT,
            PRIMARY KEY (base_curso_id, alvo_curso_id)
        );
        """
    )

    colunas_sim = {r[1] for r in conn.execute("PRAGMA table_info(similaridade_ementa)")}
    if colunas_sim and "score_final" not in colunas_sim:
        conn.execute("ALTER TABLE similaridade_ementa ADD COLUMN score_final REAL")
    if colunas_sim and "motivo" not in colunas_sim:
        conn.execute("ALTER TABLE similaridade_ementa ADD COLUMN motivo TEXT")

    colunas_curso = {r[1] for r in conn.execute("PRAGMA table_info(curso)")}
    if colunas_curso and "eh_nucleo_comum" not in colunas_curso:
        conn.execute("ALTER TABLE curso ADD COLUMN eh_nucleo_comum INTEGER NOT NULL DEFAULT 0")
        conn.execute("ALTER TABLE curso ADD COLUMN nucleo_comum_motivo TEXT")

    conn.executescript(VIEW_EQUIVALENCIA)
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

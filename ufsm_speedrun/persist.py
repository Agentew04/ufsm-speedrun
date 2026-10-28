"""Helpers de persistência compartilhados entre as fases de coleta."""

from __future__ import annotations

import sqlite3


def upsert_disciplina(conn: sqlite3.Connection, d: dict) -> None:
    """Insere/atualiza o registro global de uma disciplina.

    Nunca toca nas colunas de ementa (`programa_texto`, `bibliografia_texto`,
    `objetivos_html`) — elas são preenchidas só pela Fase 4, e um reprocessamento
    da Fase 2/3 não pode apagá-las.
    """
    depto = d.get("departamento") or {}
    conn.execute(
        """
        INSERT INTO disciplina (id, codigo, nome, nome_ingles, creditos, ch_total,
                                ch_extensao, ch_encargo, departamento_id,
                                departamento_nome, situacao_codigo, situacao, tipo)
        VALUES (:id, :codigo, :nome, :nome_ingles, :creditos, :ch_total,
                :ch_extensao, :ch_encargo, :depto_id,
                :depto_nome, :sit_codigo, :situacao, :tipo)
        ON CONFLICT(id) DO UPDATE SET
            codigo = excluded.codigo,
            nome = excluded.nome,
            nome_ingles = COALESCE(excluded.nome_ingles, disciplina.nome_ingles),
            creditos = COALESCE(excluded.creditos, disciplina.creditos),
            ch_total = COALESCE(excluded.ch_total, disciplina.ch_total),
            ch_extensao = COALESCE(excluded.ch_extensao, disciplina.ch_extensao),
            ch_encargo = COALESCE(excluded.ch_encargo, disciplina.ch_encargo),
            departamento_id = COALESCE(excluded.departamento_id, disciplina.departamento_id),
            departamento_nome = COALESCE(excluded.departamento_nome, disciplina.departamento_nome),
            situacao_codigo = COALESCE(excluded.situacao_codigo, disciplina.situacao_codigo),
            situacao = COALESCE(excluded.situacao, disciplina.situacao),
            tipo = COALESCE(excluded.tipo, disciplina.tipo)
        """,
        {
            "id": d["id"],
            "codigo": d["codigo"],
            "nome": d.get("descricao") or "",
            "nome_ingles": d.get("nomeIngles"),
            "creditos": d.get("creditos"),
            "ch_total": d.get("cargaHoraria"),
            "ch_extensao": d.get("cargaHorariaExtensao"),
            "ch_encargo": d.get("encargoDidatico"),
            "depto_id": depto.get("id"),
            "depto_nome": depto.get("descricao"),
            "sit_codigo": (d.get("situacao") or {}).get("codigo"),
            "situacao": (d.get("situacao") or {}).get("descricao"),
            "tipo": (d.get("tipo") or {}).get("descricao"),
        },
    )

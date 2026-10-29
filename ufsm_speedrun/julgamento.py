"""Fase 6b — adjudicação da banda prioritária (LLM / humano).

A heurística da Fase 6a separa 3 classes, mas deixa uma faixa cinzenta. Aqui a
gente exporta essa faixa em lotes, deixa um julgador (LLM ou pessoa) decidir e
grava o veredito separado do palpite heurístico.

Modelo de dados:
    similaridade_ementa  -> palpite automático (nunca é sobrescrito)
    equivalencia_julgada -> veredito de quem julgou

Formato do lote (entrada):
    {"lote": 3, "pares": [{"chave": "123:456", "a": {...}, "b": {...}, ...}]}

Formato do veredito (saída):
    {"lote": 3, "pares": [{"chave": "123:456", "veredito": "equivalente",
                           "confianca": 0.9, "justificativa": "..."}]}
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from . import config

VEREDITOS_VALIDOS = {"equivalente", "parcial", "nao_equivalente"}

INSTRUCOES = """\
Você está decidindo se duas disciplinas da UFSM são equivalentes para fins de
aproveitamento de estudos.

Regras:
1. Julgue pelo CONTEÚDO (ementa/programa), não pelo nome. Nomes em disciplinas
   sequenciais são parecidos de propósito.
2. Disciplinas sequenciais (I/II/III/IV, A/B/C, 1/2/3) NUNCA são equivalentes.
3. `equivalente` = o conteúdo cobre o da outra de modo que cursar uma dispensa a
   outra (considere a carga horária: a maior pode cobrir a menor, o contrário não).
4. `parcial` = há sobreposição relevante, mas não dá para dispensar com segurança.
5. `nao_equivalente` = conteúdos diferentes, ou só compartilham boilerplate.
6. Confiança entre 0 e 1. Se a ementa estiver vazia/genérica, confiança <= 0.4.
7. Justificativa em uma frase curta, em português, citando o que pesou.

Responda APENAS com JSON válido, no formato:
{"lote": <n>, "pares": [{"chave": "<a>:<b>", "veredito": "equivalente|parcial|nao_equivalente",
                         "confianca": <0..1>, "justificativa": "<frase>"}]}
"""


def migrar(conn: sqlite3.Connection) -> None:
    conn.execute(
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
        )
        """
    )
    conn.commit()


def _pares_prioritarios(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT se.disciplina_a, se.disciplina_b, se.score_final, se.score_cosine,
               se.ch_a, se.ch_b, se.motivo,
               a.codigo AS ca, a.nome AS na, a.programa_texto AS pa,
               b.codigo AS cb, b.nome AS nb, b.programa_texto AS pb
        FROM similaridade_ementa se
        JOIN disciplina a ON a.id = se.disciplina_a
        JOIN disciplina b ON b.id = se.disciplina_b
        WHERE se.veredito = 'revisar'
          AND se.score_final >= 0.60
          AND se.motivo NOT LIKE '%sequ%'
          AND NOT EXISTS (
              SELECT 1 FROM equivalencia_julgada ej
              WHERE ej.disciplina_a = se.disciplina_a
                AND ej.disciplina_b = se.disciplina_b
          )
        ORDER BY se.score_final DESC
        """
    ).fetchall()


def exportar_lotes(conn: sqlite3.Connection, destino: Path, tamanho: int = 0,
                   lotes: int = 10) -> list[Path]:
    pares = _pares_prioritarios(conn)
    if not pares:
        return []

    tamanho = tamanho or max(1, -(-len(pares) // max(1, lotes)))
    destino.mkdir(parents=True, exist_ok=True)

    caminhos: list[Path] = []
    total = -(-len(pares) // tamanho)
    for i in range(total):
        fatia = pares[i * tamanho:(i + 1) * tamanho]
        if not fatia:
            continue
        corpo = {
            "lote": i + 1,
            "total_lotes": total,
            "instrucoes": INSTRUCOES,
            "pares": [
                {
                    "chave": f"{p['disciplina_a']}:{p['disciplina_b']}",
                    "a": {
                        "codigo": p["ca"], "nome": p["na"], "ch": p["ch_a"],
                        "ementa": (p["pa"] or "").strip()[:2500],
                    },
                    "b": {
                        "codigo": p["cb"], "nome": p["nb"], "ch": p["ch_b"],
                        "ementa": (p["pb"] or "").strip()[:2500],
                    },
                    "score_heuristico": round(p["score_final"], 3),
                    "cosine": round(p["score_cosine"], 3),
                    "motivo": p["motivo"],
                }
                for p in fatia
            ],
        }
        caminho = destino / f"lote-{i + 1:02d}.json"
        caminho.write_text(json.dumps(corpo, ensure_ascii=False, indent=1), encoding="utf-8")
        caminhos.append(caminho)

    print(f"  {len(pares)} pares exportados em {len(caminhos)} lote(s) → {destino}")
    return caminhos


def aplicar(conn: sqlite3.Connection, origem: Path, julgador: str = "llm") -> dict:
    """Lê os arquivos de veredito e grava em equivalencia_julgada."""
    migrar(conn)
    arquivos = sorted(origem.glob("lote-*.json"))
    arquivos = [a for a in arquivos if "veredicto" in a.name or a.name.endswith(".out.json")]
    if not arquivos:
        # fallback: qualquer json que não seja o de entrada
        arquivos = [a for a in sorted(origem.glob("*.json")) if not re.fullmatch(r"lote-\d+\.json", a.name)]

    agora = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    total = aplicados = invalidos = 0
    for arquivo in arquivos:
        try:
            dados = json.loads(arquivo.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"  !! {arquivo.name}: JSON inválido ({exc})")
            invalidos += 1
            continue

        for par in dados.get("pares", []):
            total += 1
            veredito = str(par.get("veredito", "")).strip().lower()
            chave = str(par.get("chave", ""))
            if veredito not in VEREDITOS_VALIDOS or ":" not in chave:
                invalidos += 1
                continue
            a, b = (int(x) for x in chave.split(":", 1))
            confianca = par.get("confianca")
            try:
                confianca = float(confianca) if confianca is not None else None
            except (TypeError, ValueError):
                confianca = None
            conn.execute(
                """
                INSERT INTO equivalencia_julgada
                    (disciplina_a, disciplina_b, veredito, confianca, justificativa,
                     julgador, julgado_em)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(disciplina_a, disciplina_b) DO UPDATE SET
                    veredito = excluded.veredito, confianca = excluded.confianca,
                    justificativa = excluded.justificativa, julgador = excluded.julgador,
                    julgado_em = excluded.julgado_em
                """,
                (a, b, veredito, confianca, (par.get("justificativa") or "")[:500],
                 julgador, agora),
            )
            aplicados += 1
    conn.commit()
    print(f"  vereditos: {aplicados} aplicados de {total} lidos ({invalidos} inválidos)")
    return {"aplicados": aplicados, "lidos": total, "invalidos": invalidos}


def relatorio(conn: sqlite3.Connection) -> None:
    escalar = lambda s: conn.execute(s).fetchone()[0]  # noqa: E731
    print("\n" + "=" * 72)
    print("RELATÓRIO — FASE 6b (adjudicação)")
    print("=" * 72)
    print(f"  pares julgados ............. {escalar('SELECT COUNT(*) FROM equivalencia_julgada')}")
    for veredito, n, media in conn.execute(
        "SELECT veredito, COUNT(*), ROUND(AVG(confianca), 2) "
        "FROM equivalencia_julgada GROUP BY veredito ORDER BY COUNT(*) DESC"
    ):
        print(f"    {veredito:<18} {n:>4}  (confiança média {media})")

    print("\n  confirmados que o SIE NÃO declarava (ganho real do projeto):")
    linhas = conn.execute(
        """
        WITH oficiais AS (
            SELECT DISTINCT MIN(dc.disciplina_id, ei.disciplina_req_id) AS a,
                            MAX(dc.disciplina_id, ei.disciplina_req_id) AS b
            FROM equivalencia_item ei
            JOIN equivalencia_bloco eb ON eb.id = ei.bloco_id
            JOIN disciplina_curriculo dc ON dc.id = eb.disciplina_curriculo_id
            WHERE ei.disciplina_req_id IS NOT NULL
              AND ei.disciplina_req_id != dc.disciplina_id
        )
        SELECT a.codigo, a.nome, b.codigo, b.nome, ej.confianca
        FROM equivalencia_julgada ej
        JOIN disciplina a ON a.id = ej.disciplina_a
        JOIN disciplina b ON b.id = ej.disciplina_b
        WHERE ej.veredito = 'equivalente'
          AND NOT EXISTS (SELECT 1 FROM oficiais o
                          WHERE o.a = ej.disciplina_a AND o.b = ej.disciplina_b)
        ORDER BY ej.confianca DESC
        LIMIT 20
        """
    ).fetchall()
    for ca, na, cb, nb, conf in linhas:
        print(f"    {ca} {na[:38]:<38} ↔ {cb} {nb[:38]:<38} (conf {conf})")
    print()

"""Fase 6a — equivalência heurística entre disciplinas.

Regra de negócio do projeto:
    candidato a equivalente se  CH_do_candidato >= CH_do_alvo
                          e     ementa >= 75% "igual"

O que a medição mostrou (ver docs/equivalencia.md):
  * Levenshtein no NOME é **inútil como decisão**: os pares com nome mais parecido
    são justamente os que NÃO são equivalentes (TCC I vs TCC II dá 0.97).
    Nome só serve para (a) bloquear candidatos e (b) *detectar* o sufixo sequencial.
  * TF-IDF na EMENTA separa de verdade, mas como *ranking*, não como regra binária.

Arquitetura (funil):
    1. bloqueio: top-k vizinhos TF-IDF de cada disciplina  (~70k pares, não 62M)
    2. filtros duros: sufixo sequencial, razão de carga horária
    3. score combinado: ementa + nome + CH + departamento
    4. veredito: equivalente | revisar | nao_equivalente
    5. banda "revisar" exportada para adjudicação (humana ou LLM)
"""

from __future__ import annotations

import csv
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

from . import config

STOPWORDS = set("""
a o as os um uma uns umas de do da dos das em no na nos nas por pelo pela para com sem
sob sobre entre e ou mas que se como quando onde qual quais cujo cuja ao aos ser esta
este isso isto aquilo seu sua seus suas ele ela eles elas nao mais menos muito pouco
todo toda todos todas outro outra outros outras mesmo mesma sao foi seja sendo ter tem
teu tua pode podem deve devem ainda tambem ja apenas atraves assim cada qualquer bem
mal aqui ali la entao portanto contudo porem
""".split())

TOKEN = re.compile(r"[a-z]{3,}")

# sufixos que marcam disciplinas *sequenciais* (e portanto NÃO equivalentes)
ROMANOS = {"i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x"}
# 'i', 'v' e 'x' não são palavras do português: soltos no nome, são numeral romano.
ROMANOS_QUALQUER = ROMANOS
LETRAS = {"a", "b", "c", "d", "e"}
NUMEROS = {str(n) for n in range(1, 11)}
SUFIXOS = ROMANOS | LETRAS | NUMEROS


@dataclass
class Config:
    top_k: int = 12
    peso_ementa: float = 0.62
    peso_nome: float = 0.14
    peso_ch: float = 0.16
    peso_depto: float = 0.08
    limiar_equivalente: float = 0.55
    limiar_nao: float = 0.22
    razao_ch_minima: float = 0.70   # min/max de CH para considerar plausível
    min_tokens_ementa: int = 20     # ementa muito curta = sinal fraco
    min_jaccard_nome: float = 0.75  # ementa idêntica + nome muito diferente = suspeito


@dataclass
class Resultado:
    candidatos: int = 0
    equivalente: int = 0
    revisar: int = 0
    nao_equivalente: int = 0
    oficiais: int = 0
    recuperados: int = 0


# ------------------------------------------------------------------ texto
def normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFKD", (texto or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def tokens(texto: str) -> list[str]:
    return [w for w in TOKEN.findall(normalizar(texto)) if w not in STOPWORDS]


def preparar(texto: str) -> str:
    return " ".join(tokens(texto))


def marcadores_sequencia(nome: str) -> tuple[str, ...]:
    """Marcadores de sequência do nome: 'FÍSICA II', 'CÁLCULO A', 'ORQUESTRA IV - A'.

    Não dá para usar o tokenizador normal: ele exige 3+ letras e jogaria fora
    'i', 'ii', 'iv', 'v'. Aqui a regra é posicional:
      * par final "- X" (a letra depois do hífen);
      * último token, se for romano/número;
      * numerais romanos inequívocos em qualquer posição ('ii', 'iii', 'iv', …).
    """
    partes = re.findall(r"[a-z0-9]+|-", normalizar(nome))
    achados: list[str] = []

    if len(partes) >= 2 and partes[-2] == "-":
        if partes[-1] in SUFIXOS:          # "ORQUESTRA IV - A" -> 'a' é marcador
            achados.append(partes[-1])     # "SEMINÁRIO IV - VIOLINO" -> 'violino' não é
        partes = partes[:-2]

    if partes and (partes[-1] in ROMANOS or partes[-1] in NUMEROS or partes[-1] in LETRAS):
        achados.append(partes[-1])

    achados.extend(p for p in partes if p in ROMANOS_QUALQUER)
    return tuple(sorted(set(achados)))


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# ------------------------------------------------------------------ dados
def carregar(conn: sqlite3.Connection):
    linhas = conn.execute(
        "SELECT id, codigo, nome, ch_total, programa_texto, objetivos_html, departamento_nome "
        "FROM disciplina"
    ).fetchall()

    registros: dict[int, dict] = {}
    for r in linhas:
        html = re.sub(r"<[^>]+>", " ", r["objetivos_html"] or "")
        texto = preparar(f"{r['programa_texto'] or ''} {html}")
        registros[r["id"]] = {
            "id": r["id"],
            "codigo": r["codigo"],
            "nome": r["nome"],
            "ch": r["ch_total"] or 0,
            "depto": (r["departamento_nome"] or "").strip().lower(),
            "texto": texto,
            "nome_tokens": set(tokens(r["nome"])),
            "marcadores": marcadores_sequencia(r["nome"]),
            "n_tokens": len(texto.split()),
        }
    return registros


def pares_oficiais(conn: sqlite3.Connection) -> set[tuple[int, int]]:
    pares = set()
    for r in conn.execute(
        """
        SELECT DISTINCT dc.disciplina_id a, ei.disciplina_req_id b
        FROM equivalencia_item ei
        JOIN equivalencia_bloco eb ON eb.id = ei.bloco_id
        JOIN disciplina_curriculo dc ON dc.id = eb.disciplina_curriculo_id
        WHERE ei.disciplina_req_id IS NOT NULL AND ei.disciplina_req_id != dc.disciplina_id
        """
    ):
        a, b = r[0], r[1]
        pares.add((a, b) if a < b else (b, a))
    return pares


# ------------------------------------------------------------- bloqueio
def gerar_candidatos(X, ids: list[int], top_k: int) -> set[tuple[int, int, float]]:
    """Top-k vizinhos por cosseno, em blocos (evita matriz n×n na memória)."""
    n = X.shape[0]
    pares: dict[tuple[int, int], float] = {}
    bloco = 512
    for inicio in range(0, n, bloco):
        fim = min(inicio + bloco, n)
        sims = (X[inicio:fim] @ X.T).toarray()
        for linha in range(fim - inicio):
            sims[linha, inicio + linha] = -1.0
            top = np.argpartition(-sims[linha], top_k)[:top_k]
            for j in top:
                sim = float(sims[linha, j])
                if sim <= 0:
                    continue
                a, b = ids[inicio + linha], ids[int(j)]
                chave = (a, b) if a < b else (b, a)
                if chave not in pares or sim > pares[chave]:
                    pares[chave] = sim
    return {(a, b, s) for (a, b), s in pares.items()}


# ------------------------------------------------------------- pontuação
def pontuar(a: int, b: int, cos: float, reg: dict[int, dict],
            cfg: Config) -> tuple[float, bool, bool, str]:
    """Devolve (score_final, sufixo_ok, ch_ok, motivo)."""
    ra, rb = reg[a], reg[b]
    jac = jaccard(ra["nome_tokens"], rb["nome_tokens"])
    ch_a, ch_b = ra["ch"], rb["ch"]
    razao_ch = (min(ch_a, ch_b) / max(ch_a, ch_b)) if max(ch_a, ch_b) else 0.0
    mesmo_depto = 1.0 if ra["depto"] and ra["depto"] == rb["depto"] else 0.0

    score = (
        cfg.peso_ementa * cos
        + cfg.peso_nome * jac
        + cfg.peso_ch * razao_ch
        + cfg.peso_depto * mesmo_depto
    )

    # Sequência: 'FÍSICA I' != 'FÍSICA II' != 'FÍSICA III'; 'ORQUESTRA IV - A' != 'V - A'
    sufixo_ok = ra["marcadores"] == rb["marcadores"]
    ch_ok = razao_ch >= cfg.razao_ch_minima

    motivos = []
    if not sufixo_ok:
        motivos.append(f"sequência {ra['marcadores']}≠{rb['marcadores']}")
    if not ch_ok:
        motivos.append(f"CH {ch_a}h×{ch_b}h")
    if min(ra["n_tokens"], rb["n_tokens"]) < cfg.min_tokens_ementa:
        motivos.append("ementa curta/genérica")
    # ementa idêntica + nome diferente = boilerplate ou duplicata: exige revisão
    if cos >= 0.999 and jac < cfg.min_jaccard_nome:
        motivos.append("ementa idêntica, nome diferente")
    return score, sufixo_ok, ch_ok, "; ".join(motivos)


def classificar(score: float, motivo: str, cfg: Config) -> str:
    """Sem nenhum impedimento e score alto -> equivalente; caso contrário, revisar."""
    if score >= cfg.limiar_equivalente and not motivo:
        return "equivalente"
    if score <= cfg.limiar_nao:
        return "nao_equivalente"
    return "revisar"


# ------------------------------------------------------------------- run
def run(conn: sqlite3.Connection, cfg: Config | None = None, *,
        exportar: bool = True) -> Resultado:
    from . import db as _db

    _db.migrar(conn)
    cfg = cfg or Config()
    reg = carregar(conn)

    com_texto = [i for i, r in reg.items() if r["texto"]]
    print(f"disciplinas no catálogo .... {len(reg)}")
    print(f"com ementa utilizável ...... {len(com_texto)}")
    if len(com_texto) < 100:
        raise RuntimeError("poucas disciplinas com ementa — rode a fase 4 antes")

    ids = com_texto
    textos = [reg[i]["texto"] for i in ids]
    vetor = TfidfVectorizer(min_df=2, max_df=0.85, sublinear_tf=True)
    X = normalize(vetor.fit_transform(textos))
    print(f"vocabulário TF-IDF .......... {len(vetor.vocabulary_)} termos")

    print("bloqueando candidatos (top-k vizinhos)…", flush=True)
    candidatos = gerar_candidatos(X, ids, cfg.top_k)
    print(f"pares candidatos ........... {len(candidatos)}")

    oficiais = pares_oficiais(conn)
    resultado = Resultado(candidatos=len(candidatos), oficiais=len(oficiais))

    print("pontuando…", flush=True)
    linhas = []
    agora = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    # limpa resultados anteriores: o conjunto de candidatos pode mudar entre runs
    # (ementas novas entram na matriz) e linha velha viraria veredito fantasma
    conn.execute("DELETE FROM similaridade_ementa")
    for a, b, cos in candidatos:
        score, sufixo_ok, ch_ok, motivo = pontuar(a, b, cos, reg, cfg)
        veredito = classificar(score, motivo, cfg)
        if veredito == "equivalente":
            resultado.equivalente += 1
        elif veredito == "revisar":
            resultado.revisar += 1
        else:
            resultado.nao_equivalente += 1
        if (a, b) in oficiais and veredito == "equivalente":
            resultado.recuperados += 1
        linhas.append((a, b, cos, jaccard(reg[a]["nome_tokens"], reg[b]["nome_tokens"]),
                       score, reg[a]["ch"], reg[b]["ch"], veredito, motivo, agora))

    conn.executemany(
        """
        INSERT INTO similaridade_ementa
            (disciplina_a, disciplina_b, score_cosine, score_jaccard, score_final,
             ch_a, ch_b, veredito, motivo, calculado_em)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(disciplina_a, disciplina_b) DO UPDATE SET
            score_cosine = excluded.score_cosine, score_jaccard = excluded.score_jaccard,
            score_final = excluded.score_final, ch_a = excluded.ch_a, ch_b = excluded.ch_b,
            veredito = excluded.veredito, motivo = excluded.motivo,
            calculado_em = excluded.calculado_em
        """,
        linhas,
    )
    conn.commit()

    if exportar:
        _exportar_revisao(conn)

    return resultado


def _exportar_revisao(conn: sqlite3.Connection) -> tuple[int, int]:
    """Exporta a banda de revisão.

    Separa o joio do trigo: a maior parte dos 58k pares é rejeitada por regra
    (sequência I/II/III) ou tem score baixo. O subconjunto que vale adjudicação
    humana/LLM é o de score alto SEM conflito de sequência.
    """
    destino_dir = config.DATA_DIR / "exports"
    destino_dir.mkdir(parents=True, exist_ok=True)

    COLS = """
        SELECT se.disciplina_a, se.disciplina_b, se.score_final, se.score_cosine,
               se.ch_a, se.ch_b, se.motivo,
               a.codigo, a.nome, a.programa_texto,
               b.codigo, b.nome, b.programa_texto
        FROM similaridade_ementa se
        JOIN disciplina a ON a.id = se.disciplina_a
        JOIN disciplina b ON b.id = se.disciplina_b
        WHERE se.veredito = 'revisar'
    """

    escritos = {}
    for nome_arquivo, filtro in (
        ("equivalencias-revisar.csv", ""),
        ("equivalencias-prioritarias.csv",
         " AND se.score_final >= 0.60 AND se.motivo NOT LIKE '%sequ%'"),
    ):
        corpo = conn.execute(COLS + filtro + " ORDER BY se.score_final DESC").fetchall()
        caminho = destino_dir / nome_arquivo
        with caminho.open("w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh, delimiter=";")
            w.writerow(["disciplina_a", "codigo_a", "ch_a", "ementa_a",
                        "disciplina_b", "codigo_b", "ch_b", "ementa_b",
                        "score", "cosine", "motivo"])
            for a, b, score, cos, ch_a, ch_b, motivo, ca, na, pa, cb, nb, pb in corpo:
                w.writerow([na, ca, ch_a, (pa or "")[:600].replace("\n", " "),
                            nb, cb, ch_b, (pb or "")[:600].replace("\n", " "),
                            f"{score:.3f}", f"{cos:.4f}", motivo])
        escritos[nome_arquivo] = len(corpo)
        print(f"  exportado {nome_arquivo:<34} {len(corpo):>6} pares")

    return escritos["equivalencias-revisar.csv"], escritos["equivalencias-prioritarias.csv"]


def _resumo_banda(conn: sqlite3.Connection) -> None:
    print("\n  banda de revisão por motivo:")
    consulta = """
        SELECT CASE
                 WHEN motivo LIKE '%sequ%' THEN 'rejeitado por regra (sequência I/II/III)'
                 WHEN motivo LIKE '%CH %' THEN 'carga horária incompatível'
                 WHEN motivo LIKE '%curta%' THEN 'ementa curta/genérica'
                 WHEN motivo LIKE '%id%ntica%' THEN 'ementa idêntica mas nome diferente'
                 WHEN coalesce(motivo, '') = '' THEN 'ambíguo puro (sem impedimento, score médio)'
                 ELSE motivo
               END AS m, COUNT(*), ROUND(AVG(score_final), 2)
        FROM similaridade_ementa
        WHERE veredito = 'revisar'
        GROUP BY m ORDER BY COUNT(*) DESC
    """
    for motivo, n, media in conn.execute(consulta):
        print(f"    {n:>6}  avg={media:.2f}  {motivo}")


# --------------------------------------------------------------- relatório
def relatorio(conn: sqlite3.Connection, r: Resultado) -> None:
    print("\n" + "=" * 72)
    print("RELATÓRIO — FASE 6a (equivalência heurística)")
    print("=" * 72)
    print(f"  pares candidatos ........... {r.candidatos}")
    print(f"  equivalência automática .... {r.equivalente}")
    print(f"  banda de revisão ........... {r.revisar}")
    print(f"  descartados ................ {r.nao_equivalente}")
    print(f"  equivalências oficiais ..... {r.oficiais}")
    if r.oficiais:
        print(f"  recall sobre as oficiais ... {r.recuperados / r.oficiais:.1%} "
              f"({r.recuperados}/{r.oficiais} reconhecidas como 'equivalente')")
        candidatas = conn.execute(
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
            SELECT COUNT(*) FROM oficiais o
            JOIN similaridade_ementa se ON se.disciplina_a = o.a AND se.disciplina_b = o.b
            """
        ).fetchone()[0]
        if candidatas:
            print(f"  ...entre as que viraram candidatas (ementa parecida o bastante): "
                  f"{r.recuperados}/{candidatas} = {r.recuperados / candidatas:.0%}")

    _resumo_banda(conn)

    print("\n  descobertas (equivalente automático, NÃO declarado pelo SIE):")
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
        SELECT a.codigo, a.nome, b.codigo, b.nome, se.score_final, se.score_cosine,
               se.ch_a, se.ch_b
        FROM similaridade_ementa se
        JOIN disciplina a ON a.id = se.disciplina_a
        JOIN disciplina b ON b.id = se.disciplina_b
        WHERE se.veredito = 'equivalente'
          AND NOT EXISTS (SELECT 1 FROM oficiais o
                          WHERE o.a = se.disciplina_a AND o.b = se.disciplina_b)
        ORDER BY se.score_final DESC
        LIMIT 15
        """
    ).fetchall()
    for ca, na, cb, nb, score, cos, cha, chb in linhas:
        print(f"    {score:.2f} (cos {cos:.2f}, {cha}h×{chb}h)  "
              f"{ca} {na[:30]:<30} ↔ {cb} {nb[:30]}")

    print("\n  pares na banda de revisão (top 8, ordenados por score):")
    for row in conn.execute(
        """
        SELECT a.codigo, a.nome, b.codigo, b.nome, se.score_final, se.motivo
        FROM similaridade_ementa se
        JOIN disciplina a ON a.id = se.disciplina_a
        JOIN disciplina b ON b.id = se.disciplina_b
        WHERE se.veredito = 'revisar'
        ORDER BY se.score_final DESC LIMIT 8
        """
    ):
        print(f"    {row[4]:.2f}  {row[0]} {row[1][:28]:<28} ↔ {row[2]} {row[3][:28]:<28} {row[5]}")

    print("\n  distribuição de score nos pares oficiais que foram candidatos:")
    for row in conn.execute(
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
        SELECT
          SUM(CASE WHEN se.score_final >= 0.55 THEN 1 ELSE 0 END),
          SUM(CASE WHEN se.score_final >= 0.30 AND se.score_final < 0.55 THEN 1 ELSE 0 END),
          SUM(CASE WHEN se.score_final < 0.30 THEN 1 ELSE 0 END),
          COUNT(*)
        FROM similaridade_ementa se
        JOIN oficiais o ON o.a = se.disciplina_a AND o.b = se.disciplina_b
        """
    ):
        alto, medio, baixo, total = row
        if total:
            print(f"    >=0.55: {alto} · 0.30–0.55: {medio} · <0.30: {baixo} · total {total}")
    print()

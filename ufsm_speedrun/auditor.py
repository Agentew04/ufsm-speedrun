"""Fase 6c — auditor do otimizador.

O otimizador "de produção" é o do front (`web/src/lib/plan.ts` e `speedrun.ts`).
Este módulo é uma **segunda implementação, de propósito**: duas implementações
independentes sobre o mesmo banco se vigiam. Foi assim que apareceu o bug das
5.008 equivalências sem referência.

Ele faz três coisas:
  1. reimplementa o modelo de cotas e o score marginal do front (port fiel);
  2. roda o guloso que fecha os 148 cursos e grava `rota_gulosa`;
  3. grava `rota_benchmark` (custo base × alvo) e um JSON para o front comparar.

Divergência entre os dois lados é **sintoma**, não ruído: ou uma regra mudou de
um lado só, ou o dado mudou embaixo.

Uso:
    python -m ufsm_speedrun auditar
    python -m ufsm_speedrun auditar --front data/exports/front-speedrun.json
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import config

# tipos de oferta (ver endpoints.TIPO_DISCIPLINA_CURRICULO)
OBRIGATORIA = 1
ELETIVA_MENU = {2, 3}
DCG = {5, 7}
ATIVIDADE = {4, 8}


@dataclass
class Oferta:
    dc_id: int
    disc_id: int
    estrutura_id: int
    tipo_item: int
    periodo: int
    ch: int
    codigo: str
    nome: str


@dataclass
class Estrutura:
    id: int
    pai_id: int | None
    descricao: str
    ch_minima: int


@dataclass
class Quota:
    descricao: str
    horas: int
    kind: str            # eletiva | dcg | livre | atividade
    candidatos: list[int] = field(default_factory=list)
    residual: bool = False


@dataclass
class Curso:
    id: int
    nome: str
    nucleo_comum: bool
    ch_total: int
    ch_max_periodo: int
    periodo_ideal: int
    estruturas: list[Estrutura]
    ofertas: list[Oferta]
    fixed: list[Oferta]
    fixed_ids: set[int]
    fixed_horas: int
    quotas: list[Quota]
    atividades_horas: int
    carga_semestre: int
    semestres: int
    prereqs: dict[int, list[list[tuple[int, int | None]]]]
    equivals: dict[int, list[int]]
    ch_por_disc: dict[int, int] = field(default_factory=dict)


@dataclass
class Done:
    ids: set[int]
    free_horas: int
    free_aberto: int
    ch_of: dict[int, int]


# ----------------------------------------------------------------- carregar
def carregar(conn: sqlite3.Connection, *, com_julgadas: bool = True) -> tuple[list[Curso], dict[int, int]]:
    disc_ch = {
        r[0]: r[1] or 0
        for r in conn.execute("SELECT id, ch_total FROM disciplina")
    }

    cursos_raw = conn.execute(
        """
        SELECT c.id, c.nome, c.eh_nucleo_comum, v.id AS versao_id, v.ch_total,
               v.ch_max_periodo, v.periodo_ideal
        FROM curso c
        JOIN versao_curriculo v ON v.curso_id = c.id AND v.selecionada = 1
        ORDER BY c.nome
        """
    ).fetchall()

    # pré-requisitos por oferta
    prereq_raw = conn.execute(
        """
        SELECT pb.disciplina_curriculo_id AS dc_id, pi.tipo_item, pi.disciplina_req_id
        FROM prereq_bloco pb
        JOIN prereq_item pi ON pi.bloco_id = pb.id
        ORDER BY pb.id, pi.id
        """
    ).fetchall()
    prereq_por_dc: dict[int, list[list[tuple[int, int | None]]]] = {}
    for dc_id, tipo, req in prereq_raw:
        prereq_por_dc.setdefault(dc_id, []).append([])
        prereq_por_dc[dc_id][-1].append((tipo, req))

    # equivalências: view = oficial + julgadas (ou só oficial)
    if com_julgadas:
        equiv_rows = conn.execute(
            "SELECT alvo_id, substituta_id FROM v_equivalencia_efetiva "
            "GROUP BY alvo_id, substituta_id"
        ).fetchall()
    else:
        equiv_rows = conn.execute(
            """
            SELECT dc.disciplina_id AS alvo_id, ei.disciplina_req_id AS substituta_id
            FROM equivalencia_item ei
            JOIN equivalencia_bloco eb ON eb.id = ei.bloco_id
            JOIN disciplina_curriculo dc ON dc.id = eb.disciplina_curriculo_id
            WHERE ei.disciplina_req_id IS NOT NULL
            GROUP BY alvo_id, substituta_id
            """
        ).fetchall()
    equiv_por_disc: dict[int, list[int]] = {}
    for alvo, sub in equiv_rows:
        equiv_por_disc.setdefault(alvo, []).append(sub)

    cursos: list[Curso] = []
    for row in cursos_raw:
        curso_id, nome, nucleo, versao_id, ch_total, ch_max, periodo_ideal = row

        estruturas = [
            Estrutura(id=r[0], pai_id=r[1], descricao=r[2] or "", ch_minima=r[3] or 0)
            for r in conn.execute(
                "SELECT id, pai_id, descricao, ch_minima FROM estrutura WHERE versao_id = ? ORDER BY id",
                (versao_id,),
            )
        ]
        ofertas = [
            Oferta(dc_id=r[0], disc_id=r[1], estrutura_id=r[2], tipo_item=r[3],
                   periodo=r[4] or 0, ch=r[5] or 0, codigo=r[6] or "", nome=r[7] or "")
            for r in conn.execute(
                """
                SELECT dc.id, dc.disciplina_id, dc.estrutura_id, dc.tipo_item,
                       dc.periodo_ideal, d.ch_total, d.codigo, d.nome
                FROM disciplina_curriculo dc
                JOIN disciplina d ON d.id = dc.disciplina_id
                WHERE dc.versao_id = ?
                ORDER BY dc.id
                """,
                (versao_id,),
            )
        ]
        cursos.append(
            _montar_curso(
                curso_id, nome, bool(nucleo), ch_total or 0, ch_max or 0,
                periodo_ideal or 0, estruturas, ofertas,
                prereq_por_dc, equiv_por_disc,
            )
        )

    return cursos, disc_ch


def _montar_curso(
    curso_id: int, nome: str, nucleo_comum: bool, ch_total: int, ch_max_periodo: int,
    periodo_ideal: int, estruturas: list[Estrutura], ofertas: list[Oferta],
    prereq_por_dc: dict[int, list[list[tuple[int, int | None]]]],
    equiv_por_disc: dict[int, list[int]],
) -> Curso:
    """Port fiel de buildCourse (web/src/db/load.ts:312)."""
    fixed: list[Oferta] = []
    fixed_ids: set[int] = set()
    for o in ofertas:
        if o.tipo_item != OBRIGATORIA or o.disc_id in fixed_ids:
            continue
        fixed_ids.add(o.disc_id)
        fixed.append(o)
    fixed.sort(key=lambda o: (o.periodo, o.codigo))
    fixed_horas = sum(o.ch for o in fixed)

    fixed_ch_por_estrutura: dict[int, int] = {}
    vistos: set[int] = set()
    for o in ofertas:
        if o.tipo_item != OBRIGATORIA or o.disc_id in vistos:
            continue
        vistos.add(o.disc_id)
        fixed_ch_por_estrutura[o.estrutura_id] = fixed_ch_por_estrutura.get(o.estrutura_id, 0) + o.ch

    por_id = {e.id: e for e in estruturas}

    def tem_ancestral_com_cota(e: Estrutura) -> bool:
        pai = por_id.get(e.pai_id) if e.pai_id else None
        guarda = 0
        while pai and guarda < 32:
            guarda += 1
            if pai.ch_minima > 0:
                return True
            pai = por_id.get(pai.pai_id) if pai.pai_id else None
        return False

    quotas: list[Quota] = []
    for e in estruturas:
        if e.ch_minima <= 0 or tem_ancestral_com_cota(e):
            continue
        deficit = e.ch_minima - fixed_ch_por_estrutura.get(e.id, 0)
        if deficit <= 0:
            continue
        da_estrutura = [o for o in ofertas if o.estrutura_id == e.id]
        candidatos = [o.disc_id for o in da_estrutura if o.tipo_item in ELETIVA_MENU | DCG]
        tem_dcg = any(o.tipo_item in DCG for o in da_estrutura)
        atividades = [o for o in da_estrutura if o.tipo_item in ATIVIDADE]
        parece_atividade = bool(re.search(r"atividad|extens", e.descricao, re.I))

        if not atividades and not candidatos and parece_atividade:
            quotas.append(Quota(e.descricao, deficit, "atividade"))
            continue

        kind = "dcg" if tem_dcg else ("eletiva" if candidatos else "livre")
        quotas.append(Quota(e.descricao, deficit, kind, candidatos))

    quotas.sort(key=lambda q: -q.horas)

    modelado = fixed_horas + sum(q.horas for q in quotas)
    sobra = ch_total - modelado
    if sobra > 60:
        quotas.append(Quota("Horas do currículo fora dos núcleos mapeados",
                            sobra, "livre", [], residual=True))

    por_periodo: dict[int, int] = {}
    for o in fixed:
        if o.periodo >= 99:
            continue
        por_periodo[o.periodo] = por_periodo.get(o.periodo, 0) + o.ch
    cargas = sorted(por_periodo.values())
    mediana = cargas[len(cargas) // 2] if cargas else 0
    carga_semestre = ch_max_periodo if ch_max_periodo > 0 else (mediana or 480)

    semestres = max([periodo_ideal, *por_periodo.keys(), 0]) or (
        -(-ch_total // carga_semestre) if carga_semestre else 0
    )

    prereqs: dict[int, list[list[tuple[int, int | None]]]] = {}
    equivals: dict[int, list[int]] = {}
    for o in ofertas:
        if o.dc_id in prereq_por_dc:
            prereqs[o.disc_id] = prereq_por_dc[o.dc_id]
        if o.disc_id in equiv_por_disc:
            equivals[o.disc_id] = equiv_por_disc[o.disc_id]

    return Curso(
        id=curso_id, nome=nome, nucleo_comum=nucleo_comum, ch_total=ch_total,
        ch_max_periodo=ch_max_periodo, periodo_ideal=periodo_ideal,
        estruturas=estruturas, ofertas=ofertas, fixed=fixed, fixed_ids=fixed_ids,
        fixed_horas=fixed_horas, quotas=quotas,
        atividades_horas=sum(q.horas for q in quotas if q.kind == "atividade"),
        carga_semestre=carga_semestre, semestres=semestres,
        prereqs=prereqs, equivals=equivals,
        ch_por_disc={o.disc_id: o.ch for o in ofertas},
    )


# ------------------------------------------------------------------- score
def make_done(curso: Curso, concluido_ate: int | None = None) -> Done:
    ids: set[int] = set()
    ch_of: dict[int, int] = {}
    for o in curso.fixed:
        if concluido_ate is not None and o.periodo < 99 and o.periodo > concluido_ate:
            continue
        ids.add(o.disc_id)
        ch_of[o.disc_id] = o.ch

    fracao = 1.0
    if concluido_ate is not None and curso.semestres > 0:
        fracao = min(1.0, max(0.0, concluido_ate / curso.semestres))

    free_horas = free_aberto = 0
    for q in curso.quotas:
        if q.kind == "atividade":
            continue
        h = round(q.horas * fracao)
        free_horas += h
        if not q.residual and q.kind in ("dcg", "livre"):
            free_aberto += h
    return Done(ids, free_horas, free_aberto, ch_of)


def _prereq_ok(curso: Curso, disc_id: int, disponiveis: set[int]) -> bool:
    blocos = curso.prereqs.get(disc_id)
    if not blocos:
        return True
    return any(
        all(
            (tipo not in (1, 2)) or req is None or req in disponiveis
            for tipo, req in bloco
        )
        for bloco in blocos
    )


def score(curso: Curso, done: Done) -> dict:
    """Port de scoreCourse (web/src/lib/plan.ts:143) sem agenda."""
    cobertas_por_equiv: set[int] = set()
    for alvo, substitutos in curso.equivals.items():
        if alvo in done.ids:
            continue
        if any(s in done.ids for s in substitutos):
            cobertas_por_equiv.add(alvo)

    fixed_covered, fixed_equiv, fixed_missing = [], [], []
    for o in curso.fixed:
        if o.disc_id in done.ids:
            fixed_covered.append(o)
        elif o.disc_id in cobertas_por_equiv:
            fixed_equiv.append(o)
        else:
            fixed_missing.append(o)

    # DCG estratégica: horas de cota aberta do curso-base cobrem obrigatórias
    livre = min(done.free_aberto, done.free_horas)
    fixed_dcg = []
    if livre > 0 and fixed_missing:
        disponiveis = set(done.ids)
        restantes = sorted(fixed_missing, key=lambda o: -o.ch)
        cobrou = True
        while cobrou and restantes and livre > 0:
            cobrou = False
            sobra = []
            for o in restantes:
                if o.ch <= livre and _prereq_ok(curso, o.disc_id, disponiveis):
                    livre -= o.ch
                    fixed_dcg.append(o)
                    disponiveis.add(o.disc_id)
                    cobrou = True
                else:
                    sobra.append(o)
            restantes = sobra
        fixed_missing = restantes

    surplus = done.free_horas - sum(o.ch for o in fixed_dcg)
    for did, horas in done.ch_of.items():
        if did in curso.fixed_ids:
            continue
        surplus += horas

    free_need = 0
    for q in curso.quotas:
        if q.kind == "atividade":
            continue
        coberto = 0
        if q.kind == "eletiva":
            for cand in q.candidatos:
                if coberto >= q.horas:
                    break
                if cand not in done.ids:
                    continue
                ch = done.ch_of.get(cand, 0)
                coberto += ch
                surplus = max(0, surplus - ch)
            coberto = min(coberto, q.horas)
        else:
            coberto = min(q.horas, surplus)
            surplus -= coberto
        free_need += max(0, q.horas - coberto)

    missing_ch = sum(o.ch for o in fixed_missing)
    return {
        "extra_horas": missing_ch + free_need,
        "extra_disciplinas": len(fixed_missing) + (-(-free_need // 60) if free_need else 0),
        "free_need": free_need,
        "fixed_missing": fixed_missing,
        "fixed_dcg": fixed_dcg,
        "semestres": -(-(missing_ch + free_need) // max(1, curso.carga_semestre)),
    }


# ------------------------------------------------------------------ guloso
def build_speedrun(cursos: list[Curso], base: Curso, done: Done) -> dict:
    """Port de buildSpeedrun (web/src/lib/speedrun.ts:155)."""
    pool = set(done.ids)
    pool_ch = sum(done.ch_of.values())
    livre_aberto = done.free_aberto
    livre_fechado = max(0, done.free_horas - done.free_aberto)

    cursos_de: dict[int, int] = {}
    for c in cursos:
        for o in c.fixed:
            cursos_de[o.disc_id] = cursos_de.get(o.disc_id, 0) + 1

    alvos = [c for c in cursos if not c.nucleo_comum and c.id != base.id]
    restantes = {c.id: c for c in alvos}
    passos = []
    horas_acum = 0

    while restantes:
        melhor_id, melhor, melhor_chave = None, None, float("inf")
        for cid, target in restantes.items():
            m = _margem(target, pool, pool_ch, livre_aberto, livre_fechado, cursos_de)
            chave = m["horas"] + len(m["missing"]) * 1e-3 + cid * 1e-9
            if chave < melhor_chave:
                melhor_chave, melhor, melhor_id = chave, m, cid

        if melhor is None:
            break
        target = restantes.pop(melhor_id)

        livre_aberto -= melhor["livre_usado"]
        for o in melhor["cobertos"]:
            if o.disc_id not in pool:
                pool.add(o.disc_id)
                pool_ch += o.ch
        for o in melhor["missing"]:
            if o.disc_id not in pool:
                pool.add(o.disc_id)
                pool_ch += o.ch
        for did, ch in melhor["picks"]:
            if did not in pool:
                pool.add(did)
                pool_ch += ch

        horas_acum += melhor["horas"]
        passos.append({
            "ordem": len(passos) + 1,
            "curso_id": target.id,
            "curso": target.nome,
            "horas_passo": melhor["horas"],
            "horas_acum": horas_acum,
            "disciplinas_novas": len(melhor["missing"]) + len(melhor["picks"]),
            "semestre": -(-horas_acum // max(1, base.carga_semestre)),
        })

    return {"passos": passos, "total_disc": len(pool), "total_horas": horas_acum,
            "horas_base": pool_ch + done.free_horas}


def _margem(target: Curso, pool: set[int], pool_ch: int, livre_aberto: int,
            livre_fechado: int, cursos_de: dict[int, int]) -> dict:
    """Port de margem (web/src/lib/speedrun.ts:59)."""
    covered_ch = 0
    missing = []
    for o in target.fixed:
        if o.disc_id in pool:
            covered_ch += o.ch
            continue
        if any(s in pool for s in target.equivals.get(o.disc_id, [])):
            covered_ch += o.ch
            continue
        missing.append(o)

    livre = livre_aberto
    cobertos = []
    if livre > 0 and missing:
        resto = []
        for o in sorted(missing, key=lambda x: -x.ch):
            if o.ch <= livre:
                livre -= o.ch
                cobertos.append(o)
            else:
                resto.append(o)
        missing = resto

    surplus = livre + livre_fechado + pool_ch - covered_ch
    horas = 0
    picks: list[tuple[int, int]] = []

    for q in target.quotas:
        if q.kind == "atividade":
            continue
        coberto = 0
        if q.kind == "eletiva":
            for cand in q.candidatos:
                if coberto >= q.horas:
                    break
                if cand not in pool:
                    continue
                ch = target.ch_por_disc.get(cand, 0)
                coberto += ch
                surplus = max(0, surplus - ch)
            coberto = min(coberto, q.horas)
        else:
            coberto = min(q.horas, surplus)
            surplus -= coberto
        falta = q.horas - coberto
        if falta <= 0:
            continue
        if q.kind == "eletiva" and q.candidatos:
            cands = sorted(
                (c for c in q.candidatos if c not in pool),
                key=lambda c: -cursos_de.get(c, 0),
            )
            for cand in cands:
                if falta <= 0:
                    break
                ch = target.ch_por_disc.get(cand, 0)
                picks.append((cand, ch))
                falta -= ch
            if falta > 0:
                horas += falta
        else:
            horas += falta

    horas += sum(o.ch for o in missing) + sum(ch for _, ch in picks)
    return {"missing": missing, "horas": horas, "picks": picks,
            "cobertos": cobertos, "livre_usado": livre_aberto - livre}


# --------------------------------------------------------------- benchmark
def run(conn: sqlite3.Connection, base_id: int | None = None,
        com_julgadas: bool = True, exportar: bool = True) -> dict:
    from . import db as _db

    _db.migrar(conn)
    cursos, _ = carregar(conn, com_julgadas=com_julgadas)
    por_id = {c.id: c for c in cursos}

    base = por_id.get(base_id) if base_id else next(
        (c for c in cursos if "Ciência da Computação" in c.nome), None
    )
    if base is None:
        raise RuntimeError("curso-base não encontrado")

    print(f"  cursos carregados ........ {len(cursos)}")
    print(f"  base ..................... {base.nome} ({base.ch_total} h)")
    print(f"  equivalências ............. {'oficial + julgada' if com_julgadas else 'só oficial'}")

    done = make_done(base)
    print(f"  disciplinas concluídas ... {len(done.ids)}")
    print(f"  horas livres ............. {done.free_horas} h "
          f"(abertas: {done.free_aberto} h)")

    agora = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    print("\n  calculando benchmark base × alvo…", flush=True)
    conn.execute("DELETE FROM rota_benchmark WHERE base_curso_id = ?", (base.id,))
    linhas = []
    for alvo in cursos:
        if alvo.id == base.id:
            continue
        s = score(alvo, done)
        linhas.append((base.id, alvo.id, s["extra_horas"], s["extra_disciplinas"],
                       s["semestres"], agora))
    conn.executemany(
        "INSERT INTO rota_benchmark (base_curso_id, alvo_curso_id, horas, disciplinas, "
        "semestres, calculado_em) VALUES (?, ?, ?, ?, ?, ?)",
        linhas,
    )

    print("  rodando o guloso…", flush=True)
    rota = build_speedrun(cursos, base, done)
    conn.execute("DELETE FROM rota_gulosa")
    conn.executemany(
        "INSERT INTO rota_gulosa (ordem, curso_id, horas_passo, horas_acum, semestre, "
        "disciplinas_novas) VALUES (?, ?, ?, ?, ?, ?)",
        [(p["ordem"], p["curso_id"], p["horas_passo"], p["horas_acum"],
          p["semestre"], p["disciplinas_novas"]) for p in rota["passos"]],
    )
    conn.commit()

    print(f"\n  rota gulosa: {len(rota['passos'])} cursos · "
          f"{rota['total_disc']} disciplinas · {rota['total_horas']} h")

    saida = None
    if exportar:
        saida = config.DATA_DIR / "exports" / "auditoria-rota.json"
        saida.parent.mkdir(parents=True, exist_ok=True)
        saida.write_text(json.dumps({
            "base_curso_id": base.id,
            "base": base.nome,
            "com_julgadas": com_julgadas,
            "carga_semestre": base.carga_semestre,
            "total_disc": rota["total_disc"],
            "total_horas": rota["total_horas"],
            "horas_base": rota["horas_base"],
            "passos": rota["passos"],
            "benchmark": [
                {"alvo_curso_id": a, "horas": h, "disciplinas": d, "semestres": s}
                for _, a, h, d, s, _ in linhas
            ],
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  exportado ................. {saida}")

    return {"base": base, "rota": rota, "benchmark": linhas, "saida": saida}


# -------------------------------------------------------------- comparação
def comparar(conn: sqlite3.Connection, arquivo: Path) -> int:
    """Compara o JSON do front com o benchmark do Python. 0 = idêntico."""
    dados = json.loads(Path(arquivo).read_text(encoding="utf-8"))
    divergencias = 0

    rota_db = conn.execute(
        "SELECT curso_id, horas_passo, horas_acum FROM rota_gulosa ORDER BY ordem"
    ).fetchall()
    rota_front = dados.get("passos") or []

    if len(rota_db) != len(rota_front):
        print(f"  ✗ tamanho da rota: python={len(rota_db)} front={len(rota_front)}")
        divergencias += 1
    else:
        for (cid, hp, ha), p in zip(rota_db, rota_front):
            if cid != p.get("curso_id") or abs(hp - p.get("horasPasso", hp)) > 1:
                divergencias += 1
                print(f"    passo {p.get('ordem')}: python={cid}/{hp}h "
                      f"front={p.get('curso_id')}/{p.get('horasPasso')}h")

    banco = {
        a: (h, d, s) for a, h, d, s in conn.execute(
            "SELECT alvo_curso_id, horas, disciplinas, semestres FROM rota_benchmark "
            "WHERE base_curso_id = ?", (dados.get("base_curso_id"),)
        )
    }
    for item in dados.get("benchmark") or []:
        alvo = item.get("alvo_curso_id")
        if alvo not in banco:
            continue
        h, d, s = banco[alvo]
        if (abs(h - item.get("horas", h)) > 1 or d != item.get("disciplinas")
                or s != item.get("semestres")):
            divergencias += 1
            if divergencias <= 20:
                print(f"    alvo {alvo}: python={h}h/{d}d/{s}s "
                      f"front={item.get('horas')}h/{item.get('disciplinas')}d/"
                      f"{item.get('semestres')}s")

    total = max(1, len(dados.get("benchmark") or []))
    print(f"\n  {divergencias} divergência(s) em {total} alvos comparados")
    if divergencias == 0:
        print("  ✓ as duas implementações concordam")
    return 0 if divergencias == 0 else 1

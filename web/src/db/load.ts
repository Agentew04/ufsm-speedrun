import initSqlJs, { type Database, type SqlJsStatic } from 'sql.js'
import wasmUrl from 'sql.js/dist/sql-wasm.wasm?url'
import type {
  CourseModel,
  Curso,
  Disciplina,
  EquivItem,
  Estrutura,
  Oferta,
  PrereqBloco,
  Quota,
  Universe,
  Versao,
} from './types'

let sqlPromise: Promise<SqlJsStatic> | null = null

function getSql(): Promise<SqlJsStatic> {
  if (!sqlPromise) {
    sqlPromise = initSqlJs({ locateFile: () => wasmUrl })
  }
  return sqlPromise
}

export const DB_MAGIC = 'SQLite format 3'

/** Descomprime um .gz (DecompressionStream: Edge/Chrome/Firefox modernos). */
export async function gunzip(bytes: ArrayBuffer): Promise<ArrayBuffer> {
  const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))
  return await new Response(stream).arrayBuffer()
}

export function isGzip(bytes: ArrayBuffer): boolean {
  const b = new Uint8Array(bytes, 0, Math.min(2, bytes.byteLength))
  return b.length === 2 && b[0] === 0x1f && b[1] === 0x8b
}

export function isSqlite(bytes: ArrayBuffer): boolean {
  const head = new TextDecoder('latin1').decode(bytes.slice(0, 16))
  return head.startsWith(DB_MAGIC)
}

/** Normaliza o que veio do disco/rede: aceita .db e .db.gz. */
export async function paraSqlite(bytes: ArrayBuffer): Promise<ArrayBuffer> {
  return isGzip(bytes) ? gunzip(bytes) : bytes
}

export async function openDatabase(bytes: ArrayBuffer): Promise<Database> {
  const SQL = await getSql()
  return new SQL.Database(new Uint8Array(bytes))
}

function q<T extends Record<string, unknown>>(db: Database, sql: string): T[] {
  const res = db.exec(sql)
  if (!res.length) return []
  const { columns, values } = res[0]
  return values.map((value) => {
    const row: Record<string, unknown> = {}
    columns.forEach((col, i) => {
      row[col] = value[i]
    })
    return row as T
  })
}

const num = (v: unknown): number => (typeof v === 'number' ? v : Number(v ?? 0) || 0)
const optNum = (v: unknown): number | null => (v === null || v === undefined ? null : num(v))
const str = (v: unknown): string => (v === null || v === undefined ? '' : String(v))
const optStr = (v: unknown): string | null => (v === null || v === undefined ? null : String(v))

export interface LoadProgress {
  label: string
}

/**
 * Monta o universo em memória a partir do banco. Uma passada por tabela.
 * Tolerante a tabelas ainda vazias (a coleta pode estar em andamento).
 */
export function loadUniverse(db: Database, onProgress?: (p: LoadProgress) => void): Universe {
  onProgress?.({ label: 'lendo cursos' })
  const temColunaNucleo = q<{ name: string }>(db, 'PRAGMA table_info(curso)').some(
    (r) => str(r.name) === 'eh_nucleo_comum',
  )
  const cursos = q<{
    id: number
    nome: string
    nome_lista: string | null
    campus: string | null
    modalidade: string | null
    grau: string | null
    classificacao: string | null
    eh_nucleo_comum: number | null
    nucleo_comum_motivo: string | null
  }>(
    db,
    temColunaNucleo
      ? `SELECT id, nome, nome_lista, campus, modalidade, grau, classificacao,
                eh_nucleo_comum, nucleo_comum_motivo
           FROM curso ORDER BY nome`
      : `SELECT id, nome, nome_lista, campus, modalidade, grau, classificacao,
                NULL AS eh_nucleo_comum, NULL AS nucleo_comum_motivo
           FROM curso ORDER BY nome`,
  )

  const versoes = q<Record<string, unknown>>(
    db,
    `SELECT id, curso_id, ano, numero, ch_total, ch_min_periodo, ch_max_periodo,
            periodo_ideal, tipo_periodo
       FROM versao_curriculo WHERE selecionada = 1`,
  )

  onProgress?.({ label: 'lendo estruturas' })
  const estruturas = q<Record<string, unknown>>(
    db,
    `SELECT e.id, e.versao_id, e.pai_id, e.descricao, e.ch_minima, e.ordem
       FROM estrutura e
       JOIN versao_curriculo v ON v.id = e.versao_id
      WHERE v.selecionada = 1
      ORDER BY e.ordem IS NULL, e.ordem, e.id`,
  )

  onProgress?.({ label: 'lendo ofertas' })
  const ofertasRaw = q<Record<string, unknown>>(
    db,
    `SELECT dc.id, dc.versao_id, dc.estrutura_id, dc.disciplina_id, dc.tipo_item,
            dc.periodo_ideal, dc.periodo_minimo, dc.tem_prereq, dc.tem_equiv,
            d.codigo, d.nome, d.ch_total, d.creditos
       FROM disciplina_curriculo dc
       JOIN disciplina d ON d.id = dc.disciplina_id
       JOIN versao_curriculo v ON v.id = dc.versao_id
      WHERE v.selecionada = 1`,
  )

  onProgress?.({ label: 'lendo pré-requisitos' })
  const prereqRaw = q<Record<string, unknown>>(
    db,
    `SELECT pb.disciplina_curriculo_id AS dc_id, pb.id AS bloco_id, pi.tipo_item,
            pi.disciplina_req_id, pi.disciplina_req_codigo, pi.numero_referencia
       FROM prereq_bloco pb
       JOIN prereq_item pi ON pi.bloco_id = pb.id`,
  )

  onProgress?.({ label: 'lendo equivalências' })  // v_equivalencia_efetiva = oficial + julgadas (Fase 6a/6b). Bancos antigos
  // podem não ter a view nem a tabela de julgadas — daí os fallbacks.
  const EQUIV_OFICIAL = `
    SELECT dc.disciplina_id AS alvo_id, ei.disciplina_req_id AS substituta_id,
           'oficial' AS origem, 1.0 AS confianca, 'equivalente' AS veredito
      FROM equivalencia_item ei
      JOIN equivalencia_bloco eb ON eb.id = ei.bloco_id
      JOIN disciplina_curriculo dc ON dc.id = eb.disciplina_curriculo_id
     WHERE ei.disciplina_req_id IS NOT NULL`
  const EQUIV_JULGADA = `
    SELECT disciplina_a AS alvo_id, disciplina_b AS substituta_id,
           'julgada' AS origem, confianca, veredito
      FROM equivalencia_julgada WHERE veredito IN ('equivalente', 'parcial')
    UNION ALL
    SELECT disciplina_b AS alvo_id, disciplina_a AS substituta_id,
           'julgada' AS origem, confianca, veredito
      FROM equivalencia_julgada WHERE veredito IN ('equivalente', 'parcial')`
  const AGRUPAR = ' SELECT alvo_id, substituta_id, MAX(origem) AS origem, MAX(confianca) AS confianca, MIN(veredito) AS veredito FROM ('

  let equivRaw: Record<string, unknown>[] = []
  try {
    equivRaw = q<Record<string, unknown>>(db, `${AGRUPAR}SELECT * FROM v_equivalencia_efetiva) GROUP BY alvo_id, substituta_id`)
  } catch {
    try {
      equivRaw = q<Record<string, unknown>>(db, `${AGRUPAR}${EQUIV_OFICIAL} UNION ALL ${EQUIV_JULGADA}) GROUP BY alvo_id, substituta_id`)
    } catch {
      equivRaw = q<Record<string, unknown>>(db, `${AGRUPAR}${EQUIV_OFICIAL}) GROUP BY alvo_id, substituta_id`)
    }
  }

  const meta = q<Record<string, unknown>>(
    db,
    `SELECT (SELECT COUNT(*) FROM curso) AS cursos,
            (SELECT COUNT(*) FROM versao_curriculo WHERE selecionada = 1) AS versoes,
            (SELECT COUNT(*) FROM disciplina_curriculo) AS ofertas,
            (SELECT COUNT(*) FROM disciplina) AS disciplinas,
            (SELECT COUNT(*) FROM disciplina_curriculo WHERE tem_prereq = 1) AS com_prereq,
            (SELECT COUNT(*) FROM disciplina_curriculo WHERE tem_equiv = 1) AS com_equiv,
            (SELECT COUNT(DISTINCT disciplina_curriculo_id) FROM prereq_bloco) AS prereq_dc,
            (SELECT COUNT(DISTINCT disciplina_curriculo_id) FROM equivalencia_bloco) AS equiv_dc,
            (SELECT COUNT(*) FROM disciplina WHERE programa_texto IS NOT NULL) AS com_ementa`,
  )[0] ?? {}

  // catálogo completo (inclui disciplina fora das versões selecionadas) —
  // serve de índice por código e alimenta o modal da cadeira
  const discRaw = q<Record<string, unknown>>(
    db,
    `SELECT id, codigo, nome, ch_total, creditos, departamento_nome, situacao
       FROM disciplina`,
  )
  const discById = new Map<number, Disciplina>()
  const discByCodigo = new Map<string, number>()
  for (const d of discRaw) {
    const id = num(d.id)
    const item: Disciplina = {
      id,
      codigo: str(d.codigo),
      nome: str(d.nome),
      ch: num(d.ch_total),
      creditos: optNum(d.creditos),
      departamento: optStr(d.departamento_nome),
      situacao: optStr(d.situacao),
    }
    discById.set(id, item)
    if (item.codigo) discByCodigo.set(item.codigo, id)
  }

  const versaoByCurso = new Map<number, Versao>()
  for (const v of versoes) {
    const cursoId = num(v.curso_id)
    versaoByCurso.set(cursoId, {
      id: num(v.id),
      cursoId,
      ano: optNum(v.ano),
      numero: optStr(v.numero),
      chTotal: optNum(v.ch_total),
      chMinPeriodo: optNum(v.ch_min_periodo),
      chMaxPeriodo: optNum(v.ch_max_periodo),
      periodoIdeal: optNum(v.periodo_ideal),
      tipoPeriodo: optStr(v.tipo_periodo),
    })
  }

  const estruturasByVersao = new Map<number, Estrutura[]>()
  for (const e of estruturas) {
    const item: Estrutura = {
      id: num(e.id),
      versaoId: num(e.versao_id),
      paiId: optNum(e.pai_id),
      descricao: str(e.descricao),
      chMinima: optNum(e.ch_minima),
      ordem: optNum(e.ordem),
    }
    const list = estruturasByVersao.get(item.versaoId)
    if (list) list.push(item)
    else estruturasByVersao.set(item.versaoId, [item])
  }

  const ofertasByVersao = new Map<number, Oferta[]>()
  for (const o of ofertasRaw) {
    const oferta: Oferta = {
      id: num(o.id),
      versaoId: num(o.versao_id),
      estruturaId: num(o.estrutura_id),
      discId: num(o.disciplina_id),
      tipoItem: num(o.tipo_item),
      periodo: num(o.periodo_ideal),
      ch: num(o.ch_total),
      creditos: optNum(o.creditos),
      codigo: str(o.codigo),
      nome: str(o.nome),
      temPrereq: num(o.tem_prereq) === 1,
      temEquiv: num(o.tem_equiv) === 1,
      periodoMinimo: optNum(o.periodo_minimo),
    }
    const list = ofertasByVersao.get(oferta.versaoId)
    if (list) list.push(oferta)
    else ofertasByVersao.set(oferta.versaoId, [oferta])
  }

  // pré-requisitos por oferta
  const prereqByDc = new Map<number, PrereqBloco[]>()
  const blocosIndex = new Map<string, PrereqBloco>()
  for (const p of prereqRaw) {
    const dcId = num(p.dc_id)
    const blocoId = num(p.bloco_id)
    let blocos = prereqByDc.get(dcId)
    if (!blocos) {
      blocos = []
      prereqByDc.set(dcId, blocos)
    }
    const key = `${dcId}:${blocoId}`
    let bloco = blocosIndex.get(key)
    if (!bloco) {
      bloco = { itens: [] }
      blocosIndex.set(key, bloco)
      blocos.push(bloco)
    }
    const discId = optNum(p.disciplina_req_id)
    const codigo = optStr(p.disciplina_req_codigo)
    bloco.itens.push({
      tipo: num(p.tipo_item),
      discId: discId ?? (codigo ? (discByCodigo.get(codigo) ?? null) : null),
      codigo,
      numero: optNum(p.numero_referencia),
    })
  }

  const equivByDisc = new Map<number, EquivItem[]>()
  for (const e of equivRaw) {
    const alvo = num(e.alvo_id)
    const sub = optNum(e.substituta_id)
    if (!alvo || !sub || alvo === sub) continue
    const item: EquivItem = {
      discId: sub,
      codigo: discById.get(sub)?.codigo ?? null,
      origem: str(e.origem) === 'julgada' ? 'julgada' : 'oficial',
      confianca: Number(e.confianca ?? 1) || 1,
      veredito: str(e.veredito) === 'parcial' ? 'parcial' : 'equivalente',
    }
    const list = equivByDisc.get(alvo)
    if (list) list.push(item)
    else equivByDisc.set(alvo, [item])
  }

  // exigências de CH por estrutura (tipo 3 do SIE). Estrutura nula = total do curso.
  const reqChByDc = new Map<number, { estruturaId: number | null; horas: number }[]>()
  try {
    for (const r of q<Record<string, unknown>>(
      db,
      'SELECT disciplina_curriculo_id AS dc_id, estrutura_id, horas FROM requisito_ch',
    )) {
      const dcId = num(r.dc_id)
      const item = { estruturaId: optNum(r.estrutura_id), horas: num(r.horas) }
      const lista = reqChByDc.get(dcId)
      if (lista) lista.push(item)
      else reqChByDc.set(dcId, [item])
    }
  } catch {
    /* banco sem requisito_ch */
  }

  // DCG: menu fechado materializado no ETL (`dcg_elegivel`) + terminais.
  // Banco antigo não tem nenhum dos dois — cai no comportamento anterior.
  const dcgMenu = new Map<number, { ids: number[]; fonte: string }>()
  try {
    for (const r of q<Record<string, unknown>>(
      db,
      'SELECT estrutura_id, disciplina_id, fonte FROM dcg_elegivel',
    )) {
      const eid = num(r.estrutura_id)
      const atual = dcgMenu.get(eid)
      if (atual) atual.ids.push(num(r.disciplina_id))
      else dcgMenu.set(eid, { ids: [num(r.disciplina_id)], fonte: str(r.fonte) })
    }
  } catch {
    /* sem dcg_elegivel */
  }
  let terminais = new Set<number>()
  try {
    terminais = new Set(
      q<{ id: number }>(db, 'SELECT id FROM disciplina WHERE eh_terminal = 1').map((r) => num(r.id)),
    )
  } catch {
    /* sem eh_terminal */
  }

  onProgress?.({ label: 'montando currículos' })
  // ABI/núcleo comum: mesmo `nome_lista` de um curso bem maior (o ABI é a
  // entrada, o diploma continua na habilitação). Ex.: Artes Cênicas 960 h vs
  // Direção/Interpretação 2.756 h; Ciências Biológicas "Núcleo Comum".
  const chPorLista = new Map<string, number>()
  for (const c of cursos) {
    const v = versaoByCurso.get(c.id)
    if (!v || !c.nome_lista) continue
    const atual = chPorLista.get(c.nome_lista) ?? 0
    chPorLista.set(c.nome_lista, Math.max(atual, v.chTotal ?? 0))
  }
  const ehNucleoComum = (nome: string, lista: string | null, chTotal: number | null) => {
    if (/n[uú]cleo comum/i.test(nome)) return true
    if (!lista || !chTotal) return false
    const irmao = chPorLista.get(lista) ?? 0
    return irmao >= chTotal * 2 && chTotal < 2000
  }

  const models: CourseModel[] = []
  for (const c of cursos) {
    const versao = versaoByCurso.get(c.id)
    if (!versao) continue
    const estruturasDoCurso = estruturasByVersao.get(versao.id) ?? []
    const ofertas = ofertasByVersao.get(versao.id) ?? []
    // classificação vem do ETL (curso.eh_nucleo_comum); o fallback cobre banco antigo
    const doBanco = num(c.eh_nucleo_comum) === 1
    const fallback = ehNucleoComum(str(c.nome), optStr(c.nome_lista), versao.chTotal)
    const model = buildCourse(
      {
        id: c.id,
        nome: str(c.nome),
        campus: optStr(c.campus),
        modalidade: optStr(c.modalidade),
        grau: optStr(c.grau),
        classificacao: optStr(c.classificacao),
        nucleoComum: doBanco || fallback,
        nucleoMotivo: optStr(c.nucleo_comum_motivo) ?? (fallback ? 'heurística do front' : null),
      },
      versao,
      estruturasDoCurso,
      ofertas,
      prereqByDc,
      equivByDisc,
      dcgMenu,
      terminais,
      reqChByDc,
    )
    models.push(model)
  }

  const cursosByDisc = new Map<number, number[]>()
  for (const m of models) {
    for (const oferta of m.ofertas) {
      const list = cursosByDisc.get(oferta.discId)
      if (list) {
        if (list[list.length - 1] !== m.curso.id) list.push(m.curso.id)
      } else {
        cursosByDisc.set(oferta.discId, [m.curso.id])
      }
    }
  }

  return {
    cursos: models,
    byCurso: new Map(models.map((m) => [m.curso.id, m])),
    disciplinas: discById,
    cursosByDisc,
    terminais,
    meta: {
      cursos: num(meta.cursos),
      versoes: num(meta.versoes),
      ofertas: num(meta.ofertas),
      disciplinas: num(meta.disciplinas),
      comPrereq: num(meta.com_prereq),
      comEquiv: num(meta.com_equiv),
      comEmenta: num(meta.com_ementa),
      coberturaPrereq: num(meta.com_prereq) ? Math.min(1, num(meta.prereq_dc) / num(meta.com_prereq)) : 1,
      coberturaEquiv: num(meta.com_equiv) ? Math.min(1, num(meta.equiv_dc) / num(meta.com_equiv)) : 1,
    },
  }
}

function buildCourse(
  curso: Curso,
  versao: Versao,
  estruturas: Estrutura[],
  ofertas: Oferta[],
  prereqByDc: Map<number, PrereqBloco[]>,
  equivByDisc: Map<number, EquivItem[]>,
  dcgMenu: Map<number, { ids: number[]; fonte: string }>,
  terminais: Set<number>,
  reqChByDc: Map<number, { estruturaId: number | null; horas: number }[]>,
): CourseModel {
  const byDisc = new Map<number, Oferta>()
  for (const o of ofertas) {
    const prev = byDisc.get(o.discId)
    if (!prev || (prev.tipoItem !== 1 && o.tipoItem === 1)) byDisc.set(o.discId, o)
  }

  // Obrigatórias: tipo 1. Dedup por disciplina (mesma cadeira em 2 núcleos).
  const fixed: Oferta[] = []
  const fixedIds = new Set<number>()
  for (const o of ofertas) {
    if (o.tipoItem !== 1) continue
    if (fixedIds.has(o.discId)) continue
    fixedIds.add(o.discId)
    fixed.push(o)
  }
  fixed.sort((a, b) => a.periodo - b.periodo || a.codigo.localeCompare(b.codigo))
  const fixedHoras = fixed.reduce((s, o) => s + o.ch, 0)

  // CH de obrigatórias por estrutura (para medir o déficit de cada cota)
  const fixedChByEstrutura = new Map<number, number>()
  const seenFixed = new Set<number>()
  for (const o of ofertas) {
    if (o.tipoItem !== 1) continue
    if (seenFixed.has(o.discId)) continue
    seenFixed.add(o.discId)
    fixedChByEstrutura.set(o.estruturaId, (fixedChByEstrutura.get(o.estruturaId) ?? 0) + o.ch)
  }

  const estruturaById = new Map(estruturas.map((e) => [e.id, e]))
  const hasQuotaAncestor = (e: Estrutura): boolean => {
    let pai = e.paiId ? estruturaById.get(e.paiId) : undefined
    let guard = 0
    while (pai && guard++ < 32) {
      if ((pai.chMinima ?? 0) > 0) return true
      pai = pai.paiId ? estruturaById.get(pai.paiId) : undefined
    }
    return false
  }

  const quotas: Quota[] = []
  let atividadesHoras = 0
  for (const e of estruturas) {
    const minima = e.chMinima ?? 0
    if (minima <= 0) continue
    if (hasQuotaAncestor(e)) continue
    const deficit = minima - (fixedChByEstrutura.get(e.id) ?? 0)
    if (deficit <= 0) continue

    const daEstrutura = ofertas.filter((o) => o.estruturaId === e.id)
    let candidatos = daEstrutura
      .filter((o) => o.tipoItem === 2 || o.tipoItem === 3 || o.tipoItem === 5 || o.tipoItem === 7)
      .map((o) => o.discId)
    const temDcg = daEstrutura.some((o) => o.tipoItem === 5 || o.tipoItem === 7)
    const atividades = daEstrutura.filter((o) => o.tipoItem === 4 || o.tipoItem === 8)
    const pareceAtividade = /atividad|extens/i.test(e.descricao)

    // DCG: o menu real vem do ETL (`dcg_elegivel`), já sem TCC/estágio.
    // Sem a tabela (banco antigo), usa as ofertas do núcleo como aproximação.
    let menuFechado = false
    if (temDcg) {
      const menu = dcgMenu.get(e.id)
      if (menu) {
        candidatos = menu.ids
        menuFechado = menu.fonte === 'menu'
      } else {
        menuFechado = candidatos.length > 0
      }
      if (terminais.size) candidatos = candidatos.filter((id) => !terminais.has(id))
    }

    if (atividades.length === 0 && candidatos.length === 0 && pareceAtividade) {
      atividadesHoras += deficit
      quotas.push({
        estruturaId: e.id,
        descricao: e.descricao,
        horas: deficit,
        kind: 'atividade',
        candidatos: [],
        residual: false,
        menuFechado: false,
      })
      continue
    }

    quotas.push({
      estruturaId: e.id,
      descricao: e.descricao,
      horas: deficit,
      kind: temDcg ? 'dcg' : candidatos.length ? 'eletiva' : 'livre',
      candidatos,
      residual: false,
      menuFechado,
    })
  }
  quotas.sort((a, b) => b.horas - a.horas)

  // Sobra entre ch_total e o que os núcleos declaram (núcleo flexível sem
  // ch_minima, ex.: Música/Bacharelado 2.400 h com 1.290 h mapeadas). Sem isso
  // o curso parecia 1.110 h mais barato do que é.
  const modelado = fixedHoras + quotas.reduce((s, q) => s + q.horas, 0)
  const sobra = (versao.chTotal ?? 0) - modelado
  if (sobra > 60) {
    quotas.push({
      estruturaId: -1,
      descricao: 'Horas do currículo fora dos núcleos mapeados',
      horas: sobra,
      kind: 'livre',
      candidatos: [],
      residual: true,
      menuFechado: false,
    })
  }

  // CH por semestre: usa o máximo oficial; senão a mediana do que está listado.
  const porPeriodo = new Map<number, number>()
  for (const o of fixed) {
    if (o.periodo >= 99) continue
    porPeriodo.set(o.periodo, (porPeriodo.get(o.periodo) ?? 0) + o.ch)
  }
  const cargas = [...porPeriodo.values()].sort((a, b) => a - b)
  const mediana = cargas.length ? cargas[Math.floor(cargas.length / 2)] : 0
  const cargaSemestre = versao.chMaxPeriodo && versao.chMaxPeriodo > 0
    ? versao.chMaxPeriodo
    : mediana || 480

  const semestres = Math.max(
    versao.periodoIdeal ?? 0,
    ...[...porPeriodo.keys(), 0],
  ) || Math.ceil((versao.chTotal ?? fixedHoras) / cargaSemestre)

  const prereqs = new Map<number, PrereqBloco[]>()
  const equivals = new Map<number, EquivItem[]>()
  const requisitoCh = new Map<number, { estruturaId: number | null; horas: number }[]>()
  for (const o of ofertas) {
    const p = prereqByDc.get(o.id)
    if (p) prereqs.set(o.discId, p)
    const e = equivByDisc.get(o.discId)
    if (e) equivals.set(o.discId, e)
    const r = reqChByDc.get(o.id)
    if (r) requisitoCh.set(o.discId, r)
  }

  return {
    curso,
    versao,
    estruturas,
    ofertas,
    fixed,
    fixedIds,
    fixedHoras,
    quotas,
    atividadesHoras,
    cargaSemestre,
    semestres,
    byDisc,
    prereqs,
    equivals,
    requisitoCh,
  }
}

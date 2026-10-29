import type { CourseModel, Oferta, Universe } from '../db/types'
import { prereqSatisfied, type Done } from './plan'

export interface RouteStep {
  ordem: number
  curso: CourseModel
  /** obrigatórias do curso que ainda não estavam no pool */
  novas: Oferta[]
  horasPasso: number
  horasAcum: number
  /** semestre (a partir da formatura do curso-base) em que o curso fecha */
  semestre: number
}

export interface Gargalo {
  discId: number
  codigo: string
  nome: string
  ch: number
  cursos: number
}

export interface Speedrun {
  passos: RouteStep[]
  cursoIds: number[]
  totalDisc: number
  totalHoras: number
  horasBase: number
  semestres: number
  carga: number
  gargalos: Gargalo[]
  /** obrigatórias de outros currículos que entraram como DCG do curso-base */
  dcgEstrategica: { discId: number; codigo: string; nome: string; ch: number }[]
  /** escolhas do menu de DCG usadas na rota (dispensaram obrigatórias) */
  dcgEscolhas: { discId: number; codigo: string; nome: string; ch: number }[]
  unicas: number
  compartilhadas: number
  /** custo concentrado: quantos passos concentram 50% das horas */
  metadeEm: number
  custoPrimeiros20: number
  custoUltimos20: number
}

interface Margem {
  missing: Oferta[]
  horas: number
  picks: number[]
  /** obrigatórias cobertas pelas horas livres (DCG) do curso-base */
  cobertos: Oferta[]
  /** obrigatórias dispensadas por escolhas do menu de DCG (não foram cursadas) */
  cobertosMenu: Oferta[]
  livreUsado: number
  /** disciplinas do menu de DCG usadas neste passo */
  menuUsado: number[]
  gastoMenu: number
}

function chDe(universo: Universe, id: number): number {
  return universo.disciplinas.get(id)?.ch ?? 0
}

/**
 * Custo marginal de fechar `target` com o pool atual. Mesma semântica do
 * scoreCourse, mas sem montar plano e com o pool como "done".
 */
function margem(
  universo: Universe,
  target: CourseModel,
  pool: Set<number>,
  poolCh: number,
  livreAberto: number,
  livreFechado: number,
  done: Done,
  cursosDe: (id: number) => number,
  menu: Map<number, number>,
  menuHoras: number,
  disponiveis?: Set<number>,
): Margem {
  let coveredCh = 0
  const missing: Oferta[] = []

  for (const o of target.fixed) {
    if (pool.has(o.discId)) {
      coveredCh += o.ch
      continue
    }
    const equivs = target.equivals.get(o.discId)
    if (equivs?.some((e) => e.discId !== null && pool.has(e.discId))) {
      coveredCh += o.ch
      continue
    }
    missing.push(o)
  }

  // horas de DCG ainda não gastas, só dentro do menu do curso-base
  let livre = livreAberto
  const cobertos: Oferta[] = []
  if (livre > 0 && missing.length) {
    const disponiveis = new Set(pool)
    let restantes = [...missing].sort((a, b) => b.ch - a.ch)
    let cobrou = true
    while (cobrou && restantes.length && livre > 0) {
      cobrou = false
      const sobra: Oferta[] = []
      for (const o of restantes) {
        const elegivel = !done.terminais.has(o.discId) && done.dcgAberta
        if (o.ch <= livre && elegivel && prereqSatisfied(target, o.discId, disponiveis)) {
          livre -= o.ch
          cobertos.push(o)
          disponiveis.add(o.discId)
          cobrou = true
        } else {
          sobra.push(o)
        }
      }
      restantes = sobra
    }
    missing.length = 0
    missing.push(...restantes)
  }

  let surplus = livre + livreFechado + poolCh - coveredCh
  let horas = 0
  const picks = new Set<number>()

  // menu de DCG do curso-base: "cursar" itens que dispensam obrigatórias do
  // alvo (a própria disciplina ou uma equivalente), consumindo o orçamento.
  const menuUsado: number[] = []
  const cobertosMenu: Oferta[] = []
  let gastoMenu = 0
  let orcamentoMenu = menuHoras
  if (orcamentoMenu > 0 && missing.length) {
    const sobraMenu: Oferta[] = []
    for (const o of [...missing].sort((a, b) => b.ch - a.ch)) {
      const substitutos = new Set<number>([o.discId])
      for (const eq of target.equivals.get(o.discId) ?? []) {
        if (eq.discId !== null) substitutos.add(eq.discId)
      }
      let escolha = -1
      let custo = Number.POSITIVE_INFINITY
      for (const [m, ch] of menu) {
        if (!substitutos.has(m)) continue
        const c = pool.has(m) ? 0 : ch
        if (c > orcamentoMenu) continue
        if (c < custo) {
          escolha = m
          custo = c
        }
      }
      if (escolha < 0) {
        sobraMenu.push(o)
        continue
      }
      orcamentoMenu -= custo
      gastoMenu += custo
      if (!pool.has(escolha)) menuUsado.push(escolha)
      cobertosMenu.push(o)
    }
    missing.length = 0
    missing.push(...sobraMenu)
  }
  surplus = Math.max(0, surplus - gastoMenu)

  for (const q of target.quotas) {
    if (q.kind === 'atividade') continue
    let coberto = 0
    const menuFechado = q.kind === 'eletiva' || (q.kind === 'dcg' && q.menuFechado)

    if (menuFechado) {
      for (const cand of q.candidatos) {
        if (coberto >= q.horas) break
        if (!pool.has(cand)) continue
        if (disponiveis && !disponiveis.has(cand)) continue
        const ch = chDe(universo, cand)
        coberto += ch
        surplus = Math.max(0, surplus - ch)
      }
      coberto = Math.min(coberto, q.horas)
    } else {
      coberto = Math.min(q.horas, surplus)
      surplus -= coberto
    }

    let falta = q.horas - coberto
    if (falta <= 0) continue

    if (menuFechado && q.candidatos.length) {
      const cands = q.candidatos
        .filter(
          (c) => !pool.has(c) && !picks.has(c) && (!disponiveis || disponiveis.has(c)),
        )
        .sort((a, b) => cursosDe(b) - cursosDe(a) || chDe(universo, b) - chDe(universo, a))
      for (const cand of cands) {
        if (falta <= 0) break
        picks.add(cand)
        falta -= chDe(universo, cand)
      }
      if (falta > 0) horas += falta
    } else {
      horas += falta
    }
  }

  for (const o of missing) horas += o.ch
  for (const p of picks) horas += chDe(universo, p)

  return {
    missing,
    horas,
    picks: [...picks],
    cobertos,
    cobertosMenu,
    livreUsado: livreAberto - livre,
    menuUsado,
    gastoMenu,
  }
}

/**
 * Rota gulosa para fechar todos os cursos: a cada passo escolhe o curso que
 * custa menos cadeiras/horas novas, dado tudo que já entrou no pool.
 *
 * A união final (e portanto o total de cadeiras) não depende da ordem — o que
 * a ordem muda é o quão cedo cada curso fecha.
 */
export function buildSpeedrun(
  universo: Universe,
  done: Done,
  base: CourseModel | null,
  opcoes?: { mesmoCampus?: boolean; disponiveis?: Set<number> },
): Speedrun {
  const mesmoCampus = opcoes?.mesmoCampus ?? false
  const disponiveis = opcoes?.disponiveis
  const pool = new Set<number>(done.ids)
  let poolCh = 0
  for (const ch of done.chOf.values()) poolCh += ch
  let livreAberto = done.dcgHoras
  let livreFechado = Math.max(0, done.freeHoras - done.dcgHoras)
  let menuHoras = done.menuHoras
  const menu = new Map(done.menu)
  const horasBase = poolCh + livreAberto + livreFechado

  const cursos = universo.cursos
  const cargas = cursos.map((c) => c.cargaSemestre).sort((a, b) => a - b)
  const carga = cargas.length ? cargas[Math.floor(cargas.length / 2)] : 540

  // quantos cursos têm a disciplina como obrigatória (critério de desempate
  // das candidatas de cota — igual ao auditor)
  const emQuantos = new Map<number, number>()
  for (const c of cursos) {
    for (const o of c.fixed) emQuantos.set(o.discId, (emQuantos.get(o.discId) ?? 0) + 1)
  }
  const cursosDe = (id: number) => emQuantos.get(id) ?? 0

  // obrigatórias de outros currículos que entraram como DCG do curso-base
  const dcgEstrategica: { discId: number; codigo: string; nome: string; ch: number }[] = []
  const dcgEscolhas: { discId: number; codigo: string; nome: string; ch: number }[] = []

  const restantes = new Set<number>(
    cursos
      .filter(
        (c) =>
          !c.curso.nucleoComum &&
          (!mesmoCampus ||
            !base?.curso.campus ||
            c.curso.campus === base.curso.campus ||
            c.curso.campus === 'EaD'),
      )
      .map((c) => c.curso.id),
  )
  const porId = new Map(cursos.map((c) => [c.curso.id, c]))
  const passos: RouteStep[] = []
  let horasAcum = 0

  while (restantes.size) {
    let melhorId = -1
    let melhor: Margem | null = null
    let melhorChave = Number.POSITIVE_INFINITY

    for (const id of restantes) {
      const target = porId.get(id)
      if (!target) continue
      const m = margem(universo, target, pool, poolCh, livreAberto, livreFechado, done, cursosDe, menu, menuHoras, disponiveis)
      const chave = m.horas + m.missing.length * 1e-3 + target.curso.id * 1e-9
      if (chave < melhorChave) {
        melhorChave = chave
        melhor = m
        melhorId = id
      }
    }

    const curso = porId.get(melhorId)
    if (!curso || !melhor) break

    // a cota de DCG do curso-base "materializa" obrigatórias do alvo
    livreAberto -= melhor.livreUsado
    // escolhas do menu de DCG: a disciplina do menu é que foi cursada
    for (const mDid of melhor.menuUsado) {
      const custo = menu.get(mDid) ?? 0
      menu.delete(mDid)
      menuHoras -= custo
      livreFechado = Math.max(0, livreFechado - custo)
      if (!pool.has(mDid)) {
        pool.add(mDid)
        poolCh += custo
        const d = universo.disciplinas.get(mDid)
        dcgEscolhas.push({ discId: mDid, codigo: d?.codigo ?? '', nome: d?.nome ?? '', ch: custo })
      }
    }
    for (const o of melhor.cobertos) {
      if (pool.has(o.discId)) continue
      pool.add(o.discId)
      poolCh += o.ch
      const d = universo.disciplinas.get(o.discId)
      dcgEstrategica.push({ discId: o.discId, codigo: o.codigo, nome: d?.nome ?? o.nome, ch: o.ch })
    }

    for (const o of melhor.missing) {
      if (pool.has(o.discId)) continue
      pool.add(o.discId)
      poolCh += o.ch
    }
    for (const p of melhor.picks) {
      if (pool.has(p)) continue
      pool.add(p)
      poolCh += chDe(universo, p)
    }
    restantes.delete(melhorId)

    horasAcum += melhor.horas
    passos.push({
      ordem: passos.length + 1,
      curso,
      novas: melhor.missing,
      horasPasso: melhor.horas,
      horasAcum,
      semestre: Math.ceil(horasAcum / carga),
    })
  }

  // estatística de compartilhamento (baseada nas obrigatórias, não nas cotas)
  let unicas = 0
  let compartilhadas = 0
  for (const id of pool) {
    if (emQuantos.get(id) === 1) unicas++
    else if ((emQuantos.get(id) ?? 0) > 1) compartilhadas++
  }

  const gargalos: Gargalo[] = [...pool]
    .map((id) => {
      const d = universo.disciplinas.get(id)
      return {
        discId: id,
        codigo: d?.codigo ?? String(id),
        nome: d?.nome ?? '',
        ch: d?.ch ?? 0,
        cursos: emQuantos.get(id) ?? 0,
      }
    })
    .filter((g) => g.cursos > 1)
    .sort((a, b) => b.cursos - a.cursos || a.ch - b.ch)
    .slice(0, 16)

  const totalHoras = horasAcum
  let acum = 0
  let metadeEm = passos.length
  for (let i = 0; i < passos.length; i++) {
    acum += passos[i].horasPasso
    if (acum >= totalHoras / 2) {
      metadeEm = i + 1
      break
    }
  }
  const soma = (arr: RouteStep[]) => arr.reduce((s, p) => s + p.horasPasso, 0)

  return {
    passos,
    cursoIds: passos.map((p) => p.curso.curso.id),
    totalDisc: pool.size,
    totalHoras,
    horasBase,
    semestres: Math.ceil(totalHoras / carga),
    carga,
    gargalos,
    dcgEstrategica,
    dcgEscolhas,
    unicas,
    compartilhadas,
    metadeEm,
    custoPrimeiros20: soma(passos.slice(0, 20)),
    custoUltimos20: soma(passos.slice(-20)),
  }
}

import type { CourseModel, Oferta, Universe } from '../db/types'

/** O que o aluno já cumpriu. */
export interface Done {
  ids: Set<number>
  /** horas de eletivas/DCG já cumpridas sem disciplina identificada (cota fechada) */
  freeHoras: number
  /** horas de cota de DCG ABERTA (aceitam qualquer disciplina não-terminal) */
  dcgHoras: number
  /** existe cota de DCG aberta (qualquer disciplina não-terminal) */
  dcgAberta: boolean
  /** menu de DCG do curso-base: discId -> CH (escolhas possíveis) */
  menu: Map<number, number>
  /** orçamento em horas do menu de DCG (soma das cotas com menu) */
  menuHoras: number
  /** TCC/TCG/estágio/monografia: nunca contam como DCG */
  terminais: Set<number>
  /** CH por disciplina (para o pool de eletivas reaproveitáveis) */
  chOf: Map<number, number>
}

export interface SemesterItem {
  key: string
  discId: number | null
  codigo: string
  nome: string
  ch: number
  sintetico: boolean
  periodo: number
}

export interface Semester {
  indice: number
  ch: number
  itens: SemesterItem[]
}

export interface QuotaPlan {
  descricao: string
  horas: number
  kind: 'eletiva' | 'dcg' | 'livre'
  cobertoPorJaFeito: number
  faltam: number
  residual: boolean
  menuFechado: boolean
  sugestoes: { discId: number; codigo: string; nome: string; ch: number }[]
}

export interface DcgChoice {
  oferta: Oferta
  /** disciplina do menu do curso-base usada como DCG */
  via: number
}

export interface CourseScore {
  target: CourseModel
  extraHoras: number
  extraDisciplinas: number
  freeNeed: number
  freeFilledByDone: number
  fixedMissing: Oferta[]
  fixedCovered: Oferta[]
  /** obrigatórias cobertas por equivalência oficial (não foram cursadas) */
  fixedEquiv: Oferta[]
  /** obrigatórias cobertas por equivalência julgada "parcial" (sinal fraco) */
  fixedEquivParcial: Oferta[]
  /** obrigatórias cobertas pelas horas de DCG/cota aberta do curso de origem */
  fixedDcg: Oferta[]
  /** obrigatórias dispensadas por escolhas do menu de DCG do curso-base */
  fixedMenu: DcgChoice[]
  semestres: number
  schedule: Semester[]
  atividadesHoras: number
  overlapCh: number
  overlapPct: number
  quotas: QuotaPlan[]
  /** pré-requisitos que o aluno ainda não cumpriu e que estão dentro do curso-alvo */
  prereqDeps: Map<number, number[]>
}

export function makeDone(
  universo: Universe,
  base: CourseModel | null,
  concluidoAte: number | null,
  overrides: Map<number, boolean>,
  extras: Set<number>,
): Done {
  const ids = new Set<number>()
  const ch = new Map<number, number>()
  let freeHoras = 0
  let dcgHoras = 0
  let dcgAberta = false
  const menu = new Map<number, number>()
  let menuHoras = 0

  const curricular = base
    ? base.fixed.filter((o) => o.periodo >= 99 || concluidoAte === null || o.periodo <= concluidoAte)
    : []

  for (const o of curricular) {
    if (overrides.get(o.discId) === false) continue
    ids.add(o.discId)
    ch.set(o.discId, universo.disciplinas.get(o.discId)?.ch ?? o.ch)
  }

  for (const [id, marcado] of overrides) {
    if (!marcado || ids.has(id)) continue
    ids.add(id)
    ch.set(id, universo.disciplinas.get(id)?.ch ?? 0)
  }

  for (const id of extras) {
    if (ids.has(id)) continue
    ids.add(id)
    ch.set(id, universo.disciplinas.get(id)?.ch ?? 0)
  }

  if (base) {
    // cotas de eletiva/DCG do curso-base contam como cumpridas no todo ou na
    // fração do curso já concluída
    const fracao = concluidoAte === null || base.semestres <= 0
      ? 1
      : Math.min(1, Math.max(0, concluidoAte / base.semestres))
    for (const q of base.quotas) {
      if (q.kind === 'atividade') continue
      const h = Math.round(q.horas * fracao)
      freeHoras += h
      if (q.residual) continue
      // DCG com menu fechado não é "hora livre": só serve para preencher a
      // própria cota do curso, nunca para cobrir obrigatória de outro curso.
      if (q.kind === 'dcg' && q.menuFechado && q.candidatos.length) {
        menuHoras += h
        for (const id of q.candidatos) {
          if (!menu.has(id)) menu.set(id, universo.disciplinas.get(id)?.ch ?? 0)
        }
      } else if (q.kind === 'dcg' || q.kind === 'livre') {
        dcgHoras += h
        dcgAberta = true
      }
    }
  }

  return { ids, freeHoras, dcgHoras, dcgAberta, menu, menuHoras, terminais: universo.terminais, chOf: ch }
}

/** Pré-requisito efetivo (só disciplinas; período/CH ficam como sinal fraco). */
function prereqDiscs(target: CourseModel, discId: number): number[] {
  const blocos = target.prereqs.get(discId)
  if (!blocos || !blocos.length) return []
  const all = new Set<number>()
  for (const b of blocos) {
    for (const it of b.itens) {
      if ((it.tipo === 1 || it.tipo === 2) && it.discId) all.add(it.discId)
    }
  }
  return [...all]
}

/**
 * A disciplina pode ser cursada agora? OR entre blocos, AND dentro do bloco.
 * Itens de período/CH são tratados como sinal fraco (ignorados).
 */
export function prereqSatisfied(target: CourseModel, discId: number, disponiveis: Set<number>): boolean {
  const blocos = target.prereqs.get(discId)
  if (!blocos || !blocos.length) return true
  return blocos.some((bloco) =>
    bloco.itens.every((it) => {
      if (it.tipo !== 1 && it.tipo !== 2) return true
      if (!it.discId) return true
      return disponiveis.has(it.discId)
    }),
  )
}

export function scoreCourse(
  target: CourseModel,
  done: Done,
  opcoes?: { agenda?: boolean; leve?: boolean; estrategica?: boolean },
): CourseScore {
  const agenda = opcoes?.agenda ?? true
  const leve = opcoes?.leve ?? false
  const estrategica = opcoes?.estrategica ?? true
  const fixedCovered: Oferta[] = []
  const fixedEquiv: Oferta[] = []
  const fixedEquivParcial: Oferta[] = []
  const fixedDcg: Oferta[] = []
  const fixedMissing: Oferta[] = []

  // equivalência efetiva (oficial + julgada): "parcial" conta como cobertura,
  // mas fica marcada na UI como sinal mais fraco.
  const equivStatus = new Map<number, 'equivalente' | 'parcial'>()
  for (const [discId, itens] of target.equivals) {
    if (done.ids.has(discId)) continue
    let full = false
    let parcial = false
    for (const it of itens) {
      if (it.discId === null || !done.ids.has(it.discId)) continue
      if (it.veredito === 'parcial') parcial = true
      else full = true
    }
    if (full) equivStatus.set(discId, 'equivalente')
    else if (parcial) equivStatus.set(discId, 'parcial')
  }

  for (const o of target.fixed) {
    if (done.ids.has(o.discId)) fixedCovered.push(o)
    else if (equivStatus.get(o.discId) === 'equivalente') fixedEquiv.push(o)
    else if (equivStatus.get(o.discId) === 'parcial') fixedEquivParcial.push(o)
    else fixedMissing.push(o)
  }

  // DCG estratégica (cota aberta): horas livres do curso-base cobrem
  // obrigatórias do alvo. TCC/estágio/monografia nunca entram.
  const elegivelDcg = (id: number) => !done.terminais.has(id) && done.dcgAberta
  let livre = estrategica ? Math.min(done.dcgHoras, done.freeHoras) : 0
  let livreUsado = 0
  if (livre > 0 && fixedMissing.length) {
    const disponiveis = new Set(done.ids)
    let restantes = [...fixedMissing].sort((a, b) => b.ch - a.ch)
    let cobrou = true
    while (cobrou && restantes.length && livre > 0) {
      cobrou = false
      const sobraDestaRodada: Oferta[] = []
      for (const o of restantes) {
        if (o.ch <= livre && elegivelDcg(o.discId) && prereqSatisfied(target, o.discId, disponiveis)) {
          livre -= o.ch
          livreUsado += o.ch
          fixedDcg.push(o)
          disponiveis.add(o.discId)
          cobrou = true
        } else {
          sobraDestaRodada.push(o)
        }
      }
      restantes = sobraDestaRodada
    }
    fixedMissing.length = 0
    fixedMissing.push(...restantes)
  }

  // DCG estratégica (menu): "cursar" itens do menu do curso-base que dispensam
  // uma obrigatória do alvo (a própria disciplina ou uma equivalente oficial).
  // O orçamento é consumido, então cada escolha vale uma vez só.
  const fixedMenu: DcgChoice[] = []
  let menuUsado = 0
  if (estrategica && done.menuHoras > 0 && done.menu.size > 0 && fixedMissing.length) {
    let orcamento = done.menuHoras
    const sobraMenu: Oferta[] = []
    for (const o of [...fixedMissing].sort((a, b) => b.ch - a.ch)) {
      const substitutos = new Set<number>([o.discId])
      for (const eq of target.equivals.get(o.discId) ?? []) {
        if (eq.discId !== null) substitutos.add(eq.discId)
      }
      let escolha = -1
      let custo = Number.POSITIVE_INFINITY
      for (const [m, ch] of done.menu) {
        if (!substitutos.has(m) || ch > orcamento) continue
        if (ch < custo) {
          escolha = m
          custo = ch
        }
      }
      if (escolha < 0) {
        sobraMenu.push(o)
        continue
      }
      orcamento -= custo
      menuUsado += custo
      fixedMenu.push({ oferta: o, via: escolha })
    }
    fixedMissing.length = 0
    fixedMissing.push(...sobraMenu)
  }

  let surplus = done.freeHoras - livreUsado - menuUsado
  for (const [id, horas] of done.chOf) {
    if (target.fixedIds.has(id)) continue
    surplus += horas
  }

  const quotas: QuotaPlan[] = []
  let freeNeed = 0
  let freeFilledByDone = 0
  let atividadesHoras = 0

  for (const q of target.quotas) {
    if (q.kind === 'atividade') {
      atividadesHoras += q.horas
      continue
    }

    let coberto = 0
    const menuFechado = q.kind === 'eletiva' || (q.kind === 'dcg' && q.menuFechado)
    if (menuFechado) {
      // menu fechado: só vale disciplina que está na lista do núcleo/menu de DCG
      for (const cand of q.candidatos) {
        if (coberto >= q.horas) break
        if (!done.ids.has(cand)) continue
        const ch = done.chOf.get(cand) ?? 0
        coberto += ch
        surplus = Math.max(0, surplus - ch)
      }
      coberto = Math.min(coberto, q.horas)
    } else {
      // DCG aberta / cota livre: qualquer disciplina não-terminal conta
      coberto = Math.min(q.horas, surplus)
      surplus -= coberto
    }

    freeFilledByDone += coberto
    const faltam = q.horas - coberto

    const sugestoes: QuotaPlan['sugestoes'] = []
    if (!leve && faltam > 0 && q.candidatos.length) {
      let restante = faltam
      for (const cand of q.candidatos) {
        if (restante <= 0) break
        if (done.ids.has(cand)) continue
        const d = target.byDisc.get(cand)
        if (!d) continue
        sugestoes.push({ discId: cand, codigo: d.codigo, nome: d.nome, ch: d.ch })
        restante -= d.ch
      }
    }

    quotas.push({
      descricao: q.descricao,
      horas: q.horas,
      kind: q.kind === 'livre' ? 'livre' : q.kind === 'dcg' ? 'dcg' : 'eletiva',
      cobertoPorJaFeito: coberto,
      faltam,
      residual: q.residual,
      menuFechado: q.menuFechado,
      sugestoes,
    })
    freeNeed += faltam
  }

  const missingCh = fixedMissing.reduce((s, o) => s + o.ch, 0)
  const extraHoras = missingCh + freeNeed
  const extraDisciplinas = fixedMissing.length + Math.ceil(freeNeed / 60)

  const prereqDeps = new Map<number, number[]>()
  if (!leve) {
    for (const o of fixedMissing) {
      const deps = prereqDiscs(target, o.discId).filter((d) => !done.ids.has(d))
      if (deps.length) prereqDeps.set(o.discId, deps)
    }
  }

  const itens: SemesterItem[] = fixedMissing.map((o) => ({
    key: `d${o.discId}`,
    discId: o.discId,
    codigo: o.codigo,
    nome: o.nome,
    ch: o.ch,
    sintetico: false,
    periodo: o.periodo,
  }))

  if (freeNeed > 0) {
    let restante = freeNeed
    let i = 0
    while (restante > 0 && i < 40) {
      const horas = Math.min(60, restante)
      itens.push({
        key: `e${i}`,
        discId: null,
        codigo: 'eletiva',
        nome: horas >= 60 ? 'Eletiva/DCG a escolher' : `Eletiva/DCG a escolher (${horas}h)`,
        ch: horas,
        sintetico: true,
        periodo: 99,
      })
      restante -= horas
      i++
    }
  }

  const schedule = agenda && !leve ? planSemesters(target, itens, done) : []

  const overlapCh = [
    ...fixedCovered,
    ...fixedEquiv,
    ...fixedEquivParcial,
    ...fixedDcg,
    ...fixedMenu.map((c) => c.oferta),
  ].reduce((s, o) => s + o.ch, 0)

  return {
    target,
    extraHoras,
    extraDisciplinas,
    freeNeed,
    freeFilledByDone,
    fixedMissing,
    fixedCovered,
    fixedEquiv,
    fixedEquivParcial,
    fixedDcg,
    fixedMenu,
    semestres: agenda && !leve ? schedule.length : Math.ceil(extraHoras / Math.max(1, target.cargaSemestre)),
    schedule,
    atividadesHoras,
    overlapCh,
    overlapPct: target.fixedHoras > 0 ? overlapCh / target.fixedHoras : 0,
    quotas,
    prereqDeps,
  }
}

/**
 * Aloca as disciplinas faltantes em semestres respeitando pré-requisitos,
 * período mínimo ("vencido"), CH mínima por estrutura e o limite de CH por
 * semestre do curso-alvo.
 */
export function planSemesters(target: CourseModel, itens: SemesterItem[], done: Done): Semester[] {
  if (!itens.length) return []
  const cap = Math.max(120, target.cargaSemestre || 480)
  const memo = new Map<number, number>()
  const visiting = new Set<number>()
  const missing = new Set(itens.filter((i) => i.discId !== null).map((i) => i.discId as number))

  // período mínimo por disciplina (pode variar entre ofertas: pega o maior)
  const periodoMinimo = new Map<number, number>()
  for (const o of target.ofertas) {
    const pm = o.periodoMinimo ?? 0
    if (pm > 0) periodoMinimo.set(o.discId, Math.max(periodoMinimo.get(o.discId) ?? 0, pm))
  }

  // CH acumulada por período das obrigatórias do curso, por estrutura e no total
  const chPorEstrutura = new Map<number | null, { periodo: number; acum: number }[]>()
  const bruto = new Map<number | null, Map<number, number>>()
  const soma = (chave: number | null, periodo: number, ch: number) => {
    const porPeriodo = bruto.get(chave) ?? new Map<number, number>()
    porPeriodo.set(periodo, (porPeriodo.get(periodo) ?? 0) + ch)
    bruto.set(chave, porPeriodo)
  }
  for (const o of target.fixed) {
    if (o.periodo >= 99) continue
    soma(o.estruturaId, o.periodo, o.ch)
    soma(null, o.periodo, o.ch)
  }
  for (const [chave, porPeriodo] of bruto) {
    const periodos = [...porPeriodo.entries()].sort((a, b) => a[0] - b[0])
    let acum = 0
    chPorEstrutura.set(
      chave,
      periodos.map(([periodo, ch]) => {
        acum += ch
        return { periodo, acum }
      }),
    )
  }

  // CH que o aluno já tem em cada estrutura do curso-alvo
  const chFeita = new Map<number | null, number>()
  const vistosEstrutura = new Map<number | null, Set<number>>()
  const vistosTotal = new Set<number>()
  for (const o of target.ofertas) {
    if (!done.ids.has(o.discId)) continue
    const set = vistosEstrutura.get(o.estruturaId) ?? new Set<number>()
    if (!set.has(o.discId)) {
      set.add(o.discId)
      chFeita.set(o.estruturaId, (chFeita.get(o.estruturaId) ?? 0) + o.ch)
      vistosEstrutura.set(o.estruturaId, set)
    }
    if (!vistosTotal.has(o.discId)) {
      vistosTotal.add(o.discId)
      chFeita.set(null, (chFeita.get(null) ?? 0) + o.ch)
    }
  }

  const memoRestricao = new Map<number, number>()
  /** período mais cedo possível só pelas condições estáticas (tipo 5 e tipo 3) */
  const restricaoEstatica = (discId: number): number => {
    const cache = memoRestricao.get(discId)
    if (cache !== undefined) return cache
    let resultado = 1

    const pm = periodoMinimo.get(discId) ?? 0
    if (pm > 0) resultado = Math.max(resultado, pm + 1)

    const exigencias = target.requisitoCh.get(discId)
    if (exigencias?.length) {
      const proprio = target.byDisc.get(discId)?.periodo ?? 99
      const piso = proprio > 0 && proprio < 99 ? proprio : 0
      for (const req of exigencias) {
        const ja = chFeita.get(req.estruturaId) ?? 0
        if (ja >= req.horas) continue
        const falta = req.horas - ja
        const curva = chPorEstrutura.get(req.estruturaId) ?? []
        const ponto = curva.find((p) => p.acum >= falta)
        if (ponto) {
          resultado = Math.max(resultado, ponto.periodo + 1)
        } else {
          // sem timeline da estrutura: respeita ao menos o período ideal da
          // própria disciplina (senão a exigência sumiria da agenda)
          const ultimo = curva.length ? curva[curva.length - 1].periodo : 0
          resultado = Math.max(resultado, ultimo, piso)
        }
      }
    }

    memoRestricao.set(discId, resultado)
    return resultado
  }

  const earliest = (discId: number): number => {
    const cached = memo.get(discId)
    if (cached !== undefined) return cached
    if (visiting.has(discId)) return 1
    visiting.add(discId)
    const blocos = target.prereqs.get(discId)
    let resultado = restricaoEstatica(discId)
    if (blocos && blocos.length) {
      let melhor = Number.POSITIVE_INFINITY
      for (const bloco of blocos) {
        let pronto = 0
        for (const it of bloco.itens) {
          if (it.tipo !== 1 && it.tipo !== 2) continue
          if (!it.discId) continue
          if (done.ids.has(it.discId)) continue
          if (missing.has(it.discId)) pronto = Math.max(pronto, earliest(it.discId))
          // pré-requisito fora do currículo-alvo: assume cumprido
        }
        melhor = Math.min(melhor, pronto + 1)
      }
      if (Number.isFinite(melhor)) resultado = Math.max(resultado, melhor)
    }
    visiting.delete(discId)
    memo.set(discId, resultado)
    return resultado
  }

  const restantes = [...itens]
  const semesters: Semester[] = []

  while (restantes.length && semesters.length < 48) {
    const indice = semesters.length + 1
    const disponiveis = restantes
      .map((it) => ({ it, inicio: it.discId === null ? 1 : earliest(it.discId) }))
      .filter((x) => x.inicio <= indice)
      // disciplinas reais primeiro; as eletivas sintéticas ("a escolher") vão
      // preenchendo as sobras no fim, não os primeiros semestres
      .sort(
        (a, b) =>
          a.inicio - b.inicio ||
          Number(a.it.sintetico) - Number(b.it.sintetico) ||
          b.it.ch - a.it.ch,
      )

    if (!disponiveis.length) {
      // ciclo de pré-requisitos ou dado inconsistente: joga o resto num bloco
      const bloco: Semester = { indice, ch: 0, itens: [] }
      for (const it of restantes.splice(0)) {
        bloco.itens.push(it)
        bloco.ch += it.ch
      }
      semesters.push(bloco)
      break
    }

    const bloco: Semester = { indice, ch: 0, itens: [] }
    for (const { it } of disponiveis) {
      if (bloco.ch > 0 && bloco.ch + it.ch > cap) continue
      bloco.itens.push(it)
      bloco.ch += it.ch
      restantes.splice(restantes.indexOf(it), 1)
    }
    semesters.push(bloco)
  }

  return semesters
}

export function rankCourses(
  universo: Universe,
  done: Done,
  opcoes?: { agenda?: boolean; estrategica?: boolean },
): CourseScore[] {
  return universo.cursos
    .map((c) => scoreCourse(c, done, { agenda: opcoes?.agenda ?? true, estrategica: opcoes?.estrategica }))
    .sort((a, b) => a.semestres - b.semestres || a.extraHoras - b.extraHoras || a.extraDisciplinas - b.extraDisciplinas)
}

/** Versão sem agenda, para a matriz 148×148. */
export function scoreFast(target: CourseModel, done: Done): { semestres: number; extraHoras: number; extraDisciplinas: number } {
  const s = scoreCourse(target, done, { agenda: false, leve: true })
  return { semestres: s.semestres, extraHoras: s.extraHoras, extraDisciplinas: s.extraDisciplinas }
}

/** Matriz base × alvo com o custo de fechar cada curso partindo de cada curso. */
export function buildMatrix(universo: Universe): { cursos: CourseModel[]; semestres: number[][] } {
  const cursos = universo.cursos.filter((c) => !c.curso.nucleoComum)
  const semestres: number[][] = []
  for (const base of cursos) {
    const done = makeDone(universo, base, null, new Map(), new Set())
    const linha: number[] = []
    for (const alvo of cursos) {
      if (alvo.curso.id === base.curso.id) {
        linha.push(0)
        continue
      }
      linha.push(scoreFast(alvo, done).semestres)
    }
    semestres.push(linha)
  }
  return { cursos, semestres }
}

export interface Insight {
  discId: number
  codigo: string
  nome: string
  ch: number
  cursos: number[]
}

/** Disciplinas que mais destravam cursos que o aluno ainda não tem. */
export function leverInsights(universo: Universe, done: Done, limite = 25): Insight[] {
  const out: Insight[] = []
  for (const [discId, cursos] of universo.cursosByDisc) {
    if (done.ids.has(discId)) continue
    if (cursos.length < 3) continue
    const d = universo.disciplinas.get(discId)
    if (!d) continue
    out.push({ discId, codigo: d.codigo, nome: d.nome, ch: d.ch, cursos })
  }
  out.sort((a, b) => b.cursos.length - a.cursos.length || a.ch - b.ch)
  return out.slice(0, limite)
}

/** Quantos cursos ficam a 0 / 1 / 2 disciplinas de distância. */
export function distanciaResumo(scores: CourseScore[]) {
  let zero = 0
  let uma = 0
  let duas = 0
  for (const s of scores) {
    if (s.extraDisciplinas === 0) zero++
    else if (s.extraDisciplinas === 1) uma++
    else if (s.extraDisciplinas === 2) duas++
  }
  return { zero, uma, duas }
}

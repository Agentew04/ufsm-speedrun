import type { ElementDefinition } from 'cytoscape'
import type { CourseModel, Universe } from '../db/types'
import type { CourseScore, Done } from './plan'

export interface NetworkOpts {
  base: CourseModel
  alvos: CourseModel[]
  done: Done
  limite?: number
  minCursos?: number
}

export interface NetworkResult {
  elements: ElementDefinition[]
  discTotal: number
  discMostrados: number
}

/**
 * Grafo bipartido curso ↔ disciplina, só com as disciplinas que aparecem em
 * mais de um dos cursos escolhidos. Os "hubs" são o que se reaproveita.
 */
export function buildNetwork(
  universe: Universe,
  { base, alvos, done, limite = 36, minCursos = 3 }: NetworkOpts,
): NetworkResult {
  const selecionados = [base, ...alvos]
  const cursosPorDisc = new Map<number, Set<number>>()

  for (const curso of selecionados) {
    for (const o of curso.fixed) {
      const set = cursosPorDisc.get(o.discId) ?? new Set<number>()
      set.add(curso.curso.id)
      cursosPorDisc.set(o.discId, set)
    }
    for (const q of curso.quotas) {
      if (q.kind === 'atividade') continue
      for (const cand of q.candidatos) {
        const set = cursosPorDisc.get(cand) ?? new Set<number>()
        set.add(curso.curso.id)
        cursosPorDisc.set(cand, set)
      }
    }
  }

  const elements: ElementDefinition[] = []

  for (let i = 0; i < selecionados.length; i++) {
    const curso = selecionados[i]
    const nome = curso.curso.nome.replace(/^(Bacharelado|Licenciatura) em /, '')
    elements.push({
      data: {
        id: `c${curso.curso.id}`,
        label: nome.length > 38 ? `${nome.slice(0, 36)}…` : nome,
        title: `${nome}\n${curso.curso.campus ?? ''} · ${curso.curso.modalidade ?? ''}`,
        kind: 'curso',
        root: curso.curso.id === base.curso.id,
        campus: curso.curso.campus ?? '',
        size: 158,
      },
      position: { x: 30, y: 40 + i * 58 },
    })
  }

  const compartilhadas = [...cursosPorDisc.entries()]
    .filter(([, cursos]) => cursos.size >= minCursos)
    .sort((a, b) => b[1].size - a[1].size)

  const discos = compartilhadas.slice(0, limite)

  const linhas = 12
  for (let idx = 0; idx < discos.length; idx++) {
    const [discId, cursos] = discos[idx]
    const d = universe.disciplinas.get(discId)
    if (!d) continue
    const coluna = Math.floor(idx / linhas)
    elements.push({
      data: {
        id: `d${discId}`,
        label: d.codigo,
        title: d.nome,
        kind: 'disc',
        ch: d.ch,
        done: done.ids.has(discId),
        cursos: cursos.size,
        size: 9 + Math.min(10, cursos.size * 2.5),
      },
      position: { x: 400 + coluna * 260, y: 24 + (idx % linhas) * 30 },
    })
    for (const cursoId of cursos) {
      elements.push({
        data: {
          id: `cd${cursoId}-${discId}`,
          source: `c${cursoId}`,
          target: `d${discId}`,
        },
      })
    }
  }

  return { elements, discTotal: compartilhadas.length, discMostrados: discos.length }
}

export interface PrereqNode {
  id: string
  label: string
  title: string
  ch: number
  periodo: number
  done: boolean
  tipo: number
  x: number
  y: number
  bloqueia: number
}

/** Grafo de pré-requisitos do curso-alvo, com colunas por período. */
export function buildPrereqGraph(
  universe: Universe,
  target: CourseModel,
  done: Done,
  score: CourseScore,
): { nodes: PrereqNode[]; edges: ElementDefinition[]; colLabels: ElementDefinition[] } {
  const nodes: PrereqNode[] = []
  const colunas = new Map<number, number>()
  const usadas = new Set<number>()
  const presentes = new Set<number>(target.fixed.map((o) => o.discId))
  const edges: ElementDefinition[] = []
  const arestas = new Set<string>()
  const espaco = 200
  const posCol = (col: number) => (col >= 99 ? 14 : col) * espaco

  const ordenadas = [...target.fixed].sort(
    (a, b) => a.periodo - b.periodo || a.codigo.localeCompare(b.codigo),
  )

  const bloqueia = new Map<number, number>()
  for (const [discId, deps] of score.prereqDeps) {
    const base = target.byDisc.get(discId)
    if (!base) continue
    for (const dep of deps) bloqueia.set(dep, (bloqueia.get(dep) ?? 0) + 1)
  }

  for (const o of ordenadas) {
    const col = o.periodo >= 99 ? 99 : o.periodo
    const idx = colunas.get(col) ?? 0
    colunas.set(col, idx + 1)
    usadas.add(col)
    const d = universe.disciplinas.get(o.discId)
    nodes.push({
      id: `d${o.discId}`,
      label: o.codigo,
      title: `${o.codigo} — ${o.nome}\n${d?.ch ?? o.ch} h · ${o.periodo >= 99 ? 'qualquer período' : `${o.periodo}º período`}`,
      ch: o.ch,
      periodo: col,
      done: done.ids.has(o.discId),
      tipo: o.tipoItem,
      x: posCol(col),
      y: idx * 62,
      bloqueia: bloqueia.get(o.discId) ?? 0,
    })
  }

  const colLabels: ElementDefinition[] = [...usadas]
    .sort((a, b) => a - b)
    .map((col) => ({
      data: {
        id: `col${col}`,
        label: col >= 99 ? 'qualquer' : `${col}º`,
        kind: 'col',
      },
      position: { x: posCol(col), y: -52 },
      selectable: false,
      grabbable: false,
    }))

  for (const o of target.fixed) {
    const blocos = target.prereqs.get(o.discId)
    if (!blocos) continue
    for (const bloco of blocos) {
      for (const it of bloco.itens) {
        if (it.tipo !== 1 && it.tipo !== 2) continue
        if (!it.discId || !presentes.has(it.discId)) continue
        const key = `${it.discId}->${o.discId}`
        if (arestas.has(key)) continue
        arestas.add(key)
        edges.push({
          data: {
            id: `p${key}`,
            source: `d${it.discId}`,
            target: `d${o.discId}`,
            kind: 'prereq',
          },
        })
      }
    }
  }

  for (const o of target.fixed) {
    const equivals = target.equivals.get(o.discId)
    if (!equivals) continue
    for (const eq of equivals) {
      if (!eq.discId || !presentes.has(eq.discId)) continue
      const key = `${eq.discId}~${o.discId}`
      if (arestas.has(key)) continue
      arestas.add(key)
      edges.push({
        data: {
          id: `e${key}`,
          source: `d${eq.discId}`,
          target: `d${o.discId}`,
          kind: 'equiv',
        },
      })
    }
  }

  return { nodes, edges, colLabels }
}

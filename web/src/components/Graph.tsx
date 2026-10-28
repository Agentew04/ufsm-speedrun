import { useEffect, useMemo, useRef, useState } from 'react'
import cytoscape, {
  type Core,
  type ElementDefinition,
  type LayoutOptions,
  type StylesheetStyle,
} from 'cytoscape'

const ESTILO: StylesheetStyle[] = [
  {
    selector: 'node[kind="disc"]',
    style: {
      label: 'data(label)',
      'font-family': 'ui-monospace, monospace',
      'font-size': 10,
      color: '#c3d1e2',
      'text-valign': 'bottom',
      'text-margin-y': 4,
      width: 'data(size)',
      height: 'data(size)',
      'background-color': '#22334a',
      'border-width': 1,
      'border-color': '#2f4763',
    },
  },
  {
    selector: 'node[kind="disc"].done',
    style: { 'background-color': '#b7f36b', 'border-color': '#d6ffa0' },
  },
  {
    selector: 'node[kind="disc"].novo',
    style: { 'background-color': '#ffc35c', 'border-color': '#ffd88f' },
  },
  {
    selector: 'node[kind="curso"]',
    style: {
      label: 'data(label)',
      'font-family': 'system-ui, sans-serif',
      'font-size': 10,
      'font-weight': 600,
      color: '#e8f1fb',
      width: 'data(size)',
      height: 34,
      'text-valign': 'center',
      'text-halign': 'center',
      'text-wrap': 'wrap',
      'text-max-width': '148px',
      shape: 'round-rectangle',
      'background-color': '#16212f',
      'border-width': 1.2,
      'border-color': '#3a5373',
      padding: '8px',
    },
  },
  {
    selector: 'node[kind="curso"].root',
    style: { 'background-color': '#1b2a19', 'border-color': '#b7f36b', 'border-width': 2 },
  },
  {
    selector: 'node[kind="col"]',
    style: {
      label: 'data(label)',
      'font-family': 'ui-monospace, monospace',
      'font-size': 10,
      color: '#5b6a7f',
      width: 1,
      height: 1,
      'background-opacity': 0,
      'border-width': 0,
      'text-valign': 'center',
      'text-halign': 'center',
    },
  },
  {
    selector: 'edge',
    style: {
      width: 0.9,
      'line-color': '#2a394d',
      'curve-style': 'bezier',
      'target-arrow-shape': 'none',
      opacity: 0.5,
    },
  },
  {
    selector: 'edge[kind="prereq"]',
    style: {
      width: 1.4,
      'line-color': '#5db6d6',
      'target-arrow-shape': 'triangle',
      'target-arrow-color': '#5db6d6',
      'arrow-scale': 0.7,
      opacity: 0.9,
    },
  },
  {
    selector: 'edge[kind="equiv"]',
    style: { width: 1.2, 'line-color': '#b79bff', 'line-style': 'dashed', opacity: 0.85 },
  },
  { selector: 'node.dim', style: { opacity: 0.12 } },
  { selector: 'edge.dim', style: { opacity: 0.06 } },
  { selector: 'node.hl', style: { 'border-width': 2.5, 'border-color': '#ffffff' } },
]

const LAYOUT_PRESET: LayoutOptions = { name: 'preset', fit: true, padding: 30 }
const LAYOUT_REDE: LayoutOptions = {
  name: 'preset',
  fit: true,
  padding: 26,
}

function Graph({
  elements,
  height,
  layout,
  onReady,
}: {
  elements: ElementDefinition[]
  height: number
  layout: LayoutOptions
  onReady?: (cy: Core) => void
}) {
  const container = useRef<HTMLDivElement>(null)
  const [hover, setHover] = useState<string | null>(null)

  useEffect(() => {
    if (!container.current) return
    const cy: Core = cytoscape({
      container: container.current,
      elements,
      style: ESTILO,
      layout,
      wheelSensitivity: 0.2,
      minZoom: 0.12,
      maxZoom: 3,
    })
    onReady?.(cy)
    cy.on('mouseover', 'node', (evt) => {
      const node = evt.target
      cy.elements().addClass('dim')
      node.closedNeighborhood().removeClass('dim')
      node.addClass('hl')
      setHover((node.data('title') as string) || (node.data('label') as string))
    })
    cy.on('mouseout', 'node', () => {
      cy.elements().removeClass('dim hl')
      setHover(null)
    })

    const ro = new ResizeObserver(() => cy.resize())
    ro.observe(container.current)

    return () => {
      ro.disconnect()
      cy.destroy()
    }
  }, [elements, layout, onReady])

  return (
    <div className="graph-shell" style={{ height }}>
      <div className="graph-canvas" ref={container} />
      {hover && <div className="graph-hover mono">{hover}</div>}
    </div>
  )
}

export function PrereqGraph({
  elements,
  temPrereq,
  temEquiv,
  altura = 520,
}: {
  elements: ElementDefinition[]
  temPrereq: number
  temEquiv: number
  altura?: number
}) {
  const [filtro, setFiltro] = useState<'tudo' | 'novas'>('tudo')
  const [cy, setCy] = useState<Core | null>(null)

  const filtrados = useMemo(() => {
    if (filtro === 'tudo') return elements
    const visiveis = new Set(
      elements
        .filter((e) => e.data.kind === 'disc' && !String(e.classes ?? '').includes('done'))
        .map((e) => String(e.data.id)),
    )
    return elements.filter((e) => {
      if (e.data.kind === 'disc') return visiveis.has(String(e.data.id))
      return visiveis.has(String(e.data.source)) && visiveis.has(String(e.data.target))
    })
  }, [elements, filtro])

  return (
    <div className="graph-block">
      <div className="graph-toolbar">
        <span className="eyebrow">grafo do currículo</span>
        <div className="seg">
          <button type="button" className={filtro === 'tudo' ? 'is-on' : ''} onClick={() => setFiltro('tudo')}>
            tudo
          </button>
          <button type="button" className={filtro === 'novas' ? 'is-on' : ''} onClick={() => setFiltro('novas')}>
            só o que falta
          </button>
        </div>
        <div className="seg">
          <button type="button" onClick={() => cy?.fit(undefined, 30)} title="enquadrar tudo">
            caber
          </button>
          <button type="button" onClick={() => cy?.zoom(1)} title="zoom 100%">
            100%
          </button>
        </div>
        <span className="tiny dim">
          {temPrereq} pré-requisitos · {temEquiv} equivalências
          {temPrereq === 0 && ' — a coleta ainda não chegou neste curso'}
        </span>
      </div>
      <Graph elements={filtrados} layout={LAYOUT_PRESET} height={altura} onReady={setCy} />
      <div className="legend">
        <span><i className="dot done" /> já cumprida</span>
        <span><i className="dot new" /> nova</span>
        <span><i className="line solid" /> pré-requisito</span>
        <span><i className="line dashed" /> equivalência</span>
        <span className="dim">colunas = período ideal</span>
      </div>
    </div>
  )
}

export function NetworkGraph({
  elements,
  legenda,
  semCompartilhadas,
}: {
  elements: ElementDefinition[]
  legenda: string
  semCompartilhadas: boolean
}) {
  return (
    <div className="graph-block">
      <div className="graph-toolbar">
        <span className="eyebrow">rede de reaproveitamento</span>
        <span className="tiny dim">{legenda}</span>
      </div>
      {semCompartilhadas ? (
        <div className="graph-vazio">
          Nenhuma disciplina em comum entre esses cursos — os códigos de disciplina mudam quando o
          currículo é reformado. Tente outro conjunto de cursos-alvo ou veja o grafo de
          pré-requisitos na aba Curso.
        </div>
      ) : (
        <Graph elements={elements} layout={LAYOUT_REDE} height={560} />
      )}
      <div className="legend">
        <span><i className="dot done" /> você já tem</span>
        <span><i className="dot other" /> compartilhada</span>
        <span><i className="line net" /> curso exige/lista</span>
        <span className="dim">arraste os nós · role para dar zoom</span>
      </div>
    </div>
  )
}

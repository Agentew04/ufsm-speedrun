import { useEffect, useRef, useState } from 'react'
import type { Universe } from '../db/types'
import { buildMatrix } from '../lib/plan'
import { norm } from '../lib/format'

interface Props {
  universo: Universe
  baseId: number | null
  onPick: (baseId: number, targetId: number) => void
}

const CORES = ['#b7f36b', '#d7ea63', '#ffc35c', '#ff9a5c', '#ff6f6f', '#b4455e', '#3a1f33']

function cor(sem: number): string {
  if (sem <= 0) return CORES[0]
  if (sem === 1) return CORES[1]
  if (sem === 2) return CORES[2]
  if (sem === 3) return CORES[3]
  if (sem === 4) return CORES[4]
  if (sem <= 6) return CORES[5]
  return CORES[6]
}

export function Matrix({ universo, baseId, onPick }: Props) {
  const [dados, setDados] = useState<{ cursos: typeof universo.cursos; semestres: number[][] } | null>(null)
  const [hover, setHover] = useState<{ i: number; j: number } | null>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)

  const celula = 6
  const n = dados?.cursos.length ?? universo.cursos.length

  useEffect(() => {
    if (dados) return
    const t = setTimeout(() => setDados(buildMatrix(universo)), 40)
    return () => clearTimeout(t)
  }, [dados, universo])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || !dados) return
    const dpr = Math.min(2, window.devicePixelRatio || 1)
    const size = n * celula
    canvas.width = size * dpr
    canvas.height = size * dpr
    canvas.style.width = `${size}px`
    canvas.style.height = `${size}px`
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.scale(dpr, dpr)
    ctx.clearRect(0, 0, size, size)
    for (let i = 0; i < n; i++) {
      for (let j = 0; j < n; j++) {
        ctx.fillStyle = i === j ? '#1d2b3c' : cor(dados.semestres[i][j])
        ctx.globalAlpha = i === j ? 0.5 : 0.92
        ctx.fillRect(j * celula, i * celula, celula - 1, celula - 1)
      }
    }
    ctx.globalAlpha = 1

    if (baseId) {
      const idx = dados.cursos.findIndex((c) => c.curso.id === baseId)
      if (idx >= 0) {
        ctx.strokeStyle = '#ffffff'
        ctx.lineWidth = 1
        ctx.strokeRect(0.5, idx * celula + 0.5, size - 1, celula - 1)
      }
    }
    if (hover) {
      ctx.strokeStyle = '#ffffff'
      ctx.lineWidth = 1.5
      ctx.strokeRect(hover.j * celula + 0.5, hover.i * celula + 0.5, celula - 1, celula - 1)
      ctx.strokeRect(hover.i * celula + 0.5, hover.j * celula + 0.5, celula - 1, celula - 1)
    }
  }, [dados, baseId, hover, n])

  const nomes = dados ? dados.cursos.map((c) => c.curso.nome) : []
  const idxBusca = (texto: string) => {
    if (!dados) return -1
    const t = norm(texto)
    return dados.cursos.findIndex((c) => norm(c.curso.nome).includes(t))
  }

  return (
    <div className="matrix-view">
      <div className="matrix-head">
        <div>
          <span className="eyebrow">mapa completo</span>
          <h2>De qualquer curso para qualquer curso</h2>
          <p className="hint">
            Cada célula é o custo (em semestres extras) de fechar o curso da coluna partindo do
            curso da linha, assumindo o curso da linha concluído. Clique para explorar o par.
          </p>
        </div>
        <div className="matrix-legend">
          {['0', '1', '2', '3', '4', '5–6', '7+'].map((label, i) => (
            <span key={label}>
              <i style={{ background: CORES[i] }} />
              {label}
            </span>
          ))}
        </div>
      </div>

      {!dados ? (
        <div className="matrix-loading">
          <div className="spinner" />
          calculando {n * n} rotas…
        </div>
      ) : (
        <div className="matrix-body">
          <div className="matrix-canvas-wrap">
            <canvas
              ref={canvasRef}
              onMouseMove={(e) => {
                const rect = (e.target as HTMLCanvasElement).getBoundingClientRect()
                const j = Math.floor((e.clientX - rect.left) / celula)
                const i = Math.floor((e.clientY - rect.top) / celula)
                if (i >= 0 && j >= 0 && i < n && j < n) setHover({ i, j })
              }}
              onMouseLeave={() => setHover(null)}
              onClick={() => {
                if (!hover) return
                onPick(dados.cursos[hover.i].curso.id, dados.cursos[hover.j].curso.id)
              }}
            />
          </div>
          <div className="matrix-side">
            {hover ? (
              <div className="matrix-card">
                <span className="eyebrow">par selecionado</span>
                <div className="mm-row">
                  <span className="dim tiny">de</span>
                  <b>{nomes[hover.i]}</b>
                </div>
                <div className="mm-row">
                  <span className="dim tiny">para</span>
                  <b>{nomes[hover.j]}</b>
                </div>
                <div className="mm-big">
                  {dados.semestres[hover.i][hover.j] === 0
                    ? 'já coberto'
                    : `+${dados.semestres[hover.i][hover.j]} semestres`}
                </div>
                <button
                  type="button"
                  className="primary"
                  onClick={() => onPick(dados.cursos[hover.i].curso.id, dados.cursos[hover.j].curso.id)}
                >
                  abrir esse par
                </button>
              </div>
            ) : (
              <div className="matrix-card dim">
                <span className="eyebrow">dica</span>
                <p className="tiny">
                  Passe o mouse sobre a matriz. A linha é o curso de origem, a coluna o de destino.
                  A diagonal é o próprio curso.
                </p>
              </div>
            )}
            <div className="matrix-find">
              <span className="eyebrow">centralizar</span>
              {['Ciência da Computação', 'Engenharia de Computação', 'Sistemas de Informação', 'Medicina', 'Direito'].map(
                (nome) => {
                  const idx = idxBusca(nome)
                  if (idx < 0) return null
                  return (
                    <button
                      key={nome}
                      type="button"
                      className="mini-btn"
                      onClick={() => {
                        const wrap = document.querySelector('.matrix-canvas-wrap')
                        wrap?.scrollTo({ left: idx * celula - 200, top: idx * celula - 200, behavior: 'smooth' })
                        setHover({ i: idx, j: idx })
                      }}
                    >
                      {nome}
                    </button>
                  )
                },
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

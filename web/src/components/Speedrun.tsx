import { useMemo, useState } from 'react'
import type { CourseModel, Universe } from '../db/types'
import type { Done } from '../lib/plan'
import { buildSpeedrun } from '../lib/speedrun'
import { buildDiagnostico } from '../lib/diag'
import { horas, norm, num } from '../lib/format'

interface Props {
  universo: Universe
  base: CourseModel | null
  done: Done
  estrategica: boolean
  onOpenCurso: (id: number) => void
}

export function SpeedrunView({ universo, base, done, estrategica, onOpenCurso }: Props) {
  const [busca, setBusca] = useState('')
  const dados = useMemo(
    () => (base ? buildSpeedrun(universo, done) : null),
    [universo, base, done],
  )

  const exportarDiagnostico = () => {
    if (!base || !dados) return
    const payload = buildDiagnostico(universo, base, done, estrategica)
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `front-diag-${base.curso.id}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  const filtrados = useMemo(() => {
    if (!dados) return []
    const termo = norm(busca.trim())
    if (!termo) return dados.passos
    return dados.passos.filter((p) =>
      norm(`${p.curso.curso.nome} ${p.curso.curso.campus ?? ''}`).includes(termo),
    )
  }, [dados, busca])

  if (!base) {
    return (
      <div className="empty-state">
        <span className="eyebrow">run completo</span>
        <h2>Escolha seu curso à esquerda</h2>
        <p>
          A rota para fechar os 148 cursos é calculada a partir do que você já cumpriu. Sem o curso
          inicial, não há ponto de partida.
        </p>
      </div>
    )
  }

  if (!dados) return null

  const novas = dados.totalDisc - done.ids.size
  const anos = dados.semestres / 2
  const maxPasso = Math.max(...dados.passos.map((p) => p.horasPasso), 1)
  const maxAcum = Math.max(dados.totalHoras, 1)
  const W = 1000
  const H = 230
  const pad = 26
  const n = dados.passos.length
  const px = (i: number) => pad + (i / Math.max(1, n - 1)) * (W - 2 * pad)
  const linha = dados.passos
    .map((p, i) => `${px(i).toFixed(1)},${(H - pad - (p.horasAcum / maxAcum) * (H - 2 * pad)).toFixed(1)}`)
    .join(' ')
  const barraW = Math.max(1.5, ((W - 2 * pad) / Math.max(1, n)) * 0.62)
  const metadeX = px(Math.max(0, dados.metadeEm - 1))

  return (
    <div className="speedrun">
      <header className="speedrun-head">
        <div className="row-between">
          <div>
            <span className="eyebrow">run completo · {base.curso.nome}</span>
            <h2>Fechar os 148 cursos, na melhor ordem</h2>
          </div>
          <button
            type="button"
            className="ghost-btn"
            onClick={exportarDiagnostico}
            title="JSON no formato do auditor: python -m ufsm_speedrun auditar --front arquivo.json"
          >
            exportar diagnóstico
          </button>
        </div>
        <p className="hint">
          Como disciplina é global, o total de cadeiras é o mesmo em qualquer ordem — o que muda é o
          quão cedo cada curso fecha. A rota abaixo é gulosa: a cada passo escolhe o curso que custa
          menos cadeiras/horas novas, dado tudo que já entrou no bolo.
        </p>
      </header>

      <div className="kpis">
        <div className="kpi">
          <span className="kpi-label">cadeiras no run</span>
          <b>{num(dados.totalDisc)}</b>
          <span className="kpi-foot">{num(novas)} além do que você já tem</span>
        </div>
        <div className="kpi">
          <span className="kpi-label">carga horária</span>
          <b>{num(Math.round(dados.totalHoras / 1000))}k</b>
          <span className="kpi-foot">{horas(dados.totalHoras)} extras</span>
        </div>
        <div className="kpi">
          <span className="kpi-label">semestres</span>
          <b>{num(dados.semestres)}</b>
          <span className="kpi-foot">≈ {num(Math.round(anos))} anos a {horas(dados.carga)}/sem.</span>
        </div>
        <div className="kpi kpi-lime">
          <span className="kpi-label">metade do esforço</span>
          <b>{dados.metadeEm}</b>
          <span className="kpi-foot">cursos até 50% das horas</span>
        </div>
      </div>

      <div className="panel chart-panel">
        <div className="chart-head">
          <div>
            <span className="eyebrow">curva do run</span>
            <h3>Custo por passo e acumulado</h3>
          </div>
          <div className="chart-legend">
            <span><i className="bar-swatch" /> horas novas no passo</span>
            <span><i className="line-swatch" /> acumulado</span>
          </div>
        </div>
        <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label="custo por curso na rota">
          {[0.25, 0.5, 0.75].map((f) => (
            <line
              key={f}
              x1={pad}
              x2={W - pad}
              y1={H - pad - f * (H - 2 * pad)}
              y2={H - pad - f * (H - 2 * pad)}
              className="grid"
            />
          ))}
          {dados.passos.map((p, i) => {
            const h = (p.horasPasso / maxPasso) * (H - 2 * pad)
            return (
              <rect
                key={p.ordem}
                x={px(i) - barraW / 2}
                y={H - pad - h}
                width={barraW}
                height={Math.max(1, h)}
                className={`barra ${p.horasPasso === 0 ? 'is-free' : ''}`}
              >
                <title>
                  {`${p.ordem}. ${p.curso.curso.nome}\n+${p.novas.length} cadeiras · ${horas(p.horasPasso)}`}
                </title>
              </rect>
            )
          })}
          <polyline points={linha} className="linha" />
          <line x1={metadeX} x2={metadeX} y1={pad} y2={H - pad} className="meia" />
          <text x={pad} y={pad - 6} className="eixo">máx {horas(maxPasso)} no passo</text>
          <text x={W - pad} y={pad - 6} className="eixo" textAnchor="end">
            acumulado {horas(maxAcum)}
          </text>
          <text x={metadeX + 6} y={H - pad - 8} className="eixo">
            50% das horas
          </text>
          <text x={pad} y={H - 6} className="eixo">1</text>
          <text x={W - pad} y={H - 6} className="eixo" textAnchor="end">{n}</text>
        </svg>
      </div>

      <div className="insights">
        <div className="panel">
          <span className="eyebrow">leitura</span>
          <ul className="bullets">
            <li>
              Os <b>20 primeiros</b> cursos custam {horas(dados.custoPrimeiros20)}; os{' '}
              <b>20 últimos</b>, {horas(dados.custoUltimos20)}. É a diferença entre pegar cursos com
              currículo enxuto e os que têm 70+ obrigatórias.
            </li>
            <li>
              Metade do esforço está nos primeiros <b>{dados.metadeEm}</b> de {n} cursos. O resto é
              cauda longa: Medicina, Veterinária, Agronomia, Arquitetura.
            </li>
            <li>
              <b>{num(dados.unicas)}</b> cadeiras pertencem a um único currículo — nelas não existe
              reaproveitamento possível. Só <b>{num(dados.compartilhadas)}</b> aparecem em 2+ cursos.
            </li>
            <li>
              Por isso o run completo é {num(dados.semestres)} semestres (~{num(Math.round(anos))}{' '}
              anos). É um exercício de limite, não um plano de vida — o valor está em saber qual
              curso rende mais por semestre.
            </li>
            {dados.dcgEstrategica.length > 0 && (
              <li>
                <b>{dados.dcgEstrategica.length}</b> obrigatórias de outros cursos entraram como{' '}
                <b>DCG do seu curso</b> (
                {horas(dados.dcgEstrategica.reduce((s, d) => s + d.ch, 0))}):{' '}
                {dados.dcgEstrategica.slice(0, 6).map((d) => d.codigo).join(', ')}
                {dados.dcgEstrategica.length > 6 ? '…' : ''}. É a jogada que encurta o próximo
                curso sem fazer nada a mais.
              </li>
            )}
          </ul>
        </div>
        <div className="panel">
          <span className="eyebrow">gargalos</span>
          <h3>Cadeiras que servem mais cursos</h3>
          <p className="tiny dim">
            Elas aparecem em até {dados.gargalos[0]?.cursos ?? 0} currículos. Fazer uma delas
            "de graça" em vários cursos é o único reaproveitamento que existe nesta escala.
          </p>
          <div className="lever-list compact">
            {dados.gargalos.map((g) => (
              <div key={g.discId} className="lever" title={g.nome}>
                <span className="cl-code">{g.codigo}</span>
                <span className="lever-name">{g.nome}</span>
                <span className="lever-count">
                  <b>{g.cursos}</b> cursos
                </span>
                <span className="mono tiny dim">{g.ch}h</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="panel">
        <div className="chart-head">
          <div>
            <span className="eyebrow">rota</span>
            <h3>A ordem dos cursos</h3>
          </div>
          <input
            className="text-input rota-busca"
            placeholder="filtrar curso…"
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
          />
        </div>
        <div className="table-wrap rota-wrap">
          <table className="rank-table rota-table">
            <thead>
              <tr>
                <th className="col-rank">#</th>
                <th>curso</th>
                <th className="col-num">novas</th>
                <th className="col-num">CH do passo</th>
                <th className="col-num">acumulado</th>
                <th className="col-num">fecha no sem.</th>
              </tr>
            </thead>
            <tbody>
              {filtrados.map((p) => (
                <tr
                  key={p.curso.curso.id}
                  onClick={() => onOpenCurso(p.curso.curso.id)}
                  title={p.novas.map((o) => o.codigo).slice(0, 24).join(', ')}
                >
                  <td className="col-rank mono">{p.ordem}</td>
                  <td>
                    <div className="curso-cell">
                      <span className="curso-nome">
                        {p.curso.curso.nome}
                        {p.curso.curso.id === base.curso.id && (
                          <span className="you-are-here"> · você está aqui</span>
                        )}
                      </span>
                      <span className="curso-meta">{p.curso.curso.campus ?? '—'}</span>
                    </div>
                  </td>
                  <td className="col-num">
                    <span className={`big-num ${p.novas.length === 0 ? 'zero' : ''}`}>{p.novas.length}</span>
                  </td>
                  <td className="col-num mono dim">{horas(p.horasPasso)}</td>
                  <td className="col-num mono dim">{horas(p.horasAcum)}</td>
                  <td className="col-num mono">{p.semestre === 0 ? '—' : p.semestre}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="note tiny">
          A coluna "novas" conta só as obrigatórias que ainda não estavam no bolo; cotas de núcleo
          escolhidas entram no CH do passo. Semestre = CH acumulada ÷ {horas(dados.carga)} — sem
          simular pré-requisitos no run inteiro.
        </p>
      </div>
    </div>
  )
}

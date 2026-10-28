import { useMemo, useState } from 'react'
import type { CourseModel, Universe } from '../db/types'
import type { Done } from '../lib/plan'
import { horas, norm, periodoLabel, plural } from '../lib/format'
import { CourseSelect } from './CourseSelect'

interface Props {
  universo: Universe
  base: CourseModel | null
  baseId: number | null
  setBaseId: (id: number) => void
  concluidoAte: number | null
  setConcluidoAte: (n: number | null) => void
  overrides: Map<number, boolean>
  toggleDisc: (id: number, valor: boolean) => void
  limparOverrides: () => void
  extras: Set<number>
  addExtra: (id: number) => void
  removeExtra: (id: number) => void
  done: Done
  estrategica: boolean
  setEstrategica: (v: boolean) => void
}

export function BasePanel({
  universo,
  base,
  baseId,
  setBaseId,
  concluidoAte,
  setConcluidoAte,
  overrides,
  toggleDisc,
  limparOverrides,
  extras,
  addExtra,
  removeExtra,
  done,
  estrategica,
  setEstrategica,
}: Props) {
  const [aberto, setAberto] = useState(false)
  const [busca, setBusca] = useState('')

  const marcado = (discId: number, periodo: number): boolean => {
    const o = overrides.get(discId)
    if (o !== undefined) return o
    if (concluidoAte === null) return true
    return periodo >= 99 || periodo <= concluidoAte
  }

  const porPeriodo = useMemo(() => {
    if (!base) return []
    const mapa = new Map<number, typeof base.fixed>()
    for (const o of base.fixed) {
      const p = o.periodo >= 99 ? 99 : o.periodo
      const list = mapa.get(p) ?? []
      list.push(o)
      mapa.set(p, list)
    }
    return [...mapa.entries()].sort((a, b) => a[0] - b[0])
  }, [base])

  const chMarcada = useMemo(() => {
    let total = 0
    for (const id of done.ids) total += done.chOf.get(id) ?? 0
    return total
  }, [done])

  const resultados = useMemo(() => {
    const termo = norm(busca.trim())
    if (termo.length < 2) return []
    return [...universo.disciplinas.values()]
      .filter((d) => !done.ids.has(d.id) && norm(`${d.codigo} ${d.nome}`).includes(termo))
      .slice(0, 8)
  }, [busca, universo, done])

  const totalCurso = base ? base.versao.chTotal ?? base.fixedHoras : 0
  const cumpridoTotal = chMarcada + done.freeHoras

  return (
    <div className="panel base-panel">
      <div className="panel-head">
        <span className="eyebrow">01 · ponto de partida</span>
        <h2>Seu curso</h2>
      </div>

      <CourseSelect cursos={universo.cursos} value={baseId} onChange={setBaseId} />

      {!base && (
        <p className="hint">
          Escolha o curso que você cursa hoje. A partir dele calculamos o custo de fechar qualquer
          outro curso, cadeira por cadeira.
        </p>
      )}

      {base && (
        <>
          <div className="base-meta">
            <div>
              <b>{base.semestres}</b>
              <span>semestres</span>
            </div>
            <div>
              <b>{horas(base.versao.chTotal ?? base.fixedHoras)}</b>
              <span>CH total</span>
            </div>
            <div>
              <b>{base.fixed.length}</b>
              <span>obrigatórias</span>
            </div>
          </div>

          <div className="divider" />

          <div className="row-between">
            <span className="label">progresso</span>
            <span className="mono dim">
              {concluidoAte === null ? 'curso completo' : `${concluidoAte} de ${base.semestres} semestres`}
            </span>
          </div>

          <input
            className="slider"
            type="range"
            min={0}
            max={base.semestres}
            step={1}
            value={concluidoAte ?? base.semestres}
            onChange={(e) => {
              const n = Number(e.target.value)
              setConcluidoAte(n >= base.semestres ? null : n)
            }}
            aria-label="semestres concluídos"
          />
          <div className="slider-scale">
            <span>início</span>
            <span>{concluidoAte === null ? 'formado' : `${base.semestres - concluidoAte} sem. restantes`}</span>
          </div>

          <div className="bar big">
            <i style={{ width: `${totalCurso ? Math.min(100, (cumpridoTotal / totalCurso) * 100) : 0}%` }} />
          </div>
          <div className="row-between tiny dim">
            <span>{horas(cumpridoTotal)} cumpridas</span>
            <span>{horas(Math.max(0, totalCurso - cumpridoTotal))} restantes</span>
          </div>

          <div className="divider" />

          <button type="button" className="link-btn" onClick={() => setAberto((v) => !v)}>
            {aberto ? '▾' : '▸'} ajustar disciplinas ({done.ids.size} marcadas)
          </button>

          {aberto && (
            <div className="checklist">
              <div className="row-between tiny">
                <span className="dim">{plural(base.fixed.length, 'obrigatória', 'obrigatórias')}</span>
                <button type="button" className="mini-btn" onClick={limparOverrides}>
                  limpar ajustes
                </button>
              </div>
              {porPeriodo.map(([periodo, lista]) => (
                <div key={periodo} className="cl-group">
                  <div className="cl-period">{periodoLabel(periodo)}</div>
                  {lista.map((o) => (
                    <label key={o.id} className={`cl-item ${marcado(o.discId, o.periodo) ? 'is-on' : ''}`}>
                      <input
                        type="checkbox"
                        checked={marcado(o.discId, o.periodo)}
                        onChange={(e) => toggleDisc(o.discId, e.target.checked)}
                      />
                      <span className="cl-code">{o.codigo}</span>
                      <span className="cl-name" title={o.nome}>{o.nome}</span>
                      <span className="cl-ch">{o.ch}h</span>
                    </label>
                  ))}
                </div>
              ))}
            </div>
          )}

          {done.freeAberto > 0 && (
            <>
              <div className="divider" />
              <label className="toggle">
                <input
                  type="checkbox"
                  checked={estrategica}
                  onChange={(e) => setEstrategica(e.target.checked)}
                />
                DCG estratégica
              </label>
              <p className="hint tiny">
                Você tem <b>{horas(done.freeAberto)}</b> em DCG/cota aberta, que aceitam qualquer
                disciplina — então podem ter sido gastas justamente nas obrigatórias que faltam em
                outro curso. Desligue para ver o cenário sem essa escolha.
              </p>
            </>
          )}

          <div className="divider" />

          <span className="label">já fiz em outro curso/instituição</span>
          <input
            className="text-input"
            placeholder="código ou nome da disciplina…"
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
          />
          {resultados.length > 0 && (
            <div className="disc-results">
              {resultados.map((d) => (
                <button
                  key={d.id}
                  type="button"
                  className="disc-result"
                  onClick={() => {
                    addExtra(d.id)
                    setBusca('')
                  }}
                >
                  <span className="cl-code">{d.codigo}</span>
                  <span className="cl-name">{d.nome}</span>
                  <span className="cl-ch">{d.ch}h</span>
                </button>
              ))}
            </div>
          )}
          {extras.size > 0 && (
            <div className="chips">
              {[...extras].map((id) => {
                const d = universo.disciplinas.get(id)
                return (
                  <span key={id} className="chip chip-done">
                    {d?.codigo ?? id}
                    <button type="button" onClick={() => removeExtra(id)} aria-label="remover">
                      ×
                    </button>
                  </span>
                )
              })}
            </div>
          )}
        </>
      )}
    </div>
  )
}

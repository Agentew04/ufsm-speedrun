import { useMemo, useState } from 'react'
import type { Universe } from '../db/types'
import type { CourseScore, Done } from '../lib/plan'
import { leverInsights, distanciaResumo } from '../lib/plan'
import { horas, norm, num, pct } from '../lib/format'

interface Props {
  universo: Universe
  baseId: number | null
  scores: CourseScore[]
  done: Done
  onSelect: (id: number) => void
  selecionado: number | null
}

type Ordem = 'semestres' | 'ch' | 'disciplinas' | 'aproveitamento' | 'nome'

const CAMPUS_ORDEM = (a: string, b: string) => a.localeCompare(b, 'pt-BR')

export function Ranking({ universo, baseId, scores, done, onSelect, selecionado }: Props) {
  const [busca, setBusca] = useState('')
  const [campus, setCampus] = useState('todos')
  const [modalidade, setModalidade] = useState('todos')
  const [ordem, setOrdem] = useState<Ordem>('semestres')
  const [soCurto, setSoCurto] = useState(false)

  const base = baseId ? universo.byCurso.get(baseId) ?? null : null
  const todosCampi = useMemo(
    () => [...new Set(universo.cursos.map((c) => c.curso.campus ?? '—'))].sort(CAMPUS_ORDEM),
    [universo],
  )
  const modalidades = useMemo(
    () => [...new Set(universo.cursos.map((c) => c.curso.modalidade ?? '—'))].sort(CAMPUS_ORDEM),
    [universo],
  )

  const filtrados = useMemo(() => {
    const termo = norm(busca.trim())
    let list = scores.filter((s) => s.target.curso.id !== baseId)
    if (termo) {
      list = list.filter((s) =>
        norm(`${s.target.curso.nome} ${s.target.curso.campus ?? ''} ${s.target.curso.grau ?? ''}`).includes(termo),
      )
    }
    if (campus !== 'todos') list = list.filter((s) => (s.target.curso.campus ?? '—') === campus)
    if (modalidade !== 'todos') list = list.filter((s) => (s.target.curso.modalidade ?? '—') === modalidade)
    if (soCurto) list = list.filter((s) => s.semestres <= 2)

    const ordenado = [...list]
    ordenado.sort((a, b) => {
      switch (ordem) {
        case 'ch':
          return a.extraHoras - b.extraHoras
        case 'disciplinas':
          return a.extraDisciplinas - b.extraDisciplinas
        case 'aproveitamento':
          return b.overlapPct - a.overlapPct
        case 'nome':
          return a.target.curso.nome.localeCompare(b.target.curso.nome, 'pt-BR')
        default:
          return a.semestres - b.semestres || a.extraHoras - b.extraHoras
      }
    })
    return ordenado
  }, [scores, baseId, busca, campus, modalidade, ordem, soCurto])

  const semBase = useMemo(
    () => scores.filter((s) => s.target.curso.id !== baseId),
    [scores, baseId],
  )
  const resumo = useMemo(() => distanciaResumo(semBase), [semBase])
  const levers = useMemo(() => (done.ids.size ? leverInsights(universo, done, 10) : []), [universo, done])
  const mediana = useMemo(() => {
    const vals = semBase.map((s) => s.semestres).sort((a, b) => a - b)
    if (!vals.length) return 0
    return vals[Math.floor(vals.length / 2)]
  }, [semBase])

  if (!base) {
    return (
      <div className="empty-state">
        <span className="eyebrow">ranking</span>
        <h2>Escolha seu curso à esquerda</h2>
        <p>
          O ranking cruza todas as 12.313 ofertas dos 148 currículos e mostra quanto falta — em
          semestres, horas e cadeiras — para fechar cada curso partindo do seu.
        </p>
      </div>
    )
  }

  return (
    <div className="ranking">
      <div className="kpis">
        <div className="kpi kpi-lime">
          <span className="kpi-label">já cobertos</span>
          <b>{resumo.zero}</b>
          <span className="kpi-foot">cursos sem nenhuma cadeira nova</span>
        </div>
        <div className="kpi">
          <span className="kpi-label">a 1 cadeira</span>
          <b>{resumo.uma}</b>
          <span className="kpi-foot">falta só uma disciplina</span>
        </div>
        <div className="kpi">
          <span className="kpi-label">a 2 cadeiras</span>
          <b>{resumo.duas}</b>
          <span className="kpi-foot">quase lá</span>
        </div>
        <div className="kpi">
          <span className="kpi-label">mediana</span>
          <b>{num(mediana, 1)}</b>
          <span className="kpi-foot">semestres extras por curso</span>
        </div>
      </div>

      <div className="filters">
        <input
          className="text-input"
          placeholder="filtrar por curso, campus ou grau…"
          value={busca}
          onChange={(e) => setBusca(e.target.value)}
        />
        <select value={campus} onChange={(e) => setCampus(e.target.value)} aria-label="campus">
          <option value="todos">todos os campi</option>
          {todosCampi.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        <select value={modalidade} onChange={(e) => setModalidade(e.target.value)} aria-label="modalidade">
          <option value="todos">toda modalidade</option>
          {modalidades.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
        <select value={ordem} onChange={(e) => setOrdem(e.target.value as Ordem)} aria-label="ordenação">
          <option value="semestres">menos semestres extras</option>
          <option value="ch">menos horas extras</option>
          <option value="disciplinas">menos cadeiras novas</option>
          <option value="aproveitamento">maior aproveitamento</option>
          <option value="nome">nome</option>
        </select>
        <label className="toggle">
          <input type="checkbox" checked={soCurto} onChange={(e) => setSoCurto(e.target.checked)} />
          só ≤ 2 semestres
        </label>
      </div>

      <div className="table-wrap">
        <table className="rank-table">
          <thead>
            <tr>
              <th className="col-rank">#</th>
              <th>curso</th>
              <th className="col-num">sem. extras</th>
              <th className="col-num">CH extra</th>
              <th className="col-num">cadeiras</th>
              <th className="col-bar">reaproveitamento</th>
              <th className="col-go" />
            </tr>
          </thead>
          <tbody>
            {filtrados.map((s, i) => {
              const outroCampus = s.target.curso.campus !== base.curso.campus
              return (
                <tr
                  key={s.target.curso.id}
                  className={`${s.semestres === 0 ? 'is-free' : ''} ${
                    s.target.curso.id === selecionado ? 'is-selected' : ''
                  }`}
                  onClick={() => onSelect(s.target.curso.id)}
                >
                  <td className="col-rank mono">{i + 1}</td>
                  <td>
                    <div className="curso-cell">
                      <span className="curso-nome">{s.target.curso.nome}</span>
                      <span className="curso-meta">
                        {s.target.curso.campus ?? '—'}
                        {s.target.curso.modalidade ? ` · ${s.target.curso.modalidade}` : ''}
                        {outroCampus && <span className="warn" title="campus diferente do seu"> ⚠</span>}
                      </span>
                    </div>
                  </td>
                  <td className="col-num">
                    <span className={`big-num ${s.semestres === 0 ? 'zero' : ''}`}>{s.semestres}</span>
                  </td>
                  <td className="col-num mono dim">{horas(s.extraHoras)}</td>
                  <td className="col-num mono dim">{s.extraDisciplinas}</td>
                  <td className="col-bar">
                    <div className="overlap">
                      <div className="bar small">
                        <i style={{ width: `${Math.min(100, s.overlapPct * 100)}%` }} />
                      </div>
                      <span className="mono tiny dim">{pct(s.overlapPct)}</span>
                    </div>
                  </td>
                  <td className="col-go">→</td>
                </tr>
              )
            })}
          </tbody>
        </table>
        {filtrados.length === 0 && <div className="combo-empty">nenhum curso com esses filtros</div>}
      </div>

      {levers.length > 0 && (
        <div className="panel levers">
          <div className="panel-head">
            <span className="eyebrow">alavancas</span>
            <h3>O que mais destrava curso</h3>
            <p className="hint">
              Disciplinas que você ainda não tem e que aparecem no maior número de currículos.
              Fazer uma delas pode valer por vários cursos de uma vez.
            </p>
          </div>
          <div className="lever-list">
            {levers.map((l) => (
              <div key={l.discId} className="lever" title={l.cursos.slice(0, 12).join(', ')}>
                <span className="cl-code">{l.codigo}</span>
                <span className="lever-name">{l.nome}</span>
                <span className="lever-count">
                  <b>{l.cursos.length}</b> cursos
                </span>
                <span className="mono tiny dim">{l.ch}h</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

import { useMemo, useState } from 'react'
import type { CourseModel, Universe } from '../db/types'
import type { CourseScore, Done } from '../lib/plan'
import { buildPrereqGraph } from '../lib/graph'
import { horas, num, pct, periodoLabel, plural, TIPO_LABEL } from '../lib/format'
import { PrereqGraph } from './Graph'

interface Props {
  universo: Universe
  base: CourseModel | null
  target: CourseModel
  score: CourseScore
  done: Done
}

function resumoPrereq(target: CourseModel, discId: number): string[] {
  const blocos = target.prereqs.get(discId)
  if (!blocos?.length) return []
  const saida: string[] = []
  for (const bloco of blocos) {
    const itens = bloco.itens.map((it) => {
      if ((it.tipo === 1 || it.tipo === 2) && (it.codigo || it.discId)) return it.codigo ?? `#${it.discId}`
      if (it.tipo === 3) return `${it.numero ?? '?'} h`
      if (it.tipo === 4) return `${it.numero ?? '?'} créd.`
      if (it.tipo === 5) return `≥ ${it.numero ?? '?'}º período`
      return '?'
    })
    if (itens.length) saida.push(itens.join(' + '))
  }
  return saida
}

export function CourseDetail({ universo, base, target, score, done }: Props) {
  const [vista, setVista] = useState<'lista' | 'grafo'>('lista')
  const grafo = useMemo(() => buildPrereqGraph(universo, target, done, score), [universo, target, done, score])

  const elementos = useMemo(() => {
    const nodes = grafo.nodes.map((n) => ({
      data: {
        id: n.id,
        label: n.label,
        title: n.title,
        kind: 'disc',
        ch: n.ch,
        size: 14 + Math.min(12, n.ch / 8),
      },
      position: { x: n.x, y: n.y },
      classes: n.done ? 'done' : 'novo',
    }))
    return [...nodes, ...grafo.colLabels, ...grafo.edges]
  }, [grafo])

  const porPeriodo = useMemo(() => {
    const mapa = new Map<number, typeof score.fixedMissing>()
    for (const o of score.fixedMissing) {
      const p = o.periodo >= 99 ? 99 : o.periodo
      const list = mapa.get(p) ?? []
      list.push(o)
      mapa.set(p, list)
    }
    return [...mapa.entries()].sort((a, b) => a[0] - b[0])
  }, [score])

  const outroCampus = base && target.curso.campus !== base.curso.campus
  const temCota = score.quotas.some((q) => q.faltam > 0)
  const temPrereq = grafo.edges.filter((e) => e.data.kind === 'prereq').length
  const temEquiv = grafo.edges.filter((e) => e.data.kind === 'equiv').length

  return (
    <div className="detail">
      <header className="detail-head">
        <div>
          <span className="eyebrow">
            curso-alvo · currículo {target.versao.ano ?? target.versao.numero ?? '—'}
          </span>
          <h1>{target.curso.nome}</h1>
          <div className="detail-meta">
            <span className="chip">{target.curso.campus ?? '—'}</span>
            {target.curso.modalidade && <span className="chip">{target.curso.modalidade}</span>}
            {target.curso.grau && <span className="chip">{target.curso.grau}</span>}
            <span className="chip chip-ghost">{plural(target.semestres, 'semestre', 'semestres')}</span>
            <span className="chip chip-ghost">{horas(target.versao.chTotal ?? target.fixedHoras)}</span>
            {outroCampus && <span className="chip chip-warn">campus diferente do seu</span>}
            {target.curso.nucleoComum && <span className="chip chip-warn">núcleo comum / ABI</span>}
          </div>
          {target.curso.nucleoComum && (
            <p className="note tiny">
              Este currículo é a <b>entrada (ABI/núcleo comum)</b>, não o curso completo: o diploma
              continua na habilitação (ex.: Direção ou Interpretação Teatral). Ele fica fora do
              ranking justamente por isso — fechá-lo não te forma em nada.
            </p>
          )}
        </div>
      </header>

      <div className="kpis kpis-detail">
        <div className={`kpi ${score.semestres === 0 ? 'kpi-lime' : ''}`}>
          <span className="kpi-label">semestres extras</span>
          <b>{score.semestres}</b>
          <span className="kpi-foot">
            {score.semestres === 0
              ? 'nada a fazer'
              : `~${num(score.extraHoras / Math.max(1, score.semestres))} h/semestre`}
          </span>
        </div>
        <div className="kpi">
          <span className="kpi-label">cadeiras novas</span>
          <b>{score.fixedMissing.length}</b>
          <span className="kpi-foot">{plural(score.extraDisciplinas, 'disciplina', 'disciplinas')} no total</span>
        </div>
        <div className="kpi">
          <span className="kpi-label">CH extra</span>
          <b>{horas(score.extraHoras)}</b>
          <span className="kpi-foot">
            {score.freeNeed > 0 ? `${horas(score.freeNeed)} em cotas abertas` : 'só disciplinas listadas'}
          </span>
        </div>
        <div className="kpi">
          <span className="kpi-label">reaproveitamento</span>
          <b>{pct(score.overlapPct)}</b>
          <span className="kpi-foot">
            {score.fixedCovered.length + score.fixedEquiv.length + score.fixedDcg.length} de{' '}
            {target.fixed.length} obrigatórias
          </span>
        </div>
      </div>

      <div className="detail-views">
        <div className="seg">
          <button type="button" className={vista === 'lista' ? 'is-on' : ''} onClick={() => setVista('lista')}>
            lista de cadeiras
          </button>
          <button type="button" className={vista === 'grafo' ? 'is-on' : ''} onClick={() => setVista('grafo')}>
            grafo do currículo
          </button>
        </div>
        <span className="tiny dim">
          {vista === 'lista'
            ? 'o que falta, o que já vale e o plano semestre a semestre'
            : `${temPrereq} pré-requisitos · ${temEquiv} equivalências catalogadas`}
        </span>
      </div>

      {vista === 'lista' ? (
        <div className="detail-grid">
          <div className="panel">
            <div className="panel-head">
              <span className="eyebrow">o que falta</span>
              <h3>Cadeiras novas por período</h3>
            </div>

            {score.fixedMissing.length === 0 && score.freeNeed === 0 && (
              <p className="hint ok">
                Nenhuma cadeira nova. O currículo inteiro já é coberto pelo que você cumpriu.
              </p>
            )}

            <div className="disc-list">
              {porPeriodo.map(([periodo, lista]) => (
                <div key={periodo} className="disc-group">
                  <div className="disc-group-head">
                    <span className="mono">{periodoLabel(periodo)}</span>
                    <span className="tiny dim">{horas(lista.reduce((s, o) => s + o.ch, 0))}</span>
                  </div>
                  {lista.map((o) => {
                    const reqs = resumoPrereq(target, o.discId)
                    return (
                      <div key={o.id} className="disc-row">
                        <span className="cl-code">{o.codigo}</span>
                        <span className="disc-name">{o.nome}</span>
                        <span className="mono tiny dim">{o.ch}h</span>
                        <span className={`badge ${o.tipoItem === 1 ? 'b-obrig' : 'b-eletiva'}`}>
                          {TIPO_LABEL[o.tipoItem] ?? o.tipoItem}
                        </span>
                        {reqs.length > 0 && (
                          <span className="req" title={`pré-requisito (OR entre blocos): ${reqs.join(' | ')}`}>
                            req {reqs[0]}
                            {reqs.length > 1 ? '…' : ''}
                          </span>
                        )}
                      </div>
                    )
                  })}
                </div>
              ))}
            </div>

            {temCota && (
              <div className="quotas">
                <div className="divider" />
                <span className="eyebrow">cotas a preencher</span>
                {score.quotas
                  .filter((q) => q.faltam > 0)
                  .map((q, i) => (
                    <div key={i} className="quota">
                      <div className="row-between">
                        <span className="quota-name">{q.descricao}</span>
                        <span className="mono tiny dim">
                          {horas(q.horas - q.faltam)} de {horas(q.horas)}
                        </span>
                      </div>
                      <div className="bar small">
                        <i style={{ width: `${q.horas ? ((q.horas - q.faltam) / q.horas) * 100 : 0}%` }} />
                      </div>
                      <div className="quota-foot tiny">
                        {q.kind === 'livre' ? (
                          <span className="dim">
                            {q.residual
                              ? 'horas do currículo fora dos núcleos mapeados — qualquer disciplina'
                              : 'cota aberta: qualquer disciplina do catálogo'}{' '}
                            — faltam {horas(q.faltam)}
                          </span>
                        ) : q.kind === 'dcg' ? (
                          <span className="dim">
                            DCG: qualquer disciplina conta — faltam {horas(q.faltam)}
                            {q.sugestoes.length > 0 &&
                              ` · na matriz: ${q.sugestoes.slice(0, 3).map((s) => s.codigo).join(', ')}`}
                          </span>
                        ) : q.sugestoes.length ? (
                          <span className="dim">
                            só vale o menu do núcleo: {q.sugestoes.slice(0, 4).map((s) => s.codigo).join(', ')}
                            {q.sugestoes.length > 4 ? '…' : ''}
                          </span>
                        ) : (
                          <span className="dim">faltam {horas(q.faltam)} de disciplinas do núcleo</span>
                        )}
                      </div>
                    </div>
                  ))}
              </div>
            )}

            {score.atividadesHoras > 0 && (
              <p className="note tiny">
                + {horas(score.atividadesHoras)} de atividades complementares/extensão — contadas à
                parte porque não são disciplinas que você cursa em turma.
              </p>
            )}
          </div>

          <div className="side-col">
            <div className="panel">
              <div className="panel-head">
                <span className="eyebrow">de graça</span>
                <h3>O que você já mata</h3>
              </div>
              {score.fixedCovered.length === 0 && score.fixedEquiv.length === 0 && score.fixedDcg.length === 0 ? (
                <p className="hint">Nenhuma obrigatória em comum com o que você já cumpriu.</p>
              ) : (
                <ul className="covered">
                  {score.fixedCovered.map((o) => (
                    <li key={o.id}>
                      <span className="cl-code">{o.codigo}</span>
                      <span className="disc-name">{o.nome}</span>
                      <span className="mono tiny dim">{o.ch}h</span>
                    </li>
                  ))}
                  {score.fixedEquiv.map((o) => (
                    <li key={o.id}>
                      <span className="cl-code">{o.codigo}</span>
                      <span className="disc-name">{o.nome}</span>
                      <span className="badge b-equiv">equiv</span>
                    </li>
                  ))}
                  {score.fixedDcg.map((o) => (
                    <li key={o.id}>
                      <span className="cl-code">{o.codigo}</span>
                      <span className="disc-name">{o.nome}</span>
                      <span className="badge b-dcg">DCG</span>
                    </li>
                  ))}
                </ul>
              )}
              {score.fixedDcg.length > 0 && (
                <p className="note tiny">
                  <b>{horas(score.fixedDcg.reduce((s, o) => s + o.ch, 0))}</b> dessas cadeiras cabem
                  nas suas horas de DCG/cota aberta — você pode tê-las cursado como DCG no curso de
                  origem. É a jogada que faz "terminar SI logo depois de CC". Ajuste em{' '}
                  <em>DCG estratégica</em> na barra lateral.
                </p>
              )}
              {score.freeFilledByDone > 0 && (
                <p className="note tiny">
                  + {horas(score.freeFilledByDone)} de cotas de eletiva/DCG cobertas pelas
                  disciplinas que você já fez fora das obrigatórias.
                </p>
              )}
              {score.overlapPct < 0.15 && (
                <p className="note tiny">
                  Sobreposição baixa: reformas curriculares trocam os códigos das disciplinas.
                  Quando a coleta de equivalências terminar, a matriz antiga passa a ser creditada
                  automaticamente no lugar da nova.
                </p>
              )}
            </div>

            {score.schedule.length > 0 && (
              <div className="panel">
                <div className="panel-head">
                  <span className="eyebrow">plano</span>
                  <h3>Semestre a semestre</h3>
                </div>
                <div className="timeline">
                  {score.schedule.map((sem) => (
                    <div key={sem.indice} className="sem">
                      <div className="sem-head">
                        <span className="sem-idx">+{sem.indice}</span>
                        <span className="mono tiny dim">semestre</span>
                        <span className="mono tiny dim">{horas(sem.ch)}</span>
                      </div>
                      <div className="bar tiny-bar">
                        <i
                          style={{
                            width: `${Math.min(100, (sem.ch / Math.max(1, target.cargaSemestre)) * 100)}%`,
                          }}
                        />
                      </div>
                      <div className="sem-itens">
                        {sem.itens.map((it) => (
                          <span
                            key={it.key}
                            className={`pill ${it.sintetico ? 'pill-eletiva' : ''}`}
                            title={it.nome}
                          >
                            {it.sintetico ? `${it.ch}h eletiva` : it.codigo}
                          </span>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
                <p className="note tiny">
                  Heurística: respeita os pré-requisitos catalogados e o limite de{' '}
                  {horas(target.cargaSemestre)}/semestre. A coleta de pré-requisitos pode estar
                  incompleta — trate como recomendação, não como grade oficial.
                </p>
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="panel grafo-full">
          <PrereqGraph elements={elementos} temPrereq={temPrereq} temEquiv={temEquiv} altura={620} />
          <p className="note tiny">
            Colunas = período ideal do currículo. Linha azul = pré-requisito oficial (OR entre
            blocos, AND dentro do bloco); tracejada violeta = equivalência. Onde não há aresta, a
            ordem é só o período — a coleta de pré-requisitos ainda está incompleta.
          </p>
        </div>
      )}
    </div>
  )
}

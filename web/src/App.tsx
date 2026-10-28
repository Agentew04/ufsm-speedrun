import { useCallback, useDeferredValue, useEffect, useMemo, useState } from 'react'
import { loadUniverse, openDatabase } from './db/load'
import type { Universe } from './db/types'
import { makeDone, rankCourses } from './lib/plan'
import { buildNetwork } from './lib/graph'
import { DbGate } from './components/DbGate'
import { BasePanel } from './components/BasePanel'
import { Ranking } from './components/Ranking'
import { CourseDetail } from './components/CourseDetail'
import { NetworkGraph } from './components/Graph'
import { Matrix } from './components/Matrix'
import { Metodo } from './components/Metodo'
import { num } from './lib/format'

type Aba = 'ranking' | 'curso' | 'rede' | 'mapa' | 'metodo'

const ABAS: { id: Aba; label: string }[] = [
  { id: 'ranking', label: 'Ranking' },
  { id: 'curso', label: 'Curso' },
  { id: 'rede', label: 'Rede' },
  { id: 'mapa', label: 'Mapa' },
  { id: 'metodo', label: 'Método' },
]

function lerHash() {
  const h = new URLSearchParams(location.hash.replace(/^#/, ''))
  const b = Number(h.get('b') ?? '')
  const t = Number(h.get('t') ?? '')
  const a = h.get('a') as Aba | null
  return {
    base: Number.isFinite(b) && b > 0 ? b : null,
    alvo: Number.isFinite(t) && t > 0 ? t : null,
    aba: a && ABAS.some((x) => x.id === a) ? a : null,
  }
}

export default function App() {
  const [universo, setUniverso] = useState<Universe | null>(null)
  const [status, setStatus] = useState<'idle' | 'loading' | 'error'>('idle')
  const [mensagem, setMensagem] = useState<string | null>(null)

  const inicial = useMemo(() => lerHash(), [])
  const [baseId, setBaseId] = useState<number | null>(inicial.base)
  const [alvoId, setAlvoId] = useState<number | null>(inicial.alvo)
  const [aba, setAba] = useState<Aba>(inicial.aba ?? 'ranking')

  const [concluidoAte, setConcluidoAte] = useState<number | null>(null)
  const [overrides, setOverrides] = useState<Map<number, boolean>>(new Map())
  const [extras, setExtras] = useState<Set<number>>(new Set())
  const [alvosRede, setAlvosRede] = useState(8)
  const [redeOrdem, setRedeOrdem] = useState<'aproveitamento' | 'baratos'>('aproveitamento')

  const onBytes = useCallback(async (bytes: ArrayBuffer) => {
    setStatus('loading')
    setMensagem('abrindo sqlite…')
    try {
      const db = await openDatabase(bytes)
      const u = loadUniverse(db, (p) => setMensagem(p.label + '…'))
      setUniverso(u)
      setStatus('idle')
      setMensagem(null)
    } catch (err) {
      console.error(err)
      setStatus('error')
      setMensagem(
        'não consegui ler o banco. Confira se é o data/ufsm.db do projeto (schema ufsm_speedrun) e se o WAL foi aplicado.',
      )
    }
  }, [])

  const base = universo && baseId ? universo.byCurso.get(baseId) ?? null : null
  const alvo = universo && alvoId ? universo.byCurso.get(alvoId) ?? null : null

  // o slider de progresso mexe em 148 planos; desacopla o input do recálculo
  const progressoDeferido = useDeferredValue(concluidoAte)

  const done = useMemo(
    () => (universo ? makeDone(universo, base, progressoDeferido, overrides, extras) : null),
    [universo, base, progressoDeferido, overrides, extras],
  )

  const scores = useMemo(() => {
    if (!universo || !base || !done) return []
    return rankCourses(universo, done)
  }, [universo, base, done])

  const scoreAlvo = useMemo(() => {
    if (!universo || !alvo || !done) return null
    return scores.find((s) => s.target.curso.id === alvo.curso.id) ?? null
  }, [scores, alvo, done, universo])

  const escolherBase = useCallback(
    (id: number) => {
      setBaseId(id)
      setConcluidoAte(null)
      setOverrides(new Map())
      setExtras(new Set())
      setAlvoId(null)
      setAba('ranking')
    },
    [],
  )

  const escolherAlvo = useCallback((id: number) => {
    setAlvoId(id)
    setAba('curso')
  }, [])

  useEffect(() => {
    const params = new URLSearchParams()
    if (baseId) params.set('b', String(baseId))
    if (alvoId) params.set('t', String(alvoId))
    if (aba) params.set('a', aba)
    const hash = params.toString()
    history.replaceState(null, '', hash ? `#${hash}` : location.pathname + location.search)
  }, [baseId, alvoId, aba])

  const toggleDisc = useCallback((id: number, valor: boolean) => {
    setOverrides((prev) => {
      const next = new Map(prev)
      next.set(id, valor)
      return next
    })
  }, [])

  const addExtra = useCallback((id: number) => {
    setExtras((prev) => new Set(prev).add(id))
  }, [])

  const removeExtra = useCallback((id: number) => {
    setExtras((prev) => {
      const next = new Set(prev)
      next.delete(id)
      return next
    })
  }, [])

  const redeData = useMemo(() => {
    if (!universo || !base || !done) return { elements: [], discTotal: 0, discMostrados: 0 }
    const candidatos = scores.filter((s) => s.target.curso.id !== base.curso.id)
    const ordenados =
      redeOrdem === 'aproveitamento'
        ? [...candidatos].sort((a, b) => b.overlapPct - a.overlapPct || a.semestres - b.semestres)
        : candidatos
    const alvos = ordenados.slice(0, alvosRede).map((s) => s.target)
    return buildNetwork(universo, { base, alvos, done })
  }, [universo, base, done, scores, alvosRede, redeOrdem])

  if (!universo || !done) {
    return <DbGate onBytes={onBytes} status={status} mensagem={mensagem} />
  }

  const melhores = scores.filter((s) => s.target.curso.id !== baseId).slice(0, 3)

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">
            ufsm<span className="slash">/</span>speedrun
          </span>
          <span className="tag">beta</span>
        </div>

        <div className="topbar-stats">
          <span className="topstat">
            <b>{num(universo.meta.cursos)}</b> cursos
          </span>
          <span className="topstat">
            <b>{num(universo.meta.ofertas)}</b> ofertas
          </span>
          <span className="topstat">
            <b>{num(universo.meta.disciplinas)}</b> disciplinas
          </span>
          <span className={`topstat ${universo.meta.comPrereq / Math.max(1, universo.meta.ofertas) < 0.9 ? 'is-warn' : ''}`}>
            pré-req <b>{Math.round((universo.meta.comPrereq / Math.max(1, universo.meta.ofertas)) * 100)}%</b>
          </span>
        </div>

        <button type="button" className="ghost-btn" onClick={() => location.reload()} title="trocar o arquivo do banco">
          trocar banco
        </button>
      </header>

      <main className="layout">
        <aside className="rail">
          <BasePanel
            universo={universo}
            base={base}
            baseId={baseId}
            setBaseId={escolherBase}
            concluidoAte={concluidoAte}
            setConcluidoAte={setConcluidoAte}
            overrides={overrides}
            toggleDisc={toggleDisc}
            limparOverrides={() => setOverrides(new Map())}
            extras={extras}
            addExtra={addExtra}
            removeExtra={removeExtra}
            done={done}
          />

          {base && melhores.length > 0 && (
            <div className="panel quick">
              <span className="eyebrow">atalhos</span>
              {melhores.map((s) => (
                <button key={s.target.curso.id} type="button" className="quick-row" onClick={() => escolherAlvo(s.target.curso.id)}>
                  <span className="quick-nome">{s.target.curso.nome}</span>
                  <span className={`quick-num ${s.semestres === 0 ? 'ok' : ''}`}>
                    {s.semestres === 0 ? '0' : `+${s.semestres}`}
                  </span>
                </button>
              ))}
              <span className="tiny dim">semestres extras · clique para abrir</span>
            </div>
          )}

          <div className="panel foot-note">
            <span className="tiny dim">
              {universo.meta.comEmenta} disciplinas com ementa indexada
              {universo.meta.comEmenta / Math.max(1, universo.meta.disciplinas) < 0.5 &&
                ' — coleta da fase 4 em andamento'}
            </span>
          </div>
        </aside>

        <section className="content">
          <nav className="tabs">
            {ABAS.map((t) => (
              <button
                key={t.id}
                type="button"
                className={`tab ${aba === t.id ? 'is-on' : ''}`}
                onClick={() => {
                  setAba(t.id)
                  if (t.id === 'curso' && !alvoId && melhores[0]) setAlvoId(melhores[0].target.curso.id)
                }}
              >
                {t.label}
              </button>
            ))}
            {aba === 'curso' && alvoId && (
              <span className="tab-context mono">{universo.byCurso.get(alvoId)?.curso.nome}</span>
            )}
          </nav>

          {aba === 'ranking' && (
            <Ranking
              universo={universo}
              baseId={baseId}
              scores={scores}
              done={done}
              onSelect={escolherAlvo}
              selecionado={alvoId}
            />
          )}

          {aba === 'curso' &&
            (alvo && scoreAlvo ? (
              <CourseDetail universo={universo} base={base} target={alvo} score={scoreAlvo} done={done} />
            ) : (
              <div className="empty-state">
                <span className="eyebrow">curso</span>
                <h2>Escolha um curso</h2>
                <p>Abra o ranking e clique em qualquer linha para ver o plano completo daquele curso.</p>
                <button type="button" className="primary" onClick={() => setAba('ranking')}>
                  ir para o ranking
                </button>
              </div>
            ))}

          {aba === 'rede' &&
            (base ? (
              <div className="rede-view">
                <div className="rede-head">
                  <div>
                    <span className="eyebrow">rede</span>
                    <h2>Quem divide cadeiras com quem</h2>
                    <p className="hint">
                      Grafo bipartido entre cursos e disciplinas. Só aparecem as disciplinas
                      compartilhadas por pelo menos dois dos cursos escolhidos — os nós maiores são
                      as que mais reaproveitam.
                    </p>
                  </div>
                  <div className="rede-controls">
                    <div className="seg">
                      <button
                        type="button"
                        className={redeOrdem === 'aproveitamento' ? 'is-on' : ''}
                        onClick={() => setRedeOrdem('aproveitamento')}
                      >
                        maior reaproveitamento
                      </button>
                      <button
                        type="button"
                        className={redeOrdem === 'baratos' ? 'is-on' : ''}
                        onClick={() => setRedeOrdem('baratos')}
                      >
                        mais baratos
                      </button>
                    </div>
                    <label className="rede-slider">
                      <span className="tiny dim">{alvosRede} cursos-alvo</span>
                      <input
                        type="range"
                        min={2}
                        max={20}
                        value={alvosRede}
                        onChange={(e) => setAlvosRede(Number(e.target.value))}
                        className="slider"
                      />
                    </label>
                  </div>
                </div>
                <NetworkGraph
                  elements={redeData.elements}
                  legenda={`${base.curso.nome} + ${alvosRede} cursos · ${redeData.discMostrados} de ${redeData.discTotal} disciplinas compartilhadas`}
                  semCompartilhadas={redeData.discMostrados === 0}
                />
              </div>
            ) : (
              <div className="empty-state">
                <span className="eyebrow">rede</span>
                <h2>Escolha seu curso à esquerda</h2>
                <p>A rede mostra quais disciplinas conectam seu curso aos outros.</p>
              </div>
            ))}

          {aba === 'mapa' && (
            <Matrix
              universo={universo}
              baseId={baseId}
              onPick={(b, t) => {
                if (b !== baseId) escolherBase(b)
                setAlvoId(t)
                setAba('curso')
              }}
            />
          )}

          {aba === 'metodo' && <Metodo universo={universo} />}
        </section>
      </main>
    </div>
  )
}

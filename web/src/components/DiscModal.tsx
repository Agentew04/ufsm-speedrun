import { useEffect, useState } from 'react'
import type { Universe } from '../db/types'
import { buscarBibliografia, buscarEmenta, type Ementa } from '../lib/conteudo'
import { horas, num } from '../lib/format'

interface Props {
  universo: Universe
  discId: number
  jaTenho: boolean
  onClose: () => void
}

type Estado<T> =
  | { status: 'loading' }
  | { status: 'ok'; dados: T }
  | { status: 'vazio' }
  | { status: 'erro'; msg: string }

export function DiscModal({ universo, discId, jaTenho, onClose }: Props) {
  const d = universo.disciplinas.get(discId)
  const [ementa, setEmenta] = useState<Estado<Ementa>>({ status: 'loading' })
  const [bibAberta, setBibAberta] = useState(false)
  const [bib, setBib] = useState<Estado<string>>({ status: 'loading' })

  // fecha com Esc e trava o scroll do fundo
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = overflow
    }
  }, [onClose])

  // ementa: baixa o banco na primeira cadeira da sessão (o modal remonta por
  // `key={discId}` no App, então o estado inicial já é "loading")
  useEffect(() => {
    let ativo = true
    buscarEmenta(discId)
      .then((r) => {
        if (!ativo) return
        if (!r || (!r.programa && !r.objetivos)) setEmenta({ status: 'vazio' })
        else setEmenta({ status: 'ok', dados: r })
      })
      .catch((err: Error) => {
        if (ativo) setEmenta({ status: 'erro', msg: err.message })
      })
    return () => {
      ativo = false
    }
  }, [discId])

  // bibliografia: só baixa quando o bloco é expandido
  const abrirBibliografia = () => {
    const proximo = !bibAberta
    setBibAberta(proximo)
    if (!proximo || bib.status === 'ok' || bib.status === 'vazio') return
    setBib({ status: 'loading' })
    buscarBibliografia(discId)
      .then((texto) => setBib(texto ? { status: 'ok', dados: texto } : { status: 'vazio' }))
      .catch((err: Error) => setBib({ status: 'erro', msg: err.message }))
  }

  if (!d) return null

  const cursos = universo.cursosByDisc.get(discId) ?? []
  const nomes = cursos.slice(0, 6).map((id) => universo.byCurso.get(id)?.curso.nome ?? `#${id}`)
  const terminal = universo.terminais.has(discId)

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={`${d.codigo} — ${d.nome}`}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <header className="modal-head">
          <div>
            <span className="eyebrow">disciplina</span>
            <h2>
              <span className="modal-code">{d.codigo}</span> {d.nome}
            </h2>
          </div>
          <button type="button" className="modal-close" onClick={onClose} aria-label="fechar">
            ×
          </button>
        </header>

        <div className="modal-meta">
          <span className="chip">{horas(d.ch)}</span>
          {d.creditos != null && <span className="chip">{num(d.creditos)} créditos</span>}
          {d.departamento && <span className="chip">{d.departamento}</span>}
          {d.situacao && <span className="chip chip-ghost">{d.situacao}</span>}
          {jaTenho && <span className="chip chip-done">você já tem</span>}
          {terminal && <span className="chip chip-warn">terminal — não conta como DCG</span>}
        </div>

        {cursos.length > 0 && (
          <p className="tiny dim modal-cursos">
            Aparece em <b>{cursos.length}</b> {cursos.length === 1 ? 'currículo' : 'currículos'}
            {nomes.length > 0 ? `: ${nomes.join(' · ')}` : ''}
            {cursos.length > nomes.length ? ` e mais ${cursos.length - nomes.length}` : ''}.
          </p>
        )}

        <section className="modal-section">
          <span className="eyebrow">ementa</span>
          {ementa.status === 'loading' && (
            <div className="modal-loading">
              <span className="spinner small" />
              baixando as ementas (~4 MB, só na primeira vez)…
            </div>
          )}
          {ementa.status === 'erro' && <p className="erro tiny">{ementa.msg}</p>}
          {ementa.status === 'vazio' && <p className="hint">Esta disciplina não tem programa cadastrado no SIE.</p>}
          {ementa.status === 'ok' && (
            <div className="modal-texto">
              {ementa.dados.programa && (
                <>
                  <h4>Programa</h4>
                  <p>{ementa.dados.programa}</p>
                </>
              )}
              {ementa.dados.objetivos && (
                <>
                  <h4>Objetivos</h4>
                  <p>{ementa.dados.objetivos}</p>
                </>
              )}
            </div>
          )}
        </section>

        <section className="modal-section">
          <button
            type="button"
            className={`bib-toggle ${bibAberta ? 'is-open' : ''}`}
            onClick={abrirBibliografia}
            aria-expanded={bibAberta}
          >
            <span className="bib-chevron">{bibAberta ? '▾' : '▸'}</span>
            bibliografia
            <span className="tiny dim">{bibAberta ? '' : 'clique para carregar'}</span>
          </button>
          {bibAberta && (
            <div className="modal-texto bib-texto">
              {bib.status === 'loading' && (
                <div className="modal-loading">
                  <span className="spinner small" />
                  baixando as bibliografias (~4 MB, só na primeira vez)…
                </div>
              )}
              {bib.status === 'erro' && <p className="erro tiny">{bib.msg}</p>}
              {bib.status === 'vazio' && <p className="hint">Sem bibliografia cadastrada no SIE.</p>}
              {bib.status === 'ok' && <p>{bib.dados}</p>}
            </div>
          )}
        </section>

        <footer className="modal-foot tiny dim">
          fonte: SIE/UFSM · o texto vem de um banco separado do núcleo (carregado sob demanda)
        </footer>
      </div>
    </div>
  )
}

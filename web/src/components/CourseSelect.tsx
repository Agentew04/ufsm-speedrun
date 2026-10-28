import { useEffect, useMemo, useRef, useState } from 'react'
import type { CourseModel } from '../db/types'
import { norm } from '../lib/format'

interface Props {
  cursos: CourseModel[]
  value: number | null
  onChange: (id: number) => void
  placeholder?: string
  autoFocus?: boolean
}

export function CourseSelect({ cursos, value, onChange, placeholder, autoFocus }: Props) {
  const [aberto, setAberto] = useState(false)
  const [busca, setBusca] = useState('')
  const [idx, setIdx] = useState(0)
  const boxRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const selecionado = useMemo(
    () => cursos.find((c) => c.curso.id === value) ?? null,
    [cursos, value],
  )

  const filtrados = useMemo(() => {
    const termo = norm(busca.trim())
    if (!termo) return cursos.slice(0, 60)
    const partes = termo.split(/\s+/)
    return cursos
      .filter((c) => {
        const alvo = norm(`${c.curso.nome} ${c.curso.campus ?? ''} ${c.curso.grau ?? ''} ${c.curso.modalidade ?? ''}`)
        return partes.every((p) => alvo.includes(p))
      })
      .slice(0, 80)
  }, [busca, cursos])

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (!boxRef.current?.contains(e.target as Node)) setAberto(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [])

  const escolher = (c: CourseModel) => {
    onChange(c.curso.id)
    setBusca('')
    setAberto(false)
    inputRef.current?.blur()
  }

  return (
    <div className="combo" ref={boxRef}>
      <div
        className={`combo-field ${aberto ? 'is-open' : ''}`}
        onClick={() => {
          setAberto(true)
          setTimeout(() => inputRef.current?.focus(), 0)
        }}
      >
        <span className="combo-icon">⌕</span>
        <input
          ref={inputRef}
          value={aberto ? busca : selecionado?.curso.nome ?? ''}
          placeholder={aberto ? 'buscar curso…' : placeholder ?? 'escolher curso…'}
          autoFocus={autoFocus}
          onChange={(e) => {
            setBusca(e.target.value)
            setIdx(0)
            setAberto(true)
          }}
          onFocus={() => setAberto(true)}
          onKeyDown={(e) => {
            if (e.key === 'ArrowDown') {
              e.preventDefault()
              setIdx((i) => Math.min(filtrados.length - 1, i + 1))
            } else if (e.key === 'ArrowUp') {
              e.preventDefault()
              setIdx((i) => Math.max(0, i - 1))
            } else if (e.key === 'Enter') {
              const c = filtrados[idx]
              if (c) escolher(c)
            } else if (e.key === 'Escape') {
              setAberto(false)
              inputRef.current?.blur()
            }
          }}
        />
        {selecionado && !aberto && (
          <span className={`combo-campus chip ${selecionado.curso.classificacao === 'EaD' ? 'chip-ead' : ''}`}>
            {selecionado.curso.campus ?? '—'}
          </span>
        )}
      </div>

      {aberto && (
        <div className="combo-list" role="listbox">
          {filtrados.length === 0 && <div className="combo-empty">nenhum curso com “{busca}”</div>}
          {filtrados.map((c, i) => (
            <button
              key={c.curso.id}
              type="button"
              role="option"
              aria-selected={i === idx}
              className={`combo-item ${i === idx ? 'is-active' : ''} ${
                c.curso.id === value ? 'is-selected' : ''
              }`}
              onMouseEnter={() => setIdx(i)}
              onClick={() => escolher(c)}
            >
              <span className="ci-nome">{c.curso.nome}</span>
              <span className="ci-meta">
                {c.curso.campus ?? '—'} · {c.curso.modalidade ?? '—'} · {c.semestres} sem
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

import { useCallback, useEffect, useRef, useState } from 'react'
import { DB_MAGIC } from '../db/load'

interface Props {
  onBytes: (bytes: ArrayBuffer, nome: string) => void
  status: 'idle' | 'loading' | 'error'
  mensagem: string | null
}

const AUTO_URL = new URLSearchParams(location.search).get('db') ?? './ufsm.db'

export function DbGate({ onBytes, status, mensagem }: Props) {
  const [drag, setDrag] = useState(false)
  const [autoFalhou, setAutoFalhou] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const autoRef = useRef(false)

  const abrir = useCallback(async (file: File) => {
    const bytes = await file.arrayBuffer()
    const head = new TextDecoder('latin1').decode(bytes.slice(0, 16))
    if (!head.startsWith(DB_MAGIC)) {
      window.alert('Esse arquivo não parece um SQLite (esperado "SQLite format 3").')
      return
    }
    onBytes(bytes, file.name)
  }, [onBytes])

  useEffect(() => {
    // StrictMode roda o efeito 2x: a ref garante um único fetch, e não
    // cancelamos no cleanup (o callback só alimenta o estado do App).
    if (autoRef.current) return
    autoRef.current = true
    ;(async () => {
      try {
        const res = await fetch(AUTO_URL, { cache: 'no-store' })
        if (!res.ok) throw new Error(String(res.status))
        const bytes = await res.arrayBuffer()
        const head = new TextDecoder('latin1').decode(bytes.slice(0, 16))
        if (!head.startsWith(DB_MAGIC)) throw new Error('não é sqlite')
        onBytes(bytes, AUTO_URL)
      } catch {
        setAutoFalhou(true)
      }
    })()
  }, [onBytes])

  return (
    <div className="gate">
      <div className="gate-inner">
        <div className="gate-brand">
          <span className="brand-mark">ufsm<span className="slash">/</span>speedrun</span>
          <span className="tag">beta</span>
        </div>

        <h1>
          Quantos semestres
          <br />
          você economiza <span className="hl">reaproveitando cadeiras</span>?
        </h1>
        <p className="gate-sub">
          Ranking de todos os 148 cursos da UFSM a partir do seu curso atual. Roda 100% no navegador:
          nada sai da sua máquina, nenhuma requisição para a UFSM.
        </p>

        <div
          className={`dropzone ${drag ? 'is-drag' : ''} ${status === 'error' ? 'is-error' : ''}`}
          onDragOver={(e) => {
            e.preventDefault()
            setDrag(true)
          }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => {
            e.preventDefault()
            setDrag(false)
            const file = e.dataTransfer.files?.[0]
            if (file) void abrir(file)
          }}
          onClick={() => inputRef.current?.click()}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') inputRef.current?.click()
          }}
        >
          <input
            ref={inputRef}
            type="file"
            accept=".db,.sqlite,.sqlite3,application/vnd.sqlite3,application/octet-stream"
            hidden
            onChange={(e) => {
              const file = e.target.files?.[0]
              if (file) void abrir(file)
            }}
          />
          {status === 'loading' ? (
            <>
              <div className="spinner" />
              <strong>{mensagem ?? 'Abrindo banco…'}</strong>
              <span>quanto maior o banco (ementas), mais demora — roda tudo na memória</span>
            </>
          ) : (
            <>
              <span className="drop-icon">⇩</span>
              <strong>Arraste o <code>ufsm.db</code> aqui</strong>
              <span>ou clique para escolher o arquivo</span>
            </>
          )}
        </div>

        <div className="gate-foot">
          {autoFalhou && (
            <span className="dim">
              Não achei <code>{AUTO_URL}</code> ao lado da página. Coloque o arquivo ali (ou use{' '}
              <code>?db=caminho</code>) e recarregue.
            </span>
          )}
          {mensagem && status === 'error' && <span className="err">{mensagem}</span>}
          <span className="dim">
            Esperado: <code>data/ufsm.db</code> do projeto — 148 cursos, 528 versões, 12.313 ofertas.
            Sem escritas: o banco é aberto só para leitura.
          </span>
        </div>

        <div className="gate-tips">
          <div>
            <b>1.</b> No projeto, rode{' '}
            <code>python web/scripts/snapshot-db.py</code> para copiar o banco com o WAL já aplicado.
          </div>
          <div>
            <b>2.</b> Sirva a pasta com <code>npm run dev</code> (ou <code>python -m http.server</code> em{' '}
            <code>dist/</code>) e abra no navegador.
          </div>
          <div>
            <b>3.</b> Se o crawl ainda estiver rodando, o front é tolerante a dados parciais
            (pré-requisitos e ementas incompletos).
          </div>
        </div>
      </div>
    </div>
  )
}

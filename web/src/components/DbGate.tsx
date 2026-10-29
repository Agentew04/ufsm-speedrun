import { useCallback, useEffect, useRef, useState } from 'react'
import { isSqlite, paraSqlite } from '../db/load'

interface Props {
  onBytes: (bytes: ArrayBuffer, nome: string) => void
  status: 'idle' | 'loading' | 'error'
  mensagem: string | null
}

const PARAM_DB = new URLSearchParams(location.search).get('db')
// o núcleo publicado é um .gz de ~2 MB; o .db é o fallback (dev/local)
const AUTO_URLS = PARAM_DB ? [PARAM_DB] : ['./ufsm.db.gz', './ufsm.db']

export function DbGate({ onBytes, status, mensagem }: Props) {
  const [drag, setDrag] = useState(false)
  const [autoFalhou, setAutoFalhou] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const autoRef = useRef(false)

  const abrir = useCallback(async (file: File) => {
    try {
      const bytes = await paraSqlite(await file.arrayBuffer())
      if (!isSqlite(bytes)) {
        window.alert('Esse arquivo não parece um SQLite (esperado "SQLite format 3" ou .db.gz).')
        return
      }
      onBytes(bytes, file.name)
    } catch (err) {
      console.error(err)
      window.alert('Não consegui descomprimir/abrir esse arquivo.')
    }
  }, [onBytes])

  useEffect(() => {
    // StrictMode roda o efeito 2x: a ref garante um único fetch, e não
    // cancelamos no cleanup (o callback só alimenta o estado do App).
    if (autoRef.current) return
    autoRef.current = true
    ;(async () => {
      for (const url of AUTO_URLS) {
        try {
          const res = await fetch(url, { cache: 'no-store' })
          if (!res.ok) continue
          const bytes = await paraSqlite(await res.arrayBuffer())
          if (!isSqlite(bytes)) continue
          onBytes(bytes, url)
          return
        } catch {
          /* tenta o próximo */
        }
      }
      setAutoFalhou(true)
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
              Não achei <code>./ufsm.db.gz</code> nem <code>./ufsm.db</code> ao lado da página.
              Coloque o arquivo ali (ou use <code>?db=caminho</code>) e recarregue.
            </span>
          )}
          {mensagem && status === 'error' && <span className="err">{mensagem}</span>}
          <span className="dim">
            Esperado: <code>data/public/ufsm-web.db.gz</code> (núcleo enxuto, ~2 MB) — o script de
            snapshot copia o <code>.db</code> e o <code>.gz</code> para cá. Sem escritas: o banco é
            aberto só para leitura.
          </span>
        </div>

        <div className="gate-tips">
          <div>
            <b>1.</b> No projeto, rode <code>python web/scripts/snapshot-db.py</code> (usa o núcleo
            publicado em <code>data/public/ufsm-web.db</code>).
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

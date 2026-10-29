import type { Database } from 'sql.js'
import { isSqlite, openDatabase, paraSqlite } from '../db/load'
import { htmlParaTexto } from './format'

/**
 * Bancos de conteúdo carregados sob demanda (nota da frente de dados §6):
 *   ementas.db.gz       4,1 MB — ao abrir a cadeira
 *   bibliografias.db.gz 4,2 MB — ao expandir a bibliografia
 * Cada um é baixado no máximo uma vez por sessão.
 */
type Fonte = 'ementas' | 'bibliografias'
const cache = new Map<Fonte, Promise<Database>>()

async function banco(fonte: Fonte): Promise<Database> {
  const pronto = cache.get(fonte)
  if (pronto) return pronto

  const promessa = (async () => {
    for (const url of [`./${fonte}.db.gz`, `./${fonte}.db`]) {
      try {
        const res = await fetch(url, { cache: 'no-store' })
        if (!res.ok) continue
        const bytes = await paraSqlite(await res.arrayBuffer())
        if (!isSqlite(bytes)) continue
        return await openDatabase(bytes)
      } catch {
        /* tenta o próximo */
      }
    }
    throw new Error(
      `não achei ${fonte}.db(.gz) ao lado da página — rode "python -m ufsm_speedrun publicar" e copie os artefatos para web/public/`,
    )
  })()

  cache.set(fonte, promessa)
  // se falhar, permite tentar de novo na próxima abertura
  promessa.catch(() => cache.delete(fonte))
  return promessa
}

export interface Ementa {
  programa: string
  objetivos: string
}

export async function buscarEmenta(discId: number): Promise<Ementa | null> {
  const db = await banco('ementas')
  const res = db.exec(
    'SELECT programa, objetivos_html FROM ementa WHERE disciplina_id = ? LIMIT 1',
    [discId],
  )
  if (!res.length || !res[0].values.length) return null
  const [programa, objetivos] = res[0].values[0]
  return {
    programa: htmlParaTexto(programa == null ? '' : String(programa)),
    objetivos: htmlParaTexto(objetivos == null ? '' : String(objetivos)),
  }
}

export async function buscarBibliografia(discId: number): Promise<string | null> {
  const db = await banco('bibliografias')
  const res = db.exec(
    'SELECT texto FROM bibliografia WHERE disciplina_id = ? LIMIT 1',
    [discId],
  )
  if (!res.length || !res[0].values.length) return null
  const texto = res[0].values[0][0]
  return texto == null ? null : htmlParaTexto(String(texto))
}

export const MESES = [
  'jan', 'fev', 'mar', 'abr', 'mai', 'jun',
  'jul', 'ago', 'set', 'out', 'nov', 'dez',
]

export function norm(s: string): string {
  return s
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
}

export function horas(n: number): string {
  if (!n) return '0 h'
  return `${Math.round(n).toLocaleString('pt-BR')} h`
}

export function num(n: number, casas = 0): string {
  return n.toLocaleString('pt-BR', { maximumFractionDigits: casas, minimumFractionDigits: casas })
}

export function pct(v: number, casas = 0): string {
  return `${(v * 100).toFixed(casas)}%`
}

export function periodoLabel(p: number): string {
  if (p >= 99 || p <= 0) return 'Qualquer'
  return `${p}º`
}

export const TIPO_LABEL: Record<number, string> = {
  1: 'Obrigatória',
  2: 'Optativa',
  3: 'Eletiva',
  4: 'Atividade Complementar',
  5: 'DCG',
  6: 'Inativa',
  7: 'DCG de Pós',
  8: 'Atividade de Pós',
}

export const TIPO_CLASSE: Record<number, string> = {
  1: 'obrig',
  2: 'eletiva',
  3: 'eletiva',
  4: 'atividade',
  5: 'dcg',
  6: 'inativa',
  7: 'dcg',
  8: 'atividade',
}

export function plural(n: number, singular: string, pluralForm: string): string {
  return `${num(n)} ${n === 1 ? singular : pluralForm}`
}

/** HTML do SIE → texto legível (sem tags, preservando parágrafos e listas). */
export function htmlParaTexto(html: string): string {
  if (!html) return ''
  const texto = html
    .replace(/<\s*br\s*\/?>/gi, '\n')
    .replace(/<\s*\/\s*(p|div|li|h[1-6]|tr)\s*>/gi, '\n')
    .replace(/<\s*li[^>]*>/gi, '• ')
    .replace(/<[^>]+>/g, '')
    .replace(/&nbsp;/gi, ' ')
    .replace(/&amp;/gi, '&')
    .replace(/&lt;/gi, '<')
    .replace(/&gt;/gi, '>')
    .replace(/&quot;/gi, '"')
    .replace(/&#39;|&apos;/gi, "'")
    .replace(/\r/g, '')
    .replace(/[ \t]+\n/g, '\n')
    .replace(/[ \t]{2,}/g, ' ')
    .trim()

  return corrigirQuebras(texto)
}

/**
 * O texto do SIE vem com quebras no meio da palavra ("Fundamenta\nção",
 * "Bibliografia B\násica"). Junta quando a linha anterior termina em letra e a
 * seguinte começa em minúscula. Também tira o rótulo "EMENTA"/"BIBLIOGRAFIA"
 * duplicado no topo (a UI já tem o título da seção).
 */
function corrigirQuebras(texto: string): string {
  const linhas = texto.replace(/^(EMENTA|BIBLIOGRAFIA)\s*\n+/i, '').split('\n')
  const saida: string[] = []
  for (const linha of linhas) {
    const ant = saida[saida.length - 1]
    if (
      ant !== undefined &&
      /[A-Za-zÀ-ÿ]$/.test(ant) &&
      !/[.:;!?]$/.test(ant) &&
      /^[a-zà-ÿ]/.test(linha)
    ) {
      saida[saida.length - 1] = `${ant}${linha}`
    } else {
      saida.push(linha)
    }
  }
  return saida.join('\n').replace(/\n{3,}/g, '\n\n').trim()
}

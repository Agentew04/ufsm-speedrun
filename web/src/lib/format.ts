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

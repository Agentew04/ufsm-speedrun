// Modelo de dados em memória. Tudo vem de data/ufsm.db (read-only), carregado
// no browser via sql.js. Nenhuma request para a UFSM.

export interface Curso {
  id: number
  nome: string
  campus: string | null
  modalidade: string | null
  grau: string | null
  classificacao: string | null
  /** ABI / núcleo comum: não é um curso completo, é a entrada que leva a uma habilitação */
  nucleoComum: boolean
}

export interface Versao {
  id: number
  cursoId: number
  ano: number | null
  numero: string | null
  chTotal: number | null
  chMinPeriodo: number | null
  chMaxPeriodo: number | null
  periodoIdeal: number | null
  tipoPeriodo: string | null
}

export interface Estrutura {
  id: number
  versaoId: number
  paiId: number | null
  descricao: string
  chMinima: number | null
  ordem: number | null
}

export interface Oferta {
  id: number
  versaoId: number
  estruturaId: number
  discId: number
  tipoItem: number
  periodo: number // 99 = "qualquer"
  ch: number
  creditos: number | null
  codigo: string
  nome: string
  temPrereq: boolean
  temEquiv: boolean
}

export interface PrereqItem {
  tipo: number // 1 disciplina, 2 correquisito, 3 CH, 4 créditos, 5 período
  discId: number | null
  codigo: string | null
  numero: number | null
}

export interface PrereqBloco {
  itens: PrereqItem[]
}

export interface EquivItem {
  discId: number | null
  codigo: string | null
}

export type QuotaKind = 'eletiva' | 'dcg' | 'livre' | 'atividade'

/** Cota de um núcleo que não é preenchida por disciplinas obrigatórias. */
export interface Quota {
  estruturaId: number
  descricao: string
  horas: number
  kind: QuotaKind
  /** disciplinas listadas como opção para essa cota */
  candidatos: number[]
  /** sobra entre ch_total do currículo e o que os núcleos declaram (núcleo sem cota) */
  residual: boolean
}

export interface CourseModel {
  curso: Curso
  versao: Versao
  estruturas: Estrutura[]
  ofertas: Oferta[]
  /** obrigatórias (tipo 1), deduplicadas por disciplina */
  fixed: Oferta[]
  fixedIds: Set<number>
  /** CH das obrigatórias (sem repetir disciplina) */
  fixedHoras: number
  quotas: Quota[]
  atividadesHoras: number
  /** CH típica por semestre (ch_max_periodo, ou mediana observada) */
  cargaSemestre: number
  semestres: number
  byDisc: Map<number, Oferta>
  prereqs: Map<number, PrereqBloco[]>
  equivals: Map<number, EquivItem[]>
}

export interface Universe {
  cursos: CourseModel[]
  byCurso: Map<number, CourseModel>
  disciplinas: Map<number, { id: number; codigo: string; nome: string; ch: number }>
  /** disciplina -> cursos que a listam */
  cursosByDisc: Map<number, number[]>
  meta: {
    cursos: number
    versoes: number
    ofertas: number
    disciplinas: number
    comPrereq: number
    comEquiv: number
    comEmenta: number
    /** fração das ofertas que declaram relação e já têm blocos coletados */
    coberturaPrereq: number
    coberturaEquiv: number
  }
}

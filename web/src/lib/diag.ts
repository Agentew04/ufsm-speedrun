import type { CourseModel, Universe } from '../db/types'
import { scoreCourse, type Done } from './plan'
import { buildSpeedrun } from './speedrun'

/**
 * JSON no formato do auditor (`python -m ufsm_speedrun auditar --front`).
 * `semestres` é o piso por CH (igual ao auditor); `semestres_plano` é o plano
 * com pré-requisitos que a UI mostra.
 */
export function buildDiagnostico(
  universo: Universe,
  base: CourseModel,
  done: Done,
  estrategica: boolean,
  opcoes?: { mesmoCampus?: boolean; disponiveis?: Set<number> },
) {
  const mesmoCampus = opcoes?.mesmoCampus ?? false
  const disponiveis = opcoes?.disponiveis
  const run = buildSpeedrun(universo, done, base, { mesmoCampus, disponiveis })

  const benchmark = universo.cursos
    .filter((c) => !c.curso.nucleoComum)
    .filter(
      (c) =>
        !mesmoCampus ||
        !base.curso.campus ||
        c.curso.campus === base.curso.campus ||
        c.curso.campus === 'EaD',
    )
    .map((c) => {
      const s = scoreCourse(c, done, { estrategica, disponiveis })
      return {
        alvo_curso_id: c.curso.id,
        horas: Math.round(s.extraHoras),
        disciplinas: s.extraDisciplinas,
        semestres: Math.ceil(s.extraHoras / Math.max(1, c.cargaSemestre)),
        semestres_plano: s.semestres,
      }
    })

  const passos = run.passos
    .filter((p) => p.curso.curso.id !== base.curso.id)
    .map((p, i) => ({
      ordem: i + 1,
      curso_id: p.curso.curso.id,
      horasPasso: Math.round(p.horasPasso),
    }))

  return { base_curso_id: base.curso.id, passos, benchmark }
}

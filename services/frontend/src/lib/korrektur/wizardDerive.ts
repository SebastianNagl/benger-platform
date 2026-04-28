/**
 * Pure helper that maps the wizard's selected evaluation configs onto the
 * project-update payload fields that gate the Korrektur flow downstream.
 *
 * Invoked from ProjectCreationWizard's finish step. Extracted so it can be
 * unit-tested without mounting the full wizard.
 */

import type { EvaluationConfig } from '@/lib/api/evaluation-types'

export interface KorrekturProjectFields {
  korrektur_enabled?: boolean
  korrektur_config?: Array<{ value: string; background: string }>
}

export function deriveKorrekturProjectFields(
  evaluationConfigs: EvaluationConfig[],
): KorrekturProjectFields {
  const korrekturClassic = evaluationConfigs.find(
    (c) => c?.metric === 'korrektur_classic',
  )
  const korrekturFalloesung = evaluationConfigs.find(
    (c) => c?.metric === 'korrektur_falloesung',
  )

  if (!korrekturClassic && !korrekturFalloesung) {
    return {}
  }

  const result: KorrekturProjectFields = { korrektur_enabled: true }
  const labels = (korrekturClassic?.metric_parameters as any)?.highlight_labels
  if (Array.isArray(labels) && labels.length > 0) {
    result.korrektur_config = labels
  }
  return result
}

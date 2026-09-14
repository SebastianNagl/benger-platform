/**
 * Save-time evaluation config warnings, phrased in the reader's language.
 *
 * The eval-config PUT answers with warnings that carry a code, structured
 * fields and an English `message`. Showing that message put English inside
 * German toasts. Known codes are phrased here from their fields; an unknown
 * code falls back to the server's message.
 */

export interface EvaluationConfigWarning {
  code?: string
  config_id?: string | null
  metric?: string
  side?: string
  generations?: number
  annotations?: number
  selectors?: string[]
  message?: unknown
}

type Translate = (key: string, vars?: Record<string, unknown>) => string

interface ConfigLabel {
  id?: string
  display_name?: string
  metric?: string
}

export function describeEvaluationConfigWarning(
  warning: EvaluationConfigWarning,
  configs: ReadonlyArray<ConfigLabel>,
  t: Translate,
): string {
  const config = configs.find((c) => c.id === warning.config_id)
  const name = config?.display_name || warning.config_id || warning.metric || ''
  const selectors = Array.isArray(warning.selectors) ? warning.selectors : []
  const fields = selectors.length > 0 ? ` (${selectors.join(', ')})` : ''

  if (warning.code === 'no_reference_fields') {
    return t('evaluationBuilder.warnings.noReferenceFields', { name })
  }
  if (warning.code === 'no_matching_subjects' && warning.side === 'model') {
    return t('evaluationBuilder.warnings.modelSideWithoutGenerations', {
      name,
      fields,
      count: warning.annotations ?? 0,
    })
  }
  if (warning.code === 'no_matching_subjects' && warning.side === 'human') {
    return t('evaluationBuilder.warnings.humanSideWithoutAnswers', {
      name,
      fields,
      count: warning.generations ?? 0,
    })
  }
  return typeof warning.message === 'string' ? warning.message : ''
}

/** Every warning of a save response as a sentence, skipping empty ones. */
export function describeEvaluationConfigWarnings(
  warnings: unknown,
  configs: ReadonlyArray<ConfigLabel>,
  t: Translate,
): string[] {
  if (!Array.isArray(warnings)) return []
  return warnings
    .filter(
      (warning): warning is EvaluationConfigWarning =>
        !!warning && typeof warning === 'object',
    )
    .map((warning) => describeEvaluationConfigWarning(warning, configs, t))
    .filter((sentence) => sentence.length > 0)
}

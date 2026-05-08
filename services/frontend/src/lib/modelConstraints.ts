import type { ParameterConstraints } from '@/lib/api/types'

export interface TemperatureConstraints {
  min: number
  max: number
  default: number
  fixed: boolean
  fixedValue?: number
  reason?: string
}

/**
 * Derive temperature constraints from a model's parameter_constraints.
 * Falls back to provider-level ranges if no model-specific constraints exist.
 */
export function getTemperatureConstraints(
  model: { parameter_constraints?: ParameterConstraints | null; provider?: string } | undefined,
  providerRanges?: Record<string, { min: number; max: number }>
): TemperatureConstraints {
  const pc = model?.parameter_constraints?.temperature
  if (pc && !pc.supported) {
    const v = pc.required_value ?? 1.0
    return { min: v, max: v, default: v, fixed: true, fixedValue: v, reason: pc.reason }
  }
  if (pc) {
    const providerDefault = providerRanges?.[model?.provider?.toLowerCase() ?? '']
    return {
      min: pc.min ?? providerDefault?.min ?? 0,
      max: pc.max ?? providerDefault?.max ?? 2,
      default: pc.default ?? 0,
      fixed: false,
      reason: pc.reason,
    }
  }
  // Fallback to provider range
  const pr = providerRanges?.[model?.provider?.toLowerCase() ?? ''] ?? { min: 0, max: 2 }
  return { min: pr.min, max: pr.max, default: 0, fixed: false }
}

/**
 * Get the model-specific default max_tokens, if defined.
 */
export function getDefaultMaxTokens(
  model: { parameter_constraints?: ParameterConstraints | null } | undefined
): number | undefined {
  return model?.parameter_constraints?.max_tokens?.default
}


// ────────────────────────────────────────────────────────────────────────
// Recommended-parameters helpers (migration 046)
//
// Each LLMModelResponse from /api/llm_models/public/models can carry a
// `recommended_parameters` block sourced from provider docs:
//
//   recommended_parameters: {
//     default:    { temperature?, max_tokens?, top_p?, seed?, ... },
//     evaluation: { temperature?, ... },         // optional override
//     provenance: { source: URL, retrieved: ISO-date }
//   }
//
// Resolution per (key, mode) at the worker mirrors here:
//   user_per_model > user_project > recommended[mode] > recommended.default
// then `parameter_constraints` clamps the final value.
// ────────────────────────────────────────────────────────────────────────

export interface RecommendedParameters {
  default?: Record<string, number | string | boolean>
  generation?: Record<string, number | string | boolean>
  evaluation?: Record<string, number | string | boolean>
  provenance?: { source?: string; retrieved?: string }
}

type ParamMode = 'generation' | 'evaluation'
type ModelLike = {
  recommended_parameters?: RecommendedParameters | null
} | undefined

/**
 * Look up the recommended value for one parameter key on a model, scoped
 * to a usage mode. Returns the mode-specific value first, then falls
 * back to the `default` block. `undefined` when the model has no
 * recommendation for that key in either block.
 */
export function getRecommendedParam(
  model: ModelLike,
  key: string,
  mode: ParamMode = 'generation',
): number | string | boolean | undefined {
  const rec = model?.recommended_parameters
  if (!rec) return undefined
  const modeBlock = (rec[mode] || {}) as Record<string, number | string | boolean>
  if (key in modeBlock) return modeBlock[key]
  const defaultBlock = (rec.default || {}) as Record<string, number | string | boolean>
  if (key in defaultBlock) return defaultBlock[key]
  return undefined
}

/**
 * Whether the user's current value differs from the recommended value
 * for this (key, mode). False when either no recommendation exists or
 * the values match. Numeric tolerance: equality is exact (we want to
 * surface even a 0.7 → 0.65 deviation).
 */
export function isOverridden(
  model: ModelLike,
  key: string,
  currentValue: number | string | boolean | undefined,
  mode: ParamMode = 'generation',
): boolean {
  if (currentValue === undefined || currentValue === null) return false
  const rec = getRecommendedParam(model, key, mode)
  if (rec === undefined) return false
  return rec !== currentValue
}

/**
 * Whether this model carries any recommendation block at all. Used to
 * branch UI between "abweichend von empfohlen" and "keine Empfehlung"
 * messaging.
 */
export function hasRecommendations(model: ModelLike): boolean {
  const rec = model?.recommended_parameters
  if (!rec) return false
  const d = rec.default || {}
  const g = rec.generation || {}
  const e = rec.evaluation || {}
  return (
    Object.keys(d).length > 0 ||
    Object.keys(g).length > 0 ||
    Object.keys(e).length > 0
  )
}

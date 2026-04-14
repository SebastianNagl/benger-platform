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

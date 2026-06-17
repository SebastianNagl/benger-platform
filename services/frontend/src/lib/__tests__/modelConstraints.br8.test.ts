/**
 * Branch coverage: getTemperatureConstraints + getDefaultMaxTokens.
 *
 * modelConstraints.test.ts already locks the recommended-parameter helpers,
 * but the constraint-derivation paths (the four branches of
 * getTemperatureConstraints and getDefaultMaxTokens) were uncovered. These
 * feed the temperature/max-tokens inputs in the LLM-Judge picker, so each
 * derivation path must stay pinned.
 */

import {
  getDefaultMaxTokens,
  getTemperatureConstraints,
} from '@/lib/modelConstraints'

const PROVIDER_RANGES = {
  openai: { min: 0, max: 2 },
  anthropic: { min: 0, max: 1 },
}

describe('getTemperatureConstraints', () => {
  it('returns a fixed constraint when the model declares temperature unsupported', () => {
    const model = {
      provider: 'openai',
      parameter_constraints: {
        temperature: { supported: false, required_value: 1.0, reason: 'GPT-5 family' },
      },
    }
    const c = getTemperatureConstraints(model, PROVIDER_RANGES)
    expect(c).toEqual({
      min: 1.0,
      max: 1.0,
      default: 1.0,
      fixed: true,
      fixedValue: 1.0,
      reason: 'GPT-5 family',
    })
  })

  it('defaults the fixed value to 1.0 when required_value is absent', () => {
    const model = {
      provider: 'openai',
      parameter_constraints: { temperature: { supported: false } },
    }
    const c = getTemperatureConstraints(model, PROVIDER_RANGES)
    expect(c.fixed).toBe(true)
    expect(c.fixedValue).toBe(1.0)
    expect(c.min).toBe(1.0)
    expect(c.max).toBe(1.0)
  })

  it('merges model min/max/default with provider defaults for a supported constraint', () => {
    const model = {
      provider: 'anthropic',
      parameter_constraints: {
        temperature: { supported: true, min: 0.1, max: 0.9, default: 0.4, reason: 'docs' },
      },
    }
    const c = getTemperatureConstraints(model, PROVIDER_RANGES)
    expect(c).toEqual({
      min: 0.1,
      max: 0.9,
      default: 0.4,
      fixed: false,
      reason: 'docs',
    })
  })

  it('falls back to provider range when a supported constraint omits min/max', () => {
    const model = {
      provider: 'anthropic',
      parameter_constraints: { temperature: { supported: true } },
    }
    const c = getTemperatureConstraints(model, PROVIDER_RANGES)
    // min/max fall back to anthropic provider range; default falls back to 0.
    expect(c.min).toBe(0)
    expect(c.max).toBe(1)
    expect(c.default).toBe(0)
    expect(c.fixed).toBe(false)
  })

  it('falls back to hardcoded 0/2 when a supported constraint omits min/max and provider is unknown', () => {
    const model = {
      provider: 'mystery-provider',
      parameter_constraints: { temperature: { supported: true } },
    }
    const c = getTemperatureConstraints(model, PROVIDER_RANGES)
    expect(c.min).toBe(0)
    expect(c.max).toBe(2)
  })

  it('uses the provider range when the model has no parameter_constraints', () => {
    const model = { provider: 'openai' }
    const c = getTemperatureConstraints(model, PROVIDER_RANGES)
    expect(c).toEqual({ min: 0, max: 2, default: 0, fixed: false })
  })

  it('uses the generic 0/2 fallback when provider is unknown and no constraints exist', () => {
    const model = { provider: 'nobody' }
    const c = getTemperatureConstraints(model, PROVIDER_RANGES)
    expect(c).toEqual({ min: 0, max: 2, default: 0, fixed: false })
  })

  it('handles an undefined model and undefined provider ranges gracefully', () => {
    const c = getTemperatureConstraints(undefined)
    expect(c).toEqual({ min: 0, max: 2, default: 0, fixed: false })
  })

  it('handles a model with a provider but no matching range and no constraints', () => {
    const c = getTemperatureConstraints({ provider: undefined })
    expect(c).toEqual({ min: 0, max: 2, default: 0, fixed: false })
  })
})

describe('getDefaultMaxTokens', () => {
  it('returns the catalog default when present', () => {
    const model = { parameter_constraints: { max_tokens: { default: 2048 } } }
    expect(getDefaultMaxTokens(model)).toBe(2048)
  })

  it('returns undefined when no max_tokens default is declared', () => {
    expect(getDefaultMaxTokens({ parameter_constraints: {} })).toBeUndefined()
    expect(getDefaultMaxTokens({})).toBeUndefined()
    expect(getDefaultMaxTokens(undefined)).toBeUndefined()
  })
})

/**
 * Tests for the recommended-parameters helpers (migration 046).
 *
 * The badge UI in GenerationControlModal / EvaluationBuilder consumes
 * these to surface "Empfehlung: X / Verschiedene / Keine" badges next
 * to temperature & max_tokens inputs. Lock the contract so a future
 * refactor can't silently drop a recommendation.
 */

import {
  getRecommendedParam,
  hasRecommendations,
  isOverridden,
} from '@/lib/modelConstraints'

const modelWithSplit = {
  recommended_parameters: {
    default: { max_tokens: 4000 },
    generation: { temperature: 0.7 },
    evaluation: { temperature: 0.0 },
    provenance: { source: 'docs', retrieved: '2026-05-07' },
  },
}

const modelWithDefaultOnly = {
  recommended_parameters: {
    default: { temperature: 1.0, max_tokens: 8000 },
    provenance: { source: 'docs', retrieved: '2026-05-07' },
  },
}

const modelWithoutRecommendations = {
  recommended_parameters: null,
}

describe('getRecommendedParam', () => {
  it('returns the mode-specific value when present', () => {
    expect(getRecommendedParam(modelWithSplit, 'temperature', 'generation')).toBe(0.7)
    expect(getRecommendedParam(modelWithSplit, 'temperature', 'evaluation')).toBe(0.0)
  })

  it('falls back to the default block when the mode block lacks the key', () => {
    // max_tokens lives only in `default`; it should surface for both modes.
    expect(getRecommendedParam(modelWithSplit, 'max_tokens', 'generation')).toBe(4000)
    expect(getRecommendedParam(modelWithSplit, 'max_tokens', 'evaluation')).toBe(4000)
  })

  it('treats default-only models as applying to either mode', () => {
    expect(getRecommendedParam(modelWithDefaultOnly, 'temperature', 'generation')).toBe(1.0)
    expect(getRecommendedParam(modelWithDefaultOnly, 'temperature', 'evaluation')).toBe(1.0)
  })

  it('returns undefined when the model carries no recommendation', () => {
    expect(getRecommendedParam(modelWithoutRecommendations, 'temperature')).toBeUndefined()
    expect(getRecommendedParam(undefined, 'temperature')).toBeUndefined()
  })

  it('returns undefined when the recommendation lacks the requested key', () => {
    expect(getRecommendedParam(modelWithSplit, 'top_p', 'generation')).toBeUndefined()
  })
})

describe('isOverridden', () => {
  it('flags a deviating user value as overridden', () => {
    expect(isOverridden(modelWithSplit, 'temperature', 0.3, 'generation')).toBe(true)
  })

  it('returns false when the user value matches the recommendation exactly', () => {
    expect(isOverridden(modelWithSplit, 'temperature', 0.7, 'generation')).toBe(false)
  })

  it('returns false when the model has no recommendation to deviate from', () => {
    expect(isOverridden(modelWithoutRecommendations, 'temperature', 0.3)).toBe(false)
  })

  it('returns false when the user has not set a value yet', () => {
    expect(isOverridden(modelWithSplit, 'temperature', undefined, 'generation')).toBe(false)
  })
})

describe('hasRecommendations', () => {
  it('returns true when any of default/generation/evaluation block has keys', () => {
    expect(hasRecommendations(modelWithSplit)).toBe(true)
    expect(hasRecommendations(modelWithDefaultOnly)).toBe(true)
  })

  it('returns false when no recommendation block exists', () => {
    expect(hasRecommendations(modelWithoutRecommendations)).toBe(false)
    expect(hasRecommendations(undefined)).toBe(false)
  })

  it('returns false for an empty recommendations block', () => {
    // Pathological case — block exists but every sub-block is empty.
    expect(
      hasRecommendations({
        recommended_parameters: {
          default: {},
          generation: {},
          evaluation: {},
          provenance: { source: 'docs', retrieved: '2026-05-07' },
        },
      }),
    ).toBe(false)
  })
})

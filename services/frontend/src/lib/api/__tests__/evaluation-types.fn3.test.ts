/**
 * fn3 function coverage for evaluation-types.ts
 * Targets: getDimensionDisplayName, isSpecialFieldValue, getFieldDisplayName,
 *          generateEvaluationId
 */

import {
  getDimensionDisplayName,
  isSpecialFieldValue,
  getFieldDisplayName,
  generateEvaluationId,
  FIELD_SPECIFIERS,
  METRIC_DEFINITIONS,
  GROUPED_METRICS,
} from '../evaluation-types'

describe('evaluation-types fn3', () => {
  describe('getDimensionDisplayName', () => {
    it('returns display name for known dimension', () => {
      const result = getDimensionDisplayName('helpfulness')
      expect(typeof result).toBe('string')
      expect(result.length).toBeGreaterThan(0)
    })

    it('returns formatted name for unknown dimension', () => {
      const result = getDimensionDisplayName('some_unknown_dim')
      expect(typeof result).toBe('string')
    })
  })

  describe('isSpecialFieldValue', () => {
    it('returns true for special field specifiers', () => {
      // Check if any of the FIELD_SPECIFIERS values are recognized
      const specifiers = Object.values(FIELD_SPECIFIERS)
      if (specifiers.length > 0) {
        expect(isSpecialFieldValue(specifiers[0] as string)).toBe(true)
      }
    })

    it('returns false for regular field name', () => {
      expect(isSpecialFieldValue('my_regular_field')).toBe(false)
    })
  })

  describe('getFieldDisplayName', () => {
    it('returns display name for regular field', () => {
      const result = getFieldDisplayName('answer_text')
      expect(typeof result).toBe('string')
      expect(result.length).toBeGreaterThan(0)
    })

    it('returns display name for special field', () => {
      const specifiers = Object.values(FIELD_SPECIFIERS)
      if (specifiers.length > 0) {
        const result = getFieldDisplayName(specifiers[0] as string)
        expect(typeof result).toBe('string')
      }
    })
  })

  describe('generateEvaluationId', () => {
    it('generates unique IDs', () => {
      const id1 = generateEvaluationId('bleu')
      const id2 = generateEvaluationId('bleu')
      expect(id1).not.toBe(id2)
    })

    it('includes metric name in ID', () => {
      const id = generateEvaluationId('rouge_l')
      expect(id).toContain('rouge_l')
    })
  })

  describe('METRIC_DEFINITIONS', () => {
    it('contains expected metrics', () => {
      expect(Object.keys(METRIC_DEFINITIONS).length).toBeGreaterThan(0)
    })

    it('each metric has required fields', () => {
      for (const [key, metric] of Object.entries(METRIC_DEFINITIONS)) {
        expect(metric).toHaveProperty('name')
        expect(metric).toHaveProperty('category')
      }
    })
  })

  describe('GROUPED_METRICS', () => {
    it('is a non-empty array', () => {
      expect(Array.isArray(GROUPED_METRICS)).toBe(true)
      expect(GROUPED_METRICS.length).toBeGreaterThan(0)
    })
  })
})

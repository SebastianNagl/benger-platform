/**
 * Tests for evaluation type utilities
 */

import {
  FIELD_SPECIFIERS,
  generateEvaluationId,
  getDimensionDisplayName,
  getFieldDisplayName,
  getFieldDisplayNameKey,
  getFieldLabel,
  isSpecialFieldValue,
} from '../evaluation-types'

describe('getDimensionDisplayName', () => {
  it('should return known dimension display names', () => {
    // Known type-specific dimensions should return proper names
    const result = getDimensionDisplayName('accuracy')
    expect(typeof result).toBe('string')
    expect(result.length).toBeGreaterThan(0)
  })

  it('should capitalize unknown dimensions', () => {
    expect(getDimensionDisplayName('custom_metric')).toBe('Custom metric')
  })

  it('should capitalize single word dimensions', () => {
    expect(getDimensionDisplayName('bleu')).toBe('Bleu')
  })

  it('should replace underscores with spaces', () => {
    expect(getDimensionDisplayName('some_long_name')).toBe('Some long name')
  })
})

describe('isSpecialFieldValue', () => {
  it('should return true for ALL_MODEL', () => {
    expect(isSpecialFieldValue(FIELD_SPECIFIERS.ALL_MODEL)).toBe(true)
  })

  it('should return true for ALL_HUMAN', () => {
    expect(isSpecialFieldValue(FIELD_SPECIFIERS.ALL_HUMAN)).toBe(true)
  })

  it('should return false for regular field names', () => {
    expect(isSpecialFieldValue('answer')).toBe(false)
    expect(isSpecialFieldValue('text')).toBe(false)
  })
})

describe('getFieldDisplayName', () => {
  it('should return display name for ALL_MODEL', () => {
    expect(getFieldDisplayName(FIELD_SPECIFIERS.ALL_MODEL)).toBe(
      'All model responses',
    )
  })

  it('should return display name for ALL_HUMAN', () => {
    expect(getFieldDisplayName(FIELD_SPECIFIERS.ALL_HUMAN)).toBe(
      'All human annotations',
    )
  })

  it('should return field name as-is for regular fields', () => {
    expect(getFieldDisplayName('answer')).toBe('answer')
    expect(getFieldDisplayName('text_field')).toBe('text_field')
  })
})

describe('generateEvaluationId', () => {
  it('should generate a unique ID starting with metric name', () => {
    const id = generateEvaluationId('bleu')
    expect(id).toMatch(/^bleu-/)
  })

  it('should generate different IDs on each call', () => {
    const id1 = generateEvaluationId('rouge')
    const id2 = generateEvaluationId('rouge')
    expect(id1).not.toBe(id2)
  })

  it('should contain timestamp and random parts', () => {
    const id = generateEvaluationId('metric')
    const parts = id.split('-')
    expect(parts.length).toBeGreaterThanOrEqual(3)
  })
})

describe('FIELD_SPECIFIERS', () => {
  it('should have ALL_MODEL and ALL_HUMAN', () => {
    expect(FIELD_SPECIFIERS.ALL_MODEL).toBeDefined()
    expect(FIELD_SPECIFIERS.ALL_HUMAN).toBeDefined()
    expect(typeof FIELD_SPECIFIERS.ALL_MODEL).toBe('string')
    expect(typeof FIELD_SPECIFIERS.ALL_HUMAN).toBe('string')
  })
})

describe('getFieldDisplayNameKey', () => {
  it('names the i18n key of each bulk selector', () => {
    expect(getFieldDisplayNameKey('__all_model__')).toBe(
      'evaluationBuilder.fields.allModelResponses',
    )
    expect(getFieldDisplayNameKey('__all_human__')).toBe(
      'evaluationBuilder.fields.allHumanAnnotations',
    )
  })

  it('has no key for a plain field, which keeps its own name', () => {
    expect(getFieldDisplayNameKey('human:loesung')).toBeUndefined()
    expect(getFieldDisplayName('human:loesung')).toBe('human:loesung')
  })
})

describe('getFieldLabel', () => {
  const t = (key: string) => `translated:${key}`

  it('translates a bulk selector through its key', () => {
    expect(getFieldLabel('__all_model__', t)).toBe(
      'translated:evaluationBuilder.fields.allModelResponses',
    )
  })

  it('keeps a plain field name as it is', () => {
    expect(getFieldLabel('human:loesung', t)).toBe('human:loesung')
  })
})

/**
 * @jest-environment jsdom
 *
 * Branch coverage tests for taskTemplate.ts validateFieldValue.
 * Targets 5 uncovered branches: custom validation rule messages for
 * minLength, maxLength, min, max, pattern rules.
 */

import {
  validateFieldValue,
  TaskTemplateField,
} from '../taskTemplate'

function makeField(overrides?: Partial<TaskTemplateField>): TaskTemplateField {
  return {
    name: 'testField',
    type: 'text',
    display: { annotation: 'editable', table: 'column', creation: 'editable' },
    source: 'annotation',
    ...overrides,
  }
}

describe('validateFieldValue - validation rule custom messages', () => {
  it('uses default minLength message when rule has no custom message', () => {
    const field = makeField({
      validation: [{ type: 'minLength', value: 5 }],
    })
    const result = validateFieldValue(field, 'ab')
    expect(result.valid).toBe(false)
    expect(result.errors[0]).toContain('at least 5 characters')
  })

  it('uses custom minLength message when provided', () => {
    const field = makeField({
      validation: [{ type: 'minLength', value: 5, message: 'Too short!' }],
    })
    const result = validateFieldValue(field, 'ab')
    expect(result.valid).toBe(false)
    expect(result.errors[0]).toBe('Too short!')
  })

  it('uses default maxLength message when rule has no custom message', () => {
    const field = makeField({
      validation: [{ type: 'maxLength', value: 3 }],
    })
    const result = validateFieldValue(field, 'abcde')
    expect(result.valid).toBe(false)
    expect(result.errors[0]).toContain('at most 3 characters')
  })

  it('uses custom maxLength message when provided', () => {
    const field = makeField({
      validation: [{ type: 'maxLength', value: 3, message: 'Too long!' }],
    })
    const result = validateFieldValue(field, 'abcde')
    expect(result.valid).toBe(false)
    expect(result.errors[0]).toBe('Too long!')
  })

  it('uses default min message when rule has no custom message', () => {
    const field = makeField({
      type: 'number',
      validation: [{ type: 'min', value: 10 }],
    })
    const result = validateFieldValue(field, 5)
    expect(result.valid).toBe(false)
    expect(result.errors[0]).toContain('at least 10')
  })

  it('uses custom min message when provided', () => {
    const field = makeField({
      type: 'number',
      validation: [{ type: 'min', value: 10, message: 'Below minimum!' }],
    })
    const result = validateFieldValue(field, 5)
    expect(result.valid).toBe(false)
    expect(result.errors[0]).toBe('Below minimum!')
  })

  it('uses default max message when rule has no custom message', () => {
    const field = makeField({
      type: 'number',
      validation: [{ type: 'max', value: 100 }],
    })
    const result = validateFieldValue(field, 150)
    expect(result.valid).toBe(false)
    expect(result.errors[0]).toContain('at most 100')
  })

  it('uses custom max message when provided', () => {
    const field = makeField({
      type: 'number',
      validation: [{ type: 'max', value: 100, message: 'Above max!' }],
    })
    const result = validateFieldValue(field, 150)
    expect(result.valid).toBe(false)
    expect(result.errors[0]).toBe('Above max!')
  })

  it('uses default pattern message when rule has no custom message', () => {
    const field = makeField({
      validation: [{ type: 'pattern', value: '^[A-Z]+$' }],
    })
    const result = validateFieldValue(field, 'abc')
    expect(result.valid).toBe(false)
    expect(result.errors[0]).toContain('format is invalid')
  })

  it('uses custom pattern message when provided', () => {
    const field = makeField({
      validation: [{ type: 'pattern', value: '^[A-Z]+$', message: 'Must be uppercase!' }],
    })
    const result = validateFieldValue(field, 'abc')
    expect(result.valid).toBe(false)
    expect(result.errors[0]).toBe('Must be uppercase!')
  })

  it('uses field.label in default messages when available', () => {
    const field = makeField({
      label: 'My Field',
      validation: [{ type: 'minLength', value: 5 }],
    })
    const result = validateFieldValue(field, 'ab')
    expect(result.errors[0]).toContain('My Field')
  })

  it('uses field.name in default messages when label is missing', () => {
    const field = makeField({
      validation: [{ type: 'minLength', value: 5 }],
    })
    const result = validateFieldValue(field, 'ab')
    expect(result.errors[0]).toContain('testField')
  })

  it('passes validation when value meets all rules', () => {
    const field = makeField({
      validation: [
        { type: 'minLength', value: 2 },
        { type: 'maxLength', value: 10 },
      ],
    })
    const result = validateFieldValue(field, 'hello')
    expect(result.valid).toBe(true)
    expect(result.errors).toHaveLength(0)
  })

  it('skips validation rules when value is falsy', () => {
    const field = makeField({
      validation: [{ type: 'minLength', value: 5 }],
    })
    const result = validateFieldValue(field, '')
    expect(result.valid).toBe(true)
  })
})

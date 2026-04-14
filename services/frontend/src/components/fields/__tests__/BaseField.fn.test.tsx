/**
 * Additional coverage tests for BaseField - validateFieldValue function
 */

import { validateFieldValue } from '../BaseField'
import type { TaskTemplateField } from '@/types/taskTemplate'

describe('validateFieldValue', () => {
  const makeField = (overrides: Partial<TaskTemplateField> = {}): TaskTemplateField => ({
    name: 'test_field',
    type: 'text',
    source: 'task_data',
    display: {
      annotation: 'editable',
      table: 'column',
      creation: 'editable',
    },
    ...overrides,
  })

  it('returns error when required field has empty value', () => {
    const field = makeField({ required: true, label: 'Name' })
    const errors = validateFieldValue(field, '')
    expect(errors).toContain('Name is required')
  })

  it('returns error when required field has null value', () => {
    const field = makeField({ required: true, label: 'Email' })
    const errors = validateFieldValue(field, null)
    expect(errors).toContain('Email is required')
  })

  it('returns error when required field has undefined value', () => {
    const field = makeField({ required: true, label: 'Phone' })
    const errors = validateFieldValue(field, undefined)
    expect(errors).toContain('Phone is required')
  })

  it('returns error when required field has 0 value (falsy)', () => {
    const field = makeField({ required: true, label: 'Count' })
    const errors = validateFieldValue(field, 0)
    expect(errors).toContain('Count is required')
  })

  it('returns no errors when required field has value', () => {
    const field = makeField({ required: true, label: 'Name' })
    const errors = validateFieldValue(field, 'John')
    expect(errors).toHaveLength(0)
  })

  it('returns no errors when optional field has empty value', () => {
    const field = makeField({ required: false, label: 'Notes' })
    const errors = validateFieldValue(field, '')
    expect(errors).toHaveLength(0)
  })

  it('returns no errors when required is undefined and value is empty', () => {
    const field = makeField({ label: 'Notes' })
    const errors = validateFieldValue(field, '')
    expect(errors).toHaveLength(0)
  })

  it('uses field name when label is not set', () => {
    const field = makeField({ required: true, name: 'my_field' })
    const errors = validateFieldValue(field, null)
    expect(errors).toContain('my_field is required')
  })
})

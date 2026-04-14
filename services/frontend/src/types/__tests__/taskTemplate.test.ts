/**
 * @jest-environment jsdom
 *
 * Task Template type guards and validation helpers - branch coverage tests
 * Targets uncovered branches in isTextField, isChoiceField, isNumericField,
 * and validateFieldValue.
 */

import {
  isTextField,
  isChoiceField,
  isNumericField,
  validateFieldValue,
  TaskTemplateField,
  FieldType,
} from '../taskTemplate'

describe('Type Guards', () => {
  describe('isTextField', () => {
    it('should return true for text type', () => {
      expect(isTextField('text')).toBe(true)
    })

    it('should return true for text_area type', () => {
      expect(isTextField('text_area')).toBe(true)
    })

    it('should return true for rich_text type', () => {
      expect(isTextField('rich_text')).toBe(true)
    })

    it('should return false for non-text types', () => {
      expect(isTextField('radio')).toBe(false)
      expect(isTextField('checkbox')).toBe(false)
      expect(isTextField('rating')).toBe(false)
      expect(isTextField('number')).toBe(false)
      expect(isTextField('highlight')).toBe(false)
      expect(isTextField('file_upload')).toBe(false)
      expect(isTextField('date')).toBe(false)
      expect(isTextField('email')).toBe(false)
      expect(isTextField('url')).toBe(false)
      expect(isTextField('pdf_viewer')).toBe(false)
      expect(isTextField('optimized_pdf')).toBe(false)
      expect(isTextField('text_highlight')).toBe(false)
    })
  })

  describe('isChoiceField', () => {
    it('should return true for radio type', () => {
      expect(isChoiceField('radio')).toBe(true)
    })

    it('should return true for checkbox type', () => {
      expect(isChoiceField('checkbox')).toBe(true)
    })

    it('should return false for non-choice types', () => {
      expect(isChoiceField('text')).toBe(false)
      expect(isChoiceField('text_area')).toBe(false)
      expect(isChoiceField('rating')).toBe(false)
      expect(isChoiceField('number')).toBe(false)
      expect(isChoiceField('rich_text')).toBe(false)
    })
  })

  describe('isNumericField', () => {
    it('should return true for number type', () => {
      expect(isNumericField('number')).toBe(true)
    })

    it('should return true for rating type', () => {
      expect(isNumericField('rating')).toBe(true)
    })

    it('should return false for non-numeric types', () => {
      expect(isNumericField('text')).toBe(false)
      expect(isNumericField('radio')).toBe(false)
      expect(isNumericField('checkbox')).toBe(false)
      expect(isNumericField('text_area')).toBe(false)
      expect(isNumericField('rich_text')).toBe(false)
    })
  })
})

describe('validateFieldValue', () => {
  const createField = (overrides: Partial<TaskTemplateField> = {}): TaskTemplateField => ({
    name: 'testField',
    type: 'text',
    display: {
      annotation: 'editable',
      table: 'column',
      creation: 'editable',
    },
    source: 'annotation',
    ...overrides,
  })

  describe('required validation', () => {
    it('should fail when required field has no value', () => {
      const field = createField({ required: true, label: 'Answer' })
      const result = validateFieldValue(field, '')

      expect(result.valid).toBe(false)
      expect(result.errors).toContain('Answer is required')
    })

    it('should fail when required field has null value', () => {
      const field = createField({ required: true, label: 'Answer' })
      const result = validateFieldValue(field, null)

      expect(result.valid).toBe(false)
      expect(result.errors).toContain('Answer is required')
    })

    it('should fail when required field has undefined value', () => {
      const field = createField({ required: true, label: 'Answer' })
      const result = validateFieldValue(field, undefined)

      expect(result.valid).toBe(false)
      expect(result.errors).toContain('Answer is required')
    })

    it('should use field name when label is not provided', () => {
      const field = createField({ required: true })
      const result = validateFieldValue(field, '')

      expect(result.valid).toBe(false)
      expect(result.errors).toContain('testField is required')
    })

    it('should pass when required field has a value', () => {
      const field = createField({ required: true })
      const result = validateFieldValue(field, 'some value')

      expect(result.valid).toBe(true)
      expect(result.errors).toHaveLength(0)
    })

    it('should pass when field is not required and has no value', () => {
      const field = createField({ required: false })
      const result = validateFieldValue(field, '')

      expect(result.valid).toBe(true)
      expect(result.errors).toHaveLength(0)
    })
  })

  describe('minLength validation', () => {
    it('should fail when string is too short', () => {
      const field = createField({
        label: 'Description',
        validation: [{ type: 'minLength', value: 10 }],
      })
      const result = validateFieldValue(field, 'short')

      expect(result.valid).toBe(false)
      expect(result.errors[0]).toContain('at least 10 characters')
    })

    it('should pass when string meets minimum length', () => {
      const field = createField({
        validation: [{ type: 'minLength', value: 5 }],
      })
      const result = validateFieldValue(field, 'long enough string')

      expect(result.valid).toBe(true)
    })

    it('should use custom message when provided', () => {
      const field = createField({
        validation: [{ type: 'minLength', value: 10, message: 'Too short!' }],
      })
      const result = validateFieldValue(field, 'short')

      expect(result.errors).toContain('Too short!')
    })

    it('should not validate minLength for non-string values', () => {
      const field = createField({
        validation: [{ type: 'minLength', value: 5 }],
      })
      const result = validateFieldValue(field, 42)

      expect(result.valid).toBe(true)
    })
  })

  describe('maxLength validation', () => {
    it('should fail when string exceeds maximum length', () => {
      const field = createField({
        label: 'Title',
        validation: [{ type: 'maxLength', value: 5 }],
      })
      const result = validateFieldValue(field, 'this is too long')

      expect(result.valid).toBe(false)
      expect(result.errors[0]).toContain('at most 5 characters')
    })

    it('should pass when string is within maximum length', () => {
      const field = createField({
        validation: [{ type: 'maxLength', value: 100 }],
      })
      const result = validateFieldValue(field, 'short')

      expect(result.valid).toBe(true)
    })

    it('should use custom message when provided', () => {
      const field = createField({
        validation: [{ type: 'maxLength', value: 3, message: 'Way too long' }],
      })
      const result = validateFieldValue(field, 'abcdef')

      expect(result.errors).toContain('Way too long')
    })

    it('should not validate maxLength for non-string values', () => {
      const field = createField({
        validation: [{ type: 'maxLength', value: 5 }],
      })
      const result = validateFieldValue(field, 123456)

      expect(result.valid).toBe(true)
    })
  })

  describe('min validation', () => {
    it('should fail when number is below minimum', () => {
      const field = createField({
        type: 'number',
        label: 'Score',
        validation: [{ type: 'min', value: 0 }],
      })
      const result = validateFieldValue(field, -5)

      expect(result.valid).toBe(false)
      expect(result.errors[0]).toContain('at least 0')
    })

    it('should pass when number meets minimum', () => {
      const field = createField({
        type: 'number',
        validation: [{ type: 'min', value: 0 }],
      })
      const result = validateFieldValue(field, 5)

      expect(result.valid).toBe(true)
    })

    it('should use custom message when provided', () => {
      const field = createField({
        type: 'number',
        validation: [{ type: 'min', value: 10, message: 'Must be at least 10' }],
      })
      const result = validateFieldValue(field, 5)

      expect(result.errors).toContain('Must be at least 10')
    })

    it('should skip validation when value is falsy (0)', () => {
      // Note: The source code uses `if (value && field.validation)` which
      // treats 0 as falsy, skipping all validation rules.
      const field = createField({
        type: 'number',
        validation: [{ type: 'min', value: 1 }],
      })
      const result = validateFieldValue(field, 0)

      // 0 is falsy so validation block is skipped
      expect(result.valid).toBe(true)
    })

    it('should not validate min for non-number values', () => {
      const field = createField({
        validation: [{ type: 'min', value: 5 }],
      })
      const result = validateFieldValue(field, 'not a number')

      expect(result.valid).toBe(true)
    })
  })

  describe('max validation', () => {
    it('should fail when number exceeds maximum', () => {
      const field = createField({
        type: 'number',
        label: 'Rating',
        validation: [{ type: 'max', value: 10 }],
      })
      const result = validateFieldValue(field, 15)

      expect(result.valid).toBe(false)
      expect(result.errors[0]).toContain('at most 10')
    })

    it('should pass when number is within maximum', () => {
      const field = createField({
        type: 'number',
        validation: [{ type: 'max', value: 100 }],
      })
      const result = validateFieldValue(field, 50)

      expect(result.valid).toBe(true)
    })

    it('should use custom message when provided', () => {
      const field = createField({
        type: 'number',
        validation: [{ type: 'max', value: 5, message: 'Too high' }],
      })
      const result = validateFieldValue(field, 10)

      expect(result.errors).toContain('Too high')
    })

    it('should not validate max for non-number values', () => {
      const field = createField({
        validation: [{ type: 'max', value: 5 }],
      })
      const result = validateFieldValue(field, 'string value')

      expect(result.valid).toBe(true)
    })
  })

  describe('pattern validation', () => {
    it('should fail when string does not match pattern', () => {
      const field = createField({
        label: 'Email',
        validation: [{ type: 'pattern', value: '^[a-z]+$' }],
      })
      const result = validateFieldValue(field, 'UPPERCASE')

      expect(result.valid).toBe(false)
      expect(result.errors[0]).toContain('format is invalid')
    })

    it('should pass when string matches pattern', () => {
      const field = createField({
        validation: [{ type: 'pattern', value: '^[a-z]+$' }],
      })
      const result = validateFieldValue(field, 'lowercase')

      expect(result.valid).toBe(true)
    })

    it('should use custom message when provided', () => {
      const field = createField({
        validation: [{ type: 'pattern', value: '^\\d+$', message: 'Numbers only' }],
      })
      const result = validateFieldValue(field, 'abc')

      expect(result.errors).toContain('Numbers only')
    })

    it('should not validate pattern for non-string values', () => {
      const field = createField({
        validation: [{ type: 'pattern', value: '^[a-z]+$' }],
      })
      const result = validateFieldValue(field, 42)

      expect(result.valid).toBe(true)
    })
  })

  describe('multiple validations', () => {
    it('should collect all validation errors', () => {
      const field = createField({
        required: true,
        label: 'Name',
        validation: [
          { type: 'minLength', value: 3 },
          { type: 'maxLength', value: 50 },
        ],
      })
      const result = validateFieldValue(field, 'ab')

      expect(result.valid).toBe(false)
      expect(result.errors.length).toBeGreaterThanOrEqual(1)
    })

    it('should pass all validations', () => {
      const field = createField({
        required: true,
        validation: [
          { type: 'minLength', value: 3 },
          { type: 'maxLength', value: 50 },
          { type: 'pattern', value: '^[a-zA-Z ]+$' },
        ],
      })
      const result = validateFieldValue(field, 'Valid Name')

      expect(result.valid).toBe(true)
      expect(result.errors).toHaveLength(0)
    })
  })

  describe('no validation rules', () => {
    it('should pass when no validation rules are defined', () => {
      const field = createField({})
      const result = validateFieldValue(field, 'anything')

      expect(result.valid).toBe(true)
      expect(result.errors).toHaveLength(0)
    })

    it('should pass with null value and no required flag', () => {
      const field = createField({})
      const result = validateFieldValue(field, null)

      expect(result.valid).toBe(true)
    })
  })

  describe('custom and unknown rule types', () => {
    it('should not fail on custom rule type (no built-in handler)', () => {
      const field = createField({
        validation: [{ type: 'custom', value: 'someValidator' }],
      })
      const result = validateFieldValue(field, 'value')

      expect(result.valid).toBe(true)
    })

    it('should not fail on required rule type in validation array', () => {
      const field = createField({
        validation: [{ type: 'required' }],
      })
      const result = validateFieldValue(field, 'value')

      expect(result.valid).toBe(true)
    })
  })
})

// Note: getDefaultTemperature and getDefaultMaxTokens are in useDefaultConfig.ts, not here

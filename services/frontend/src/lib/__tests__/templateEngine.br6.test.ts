/**
 * @jest-environment jsdom
 *
 * Branch coverage: templateEngine.ts
 * Targets uncovered branches:
 *   - L207: field hidden in table display
 *   - L384: label || fieldName fallback
 *   - L391: unknown field in data during validation
 *   - L427-444: evaluateFieldCondition switch cases (contains, custom, default)
 *   - L455: onCellClick callback in renderTableCell
 *   - L489: field not found in renderAnswerCell
 *   - L502-524: separator switch cases (divider, space, newline)
 *   - L548: null/undefined value in formatFieldValue
 *   - L552-636: all field type switch cases in formatFieldValue
 *   - L592-606: checkbox array vs boolean in formatFieldValue
 */

import React from 'react'
import { TemplateEngine } from '../templateEngine'

describe('templateEngine br6 - uncovered branches', () => {
  let engine: TemplateEngine

  beforeEach(() => {
    engine = new TemplateEngine()
  })

  const mkField = (
    name: string,
    type: string,
    overrides: Record<string, any> = {}
  ) => ({
    name,
    type: type as any,
    label: overrides.label ?? name,
    required: overrides.required ?? false,
    source: overrides.source ?? ('task_data' as const),
    display: overrides.display ?? {
      table: 'column' as const,
      annotation: 'editable' as const,
      creation: 'editable' as const,
      review: 'readonly' as const,
    },
    ...overrides,
  })

  const mkTemplate = (fields: any[], displayOverrides: Record<string, any> = {}) => ({
    id: 'test-tmpl',
    name: 'test',
    version: '1.0',
    fields,
    display_config: {
      table_columns: fields.map((f: any) => f.name),
      sort_field: fields[0]?.name || 'text',
      sort_direction: 'asc' as const,
      ...displayOverrides,
    },
  })

  describe('getTableColumns', () => {
    it('skips field with display.table === hidden (L207)', () => {
      const fields = [
        mkField('visible', 'text'),
        mkField('hidden_field', 'text', { display: { table: 'hidden', annotation: 'editable', creation: 'editable' } }),
      ]
      const template = mkTemplate(fields)
      const parsed = engine.parseTemplate(template)
      const cols = engine.getTableColumns(parsed)
      expect(cols.length).toBe(1)
      expect(cols[0].id).toBe('visible')
    })

    it('renders cell with onCellClick callback (L455)', () => {
      const fields = [mkField('text', 'text')]
      const template = mkTemplate(fields)
      const parsed = engine.parseTemplate(template)
      const onCellClick = jest.fn()
      const cols = engine.getTableColumns(parsed, { onCellClick })

      // Simulate calling the cell renderer
      const cellFn = cols[0].cell as any
      const mockInfo = {
        getValue: () => 'test-value',
        row: { original: { text: 'test-value' } },
      }
      const result = cellFn(mockInfo)
      expect(result).toBeTruthy()

      // Click the rendered element to trigger onCellClick
      const rendered = result as React.ReactElement
      rendered.props.onClick()
      expect(onCellClick).toHaveBeenCalledWith('text', 'test-value', { text: 'test-value' })
    })

    it('renders cell without onCellClick (L455 else branch)', () => {
      const fields = [mkField('text', 'text')]
      const template = mkTemplate(fields)
      const parsed = engine.parseTemplate(template)
      const cols = engine.getTableColumns(parsed)

      const cellFn = cols[0].cell as any
      const mockInfo = {
        getValue: () => 'test-value',
        row: { original: { text: 'test-value' } },
      }
      const result = cellFn(mockInfo)
      expect(result).toBeTruthy()
      // Click without onCellClick should not throw
      ;(result as React.ReactElement).props.onClick()
    })

    it('uses custom renderer when provided', () => {
      const fields = [mkField('text', 'text')]
      const template = mkTemplate(fields)
      const parsed = engine.parseTemplate(template)
      const customRenderers = {
        text: (value: any, rowData: any) => React.createElement('span', null, `custom: ${value}`),
      }
      const cols = engine.getTableColumns(parsed, { customRenderers })

      const cellFn = cols[0].cell as any
      const mockInfo = {
        getValue: () => 'hello',
        row: { original: { text: 'hello' } },
      }
      const result = cellFn(mockInfo)
      expect(result.props.children).toBe('custom: hello')
    })

    it('returns null for in_answer_cell display mode', () => {
      const fields = [
        mkField('main', 'text'),
        mkField('sub', 'text', { display: { table: 'in_answer_cell', annotation: 'editable', creation: 'editable' } }),
      ]
      const template = mkTemplate(fields)
      const parsed = engine.parseTemplate(template)
      const cols = engine.getTableColumns(parsed)

      // Find the sub field column
      const subCol = cols.find((c) => c.id === 'sub')
      expect(subCol).toBeTruthy()
      const cellFn = subCol!.cell as any
      const mockInfo = {
        getValue: () => 'val',
        row: { original: { main: 'x', sub: 'val' } },
      }
      const result = cellFn(mockInfo)
      expect(result).toBeNull()
    })

    it('handles answer_display with divider separator (L504)', () => {
      const fields = [mkField('q', 'text'), mkField('a', 'text')]
      const template = mkTemplate(fields, {
        answer_display: { fields: ['q', 'a'], separator: 'divider' },
      })
      const parsed = engine.parseTemplate(template)
      const cols = engine.getTableColumns(parsed)

      // The answer column (q) should have been enhanced
      const qCol = cols.find((c) => c.id === 'q')
      const cellFn = qCol!.cell as any
      const mockInfo = {
        getValue: () => 'question',
        row: { original: { q: 'question', a: 'answer' } },
      }
      const result = cellFn(mockInfo)
      expect(result).toBeTruthy()
    })

    it('handles answer_display with space separator (L513)', () => {
      const fields = [mkField('q', 'text'), mkField('a', 'text')]
      const template = mkTemplate(fields, {
        answer_display: { fields: ['q', 'a'], separator: 'space' },
      })
      const parsed = engine.parseTemplate(template)
      const cols = engine.getTableColumns(parsed)

      const qCol = cols.find((c) => c.id === 'q')
      const cellFn = qCol!.cell as any
      const result = cellFn({
        getValue: () => 'q',
        row: { original: { q: 'q', a: 'a' } },
      })
      expect(result).toBeTruthy()
    })

    it('handles answer_display with newline separator (L521)', () => {
      const fields = [mkField('q', 'text'), mkField('a', 'text')]
      const template = mkTemplate(fields, {
        answer_display: { fields: ['q', 'a'], separator: 'newline' },
      })
      const parsed = engine.parseTemplate(template)
      const cols = engine.getTableColumns(parsed)

      const qCol = cols.find((c) => c.id === 'q')
      const cellFn = qCol!.cell as any
      const result = cellFn({
        getValue: () => 'q',
        row: { original: { q: 'q', a: 'a' } },
      })
      expect(result).toBeTruthy()
    })

    it('handles answer_display with missing field in fieldMap (L489)', () => {
      const fields = [mkField('q', 'text')]
      const template = mkTemplate(fields, {
        table_columns: ['q'],
        answer_display: { fields: ['q', 'nonexistent'], separator: 'space' },
      })
      const parsed = engine.parseTemplate(template)
      const cols = engine.getTableColumns(parsed)

      const qCol = cols.find((c) => c.id === 'q')
      const cellFn = qCol!.cell as any
      const result = cellFn({
        getValue: () => 'q',
        row: { original: { q: 'q' } },
      })
      expect(result).toBeTruthy()
    })
  })

  describe('formatFieldValue via getTableColumns cell rendering', () => {
    const renderCell = (fieldType: string, value: any) => {
      const fields = [mkField('f', fieldType)]
      const template = mkTemplate(fields)
      const parsed = engine.parseTemplate(template)
      const cols = engine.getTableColumns(parsed)
      const cellFn = cols[0].cell as any
      return cellFn({
        getValue: () => value,
        row: { original: { f: value } },
      })
    }

    it('renders null value with dash (L548)', () => {
      const result = renderCell('text', null)
      expect(result).toBeTruthy()
    })

    it('renders undefined value with dash (L548)', () => {
      const result = renderCell('text', undefined)
      expect(result).toBeTruthy()
    })

    it('renders rich_text field (L565-570)', () => {
      const result = renderCell('rich_text', '<b>bold</b>')
      expect(result).toBeTruthy()
    })

    it('renders number field (L572-580)', () => {
      const result = renderCell('number', 42)
      expect(result).toBeTruthy()
    })

    it('renders rating field (L572-580)', () => {
      const result = renderCell('rating', 4.5)
      expect(result).toBeTruthy()
    })

    it('renders date field (L582-589)', () => {
      const result = renderCell('date', '2026-01-15')
      expect(result).toBeTruthy()
    })

    it('renders checkbox with array value (L592-600)', () => {
      const result = renderCell('checkbox', ['opt1', 'opt2'])
      expect(result).toBeTruthy()
    })

    it('renders checkbox with boolean true (L601-607, value=true)', () => {
      const result = renderCell('checkbox', true)
      expect(result).toBeTruthy()
    })

    it('renders checkbox with boolean false (L606, value ? Yes : No)', () => {
      const result = renderCell('checkbox', false)
      expect(result).toBeTruthy()
    })

    it('renders radio field (L609-616)', () => {
      const result = renderCell('radio', 'option_a')
      expect(result).toBeTruthy()
    })

    it('renders file_upload field (L618-626)', () => {
      const result = renderCell('file_upload', 'document.pdf')
      expect(result).toBeTruthy()
    })

    it('renders unknown field type with default (L628-635)', () => {
      const result = renderCell('highlight' as any, 'some highlight')
      expect(result).toBeTruthy()
    })
  })

  describe('renderAnnotationForm - evaluateFieldCondition branches', () => {
    it('field condition type=contains (L436-439)', () => {
      const fields = [
        mkField('text', 'text', {
          source: 'annotation',
          condition: { type: 'contains', field: 'text', value: 'hello' },
        }),
      ]
      const template = mkTemplate(fields)
      const parsed = engine.parseTemplate(template)
      const elements = engine.renderAnnotationForm(
        parsed,
        { text: 'hello world' },
        { text: 'hello world' },
        jest.fn()
      )
      expect(elements.length).toBe(1)
    })

    it('field condition type=contains returns false when not matching', () => {
      const fields = [
        mkField('text', 'text', {
          source: 'annotation',
          condition: { type: 'contains', field: 'text', value: 'xyz' },
        }),
      ]
      const template = mkTemplate(fields)
      const parsed = engine.parseTemplate(template)
      const elements = engine.renderAnnotationForm(
        parsed,
        { text: 'hello world' },
        { text: 'hello world' },
        jest.fn()
      )
      expect(elements.length).toBe(0)
    })

    it('field condition type=custom returns true (L440-442)', () => {
      const fields = [
        mkField('text', 'text', {
          source: 'annotation',
          condition: { type: 'custom' },
        }),
      ]
      const template = mkTemplate(fields)
      const parsed = engine.parseTemplate(template)
      const elements = engine.renderAnnotationForm(
        parsed,
        {},
        { text: 'val' },
        jest.fn()
      )
      expect(elements.length).toBe(1)
    })

    it('field condition with unknown type returns true (default case L443-444)', () => {
      const fields = [
        mkField('text', 'text', {
          source: 'annotation',
          condition: { type: 'unknown_type' as any },
        }),
      ]
      const template = mkTemplate(fields)
      const parsed = engine.parseTemplate(template)
      const elements = engine.renderAnnotationForm(
        parsed,
        {},
        { text: 'val' },
        jest.fn()
      )
      expect(elements.length).toBe(1)
    })

    it('field condition string not "exists" returns false', () => {
      const fields = [
        mkField('text', 'text', {
          source: 'annotation',
          condition: 'something_else',
        }),
      ]
      const template = mkTemplate(fields)
      const parsed = engine.parseTemplate(template)
      const elements = engine.renderAnnotationForm(
        parsed,
        {},
        { text: 'val' },
        jest.fn()
      )
      expect(elements.length).toBe(0)
    })

    it('field with source=generated returns null value (L156-158)', () => {
      const fields = [
        mkField('gen', 'text', {
          source: 'generated',
        }),
      ]
      const template = mkTemplate(fields)
      const parsed = engine.parseTemplate(template)
      const elements = engine.renderAnnotationForm(
        parsed,
        {},
        {},
        jest.fn()
      )
      expect(elements.length).toBe(1)
    })

    it('field with source=computed returns null value (L159-161)', () => {
      const fields = [
        mkField('comp', 'text', {
          source: 'computed',
        }),
      ]
      const template = mkTemplate(fields)
      const parsed = engine.parseTemplate(template)
      const elements = engine.renderAnnotationForm(
        parsed,
        {},
        {},
        jest.fn()
      )
      expect(elements.length).toBe(1)
    })

    it('field with unregistered type is skipped (L167-169)', () => {
      const fields = [
        mkField('unk', 'pdf_viewer' as any, { source: 'task_data' }),
      ]
      const template = mkTemplate(fields)
      const parsed = engine.parseTemplate(template)
      const elements = engine.renderAnnotationForm(
        parsed,
        { unk: 'data' },
        {},
        jest.fn()
      )
      // pdf_viewer not registered, so skipped
      expect(elements.length).toBe(0)
    })
  })

  describe('validateData edge cases', () => {
    it('unknown field in data is skipped (L391)', () => {
      const fields = [mkField('known', 'text')]
      const template = mkTemplate(fields)
      const parsed = engine.parseTemplate(template)
      const result = engine.validateData(parsed, { known: 'v', unknown_field: 'x' })
      expect(result.valid).toBe(true)
    })

    it('label fallback to fieldName when label is missing (L384)', () => {
      const fields = [
        mkField('myfield', 'text', { label: undefined, required: true }),
      ]
      const template = mkTemplate(fields)
      const parsed = engine.parseTemplate(template)
      const result = engine.validateData(parsed, {})
      expect(result.valid).toBe(false)
      // Error message should use 'myfield' as fallback
      expect(result.errors.myfield[0]).toContain('myfield')
    })
  })

  describe('parseLLMResponse', () => {
    it('handles structured response format (L350-352)', () => {
      const template = {
        ...mkTemplate([mkField('text', 'text')]),
        llm_config: { response_format: 'structured' as const, prompt_template: '' },
      }
      const parsed = engine.parseTemplate(template)
      const result = engine.parseLLMResponse(parsed, 'structured output')
      expect(result).toHaveProperty('response')
    })

    it('text format with field_mapping maps response key (L357-359)', () => {
      const template = {
        ...mkTemplate([mkField('text', 'text')]),
        llm_config: {
          response_format: 'text' as const,
          prompt_template: '',
          field_mapping: { response: 'answer' },
        },
      }
      const parsed = engine.parseTemplate(template)
      const result = engine.parseLLMResponse(parsed, 'plain text')
      expect(result.answer).toBe('plain text')
    })

    it('json format without field_mapping returns parsed JSON directly', () => {
      const template = {
        ...mkTemplate([mkField('text', 'text')]),
        llm_config: {
          response_format: 'json' as const,
          prompt_template: '',
        },
      }
      const parsed = engine.parseTemplate(template)
      const result = engine.parseLLMResponse(parsed, '{"key": "val"}')
      expect(result.key).toBe('val')
    })

    it('throws when no llm_config (L275-277)', () => {
      const template = mkTemplate([mkField('text', 'text')])
      const parsed = engine.parseTemplate(template)
      expect(() => engine.parseLLMResponse(parsed, 'text')).toThrow(
        'Template does not have LLM configuration'
      )
    })
  })

  describe('generatePrompt', () => {
    it('handles conditional blocks (L283-290)', () => {
      const template = {
        ...mkTemplate([mkField('context', 'text')]),
        llm_config: {
          response_format: 'text' as const,
          prompt_template: '{{#if context}}Context: {{context}}{{/if}} Answer:',
        },
      }
      const parsed = engine.parseTemplate(template)

      // With context present
      const promptWith = engine.generatePrompt(parsed, { context: 'legal case' })
      expect(promptWith).toContain('Context: legal case')

      // Without context (falsy)
      const promptWithout = engine.generatePrompt(parsed, { context: '' })
      expect(promptWithout).not.toContain('Context:')
    })

    it('handles array iteration with #each (L297-311)', () => {
      const template = {
        ...mkTemplate([mkField('items', 'text')]),
        llm_config: {
          response_format: 'text' as const,
          prompt_template: 'Items: {{#each items}}{{@index}}: {{this}}\n{{/each}}',
        },
      }
      const parsed = engine.parseTemplate(template)
      const prompt = engine.generatePrompt(parsed, { items: ['apple', 'banana'] })
      expect(prompt).toContain('0: apple')
      expect(prompt).toContain('1: banana')
    })

    it('handles #each with non-array value', () => {
      const template = {
        ...mkTemplate([mkField('items', 'text')]),
        llm_config: {
          response_format: 'text' as const,
          prompt_template: 'Items: {{#each items}}{{this}}{{/each}}',
        },
      }
      const parsed = engine.parseTemplate(template)
      const prompt = engine.generatePrompt(parsed, { items: 'not-an-array' })
      expect(prompt).toContain('Items:')
    })

    it('throws when no llm_config (L275-277)', () => {
      const template = mkTemplate([mkField('text', 'text')])
      const parsed = engine.parseTemplate(template)
      expect(() => engine.generatePrompt(parsed, {})).toThrow(
        'Template does not have LLM configuration'
      )
    })
  })

  describe('parseTemplate', () => {
    it('throws when display_config references non-existent field (L106-110)', () => {
      const template = {
        id: 'test',
        name: 'test',
        version: '1.0',
        fields: [mkField('real', 'text')],
        display_config: {
          table_columns: ['real', 'ghost'],
          sort_field: 'real',
          sort_direction: 'asc' as const,
        },
      }
      expect(() => engine.parseTemplate(template)).toThrow(
        "Display column 'ghost' not found in template fields"
      )
    })

    it('tracks editable and required fields', () => {
      const fields = [
        mkField('edit', 'text', { required: true, display: { annotation: 'editable', table: 'column', creation: 'editable' } }),
        mkField('ro', 'text', { required: false, display: { annotation: 'readonly', table: 'column', creation: 'editable' } }),
      ]
      const template = mkTemplate(fields)
      const parsed = engine.parseTemplate(template)
      expect(parsed.requiredFields.has('edit')).toBe(true)
      expect(parsed.editableFields.has('edit')).toBe(true)
      expect(parsed.editableFields.has('ro')).toBe(false)
    })
  })
})

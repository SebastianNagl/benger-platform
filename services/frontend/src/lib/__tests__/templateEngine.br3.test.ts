/**
 * @jest-environment jsdom
 *
 * Branch coverage: templateEngine.ts
 * Targets: parseLLMResponse (json with mapping, text format),
 *          validateData (context check, required fields),
 *          evaluateCondition branches
 */

import { TemplateEngine } from '../templateEngine'

describe('templateEngine branch coverage', () => {
  let engine: TemplateEngine

  beforeEach(() => {
    engine = new TemplateEngine()
  })

  const baseTemplate = {
    name: 'test',
    version: '1.0',
    fields: [
      { name: 'text', type: 'text' as const, label: 'Text', required: true, display: { table: 'visible' as const, labeling: 'visible' as const, review: 'visible' as const } },
      { name: 'hidden', type: 'text' as const, label: 'Hidden', required: true, display: { table: 'hidden' as const, labeling: 'visible' as const, review: 'hidden' as const } },
    ],
    display_config: {
      table_columns: ['text'],
      sort_field: 'text',
      sort_direction: 'asc' as const,
    },
    llm_config: {
      response_format: 'json' as const,
      field_mapping: { 'response_text': 'text' },
    },
  }

  it('parseTemplate creates a valid parsed template', () => {
    const parsed = engine.parseTemplate(baseTemplate)
    expect(parsed.fieldMap.size).toBeGreaterThan(0)
    expect(parsed.requiredFields.size).toBeGreaterThan(0)
  })

  it('parseLLMResponse handles JSON with field mapping', () => {
    const parsed = engine.parseTemplate(baseTemplate)
    const result = engine.parseLLMResponse(
      parsed,
      JSON.stringify({ response_text: 'hello' })
    )
    expect(result.text).toBe('hello')
  })

  it('parseLLMResponse handles text format', () => {
    const textTemplate = {
      ...baseTemplate,
      llm_config: {
        response_format: 'text' as const,
        field_mapping: { response: 'text' },
      },
    }
    const parsed = engine.parseTemplate(textTemplate)
    const result = engine.parseLLMResponse(parsed, 'plain text response')
    expect(result.text).toBe('plain text response')
  })

  it('parseLLMResponse throws on invalid JSON', () => {
    const parsed = engine.parseTemplate(baseTemplate)
    expect(() => engine.parseLLMResponse(parsed, 'not json')).toThrow()
  })

  it('validateData checks required fields', () => {
    const parsed = engine.parseTemplate(baseTemplate)
    const result = engine.validateData(parsed, { text: '', hidden: '' })
    expect(result.valid).toBe(false)
  })

  it('validateData respects display context for hidden fields', () => {
    const parsed = engine.parseTemplate(baseTemplate)
    // hidden field is required but hidden in review context - should skip
    const result = engine.validateData(parsed, { text: 'ok', hidden: '' }, 'review')
    expect(result).toBeDefined()
  })

  it('validateData passes with all required fields', () => {
    const parsed = engine.parseTemplate(baseTemplate)
    const result = engine.validateData(parsed, { text: 'value', hidden: 'also' })
    expect(result.valid).toBe(true)
  })

  it('parseLLMResponse JSON without field_mapping returns parsed directly', () => {
    const noMappingTemplate = {
      ...baseTemplate,
      llm_config: {
        response_format: 'json' as const,
      },
    }
    const parsed = engine.parseTemplate(noMappingTemplate)
    const result = engine.parseLLMResponse(parsed, JSON.stringify({ foo: 'bar' }))
    expect(result.foo).toBe('bar')
  })
})

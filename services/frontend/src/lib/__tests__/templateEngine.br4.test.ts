/**
 * @jest-environment jsdom
 *
 * Branch coverage: templateEngine.ts
 * Targets: L444 (evaluateCondition default case),
 *          L549 (formatFieldValue null/undefined),
 *          L567-629 (various field type rendering via renderAnnotationForm)
 */

import { TemplateEngine } from '../templateEngine'

describe('templateEngine br4 - uncovered branches', () => {
  let engine: TemplateEngine

  beforeEach(() => {
    engine = new TemplateEngine()
  })

  const makeTemplate = (fields: any[]) => ({
    name: 'test',
    version: '1.0',
    fields,
    display_config: {
      table_columns: fields.map((f: any) => f.name),
      sort_field: fields[0]?.name || 'text',
      sort_direction: 'asc' as const,
    },
  })

  it('parseTemplate with multiple field types', () => {
    const template = makeTemplate([
      { name: 'text', type: 'text' as const, label: 'Text', required: true, display: { table: 'visible' as const, labeling: 'visible' as const, review: 'visible' as const } },
      { name: 'rich', type: 'rich_text' as const, label: 'Rich', required: false, display: { table: 'visible' as const, labeling: 'visible' as const, review: 'visible' as const } },
      { name: 'num', type: 'number' as const, label: 'Number', required: false, display: { table: 'visible' as const, labeling: 'visible' as const, review: 'visible' as const } },
      { name: 'dt', type: 'date' as const, label: 'Date', required: false, display: { table: 'visible' as const, labeling: 'visible' as const, review: 'visible' as const } },
      { name: 'cb', type: 'checkbox' as const, label: 'Checkbox', required: false, display: { table: 'visible' as const, labeling: 'visible' as const, review: 'visible' as const } },
      { name: 'rd', type: 'radio' as const, label: 'Radio', required: false, display: { table: 'visible' as const, labeling: 'visible' as const, review: 'visible' as const } },
      { name: 'file', type: 'file_upload' as const, label: 'File', required: false, display: { table: 'visible' as const, labeling: 'visible' as const, review: 'visible' as const } },
      { name: 'url', type: 'url' as const, label: 'URL', required: false, display: { table: 'visible' as const, labeling: 'visible' as const, review: 'visible' as const } },
      { name: 'email', type: 'email' as const, label: 'Email', required: false, display: { table: 'visible' as const, labeling: 'visible' as const, review: 'visible' as const } },
      { name: 'rating', type: 'rating' as const, label: 'Rating', required: false, display: { table: 'visible' as const, labeling: 'visible' as const, review: 'visible' as const } },
      { name: 'textarea', type: 'text_area' as const, label: 'Text Area', required: false, display: { table: 'visible' as const, labeling: 'visible' as const, review: 'visible' as const } },
    ])

    const parsed = engine.parseTemplate(template)
    expect(parsed.fieldMap.size).toBe(11)
    expect(parsed.requiredFields.has('text')).toBe(true)
  })

  it('renderAnnotationForm renders all field types', () => {
    const template = makeTemplate([
      { name: 'text', type: 'text' as const, label: 'Text', required: false, display: { table: 'visible' as const, labeling: 'visible' as const, review: 'visible' as const } },
      { name: 'rich', type: 'rich_text' as const, label: 'Rich', required: false, display: { table: 'visible' as const, labeling: 'visible' as const, review: 'visible' as const } },
      { name: 'num', type: 'number' as const, label: 'Number', required: false, display: { table: 'visible' as const, labeling: 'visible' as const, review: 'visible' as const } },
      { name: 'dt', type: 'date' as const, label: 'Date', required: false, display: { table: 'visible' as const, labeling: 'visible' as const, review: 'visible' as const } },
      { name: 'cb', type: 'checkbox' as const, label: 'Checkbox', required: false, display: { table: 'visible' as const, labeling: 'visible' as const, review: 'visible' as const } },
      { name: 'rd', type: 'radio' as const, label: 'Radio', required: false, display: { table: 'visible' as const, labeling: 'visible' as const, review: 'visible' as const } },
      { name: 'file', type: 'file_upload' as const, label: 'File', required: false, display: { table: 'visible' as const, labeling: 'visible' as const, review: 'visible' as const } },
      { name: 'url', type: 'url' as const, label: 'URL', required: false, display: { table: 'visible' as const, labeling: 'visible' as const, review: 'visible' as const } },
    ])

    const parsed = engine.parseTemplate(template)
    const form = engine.renderAnnotationForm(
      parsed,
      { text: 'hello', rich: '<b>bold</b>', num: 42, dt: '2026-01-01', cb: true, rd: 'opt1', file: 'doc.pdf', url: 'https://example.com' },
      jest.fn(),
      'labeling',
      false
    )
    expect(form).toBeTruthy()
  })

  it('validateData returns false for missing required field', () => {
    const template = makeTemplate([
      { name: 'text', type: 'text' as const, label: 'Text', required: true, display: { table: 'visible' as const, labeling: 'visible' as const, review: 'visible' as const } },
    ])
    const parsed = engine.parseTemplate(template)
    const result = engine.validateData(parsed, {}, 'labeling')
    expect(result.valid).toBe(false)
  })

  it('validateData skips non-visible fields in given context', () => {
    const template = makeTemplate([
      { name: 'text', type: 'text' as const, label: 'Text', required: true, display: { table: 'visible' as const, labeling: 'hidden' as const, review: 'visible' as const } },
    ])
    const parsed = engine.parseTemplate(template)
    // Field is hidden in labeling context, so should not be required
    const result = engine.validateData(parsed, {}, 'labeling')
    expect(result.valid).toBe(true)
  })

  it('parseLLMResponse handles text format', () => {
    const template = {
      ...makeTemplate([
        { name: 'text', type: 'text' as const, label: 'Text', required: false, display: { table: 'visible' as const, labeling: 'visible' as const, review: 'visible' as const } },
      ]),
      llm_config: { response_format: 'text' as const },
    }
    const parsed = engine.parseTemplate(template)
    const result = engine.parseLLMResponse(parsed, 'plain text response')
    expect(result).toBeTruthy()
  })

  it('parseLLMResponse handles JSON with field mapping', () => {
    const template = {
      ...makeTemplate([
        { name: 'text', type: 'text' as const, label: 'Text', required: false, display: { table: 'visible' as const, labeling: 'visible' as const, review: 'visible' as const } },
      ]),
      llm_config: {
        response_format: 'json' as const,
        field_mapping: { response_text: 'text' },
      },
    }
    const parsed = engine.parseTemplate(template)
    const result = engine.parseLLMResponse(
      parsed,
      JSON.stringify({ response_text: 'mapped value' })
    )
    expect(result.text).toBe('mapped value')
  })

  it('parseLLMResponse throws on invalid JSON', () => {
    const template = {
      ...makeTemplate([
        { name: 'text', type: 'text' as const, label: 'Text', required: false, display: { table: 'visible' as const, labeling: 'visible' as const, review: 'visible' as const } },
      ]),
      llm_config: {
        response_format: 'json' as const,
        field_mapping: {},
      },
    }
    const parsed = engine.parseTemplate(template)
    expect(() => engine.parseLLMResponse(parsed, 'not json')).toThrow(
      'Failed to parse JSON response'
    )
  })

  it('generatePrompt creates a prompt string', () => {
    const template = {
      ...makeTemplate([
        { name: 'text', type: 'text' as const, label: 'Text', required: false, display: { table: 'visible' as const, labeling: 'visible' as const, review: 'visible' as const } },
      ]),
      llm_config: {
        response_format: 'json' as const,
        prompt_template: 'Answer the following: {{text}}',
      },
    }
    const parsed = engine.parseTemplate(template)
    const prompt = engine.generatePrompt(parsed, { text: 'What is 2+2?' })
    expect(prompt).toContain('What is 2+2?')
  })
})

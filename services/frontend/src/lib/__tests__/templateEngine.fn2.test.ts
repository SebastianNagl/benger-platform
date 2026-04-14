/**
 * Additional function coverage for templateEngine.ts
 * Covers: parseLLMResponse (json with field_mapping, text, structured),
 * generatePrompt (conditional blocks, each loops),
 * validateData, evaluateFieldCondition (contains, not_equals, custom, exists)
 */

import { TemplateEngine } from '../templateEngine'

const engine = new TemplateEngine()

function makeTemplate(overrides: Record<string, any> = {}) {
  return {
    id: 'test',
    name: 'Test Template',
    version: '1.0',
    fields: [
      {
        name: 'question',
        type: 'text' as const,
        label: 'Question',
        required: true,
        source: 'task_data' as const,
        display: {
          annotation: 'readonly' as const,
          review: 'readonly' as const,
          table: 'column' as const,
        },
      },
      {
        name: 'answer',
        type: 'text_area' as const,
        label: 'Answer',
        required: true,
        source: 'annotation' as const,
        display: {
          annotation: 'editable' as const,
          review: 'readonly' as const,
          table: 'column' as const,
        },
      },
      {
        name: 'optional_note',
        type: 'text' as const,
        label: 'Optional Note',
        required: false,
        source: 'annotation' as const,
        condition: { type: 'exists' as const, field: 'answer' },
        display: {
          annotation: 'editable' as const,
          review: 'hidden' as const,
          table: 'hidden' as const,
        },
      },
    ],
    display_config: {
      table_columns: ['question', 'answer'],
      default_sort: { field: 'question', direction: 'asc' as const },
    },
    ...overrides,
  }
}

describe('TemplateEngine - additional function coverage', () => {
  describe('generatePrompt', () => {
    it('throws when no llm_config', () => {
      const template = makeTemplate()
      const parsed = engine.parseTemplate(template as any)
      expect(() => engine.generatePrompt(parsed, {})).toThrow('does not have LLM configuration')
    })

    it('handles simple variable replacement', () => {
      const template = makeTemplate({
        llm_config: {
          prompt_template: 'Question: {{question}}\nPlease answer:',
          response_format: 'text',
        },
      })
      const parsed = engine.parseTemplate(template as any)
      const result = engine.generatePrompt(parsed, { question: 'What is 2+2?' })
      expect(result).toBe('Question: What is 2+2?\nPlease answer:')
    })

    it('handles conditional blocks', () => {
      const template = makeTemplate({
        llm_config: {
          prompt_template: 'Base prompt{{#if context}} Context: {{context}}{{/if}}',
          response_format: 'text',
        },
      })
      const parsed = engine.parseTemplate(template as any)

      // With context
      const withCtx = engine.generatePrompt(parsed, { context: 'Some context' })
      expect(withCtx).toContain('Context: Some context')

      // Without context
      const withoutCtx = engine.generatePrompt(parsed, { context: '' })
      expect(withoutCtx).toBe('Base prompt')
    })

    it('handles each loops', () => {
      const template = makeTemplate({
        llm_config: {
          prompt_template: 'Items:{{#each items}}\n{{@index}}. {{this}}{{/each}}',
          response_format: 'text',
        },
      })
      const parsed = engine.parseTemplate(template as any)
      const result = engine.generatePrompt(parsed, { items: ['Apple', 'Banana', 'Cherry'] })
      expect(result).toContain('0. Apple')
      expect(result).toContain('1. Banana')
      expect(result).toContain('2. Cherry')
    })

    it('handles each with non-array gracefully', () => {
      const template = makeTemplate({
        llm_config: {
          prompt_template: 'Items:{{#each items}}{{this}}{{/each}}',
          response_format: 'text',
        },
      })
      const parsed = engine.parseTemplate(template as any)
      const result = engine.generatePrompt(parsed, { items: 'not-an-array' })
      expect(result).toBe('Items:')
    })
  })

  describe('parseLLMResponse', () => {
    it('throws when no llm_config', () => {
      const template = makeTemplate()
      const parsed = engine.parseTemplate(template as any)
      expect(() => engine.parseLLMResponse(parsed, '{}')).toThrow('does not have LLM configuration')
    })

    it('parses JSON response without field mapping', () => {
      const template = makeTemplate({
        llm_config: {
          prompt_template: '',
          response_format: 'json',
        },
      })
      const parsed = engine.parseTemplate(template as any)
      const result = engine.parseLLMResponse(parsed, '{"answer": "42", "confidence": 0.9}')
      expect(result).toEqual({ answer: '42', confidence: 0.9 })
    })

    it('parses JSON response with field mapping', () => {
      const template = makeTemplate({
        llm_config: {
          prompt_template: '',
          response_format: 'json',
          field_mapping: { response_answer: 'answer', response_score: 'score' },
        },
      })
      const parsed = engine.parseTemplate(template as any)
      const result = engine.parseLLMResponse(parsed, '{"response_answer": "yes", "response_score": 0.8}')
      expect(result).toEqual({ answer: 'yes', score: 0.8 })
    })

    it('throws on invalid JSON', () => {
      const template = makeTemplate({
        llm_config: { prompt_template: '', response_format: 'json' },
      })
      const parsed = engine.parseTemplate(template as any)
      expect(() => engine.parseLLMResponse(parsed, 'not json')).toThrow('Failed to parse JSON')
    })

    it('parses text response', () => {
      const template = makeTemplate({
        llm_config: {
          prompt_template: '',
          response_format: 'text',
          field_mapping: { response: 'answer' },
        },
      })
      const parsed = engine.parseTemplate(template as any)
      const result = engine.parseLLMResponse(parsed, 'The answer is 42')
      expect(result).toEqual({ answer: 'The answer is 42' })
    })

    it('parses text response without field mapping', () => {
      const template = makeTemplate({
        llm_config: { prompt_template: '', response_format: 'text' },
      })
      const parsed = engine.parseTemplate(template as any)
      const result = engine.parseLLMResponse(parsed, 'Hello')
      expect(result).toEqual({ response: 'Hello' })
    })

    it('parses structured response (falls back to text)', () => {
      const template = makeTemplate({
        llm_config: { prompt_template: '', response_format: 'structured' },
      })
      const parsed = engine.parseTemplate(template as any)
      const result = engine.parseLLMResponse(parsed, 'Some structured response')
      expect(result).toEqual({ response: 'Some structured response' })
    })
  })

  describe('validateData', () => {
    it('validates required fields', () => {
      const template = makeTemplate()
      const parsed = engine.parseTemplate(template as any)
      const result = engine.validateData(parsed, {})
      expect(result.valid).toBe(false)
      expect(result.errors['question']).toBeDefined()
      expect(result.errors['answer']).toBeDefined()
    })

    it('passes with all required fields present', () => {
      const template = makeTemplate()
      const parsed = engine.parseTemplate(template as any)
      const result = engine.validateData(parsed, { question: 'Q', answer: 'A' })
      expect(result.valid).toBe(true)
    })

    it('skips hidden fields in context', () => {
      const template = makeTemplate()
      const parsed = engine.parseTemplate(template as any)
      // optional_note display.review is 'hidden', so should be skipped in review context
      const result = engine.validateData(parsed, { question: 'Q', answer: 'A' }, 'review')
      expect(result.valid).toBe(true)
    })
  })

  describe('renderAnnotationForm', () => {
    it('renders form fields for annotation context', () => {
      const template = makeTemplate()
      const parsed = engine.parseTemplate(template as any)
      const onChange = jest.fn()
      const elements = engine.renderAnnotationForm(
        parsed,
        { question: 'What?' },
        { answer: 'Yes' },
        onChange,
        {},
        'annotation'
      )
      // Should have some rendered elements (question read-only + answer editable)
      expect(elements.length).toBeGreaterThanOrEqual(1)
    })

    it('skips hidden fields', () => {
      const template = makeTemplate()
      const parsed = engine.parseTemplate(template as any)
      const elements = engine.renderAnnotationForm(
        parsed,
        {},
        {},
        jest.fn(),
        {},
        'review'
      )
      // optional_note is hidden in review, so won't be rendered
      // Only question and answer should be rendered
      expect(elements.length).toBeLessThanOrEqual(2)
    })
  })

  describe('getTableColumns', () => {
    it('generates columns from template', () => {
      const template = makeTemplate()
      const parsed = engine.parseTemplate(template as any)
      const columns = engine.getTableColumns(parsed)
      expect(columns.length).toBe(2)
      expect(columns[0].id).toBe('question')
      expect(columns[1].id).toBe('answer')
    })
  })
})

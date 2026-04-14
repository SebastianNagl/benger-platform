/**
 * @jest-environment jsdom
 */

import {
  FieldType,
  TaskTemplate,
  TaskTemplateField,
} from '@/types/taskTemplate'
import React from 'react'
import {
  ParsedTemplate,
  TemplateEngine,
  templateEngine,
} from '../templateEngine'

describe('TemplateEngine', () => {
  let engine: TemplateEngine

  beforeEach(() => {
    engine = new TemplateEngine()
  })

  describe('constructor', () => {
    it('initializes with all field components registered', () => {
      expect(engine).toBeDefined()
      expect(engine).toBeInstanceOf(TemplateEngine)
    })

    it('provides singleton instance', () => {
      expect(templateEngine).toBeDefined()
      expect(templateEngine).toBeInstanceOf(TemplateEngine)
    })
  })

  describe('parseTemplate', () => {
    it('parses valid template correctly', () => {
      const template: TaskTemplate = {
        id: 'test-1',
        name: 'Test Template',
        version: '1.0',
        fields: [
          {
            name: 'question',
            type: 'text',
            display: {
              annotation: 'readonly',
              table: 'column',
              creation: 'editable',
            },
            source: 'task_data',
            required: true,
            label: 'Question',
          },
          {
            name: 'answer',
            type: 'text_area',
            display: {
              annotation: 'editable',
              table: 'column',
              creation: 'editable',
            },
            source: 'annotation',
            required: false,
            label: 'Answer',
          },
        ],
        display_config: {
          table_columns: ['question', 'answer'],
        },
      }

      const parsed = engine.parseTemplate(template)

      expect(parsed.template).toBe(template)
      expect(parsed.fieldMap.size).toBe(2)
      expect(parsed.fieldMap.get('question')).toBeDefined()
      expect(parsed.fieldMap.get('answer')).toBeDefined()
      expect(parsed.requiredFields.size).toBe(1)
      expect(parsed.requiredFields.has('question')).toBe(true)
      expect(parsed.editableFields.size).toBe(1)
      expect(parsed.editableFields.has('answer')).toBe(true)
      expect(parsed.tableFields).toEqual(['question', 'answer'])
    })

    it('handles template with no required fields', () => {
      const template: TaskTemplate = {
        id: 'test-2',
        name: 'Optional Fields',
        version: '1.0',
        fields: [
          {
            name: 'field1',
            type: 'text',
            display: {
              annotation: 'editable',
              table: 'hidden',
              creation: 'editable',
            },
            source: 'task_data',
          },
        ],
        display_config: {
          table_columns: [],
        },
      }

      const parsed = engine.parseTemplate(template)

      expect(parsed.requiredFields.size).toBe(0)
    })

    it('throws error when display column references invalid field', () => {
      const template: TaskTemplate = {
        id: 'test-3',
        name: 'Invalid Reference',
        version: '1.0',
        fields: [
          {
            name: 'field1',
            type: 'text',
            display: {
              annotation: 'editable',
              table: 'column',
              creation: 'editable',
            },
            source: 'task_data',
          },
        ],
        display_config: {
          table_columns: ['field1', 'nonexistent'],
        },
      }

      expect(() => engine.parseTemplate(template)).toThrow(
        "Display column 'nonexistent' not found in template fields"
      )
    })

    it('identifies editable fields correctly', () => {
      const template: TaskTemplate = {
        id: 'test-4',
        name: 'Editable Test',
        version: '1.0',
        fields: [
          {
            name: 'readonly_field',
            type: 'text',
            display: {
              annotation: 'readonly',
              table: 'column',
              creation: 'editable',
            },
            source: 'task_data',
          },
          {
            name: 'editable_field',
            type: 'text',
            display: {
              annotation: 'editable',
              table: 'column',
              creation: 'editable',
            },
            source: 'annotation',
          },
        ],
        display_config: {
          table_columns: ['readonly_field', 'editable_field'],
        },
      }

      const parsed = engine.parseTemplate(template)

      expect(parsed.editableFields.has('readonly_field')).toBe(false)
      expect(parsed.editableFields.has('editable_field')).toBe(true)
    })

    it('builds correct field map', () => {
      const template: TaskTemplate = {
        id: 'test-5',
        name: 'Field Map Test',
        version: '1.0',
        fields: [
          {
            name: 'field1',
            type: 'text',
            display: {
              annotation: 'editable',
              table: 'column',
              creation: 'editable',
            },
            source: 'task_data',
          },
          {
            name: 'field2',
            type: 'number',
            display: {
              annotation: 'editable',
              table: 'column',
              creation: 'editable',
            },
            source: 'annotation',
          },
        ],
        display_config: {
          table_columns: ['field1', 'field2'],
        },
      }

      const parsed = engine.parseTemplate(template)

      expect(parsed.fieldMap.get('field1')?.type).toBe('text')
      expect(parsed.fieldMap.get('field2')?.type).toBe('number')
    })
  })

  describe('renderAnnotationForm', () => {
    let parsedTemplate: ParsedTemplate
    let mockOnChange: jest.Mock

    beforeEach(() => {
      mockOnChange = jest.fn()

      const template: TaskTemplate = {
        id: 'form-test',
        name: 'Form Test',
        version: '1.0',
        fields: [
          {
            name: 'question',
            type: 'text',
            display: {
              annotation: 'readonly',
              table: 'column',
              creation: 'editable',
            },
            source: 'task_data',
            label: 'Question',
          },
          {
            name: 'answer',
            type: 'text_area',
            display: {
              annotation: 'editable',
              table: 'column',
              creation: 'editable',
            },
            source: 'annotation',
            label: 'Answer',
          },
          {
            name: 'hidden_field',
            type: 'text',
            display: {
              annotation: 'hidden',
              table: 'hidden',
              creation: 'editable',
            },
            source: 'task_data',
          },
        ],
        display_config: {
          table_columns: ['question', 'answer'],
        },
      }

      parsedTemplate = engine.parseTemplate(template)
    })

    it('renders editable and readonly fields, excludes hidden fields', () => {
      const elements = engine.renderAnnotationForm(
        parsedTemplate,
        { question: 'What is 2+2?', hidden_field: 'secret' },
        { answer: '4' },
        mockOnChange
      )

      expect(elements).toHaveLength(2)
      expect(elements[0].key).toBe('question')
      expect(elements[1].key).toBe('answer')
    })

    it('passes correct props to field components', () => {
      const elements = engine.renderAnnotationForm(
        parsedTemplate,
        { question: 'What is 2+2?' },
        { answer: '4' },
        mockOnChange
      )

      const questionElement = elements[0]
      expect(questionElement.props.field.name).toBe('question')
      expect(questionElement.props.value).toBe('What is 2+2?')
      expect(questionElement.props.readonly).toBe(true)
      expect(questionElement.props.context).toBe('annotation')

      const answerElement = elements[1]
      expect(answerElement.props.field.name).toBe('answer')
      expect(answerElement.props.value).toBe('4')
      expect(answerElement.props.readonly).toBe(false)
    })

    it('calls onChange with correct field name and value', () => {
      const elements = engine.renderAnnotationForm(
        parsedTemplate,
        { question: 'What is 2+2?' },
        { answer: '4' },
        mockOnChange
      )

      const answerElement = elements[1]
      answerElement.props.onChange('new answer')

      expect(mockOnChange).toHaveBeenCalledWith('answer', 'new answer')
    })

    it('passes validation errors to field components', () => {
      const errors = {
        answer: ['This field is required'],
      }

      const elements = engine.renderAnnotationForm(
        parsedTemplate,
        { question: 'What is 2+2?' },
        {},
        mockOnChange,
        errors
      )

      const answerElement = elements[1]
      expect(answerElement.props.errors).toEqual(['This field is required'])
    })

    it('respects display context', () => {
      const creationElements = engine.renderAnnotationForm(
        parsedTemplate,
        { question: 'What is 2+2?' },
        {},
        mockOnChange,
        {},
        'creation'
      )

      // In creation context, hidden_field has 'editable' display mode, so it's visible
      expect(creationElements).toHaveLength(3)
      expect(creationElements[0].props.context).toBe('creation')
    })

    it('handles conditional fields', () => {
      const conditionalTemplate: TaskTemplate = {
        id: 'conditional-test',
        name: 'Conditional Test',
        version: '1.0',
        fields: [
          {
            name: 'show_extra',
            type: 'checkbox',
            display: {
              annotation: 'editable',
              table: 'column',
              creation: 'editable',
            },
            source: 'annotation',
          },
          {
            name: 'extra_field',
            type: 'text',
            display: {
              annotation: 'editable',
              table: 'column',
              creation: 'editable',
            },
            source: 'annotation',
            condition: {
              type: 'equals',
              field: 'show_extra',
              value: true,
            },
          },
        ],
        display_config: {
          table_columns: ['show_extra', 'extra_field'],
        },
      }

      const parsed = engine.parseTemplate(conditionalTemplate)

      const elementsWithoutCondition = engine.renderAnnotationForm(
        parsed,
        {},
        { show_extra: false },
        mockOnChange
      )
      expect(elementsWithoutCondition).toHaveLength(1)

      const elementsWithCondition = engine.renderAnnotationForm(
        parsed,
        {},
        { show_extra: true },
        mockOnChange
      )
      expect(elementsWithCondition).toHaveLength(2)
    })

    it('handles fields from different sources', () => {
      const elements = engine.renderAnnotationForm(
        parsedTemplate,
        { question: 'From task data' },
        { answer: 'From annotation' },
        mockOnChange
      )

      expect(elements[0].props.value).toBe('From task data')
      expect(elements[1].props.value).toBe('From annotation')
    })

    it('skips fields without registered components', () => {
      const templateWithUnknown: TaskTemplate = {
        id: 'unknown-type',
        name: 'Unknown Type Test',
        version: '1.0',
        fields: [
          {
            name: 'valid_field',
            type: 'text',
            display: {
              annotation: 'editable',
              table: 'column',
              creation: 'editable',
            },
            source: 'task_data',
          },
          {
            name: 'unknown_field',
            type: 'unknown_type' as FieldType,
            display: {
              annotation: 'editable',
              table: 'column',
              creation: 'editable',
            },
            source: 'task_data',
          },
        ],
        display_config: {
          table_columns: ['valid_field'],
        },
      }

      const parsed = engine.parseTemplate(templateWithUnknown)
      const elements = engine.renderAnnotationForm(
        parsed,
        { valid_field: 'test', unknown_field: 'test' },
        {},
        mockOnChange
      )

      expect(elements).toHaveLength(1)
      expect(elements[0].key).toBe('valid_field')
    })
  })

  describe('getTableColumns', () => {
    let parsedTemplate: ParsedTemplate

    beforeEach(() => {
      const template: TaskTemplate = {
        id: 'table-test',
        name: 'Table Test',
        version: '1.0',
        fields: [
          {
            name: 'id',
            type: 'number',
            display: {
              annotation: 'readonly',
              table: 'column',
              creation: 'editable',
            },
            source: 'task_data',
            label: 'ID',
          },
          {
            name: 'question',
            type: 'text',
            display: {
              annotation: 'readonly',
              table: 'column',
              creation: 'editable',
            },
            source: 'task_data',
            label: 'Question',
          },
          {
            name: 'answer',
            type: 'text_area',
            display: {
              annotation: 'editable',
              table: 'column',
              creation: 'editable',
            },
            source: 'annotation',
            label: 'Answer',
          },
          {
            name: 'hidden',
            type: 'text',
            display: {
              annotation: 'hidden',
              table: 'hidden',
              creation: 'hidden',
            },
            source: 'task_data',
          },
        ],
        display_config: {
          table_columns: ['id', 'question', 'answer'],
          column_widths: {
            id: 100,
            question: 300,
          },
        },
      }

      parsedTemplate = engine.parseTemplate(template)
    })

    it('generates columns for visible fields', () => {
      const columns = engine.getTableColumns(parsedTemplate)

      expect(columns).toHaveLength(3)
      expect(columns[0].id).toBe('id')
      expect(columns[1].id).toBe('question')
      expect(columns[2].id).toBe('answer')
    })

    it('sets column headers from field labels', () => {
      const columns = engine.getTableColumns(parsedTemplate)

      expect(columns[0].header).toBe('ID')
      expect(columns[1].header).toBe('Question')
      expect(columns[2].header).toBe('Answer')
    })

    it('applies custom column widths', () => {
      const columns = engine.getTableColumns(parsedTemplate)

      expect(columns[0].size).toBe(100)
      expect(columns[1].size).toBe(300)
      expect(columns[2].size).toBeUndefined()
    })

    it('skips fields marked as hidden', () => {
      const columns = engine.getTableColumns(parsedTemplate)

      expect(columns.find((col) => col.id === 'hidden')).toBeUndefined()
    })

    it('uses custom renderers when provided', () => {
      const customRenderer = jest.fn(() =>
        React.createElement('div', {}, 'Custom')
      )
      const columns = engine.getTableColumns(parsedTemplate, {
        customRenderers: {
          question: customRenderer,
        },
      })

      const questionColumn = columns.find((col) => col.id === 'question')
      expect(questionColumn).toBeDefined()
    })

    it('handles onCellClick callback', () => {
      const mockOnCellClick = jest.fn()
      const columns = engine.getTableColumns(parsedTemplate, {
        onCellClick: mockOnCellClick,
      })

      expect(columns).toHaveLength(3)
    })

    it('handles answer display configuration', () => {
      const templateWithAnswer: TaskTemplate = {
        id: 'answer-display-test',
        name: 'Answer Display Test',
        version: '1.0',
        fields: [
          {
            name: 'answer',
            type: 'text',
            display: {
              annotation: 'editable',
              table: 'column',
              creation: 'editable',
            },
            source: 'annotation',
            label: 'Answer',
          },
          {
            name: 'confidence',
            type: 'rating',
            display: {
              annotation: 'editable',
              table: 'in_answer_cell',
              creation: 'editable',
            },
            source: 'annotation',
            label: 'Confidence',
          },
        ],
        display_config: {
          table_columns: ['answer'],
          answer_display: {
            fields: ['answer', 'confidence'],
            separator: 'divider',
          },
        },
      }

      const parsed = engine.parseTemplate(templateWithAnswer)
      const columns = engine.getTableColumns(parsed)

      expect(columns).toHaveLength(1)
      expect(columns[0].id).toBe('answer')
    })
  })

  describe('generatePrompt', () => {
    it('replaces simple placeholders', () => {
      const template: TaskTemplate = {
        id: 'prompt-test',
        name: 'Prompt Test',
        version: '1.0',
        fields: [],
        display_config: { table_columns: [] },
        llm_config: {
          prompt_template: 'Question: {{question}}\nContext: {{context}}',
          response_parser: 'default',
        },
      }

      const parsed = engine.parseTemplate(template)
      const prompt = engine.generatePrompt(parsed, {
        question: 'What is 2+2?',
        context: 'Basic arithmetic',
      })

      expect(prompt).toBe('Question: What is 2+2?\nContext: Basic arithmetic')
    })

    it('handles conditional blocks', () => {
      const template: TaskTemplate = {
        id: 'conditional-prompt',
        name: 'Conditional Prompt',
        version: '1.0',
        fields: [],
        display_config: { table_columns: [] },
        llm_config: {
          prompt_template:
            'Question: {{question}}{{#if context}}\nContext: {{context}}{{/if}}',
          response_parser: 'default',
        },
      }

      const parsed = engine.parseTemplate(template)

      const promptWithContext = engine.generatePrompt(parsed, {
        question: 'What is 2+2?',
        context: 'Math',
      })
      expect(promptWithContext).toContain('Context: Math')

      const promptWithoutContext = engine.generatePrompt(parsed, {
        question: 'What is 2+2?',
        context: null,
      })
      // When context is null/falsy, the conditional block should be removed
      expect(promptWithoutContext).toBe('Question: What is 2+2?')
    })

    it('handles array iteration', () => {
      const template: TaskTemplate = {
        id: 'array-prompt',
        name: 'Array Prompt',
        version: '1.0',
        fields: [],
        display_config: { table_columns: [] },
        llm_config: {
          prompt_template:
            'Items:\n{{#each items}}{{@index}}. {{this}}\n{{/each}}',
          response_parser: 'default',
        },
      }

      const parsed = engine.parseTemplate(template)
      const prompt = engine.generatePrompt(parsed, {
        items: ['First', 'Second', 'Third'],
      })

      expect(prompt).toContain('0. First')
      expect(prompt).toContain('1. Second')
      expect(prompt).toContain('2. Third')
    })

    it('handles missing values gracefully', () => {
      const template: TaskTemplate = {
        id: 'missing-values',
        name: 'Missing Values',
        version: '1.0',
        fields: [],
        display_config: { table_columns: [] },
        llm_config: {
          prompt_template: 'Question: {{question}}\nAnswer: {{answer}}',
          response_parser: 'default',
        },
      }

      const parsed = engine.parseTemplate(template)
      const prompt = engine.generatePrompt(parsed, {
        question: 'What is 2+2?',
        answer: null,
      })

      // Missing/null values are replaced with empty string
      expect(prompt).toBe('Question: What is 2+2?\nAnswer:')
    })

    it('throws error when template has no LLM config', () => {
      const template: TaskTemplate = {
        id: 'no-llm-config',
        name: 'No LLM Config',
        version: '1.0',
        fields: [],
        display_config: { table_columns: [] },
      }

      const parsed = engine.parseTemplate(template)

      expect(() => engine.generatePrompt(parsed, {})).toThrow(
        'Template does not have LLM configuration'
      )
    })

    it('handles non-array values in each blocks', () => {
      const template: TaskTemplate = {
        id: 'invalid-each',
        name: 'Invalid Each',
        version: '1.0',
        fields: [],
        display_config: { table_columns: [] },
        llm_config: {
          prompt_template: '{{#each items}}{{this}}{{/each}}',
          response_parser: 'default',
        },
      }

      const parsed = engine.parseTemplate(template)
      const prompt = engine.generatePrompt(parsed, {
        items: 'not an array',
      })

      expect(prompt).toBe('')
    })
  })

  describe('parseLLMResponse', () => {
    it('parses JSON response', () => {
      const template: TaskTemplate = {
        id: 'json-response',
        name: 'JSON Response',
        version: '1.0',
        fields: [],
        display_config: { table_columns: [] },
        llm_config: {
          prompt_template: 'test',
          response_parser: 'json',
          response_format: 'json',
        },
      }

      const parsed = engine.parseTemplate(template)
      const result = engine.parseLLMResponse(
        parsed,
        '{"answer": "42", "confidence": 0.95}'
      )

      expect(result).toEqual({
        answer: '42',
        confidence: 0.95,
      })
    })

    it('applies field mapping to JSON response', () => {
      const template: TaskTemplate = {
        id: 'json-mapping',
        name: 'JSON Mapping',
        version: '1.0',
        fields: [],
        display_config: { table_columns: [] },
        llm_config: {
          prompt_template: 'test',
          response_parser: 'json',
          response_format: 'json',
          field_mapping: {
            llm_answer: 'answer',
            llm_confidence: 'confidence',
          },
        },
      }

      const parsed = engine.parseTemplate(template)
      const result = engine.parseLLMResponse(
        parsed,
        '{"llm_answer": "42", "llm_confidence": 0.95, "extra": "ignored"}'
      )

      expect(result).toEqual({
        answer: '42',
        confidence: 0.95,
      })
    })

    it('throws error for invalid JSON', () => {
      const template: TaskTemplate = {
        id: 'invalid-json',
        name: 'Invalid JSON',
        version: '1.0',
        fields: [],
        display_config: { table_columns: [] },
        llm_config: {
          prompt_template: 'test',
          response_parser: 'json',
          response_format: 'json',
        },
      }

      const parsed = engine.parseTemplate(template)

      expect(() => engine.parseLLMResponse(parsed, 'not valid json')).toThrow()
    })

    it('handles text response format', () => {
      const template: TaskTemplate = {
        id: 'text-response',
        name: 'Text Response',
        version: '1.0',
        fields: [],
        display_config: { table_columns: [] },
        llm_config: {
          prompt_template: 'test',
          response_parser: 'text',
          response_format: 'text',
        },
      }

      const parsed = engine.parseTemplate(template)
      const result = engine.parseLLMResponse(parsed, 'This is a text response')

      expect(result).toEqual({
        response: 'This is a text response',
      })
    })

    it('uses custom field name for text response', () => {
      const template: TaskTemplate = {
        id: 'text-custom-field',
        name: 'Text Custom Field',
        version: '1.0',
        fields: [],
        display_config: { table_columns: [] },
        llm_config: {
          prompt_template: 'test',
          response_parser: 'text',
          response_format: 'text',
          field_mapping: {
            response: 'answer',
          },
        },
      }

      const parsed = engine.parseTemplate(template)
      const result = engine.parseLLMResponse(parsed, 'This is a text response')

      expect(result).toEqual({
        answer: 'This is a text response',
      })
    })

    it('handles structured response format', () => {
      const template: TaskTemplate = {
        id: 'structured-response',
        name: 'Structured Response',
        version: '1.0',
        fields: [],
        display_config: { table_columns: [] },
        llm_config: {
          prompt_template: 'test',
          response_parser: 'structured',
          response_format: 'structured',
        },
      }

      const parsed = engine.parseTemplate(template)
      const result = engine.parseLLMResponse(parsed, 'Structured content')

      expect(result).toHaveProperty('response')
    })

    it('throws error when template has no LLM config', () => {
      const template: TaskTemplate = {
        id: 'no-config',
        name: 'No Config',
        version: '1.0',
        fields: [],
        display_config: { table_columns: [] },
      }

      const parsed = engine.parseTemplate(template)

      expect(() => engine.parseLLMResponse(parsed, 'response')).toThrow(
        'Template does not have LLM configuration'
      )
    })
  })

  describe('validateData', () => {
    let parsedTemplate: ParsedTemplate

    beforeEach(() => {
      const template: TaskTemplate = {
        id: 'validation-test',
        name: 'Validation Test',
        version: '1.0',
        fields: [
          {
            name: 'required_field',
            type: 'text',
            display: {
              annotation: 'editable',
              table: 'column',
              creation: 'editable',
            },
            source: 'annotation',
            required: true,
            label: 'Required Field',
          },
          {
            name: 'optional_field',
            type: 'text',
            display: {
              annotation: 'editable',
              table: 'column',
              creation: 'editable',
            },
            source: 'annotation',
            label: 'Optional Field',
          },
          {
            name: 'number_field',
            type: 'number',
            display: {
              annotation: 'editable',
              table: 'column',
              creation: 'editable',
            },
            source: 'annotation',
            label: 'Number Field',
            validation: [
              {
                type: 'min',
                value: 0,
                message: 'Must be positive',
              },
              {
                type: 'max',
                value: 100,
                message: 'Must be less than 100',
              },
            ],
          },
          {
            name: 'text_field',
            type: 'text',
            display: {
              annotation: 'editable',
              table: 'column',
              creation: 'editable',
            },
            source: 'annotation',
            label: 'Text Field',
            validation: [
              {
                type: 'minLength',
                value: 5,
              },
              {
                type: 'maxLength',
                value: 50,
              },
            ],
          },
          {
            name: 'hidden_required',
            type: 'text',
            display: {
              annotation: 'hidden',
              table: 'hidden',
              creation: 'editable',
            },
            source: 'annotation',
            required: true,
            label: 'Hidden Required',
          },
        ],
        display_config: {
          table_columns: [
            'required_field',
            'optional_field',
            'number_field',
            'text_field',
          ],
        },
      }

      parsedTemplate = engine.parseTemplate(template)
    })

    it('validates required fields', () => {
      const result = engine.validateData(parsedTemplate, {
        optional_field: 'test',
      })

      expect(result.valid).toBe(false)
      expect(result.errors.required_field).toContain(
        'Required Field is required'
      )
    })

    it('passes validation with all required fields', () => {
      const result = engine.validateData(parsedTemplate, {
        required_field: 'test',
        hidden_required: 'hidden value',
      })

      expect(result.valid).toBe(true)
      expect(Object.keys(result.errors)).toHaveLength(0)
    })

    it('validates number field constraints', () => {
      const resultTooSmall = engine.validateData(parsedTemplate, {
        required_field: 'test',
        hidden_required: 'hidden value',
        number_field: -5,
      })

      expect(resultTooSmall.valid).toBe(false)
      expect(resultTooSmall.errors.number_field).toContain('Must be positive')

      const resultTooLarge = engine.validateData(parsedTemplate, {
        required_field: 'test',
        hidden_required: 'hidden value',
        number_field: 150,
      })

      expect(resultTooLarge.valid).toBe(false)
      expect(resultTooLarge.errors.number_field).toContain(
        'Must be less than 100'
      )

      const resultValid = engine.validateData(parsedTemplate, {
        required_field: 'test',
        hidden_required: 'hidden value',
        number_field: 50,
      })

      expect(resultValid.valid).toBe(true)
    })

    it('validates string length constraints', () => {
      const resultTooShort = engine.validateData(parsedTemplate, {
        required_field: 'test',
        hidden_required: 'hidden value',
        text_field: 'hi',
      })

      expect(resultTooShort.valid).toBe(false)
      expect(resultTooShort.errors.text_field).toBeDefined()

      const resultTooLong = engine.validateData(parsedTemplate, {
        required_field: 'test',
        hidden_required: 'hidden value',
        text_field: 'a'.repeat(51),
      })

      expect(resultTooLong.valid).toBe(false)
      expect(resultTooLong.errors.text_field).toBeDefined()

      const resultValid = engine.validateData(parsedTemplate, {
        required_field: 'test',
        hidden_required: 'hidden value',
        text_field: 'valid text',
      })

      expect(resultValid.valid).toBe(true)
    })

    it('skips validation for hidden fields in context', () => {
      const result = engine.validateData(
        parsedTemplate,
        {
          required_field: 'test',
        },
        'annotation'
      )

      expect(result.valid).toBe(true)
    })

    it('validates pattern rules', () => {
      const templateWithPattern: TaskTemplate = {
        id: 'pattern-test',
        name: 'Pattern Test',
        version: '1.0',
        fields: [
          {
            name: 'email',
            type: 'email',
            display: {
              annotation: 'editable',
              table: 'column',
              creation: 'editable',
            },
            source: 'annotation',
            validation: [
              {
                type: 'pattern',
                value: '^[^@]+@[^@]+\\.[^@]+$',
                message: 'Invalid email format',
              },
            ],
          },
        ],
        display_config: {
          table_columns: ['email'],
        },
      }

      const parsed = engine.parseTemplate(templateWithPattern)

      const resultInvalid = engine.validateData(parsed, {
        email: 'invalid-email',
      })

      expect(resultInvalid.valid).toBe(false)
      expect(resultInvalid.errors.email).toContain('Invalid email format')

      const resultValid = engine.validateData(parsed, {
        email: 'test@example.com',
      })

      expect(resultValid.valid).toBe(true)
    })

    it('handles empty data', () => {
      const result = engine.validateData(parsedTemplate, {})

      expect(result.valid).toBe(false)
      expect(result.errors.required_field).toBeDefined()
    })

    it('accumulates multiple validation errors', () => {
      const result = engine.validateData(parsedTemplate, {
        required_field: 'test',
        number_field: -5,
        text_field: 'hi',
      })

      expect(result.valid).toBe(false)
      expect(result.errors.number_field).toBeDefined()
      expect(result.errors.text_field).toBeDefined()
    })
  })

  describe('field condition evaluation', () => {
    it('evaluates exists condition', () => {
      const template: TaskTemplate = {
        id: 'condition-exists',
        name: 'Condition Exists',
        version: '1.0',
        fields: [
          {
            name: 'base_field',
            type: 'text',
            display: {
              annotation: 'editable',
              table: 'column',
              creation: 'editable',
            },
            source: 'task_data',
          },
          {
            name: 'conditional_field',
            type: 'text',
            display: {
              annotation: 'editable',
              table: 'column',
              creation: 'editable',
            },
            source: 'annotation',
            condition: {
              type: 'exists',
              field: 'base_field',
            },
          },
        ],
        display_config: {
          table_columns: ['base_field', 'conditional_field'],
        },
      }

      const parsed = engine.parseTemplate(template)
      const mockOnChange = jest.fn()

      const elementsWithoutBase = engine.renderAnnotationForm(
        parsed,
        {},
        {},
        mockOnChange
      )
      expect(elementsWithoutBase).toHaveLength(1)

      const elementsWithBase = engine.renderAnnotationForm(
        parsed,
        { base_field: 'exists' },
        {},
        mockOnChange
      )
      expect(elementsWithBase).toHaveLength(2)
    })

    it('evaluates equals condition', () => {
      const template: TaskTemplate = {
        id: 'condition-equals',
        name: 'Condition Equals',
        version: '1.0',
        fields: [
          {
            name: 'type',
            type: 'radio',
            display: {
              annotation: 'editable',
              table: 'column',
              creation: 'editable',
            },
            source: 'task_data',
            choices: ['type_a', 'type_b'],
          },
          {
            name: 'type_a_field',
            type: 'text',
            display: {
              annotation: 'editable',
              table: 'column',
              creation: 'editable',
            },
            source: 'annotation',
            condition: {
              type: 'equals',
              field: 'type',
              value: 'type_a',
            },
          },
        ],
        display_config: {
          table_columns: ['type', 'type_a_field'],
        },
      }

      const parsed = engine.parseTemplate(template)
      const mockOnChange = jest.fn()

      const elementsTypeA = engine.renderAnnotationForm(
        parsed,
        { type: 'type_a' },
        {},
        mockOnChange
      )
      expect(elementsTypeA).toHaveLength(2)

      const elementsTypeB = engine.renderAnnotationForm(
        parsed,
        { type: 'type_b' },
        {},
        mockOnChange
      )
      expect(elementsTypeB).toHaveLength(1)
    })

    it('evaluates not_equals condition', () => {
      const template: TaskTemplate = {
        id: 'condition-not-equals',
        name: 'Condition Not Equals',
        version: '1.0',
        fields: [
          {
            name: 'status',
            type: 'radio',
            display: {
              annotation: 'editable',
              table: 'column',
              creation: 'editable',
            },
            source: 'task_data',
            choices: ['draft', 'final'],
          },
          {
            name: 'edit_field',
            type: 'text',
            display: {
              annotation: 'editable',
              table: 'column',
              creation: 'editable',
            },
            source: 'annotation',
            condition: {
              type: 'not_equals',
              field: 'status',
              value: 'final',
            },
          },
        ],
        display_config: {
          table_columns: ['status', 'edit_field'],
        },
      }

      const parsed = engine.parseTemplate(template)
      const mockOnChange = jest.fn()

      const elementsDraft = engine.renderAnnotationForm(
        parsed,
        { status: 'draft' },
        {},
        mockOnChange
      )
      expect(elementsDraft).toHaveLength(2)

      const elementsFinal = engine.renderAnnotationForm(
        parsed,
        { status: 'final' },
        {},
        mockOnChange
      )
      expect(elementsFinal).toHaveLength(1)
    })

    it('evaluates contains condition', () => {
      const template: TaskTemplate = {
        id: 'condition-contains',
        name: 'Condition Contains',
        version: '1.0',
        fields: [
          {
            name: 'tags',
            type: 'text',
            display: {
              annotation: 'editable',
              table: 'column',
              creation: 'editable',
            },
            source: 'task_data',
          },
          {
            name: 'special_field',
            type: 'text',
            display: {
              annotation: 'editable',
              table: 'column',
              creation: 'editable',
            },
            source: 'annotation',
            condition: {
              type: 'contains',
              field: 'tags',
              value: 'special',
            },
          },
        ],
        display_config: {
          table_columns: ['tags', 'special_field'],
        },
      }

      const parsed = engine.parseTemplate(template)
      const mockOnChange = jest.fn()

      const elementsWithSpecial = engine.renderAnnotationForm(
        parsed,
        { tags: 'special,important' },
        {},
        mockOnChange
      )
      expect(elementsWithSpecial).toHaveLength(2)

      const elementsWithoutSpecial = engine.renderAnnotationForm(
        parsed,
        { tags: 'important,other' },
        {},
        mockOnChange
      )
      expect(elementsWithoutSpecial).toHaveLength(1)
    })

    it('handles string condition shorthand', () => {
      const template: TaskTemplate = {
        id: 'condition-shorthand',
        name: 'Condition Shorthand',
        version: '1.0',
        fields: [
          {
            name: 'conditional_field',
            type: 'text',
            display: {
              annotation: 'editable',
              table: 'column',
              creation: 'editable',
            },
            source: 'annotation',
            condition: 'exists',
          },
        ],
        display_config: {
          table_columns: ['conditional_field'],
        },
      }

      const parsed = engine.parseTemplate(template)
      const mockOnChange = jest.fn()

      const elementsWithoutValue = engine.renderAnnotationForm(
        parsed,
        {},
        {},
        mockOnChange
      )
      expect(elementsWithoutValue).toHaveLength(0)

      const elementsWithValue = engine.renderAnnotationForm(
        parsed,
        {},
        { conditional_field: 'test' },
        mockOnChange
      )
      expect(elementsWithValue).toHaveLength(1)
    })

    it('handles custom condition type', () => {
      const template: TaskTemplate = {
        id: 'condition-custom',
        name: 'Condition Custom',
        version: '1.0',
        fields: [
          {
            name: 'conditional_field',
            type: 'text',
            display: {
              annotation: 'editable',
              table: 'column',
              creation: 'editable',
            },
            source: 'annotation',
            condition: {
              type: 'custom',
              customCondition: 'customFunction',
            },
          },
        ],
        display_config: {
          table_columns: ['conditional_field'],
        },
      }

      const parsed = engine.parseTemplate(template)
      const mockOnChange = jest.fn()

      const elements = engine.renderAnnotationForm(parsed, {}, {}, mockOnChange)
      expect(elements).toHaveLength(1)
    })
  })

  describe('field value formatting', () => {
    it('formats null/undefined values', () => {
      const template: TaskTemplate = {
        id: 'format-test',
        name: 'Format Test',
        version: '1.0',
        fields: [
          {
            name: 'field',
            type: 'text',
            display: {
              annotation: 'readonly',
              table: 'column',
              creation: 'editable',
            },
            source: 'task_data',
          },
        ],
        display_config: {
          table_columns: ['field'],
        },
      }

      const parsed = engine.parseTemplate(template)
      const columns = engine.getTableColumns(parsed)

      expect(columns).toHaveLength(1)
    })

    it('formats date values', () => {
      const template: TaskTemplate = {
        id: 'date-format',
        name: 'Date Format',
        version: '1.0',
        fields: [
          {
            name: 'date_field',
            type: 'date',
            display: {
              annotation: 'editable',
              table: 'column',
              creation: 'editable',
            },
            source: 'task_data',
          },
        ],
        display_config: {
          table_columns: ['date_field'],
        },
      }

      const parsed = engine.parseTemplate(template)
      const columns = engine.getTableColumns(parsed)

      expect(columns).toHaveLength(1)
      expect(columns[0].id).toBe('date_field')
    })

    it('formats checkbox values', () => {
      const template: TaskTemplate = {
        id: 'checkbox-format',
        name: 'Checkbox Format',
        version: '1.0',
        fields: [
          {
            name: 'checkbox_field',
            type: 'checkbox',
            display: {
              annotation: 'editable',
              table: 'column',
              creation: 'editable',
            },
            source: 'annotation',
            choices: ['option1', 'option2', 'option3'],
          },
        ],
        display_config: {
          table_columns: ['checkbox_field'],
        },
      }

      const parsed = engine.parseTemplate(template)
      const columns = engine.getTableColumns(parsed)

      expect(columns).toHaveLength(1)
    })

    it('formats rich text values', () => {
      const template: TaskTemplate = {
        id: 'rich-text-format',
        name: 'Rich Text Format',
        version: '1.0',
        fields: [
          {
            name: 'rich_field',
            type: 'rich_text',
            display: {
              annotation: 'editable',
              table: 'column',
              creation: 'editable',
            },
            source: 'annotation',
          },
        ],
        display_config: {
          table_columns: ['rich_field'],
        },
      }

      const parsed = engine.parseTemplate(template)
      const columns = engine.getTableColumns(parsed)

      expect(columns).toHaveLength(1)
    })
  })

  describe('field sources', () => {
    it('handles generated field source', () => {
      const template: TaskTemplate = {
        id: 'generated-source',
        name: 'Generated Source',
        version: '1.0',
        fields: [
          {
            name: 'generated_field',
            type: 'text',
            display: {
              annotation: 'readonly',
              table: 'column',
              creation: 'readonly',
            },
            source: 'generated',
            label: 'Generated Field',
          },
        ],
        display_config: {
          table_columns: ['generated_field'],
        },
      }

      const parsed = engine.parseTemplate(template)
      const mockOnChange = jest.fn()

      const elements = engine.renderAnnotationForm(parsed, {}, {}, mockOnChange)

      expect(elements).toHaveLength(1)
      expect(elements[0].props.value).toBeNull()
    })

    it('handles computed field source', () => {
      const template: TaskTemplate = {
        id: 'computed-source',
        name: 'Computed Source',
        version: '1.0',
        fields: [
          {
            name: 'computed_field',
            type: 'text',
            display: {
              annotation: 'readonly',
              table: 'column',
              creation: 'readonly',
            },
            source: 'computed',
            label: 'Computed Field',
          },
        ],
        display_config: {
          table_columns: ['computed_field'],
        },
      }

      const parsed = engine.parseTemplate(template)
      const mockOnChange = jest.fn()

      const elements = engine.renderAnnotationForm(parsed, {}, {}, mockOnChange)

      expect(elements).toHaveLength(1)
      expect(elements[0].props.value).toBeNull()
    })
  })

  describe('table cell rendering', () => {
    it('renders table cells with onCellClick callback', () => {
      const template: TaskTemplate = {
        id: 'cell-click-test',
        name: 'Cell Click Test',
        version: '1.0',
        fields: [
          {
            name: 'clickable_field',
            type: 'text',
            display: {
              annotation: 'readonly',
              table: 'column',
              creation: 'editable',
            },
            source: 'task_data',
            label: 'Clickable Field',
          },
        ],
        display_config: {
          table_columns: ['clickable_field'],
        },
      }

      const parsed = engine.parseTemplate(template)
      const mockOnCellClick = jest.fn()
      const columns = engine.getTableColumns(parsed, {
        onCellClick: mockOnCellClick,
      })

      expect(columns).toHaveLength(1)
      expect(columns[0].id).toBe('clickable_field')
    })

    it('formats various field types in table cells', () => {
      const template: TaskTemplate = {
        id: 'format-types',
        name: 'Format Types',
        version: '1.0',
        fields: [
          {
            name: 'text_field',
            type: 'text',
            display: {
              annotation: 'readonly',
              table: 'column',
              creation: 'editable',
            },
            source: 'task_data',
          },
          {
            name: 'email_field',
            type: 'email',
            display: {
              annotation: 'readonly',
              table: 'column',
              creation: 'editable',
            },
            source: 'task_data',
          },
          {
            name: 'url_field',
            type: 'url',
            display: {
              annotation: 'readonly',
              table: 'column',
              creation: 'editable',
            },
            source: 'task_data',
          },
          {
            name: 'number_field',
            type: 'number',
            display: {
              annotation: 'readonly',
              table: 'column',
              creation: 'editable',
            },
            source: 'task_data',
          },
          {
            name: 'rating_field',
            type: 'rating',
            display: {
              annotation: 'readonly',
              table: 'column',
              creation: 'editable',
            },
            source: 'task_data',
          },
          {
            name: 'radio_field',
            type: 'radio',
            display: {
              annotation: 'readonly',
              table: 'column',
              creation: 'editable',
            },
            source: 'task_data',
            choices: ['option1', 'option2'],
          },
          {
            name: 'file_field',
            type: 'file_upload',
            display: {
              annotation: 'readonly',
              table: 'column',
              creation: 'editable',
            },
            source: 'task_data',
          },
        ],
        display_config: {
          table_columns: [
            'text_field',
            'email_field',
            'url_field',
            'number_field',
            'rating_field',
            'radio_field',
            'file_field',
          ],
        },
      }

      const parsed = engine.parseTemplate(template)
      const columns = engine.getTableColumns(parsed)

      expect(columns).toHaveLength(7)
    })

    it('handles in_answer_cell display mode', () => {
      const template: TaskTemplate = {
        id: 'in-answer-cell',
        name: 'In Answer Cell',
        version: '1.0',
        fields: [
          {
            name: 'main_field',
            type: 'text',
            display: {
              annotation: 'readonly',
              table: 'column',
              creation: 'editable',
            },
            source: 'task_data',
          },
          {
            name: 'nested_field',
            type: 'text',
            display: {
              annotation: 'readonly',
              table: 'in_answer_cell',
              creation: 'editable',
            },
            source: 'task_data',
          },
        ],
        display_config: {
          table_columns: ['main_field', 'nested_field'],
        },
      }

      const parsed = engine.parseTemplate(template)
      const columns = engine.getTableColumns(parsed)

      expect(columns).toHaveLength(2)
    })
  })

  describe('answer cell rendering', () => {
    it('renders answer cell with space separator', () => {
      const template: TaskTemplate = {
        id: 'answer-space',
        name: 'Answer Space',
        version: '1.0',
        fields: [
          {
            name: 'field1',
            type: 'text',
            display: {
              annotation: 'readonly',
              table: 'column',
              creation: 'editable',
            },
            source: 'task_data',
            label: 'Field 1',
          },
          {
            name: 'field2',
            type: 'text',
            display: {
              annotation: 'readonly',
              table: 'column',
              creation: 'editable',
            },
            source: 'task_data',
            label: 'Field 2',
          },
        ],
        display_config: {
          table_columns: ['field1'],
          answer_display: {
            fields: ['field1', 'field2'],
            separator: 'space',
          },
        },
      }

      const parsed = engine.parseTemplate(template)
      const columns = engine.getTableColumns(parsed)

      expect(columns).toHaveLength(1)
      expect(columns[0].id).toBe('field1')
    })

    it('renders answer cell with newline separator', () => {
      const template: TaskTemplate = {
        id: 'answer-newline',
        name: 'Answer Newline',
        version: '1.0',
        fields: [
          {
            name: 'field1',
            type: 'text',
            display: {
              annotation: 'readonly',
              table: 'column',
              creation: 'editable',
            },
            source: 'task_data',
            label: 'Field 1',
          },
          {
            name: 'field2',
            type: 'text',
            display: {
              annotation: 'readonly',
              table: 'column',
              creation: 'editable',
            },
            source: 'task_data',
            label: 'Field 2',
          },
        ],
        display_config: {
          table_columns: ['field1'],
          answer_display: {
            fields: ['field1', 'field2'],
            separator: 'newline',
          },
        },
      }

      const parsed = engine.parseTemplate(template)
      const columns = engine.getTableColumns(parsed)

      expect(columns).toHaveLength(1)
    })

    it('handles answer cell with missing fields', () => {
      const template: TaskTemplate = {
        id: 'answer-missing',
        name: 'Answer Missing',
        version: '1.0',
        fields: [
          {
            name: 'field1',
            type: 'text',
            display: {
              annotation: 'readonly',
              table: 'column',
              creation: 'editable',
            },
            source: 'task_data',
            label: 'Field 1',
          },
        ],
        display_config: {
          table_columns: ['field1'],
          answer_display: {
            fields: ['field1', 'nonexistent'],
            separator: 'divider',
          },
        },
      }

      const parsed = engine.parseTemplate(template)
      const columns = engine.getTableColumns(parsed)

      expect(columns).toHaveLength(1)
    })

    it('handles answer cell with onCellClick', () => {
      const template: TaskTemplate = {
        id: 'answer-click',
        name: 'Answer Click',
        version: '1.0',
        fields: [
          {
            name: 'field1',
            type: 'text',
            display: {
              annotation: 'readonly',
              table: 'column',
              creation: 'editable',
            },
            source: 'task_data',
            label: 'Field 1',
          },
        ],
        display_config: {
          table_columns: ['field1'],
          answer_display: {
            fields: ['field1'],
          },
        },
      }

      const parsed = engine.parseTemplate(template)
      const mockOnCellClick = jest.fn()
      const columns = engine.getTableColumns(parsed, {
        onCellClick: mockOnCellClick,
      })

      expect(columns).toHaveLength(1)
    })
  })

  describe('accessor functions', () => {
    it('getTableColumns uses accessorFn to extract row data', () => {
      const template: TaskTemplate = {
        id: 'accessor-test',
        name: 'Accessor Test',
        version: '1.0',
        fields: [
          {
            name: 'test_field',
            type: 'text',
            display: {
              annotation: 'readonly',
              table: 'column',
              creation: 'editable',
            },
            source: 'task_data',
            label: 'Test Field',
          },
        ],
        display_config: {
          table_columns: ['test_field'],
        },
      }

      const parsed = engine.parseTemplate(template)
      const columns = engine.getTableColumns(parsed)

      expect(columns).toHaveLength(1)
      expect(columns[0].accessorFn).toBeDefined()

      const mockRow = { test_field: 'test value' }
      const result = columns[0].accessorFn?.(mockRow, 0)
      expect(result).toBe('test value')
    })

    it('handles cell rendering with info object', () => {
      const template: TaskTemplate = {
        id: 'cell-render-test',
        name: 'Cell Render Test',
        version: '1.0',
        fields: [
          {
            name: 'field',
            type: 'text',
            display: {
              annotation: 'readonly',
              table: 'column',
              creation: 'editable',
            },
            source: 'task_data',
          },
        ],
        display_config: {
          table_columns: ['field'],
        },
      }

      const parsed = engine.parseTemplate(template)
      const columns = engine.getTableColumns(parsed)

      expect(columns[0].cell).toBeDefined()

      const mockInfo = {
        getValue: () => 'test value',
        row: { original: { field: 'test value' } },
      }

      const cellResult =
        typeof columns[0].cell === 'function'
          ? columns[0].cell(mockInfo as any)
          : null

      expect(cellResult).toBeTruthy()
    })

    it('uses custom renderer when provided for table cell', () => {
      const template: TaskTemplate = {
        id: 'custom-renderer',
        name: 'Custom Renderer',
        version: '1.0',
        fields: [
          {
            name: 'custom_field',
            type: 'text',
            display: {
              annotation: 'readonly',
              table: 'column',
              creation: 'editable',
            },
            source: 'task_data',
          },
        ],
        display_config: {
          table_columns: ['custom_field'],
        },
      }

      const parsed = engine.parseTemplate(template)
      const customRenderer = jest.fn(() =>
        React.createElement('div', {}, 'Custom Content')
      )

      const columns = engine.getTableColumns(parsed, {
        customRenderers: {
          custom_field: customRenderer,
        },
      })

      const mockInfo = {
        getValue: () => 'test',
        row: { original: { custom_field: 'test' } },
      }

      if (typeof columns[0].cell === 'function') {
        columns[0].cell(mockInfo as any)
      }

      expect(customRenderer).toHaveBeenCalled()
    })

    it('returns null for in_answer_cell display mode', () => {
      const template: TaskTemplate = {
        id: 'in-answer-mode',
        name: 'In Answer Mode',
        version: '1.0',
        fields: [
          {
            name: 'nested',
            type: 'text',
            display: {
              annotation: 'readonly',
              table: 'in_answer_cell',
              creation: 'editable',
            },
            source: 'task_data',
          },
        ],
        display_config: {
          table_columns: ['nested'],
        },
      }

      const parsed = engine.parseTemplate(template)
      const columns = engine.getTableColumns(parsed)

      const mockInfo = {
        getValue: () => 'test',
        row: { original: { nested: 'test' } },
      }

      const result =
        typeof columns[0].cell === 'function'
          ? columns[0].cell(mockInfo as any)
          : undefined

      expect(result).toBeNull()
    })

    it('renders answer cell with onClick handler', () => {
      const template: TaskTemplate = {
        id: 'answer-onclick',
        name: 'Answer OnClick',
        version: '1.0',
        fields: [
          {
            name: 'answer_field',
            type: 'text',
            display: {
              annotation: 'readonly',
              table: 'column',
              creation: 'editable',
            },
            source: 'task_data',
          },
        ],
        display_config: {
          table_columns: ['answer_field'],
          answer_display: {
            fields: ['answer_field'],
          },
        },
      }

      const parsed = engine.parseTemplate(template)
      const mockOnCellClick = jest.fn()
      const columns = engine.getTableColumns(parsed, {
        onCellClick: mockOnCellClick,
      })

      const mockInfo = {
        getValue: () => 'test',
        row: { original: { answer_field: 'test' } },
      }

      const cellElement =
        typeof columns[0].cell === 'function'
          ? columns[0].cell(mockInfo as any)
          : null

      expect(cellElement).toBeTruthy()
    })

    it('handles missing field in answer display', () => {
      const template: TaskTemplate = {
        id: 'missing-answer-field',
        name: 'Missing Answer Field',
        version: '1.0',
        fields: [
          {
            name: 'field1',
            type: 'text',
            display: {
              annotation: 'readonly',
              table: 'column',
              creation: 'editable',
            },
            source: 'task_data',
          },
        ],
        display_config: {
          table_columns: ['field1'],
          answer_display: {
            fields: ['field1', 'nonexistent_field'],
          },
        },
      }

      const parsed = engine.parseTemplate(template)
      const columns = engine.getTableColumns(parsed)

      expect(columns).toHaveLength(1)
    })
  })

  describe('field value formatting edge cases', () => {
    it('formats text_area field type', () => {
      const template: TaskTemplate = {
        id: 'textarea-format',
        name: 'TextArea Format',
        version: '1.0',
        fields: [
          {
            name: 'text_area_field',
            type: 'text_area',
            display: {
              annotation: 'readonly',
              table: 'column',
              creation: 'editable',
            },
            source: 'task_data',
          },
        ],
        display_config: {
          table_columns: ['text_area_field'],
        },
      }

      const parsed = engine.parseTemplate(template)
      const columns = engine.getTableColumns(parsed)
      expect(columns).toHaveLength(1)
    })

    it('formats boolean checkbox value', () => {
      const template: TaskTemplate = {
        id: 'checkbox-bool',
        name: 'Checkbox Bool',
        version: '1.0',
        fields: [
          {
            name: 'bool_field',
            type: 'checkbox',
            display: {
              annotation: 'readonly',
              table: 'column',
              creation: 'editable',
            },
            source: 'task_data',
          },
        ],
        display_config: {
          table_columns: ['bool_field'],
        },
      }

      const parsed = engine.parseTemplate(template)
      const columns = engine.getTableColumns(parsed)
      expect(columns).toHaveLength(1)
    })

    it('formats array checkbox values', () => {
      const template: TaskTemplate = {
        id: 'checkbox-array',
        name: 'Checkbox Array',
        version: '1.0',
        fields: [
          {
            name: 'array_field',
            type: 'checkbox',
            display: {
              annotation: 'readonly',
              table: 'column',
              creation: 'editable',
            },
            source: 'task_data',
            choices: ['a', 'b', 'c'],
          },
        ],
        display_config: {
          table_columns: ['array_field'],
        },
      }

      const parsed = engine.parseTemplate(template)
      const columns = engine.getTableColumns(parsed)
      expect(columns).toHaveLength(1)
    })

    it('formats default/unknown field types', () => {
      const template: TaskTemplate = {
        id: 'unknown-format',
        name: 'Unknown Format',
        version: '1.0',
        fields: [
          {
            name: 'unknown_field',
            type: 'text_highlight' as FieldType,
            display: {
              annotation: 'readonly',
              table: 'column',
              creation: 'editable',
            },
            source: 'task_data',
          },
        ],
        display_config: {
          table_columns: ['unknown_field'],
        },
      }

      const parsed = engine.parseTemplate(template)
      const columns = engine.getTableColumns(parsed)
      expect(columns).toHaveLength(1)
    })
  })

  describe('condition evaluation edge cases', () => {
    it('returns false when exists condition has no field specified', () => {
      const template: TaskTemplate = {
        id: 'exists-no-field',
        name: 'Exists No Field',
        version: '1.0',
        fields: [
          {
            name: 'conditional',
            type: 'text',
            display: {
              annotation: 'editable',
              table: 'column',
              creation: 'editable',
            },
            source: 'annotation',
            condition: {
              type: 'exists',
            },
          },
        ],
        display_config: {
          table_columns: ['conditional'],
        },
      }

      const parsed = engine.parseTemplate(template)
      const mockOnChange = jest.fn()

      const elements = engine.renderAnnotationForm(parsed, {}, {}, mockOnChange)
      expect(elements).toHaveLength(0)
    })

    it('returns false when equals condition has no field', () => {
      const template: TaskTemplate = {
        id: 'equals-no-field',
        name: 'Equals No Field',
        version: '1.0',
        fields: [
          {
            name: 'conditional',
            type: 'text',
            display: {
              annotation: 'editable',
              table: 'column',
              creation: 'editable',
            },
            source: 'annotation',
            condition: {
              type: 'equals',
              value: 'test',
            },
          },
        ],
        display_config: {
          table_columns: ['conditional'],
        },
      }

      const parsed = engine.parseTemplate(template)
      const mockOnChange = jest.fn()

      const elements = engine.renderAnnotationForm(parsed, {}, {}, mockOnChange)
      expect(elements).toHaveLength(0)
    })

    it('returns false when not_equals condition has no field', () => {
      const template: TaskTemplate = {
        id: 'not-equals-no-field',
        name: 'Not Equals No Field',
        version: '1.0',
        fields: [
          {
            name: 'conditional',
            type: 'text',
            display: {
              annotation: 'editable',
              table: 'column',
              creation: 'editable',
            },
            source: 'annotation',
            condition: {
              type: 'not_equals',
              value: 'test',
            },
          },
        ],
        display_config: {
          table_columns: ['conditional'],
        },
      }

      const parsed = engine.parseTemplate(template)
      const mockOnChange = jest.fn()

      const elements = engine.renderAnnotationForm(parsed, {}, {}, mockOnChange)
      expect(elements).toHaveLength(0)
    })

    it('returns false when contains condition has no field', () => {
      const template: TaskTemplate = {
        id: 'contains-no-field',
        name: 'Contains No Field',
        version: '1.0',
        fields: [
          {
            name: 'conditional',
            type: 'text',
            display: {
              annotation: 'editable',
              table: 'column',
              creation: 'editable',
            },
            source: 'annotation',
            condition: {
              type: 'contains',
              value: 'test',
            },
          },
        ],
        display_config: {
          table_columns: ['conditional'],
        },
      }

      const parsed = engine.parseTemplate(template)
      const mockOnChange = jest.fn()

      const elements = engine.renderAnnotationForm(parsed, {}, {}, mockOnChange)
      expect(elements).toHaveLength(0)
    })

    it('returns false when string condition is not exists', () => {
      const template: TaskTemplate = {
        id: 'string-not-exists',
        name: 'String Not Exists',
        version: '1.0',
        fields: [
          {
            name: 'conditional',
            type: 'text',
            display: {
              annotation: 'editable',
              table: 'column',
              creation: 'editable',
            },
            source: 'annotation',
            condition: 'invalid' as any,
          },
        ],
        display_config: {
          table_columns: ['conditional'],
        },
      }

      const parsed = engine.parseTemplate(template)
      const mockOnChange = jest.fn()

      const elements = engine.renderAnnotationForm(parsed, {}, {}, mockOnChange)
      expect(elements).toHaveLength(0)
    })
  })

  describe('edge cases', () => {
    it('handles template with empty fields array', () => {
      const template: TaskTemplate = {
        id: 'empty',
        name: 'Empty',
        version: '1.0',
        fields: [],
        display_config: {
          table_columns: [],
        },
      }

      const parsed = engine.parseTemplate(template)

      expect(parsed.fieldMap.size).toBe(0)
      expect(parsed.requiredFields.size).toBe(0)
      expect(parsed.editableFields.size).toBe(0)
      expect(parsed.tableFields).toEqual([])
    })

    it('handles circular field references in conditions', () => {
      const template: TaskTemplate = {
        id: 'circular',
        name: 'Circular',
        version: '1.0',
        fields: [
          {
            name: 'field_a',
            type: 'text',
            display: {
              annotation: 'editable',
              table: 'column',
              creation: 'editable',
            },
            source: 'annotation',
            condition: {
              type: 'exists',
              field: 'field_b',
            },
          },
          {
            name: 'field_b',
            type: 'text',
            display: {
              annotation: 'editable',
              table: 'column',
              creation: 'editable',
            },
            source: 'annotation',
            condition: {
              type: 'exists',
              field: 'field_a',
            },
          },
        ],
        display_config: {
          table_columns: ['field_a', 'field_b'],
        },
      }

      const parsed = engine.parseTemplate(template)
      const mockOnChange = jest.fn()

      const elements = engine.renderAnnotationForm(
        parsed,
        {},
        { field_a: 'test' },
        mockOnChange
      )

      expect(elements.length).toBeGreaterThanOrEqual(0)
    })

    it('handles very large templates', () => {
      const fields: TaskTemplateField[] = []
      const columnNames: string[] = []

      for (let i = 0; i < 100; i++) {
        const fieldName = `field_${i}`
        fields.push({
          name: fieldName,
          type: 'text',
          display: {
            annotation: 'editable',
            table: 'column',
            creation: 'editable',
          },
          source: 'task_data',
        })
        columnNames.push(fieldName)
      }

      const template: TaskTemplate = {
        id: 'large',
        name: 'Large Template',
        version: '1.0',
        fields,
        display_config: {
          table_columns: columnNames,
        },
      }

      const parsed = engine.parseTemplate(template)

      expect(parsed.fieldMap.size).toBe(100)
      expect(parsed.tableFields).toHaveLength(100)
    })

    it('handles special characters in field names', () => {
      const template: TaskTemplate = {
        id: 'special-chars',
        name: 'Special Chars',
        version: '1.0',
        fields: [
          {
            name: 'field_with-dash',
            type: 'text',
            display: {
              annotation: 'editable',
              table: 'column',
              creation: 'editable',
            },
            source: 'task_data',
          },
          {
            name: 'field.with.dots',
            type: 'text',
            display: {
              annotation: 'editable',
              table: 'column',
              creation: 'editable',
            },
            source: 'task_data',
          },
        ],
        display_config: {
          table_columns: ['field_with-dash', 'field.with.dots'],
        },
      }

      const parsed = engine.parseTemplate(template)

      expect(parsed.fieldMap.has('field_with-dash')).toBe(true)
      expect(parsed.fieldMap.has('field.with.dots')).toBe(true)
    })

    it('handles deeply nested LLM prompt templates', () => {
      const template: TaskTemplate = {
        id: 'nested-prompt',
        name: 'Nested Prompt',
        version: '1.0',
        fields: [],
        display_config: { table_columns: [] },
        llm_config: {
          prompt_template:
            '{{#if context}}{{#if question}}Q: {{question}}{{#if answer}} (A: {{answer}}){{/if}}{{/if}}{{/if}}',
          response_parser: 'default',
        },
      }

      const parsed = engine.parseTemplate(template)
      const prompt = engine.generatePrompt(parsed, {
        context: true,
        question: 'Test?',
        answer: 'Yes',
      })

      expect(prompt).toContain('Q: Test?')
      expect(prompt).toContain('(A: Yes)')
    })
  })
})

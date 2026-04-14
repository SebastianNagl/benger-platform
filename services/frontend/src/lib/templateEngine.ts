/**
 * Template Engine for Unified Task Configuration
 *
 * Handles rendering of dynamic forms, table columns, and data processing
 * based on task templates. This is the core engine that powers the
 * unified configuration and display system.
 *
 * Issue #216: Implement Unified Task Configuration and Display System
 */

import {
  DisplayContext,
  FieldType,
  TaskTemplate,
  TaskTemplateField,
  validateFieldValue,
} from '@/types/taskTemplate'
import { ColumnDef } from '@tanstack/react-table'
import React from 'react'

// Import field components (to be implemented)
import { CheckboxField } from '@/components/fields/CheckboxField'
import { DateField } from '@/components/fields/DateField'
import { EmailField } from '@/components/fields/EmailField'
import { FileUploadField } from '@/components/fields/FileUploadField'
import { HighlightField } from '@/components/fields/HighlightField'
import { NumberField } from '@/components/fields/NumberField'
import { RadioField } from '@/components/fields/RadioField'
import { RatingField } from '@/components/fields/RatingField'
import { RichTextField } from '@/components/fields/RichTextField'
import { TextAreaField } from '@/components/fields/TextAreaField'
import { TextField } from '@/components/fields/TextField'
import { TextHighlightField } from '@/components/fields/TextHighlightField'
import { UrlField } from '@/components/fields/UrlField'

export interface FieldComponentProps {
  field: TaskTemplateField
  value: any
  onChange: (value: any) => void
  readonly?: boolean
  errors?: string[]
  context: DisplayContext
}

export interface ParsedTemplate {
  template: TaskTemplate
  fieldMap: Map<string, TaskTemplateField>
  requiredFields: Set<string>
  editableFields: Set<string>
  tableFields: string[]
}

export class TemplateEngine {
  private fieldComponents: Map<
    FieldType,
    React.ComponentType<FieldComponentProps>
  >

  constructor() {
    // Register field components
    this.fieldComponents = new Map([
      ['text', TextField],
      ['text_area', TextAreaField],
      ['radio', RadioField],
      ['checkbox', CheckboxField],
      ['rating', RatingField],
      ['number', NumberField],
      ['date', DateField],
      ['email', EmailField],
      ['url', UrlField],
      ['rich_text', RichTextField],
      ['file_upload', FileUploadField],
      ['highlight', HighlightField],
      ['text_highlight', TextHighlightField],
    ])
  }

  /**
   * Parse and validate a template
   */
  parseTemplate(template: TaskTemplate): ParsedTemplate {
    const fieldMap = new Map<string, TaskTemplateField>()
    const requiredFields = new Set<string>()
    const editableFields = new Set<string>()
    const tableFields: string[] = []

    // Build field map and sets
    for (const field of template.fields) {
      fieldMap.set(field.name, field)

      if (field.required) {
        requiredFields.add(field.name)
      }

      if (field.display.annotation === 'editable') {
        editableFields.add(field.name)
      }

      if (field.display.table === 'column') {
        tableFields.push(field.name)
      }
    }

    // Validate display config references valid fields
    for (const column of template.display_config.table_columns) {
      if (!fieldMap.has(column)) {
        throw new Error(
          `Display column '${column}' not found in template fields`
        )
      }
    }

    return {
      template,
      fieldMap,
      requiredFields,
      editableFields,
      tableFields,
    }
  }

  /**
   * Render a form for annotation based on template
   */
  renderAnnotationForm(
    parsedTemplate: ParsedTemplate,
    taskData: Record<string, any>,
    annotationData: Record<string, any>,
    onChange: (fieldName: string, value: any) => void,
    errors: Record<string, string[]> = {},
    context: DisplayContext = 'annotation'
  ): React.ReactElement[] {
    const elements: React.ReactElement[] = []
    const { template, fieldMap } = parsedTemplate

    for (const field of template.fields) {
      // Check display mode for current context
      const displayMode = field.display[context]
      if (displayMode === 'hidden') continue

      // Check field condition
      if (!this.evaluateFieldCondition(field, taskData, annotationData)) {
        continue
      }

      // Determine value source
      let value: any
      switch (field.source) {
        case 'task_data':
          value = taskData[field.name]
          break
        case 'annotation':
          value = annotationData[field.name]
          break
        case 'generated':
          // TODO: Handle generated fields
          value = null
          break
        case 'computed':
          // TODO: Handle computed fields
          value = null
          break
      }

      // Get field component
      const FieldComponent = this.fieldComponents.get(field.type)
      if (!FieldComponent) {
        // No component registered for field type - skipping
        continue
      }

      // Render field
      elements.push(
        React.createElement(FieldComponent, {
          key: field.name,
          field,
          value,
          onChange: (newValue) => onChange(field.name, newValue),
          readonly: displayMode === 'readonly',
          errors: errors[field.name],
          context: context,
        })
      )
    }

    return elements
  }

  /**
   * Generate table columns based on template
   */
  getTableColumns<T extends Record<string, any>>(
    parsedTemplate: ParsedTemplate,
    options: {
      onCellClick?: (field: string, value: any, rowData: T) => void
      customRenderers?: Record<
        string,
        (value: any, rowData: T) => React.ReactElement
      >
    } = {}
  ): ColumnDef<T>[] {
    const columns: ColumnDef<T>[] = []
    const { template, fieldMap } = parsedTemplate

    for (const columnName of template.display_config.table_columns) {
      const field = fieldMap.get(columnName)
      if (!field || field.display.table === 'hidden') continue

      const column: ColumnDef<T, any> = {
        id: field.name,
        header: field.label || field.name,
        accessorFn: (row) => row[field.name],
        size: template.display_config.column_widths?.[field.name],
        cell: (info) => {
          const value = info.getValue()
          const rowData = info.row.original

          // Use custom renderer if provided
          if (options.customRenderers?.[field.name]) {
            return options.customRenderers[field.name](value, rowData)
          }

          // Handle in_answer_cell display mode
          if (field.display.table === 'in_answer_cell') {
            // This field should be rendered within another field's cell
            return null
          }

          // Default rendering based on field type
          return this.renderTableCell(
            field,
            value,
            rowData,
            options.onCellClick
          )
        },
      }

      columns.push(column)
    }

    // Handle answer display configuration
    if (template.display_config.answer_display) {
      const answerFields = template.display_config.answer_display.fields
      const primaryField = answerFields[0]

      // Find the primary answer column and enhance it
      const answerColumn = columns.find((col) => col.id === primaryField)
      if (answerColumn) {
        const originalCell = answerColumn.cell
        answerColumn.cell = (info) => {
          const rowData = info.row.original
          return this.renderAnswerCell(
            parsedTemplate,
            rowData,
            template.display_config.answer_display!,
            options.onCellClick
          )
        }
      }
    }

    return columns
  }

  /**
   * Generate LLM prompt based on template and task data
   */
  generatePrompt(
    parsedTemplate: ParsedTemplate,
    taskData: Record<string, any>
  ): string {
    const { template } = parsedTemplate

    if (!template.llm_config) {
      throw new Error('Template does not have LLM configuration')
    }

    let prompt = template.llm_config.prompt_template

    // Simple template replacement (can be enhanced with a proper template engine)
    for (const [key, value] of Object.entries(taskData)) {
      // Handle conditional blocks {{#if field}}...{{/if}}
      const conditionalRegex = new RegExp(
        `{{#if ${key}}}([\\s\\S]*?){{/if}}`,
        'g'
      )
      prompt = prompt.replace(conditionalRegex, (match, content) => {
        return value ? content : ''
      })

      // Handle simple replacements {{field}}
      prompt = prompt.replace(new RegExp(`{{${key}}}`, 'g'), value || '')
    }

    // Handle array iteration {{#each items}}...{{/each}}
    const eachRegex = /{{#each (\w+)}}([\s\S]*?){{\/each}}/g
    prompt = prompt.replace(eachRegex, (match, arrayKey, content) => {
      const items = taskData[arrayKey]
      if (!Array.isArray(items)) return ''

      return items
        .map((item, index) => {
          let itemContent = content
          itemContent = itemContent.replace(/{{@index}}/g, index.toString())
          itemContent = itemContent.replace(/{{this}}/g, item)
          return itemContent
        })
        .join('')
    })

    return prompt.trim()
  }

  /**
   * Parse LLM response based on template configuration
   */
  parseLLMResponse(
    parsedTemplate: ParsedTemplate,
    response: string
  ): Record<string, any> {
    const { template } = parsedTemplate

    if (!template.llm_config) {
      throw new Error('Template does not have LLM configuration')
    }

    // Handle different response formats
    switch (template.llm_config.response_format) {
      case 'json':
        try {
          const parsed = JSON.parse(response)
          // Apply field mapping
          if (template.llm_config.field_mapping) {
            const mapped: Record<string, any> = {}
            for (const [responseField, templateField] of Object.entries(
              template.llm_config.field_mapping
            )) {
              if (responseField in parsed) {
                mapped[templateField] = parsed[responseField]
              }
            }
            return mapped
          }
          return parsed
        } catch (e) {
          throw new Error(`Failed to parse JSON response: ${e}`)
        }

      case 'structured':
        // TODO: Implement structured response parsing
        return this.parseStructuredResponse(response, parsedTemplate)

      case 'text':
      default:
        // For text responses, return as single field
        const fieldName =
          template.llm_config.field_mapping?.['response'] || 'response'
        return { [fieldName]: response }
    }
  }

  /**
   * Validate data against template
   */
  validateData(
    parsedTemplate: ParsedTemplate,
    data: Record<string, any>,
    context?: DisplayContext
  ): { valid: boolean; errors: Record<string, string[]> } {
    const errors: Record<string, string[]> = {}
    const { fieldMap, requiredFields } = parsedTemplate

    // Check required fields
    for (const fieldName of requiredFields) {
      const field = fieldMap.get(fieldName)!

      // Skip validation for fields not displayed in current context
      if (context && field.display[context] === 'hidden') {
        continue
      }

      if (!(fieldName in data) || !data[fieldName]) {
        errors[fieldName] = [`${field.label || fieldName} is required`]
      }
    }

    // Validate each field
    for (const [fieldName, value] of Object.entries(data)) {
      const field = fieldMap.get(fieldName)
      if (!field) continue

      const validation = validateFieldValue(field, value)
      if (!validation.valid) {
        errors[fieldName] = (errors[fieldName] || []).concat(validation.errors)
      }
    }

    return {
      valid: Object.keys(errors).length === 0,
      errors,
    }
  }

  // Private helper methods

  private evaluateFieldCondition(
    field: TaskTemplateField,
    taskData: Record<string, any>,
    annotationData: Record<string, any>
  ): boolean {
    if (!field.condition) return true

    const allData = { ...taskData, ...annotationData }

    if (typeof field.condition === 'string') {
      // Shorthand for 'exists'
      return (
        field.condition === 'exists' &&
        field.name in allData &&
        allData[field.name]
      )
    }

    const { type, field: conditionField, value } = field.condition

    switch (type) {
      case 'exists':
        return conditionField
          ? conditionField in allData && allData[conditionField]
          : false
      case 'equals':
        return conditionField ? allData[conditionField] === value : false
      case 'not_equals':
        return conditionField ? allData[conditionField] !== value : false
      case 'contains':
        return conditionField
          ? String(allData[conditionField]).includes(value)
          : false
      case 'custom':
        // TODO: Implement custom condition evaluation
        return true
      default:
        return true
    }
  }

  private renderTableCell(
    field: TaskTemplateField,
    value: any,
    rowData: any,
    onCellClick?: (field: string, value: any, rowData: any) => void
  ): React.ReactElement {
    const handleClick = () => {
      if (onCellClick) {
        onCellClick(field.name, value, rowData)
      }
    }

    // Base cell wrapper
    const cellContent = React.createElement(
      'div',
      {
        className:
          'cursor-pointer hover:bg-zinc-50 dark:hover:bg-zinc-800 p-2 rounded transition-colors',
        onClick: handleClick,
      },
      this.formatFieldValue(field, value)
    )

    return cellContent
  }

  private renderAnswerCell(
    parsedTemplate: ParsedTemplate,
    rowData: any,
    answerDisplay: {
      fields: string[]
      separator?: 'divider' | 'space' | 'newline'
    },
    onCellClick?: (field: string, value: any, rowData: any) => void
  ): React.ReactElement {
    const { fieldMap } = parsedTemplate
    const elements: React.ReactElement[] = []

    for (let i = 0; i < answerDisplay.fields.length; i++) {
      const fieldName = answerDisplay.fields[i]
      const field = fieldMap.get(fieldName)
      if (!field) continue

      const value = rowData[fieldName]

      elements.push(
        React.createElement(
          'div',
          { key: fieldName },
          this.formatFieldValue(field, value)
        )
      )

      // Add separator
      if (i < answerDisplay.fields.length - 1) {
        switch (answerDisplay.separator) {
          case 'divider':
            elements.push(
              React.createElement('div', {
                key: `separator-${i}`,
                className:
                  'mt-2 pt-2 border-t border-zinc-200 dark:border-zinc-700',
              })
            )
            break
          case 'space':
            elements.push(
              React.createElement('div', {
                key: `separator-${i}`,
                className: 'mt-2',
              })
            )
            break
          case 'newline':
            elements.push(React.createElement('br', { key: `separator-${i}` }))
            break
        }
      }
    }

    return React.createElement(
      'div',
      {
        className:
          'cursor-pointer hover:bg-zinc-50 dark:hover:bg-zinc-800 p-2 rounded transition-colors',
        onClick: () =>
          onCellClick?.(
            answerDisplay.fields[0],
            rowData[answerDisplay.fields[0]],
            rowData
          ),
      },
      elements
    )
  }

  private formatFieldValue(
    field: TaskTemplateField,
    value: any
  ): React.ReactNode {
    if (value === null || value === undefined) {
      return React.createElement('span', { className: 'text-zinc-400' }, '-')
    }

    switch (field.type) {
      case 'text':
      case 'text_area':
      case 'email':
      case 'url':
        return React.createElement(
          'span',
          {
            className: 'text-sm text-zinc-700 dark:text-zinc-300',
          },
          value
        )

      case 'rich_text':
        // TODO: Render rich text properly
        return React.createElement('div', {
          className: 'text-sm text-zinc-700 dark:text-zinc-300',
          dangerouslySetInnerHTML: { __html: value },
        })

      case 'number':
      case 'rating':
        return React.createElement(
          'span',
          {
            className: 'text-sm font-medium text-zinc-700 dark:text-zinc-300',
          },
          value
        )

      case 'date':
        return React.createElement(
          'span',
          {
            className: 'text-sm text-zinc-700 dark:text-zinc-300',
          },
          new Date(value).toLocaleDateString()
        )

      case 'checkbox':
        if (Array.isArray(value)) {
          return React.createElement(
            'div',
            {
              className: 'text-sm text-zinc-700 dark:text-zinc-300',
            },
            value.join(', ')
          )
        }
        return React.createElement(
          'span',
          {
            className: 'text-sm text-zinc-700 dark:text-zinc-300',
          },
          value ? 'Yes' : 'No'
        )

      case 'radio':
        return React.createElement(
          'span',
          {
            className: 'text-sm text-zinc-700 dark:text-zinc-300',
          },
          value
        )

      case 'file_upload':
        // TODO: Render file information
        return React.createElement(
          'span',
          {
            className: 'text-sm text-zinc-700 dark:text-zinc-300',
          },
          `File: ${value}`
        )

      default:
        return React.createElement(
          'span',
          {
            className: 'text-sm text-zinc-700 dark:text-zinc-300',
          },
          String(value)
        )
    }
  }

  private parseStructuredResponse(
    response: string,
    parsedTemplate: ParsedTemplate
  ): Record<string, any> {
    // TODO: Implement structured response parsing
    // This could use regex patterns, section markers, etc.
    // For now, return as text
    return { response }
  }
}

// Singleton instance
export const templateEngine = new TemplateEngine()

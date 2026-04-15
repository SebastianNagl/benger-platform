/**
 * Task Template Types
 *
 * Defines the structure for the unified task configuration and display system.
 * These types enable declarative task definitions that work across task creation,
 * annotation, data display, LLM generation, and evaluation.
 *
 * Issue #216: Implement Unified Task Configuration and Display System
 */

export type FieldType =
  | 'text' // Single line text input
  | 'text_area' // Multi-line text input
  | 'radio' // Single choice selection
  | 'checkbox' // Multiple choice selection
  | 'rating' // Numeric rating/scale
  | 'highlight' // Text highlighting/annotation
  | 'rich_text' // Formatted text editor
  | 'file_upload' // File attachments
  | 'number' // Numeric input
  | 'date' // Date picker
  | 'email' // Email input
  | 'url' // URL input
  | 'pdf_viewer' // PDF document viewer with annotations
  | 'optimized_pdf' // Optimized PDF viewer with virtual scrolling
  | 'text_highlight' // Text passage highlighting with labels

export type FieldSource = 'task_data' | 'annotation' | 'generated' | 'computed'

export type DisplayContext = 'annotation' | 'table' | 'creation' | 'review'

export type DisplayMode =
  | 'readonly'
  | 'editable'
  | 'hidden'
  | 'column'
  | 'in_answer_cell'
  | 'reference'

export interface ValidationRule {
  type:
    | 'required'
    | 'minLength'
    | 'maxLength'
    | 'min'
    | 'max'
    | 'pattern'
    | 'custom'
  value?: any
  message?: string
  customValidator?: string // Function name for custom validation
}

export interface FieldDisplay {
  annotation: DisplayMode
  table: DisplayMode
  creation: DisplayMode
  review?: DisplayMode
}

export interface FieldCondition {
  type: 'exists' | 'equals' | 'not_equals' | 'contains' | 'custom'
  field?: string
  value?: any
  customCondition?: string // Function name for custom conditions
}

export interface TaskTemplateField {
  name: string
  type: FieldType
  display: FieldDisplay
  source: FieldSource
  required?: boolean
  label?: string
  description?: string
  placeholder?: string
  defaultValue?: any
  choices?: string[] // For radio/checkbox fields
  validation?: ValidationRule[]
  condition?: FieldCondition | string // 'exists' shorthand or full condition
  metadata?: Record<string, any>
}

export interface DisplayConfig {
  table_columns: string[] // Field names to show as table columns
  answer_display?: {
    fields: string[] // Fields to show in answer cell
    separator?: 'divider' | 'space' | 'newline'
  }
  grouping?: {
    [groupName: string]: string[] // Group fields together
  }
  column_widths?: {
    [fieldName: string]: number // Custom column widths
  }
}

export interface LLMConfig {
  prompt_template: string // Template string with {{field}} placeholders
  response_parser: string // Parser function name
  system_prompt?: string
  temperature?: number
  max_tokens?: number
  response_format?: 'json' | 'text' | 'structured'
  field_mapping?: {
    [responseField: string]: string // Map LLM response fields to template fields
  }
}

export interface EvaluationMetric {
  name: string
  type:
    | 'accuracy'
    | 'f1'
    | 'bleu'
    | 'rouge'
    | 'exact_match'
    | 'reasoning_quality'
    | 'custom'
  config?: Record<string, any>
  weight?: number
}

export interface EvaluationConfig {
  metrics: EvaluationMetric[]
  requires_reference: boolean
  custom_evaluator?: string // Function name for custom evaluation
  threshold?: number // Minimum score threshold
}

export interface TaskTemplate {
  id: string
  name: string
  version: string
  description?: string
  category?: string // e.g., 'qa', 'classification', 'generation', 'custom'
  fields: TaskTemplateField[]
  display_config: DisplayConfig
  llm_config?: LLMConfig
  evaluation_config?: EvaluationConfig
  metadata?: {
    author?: string
    created_at?: string
    updated_at?: string
    tags?: string[]
    compatible_models?: string[]
  }
  validation_schema?: Record<string, any> // JSON Schema for additional validation
}

// Helper type for runtime field values
export interface FieldValue {
  field: string
  value: any
  metadata?: Record<string, any>
}

// Helper type for template instances
export interface TaskTemplateInstance {
  template_id: string
  template_version: string
  field_values: Record<string, any>
  computed_fields?: Record<string, any>
  validation_status?: {
    valid: boolean
    errors?: Array<{
      field: string
      rule: string
      message: string
    }>
  }
}

// Type guards
export function isTextField(
  type: FieldType
): type is 'text' | 'text_area' | 'rich_text' {
  return ['text', 'text_area', 'rich_text'].includes(type)
}

export function isChoiceField(type: FieldType): type is 'radio' | 'checkbox' {
  return ['radio', 'checkbox'].includes(type)
}

export function isNumericField(type: FieldType): type is 'number' | 'rating' {
  return ['number', 'rating'].includes(type)
}

// Validation helpers
export function validateFieldValue(
  field: TaskTemplateField,
  value: any
): { valid: boolean; errors: string[] } {
  const errors: string[] = []

  // Required validation
  if (field.required && !value) {
    errors.push(`${field.label || field.name} is required`)
  }

  // Type-specific validation
  if (value && field.validation) {
    for (const rule of field.validation) {
      switch (rule.type) {
        case 'minLength':
          if (typeof value === 'string' && value.length < rule.value) {
            errors.push(
              rule.message ||
                `${field.label || field.name} must be at least ${rule.value} characters`
            )
          }
          break
        case 'maxLength':
          if (typeof value === 'string' && value.length > rule.value) {
            errors.push(
              rule.message ||
                `${field.label || field.name} must be at most ${rule.value} characters`
            )
          }
          break
        case 'min':
          if (typeof value === 'number' && value < rule.value) {
            errors.push(
              rule.message ||
                `${field.label || field.name} must be at least ${rule.value}`
            )
          }
          break
        case 'max':
          if (typeof value === 'number' && value > rule.value) {
            errors.push(
              rule.message ||
                `${field.label || field.name} must be at most ${rule.value}`
            )
          }
          break
        case 'pattern':
          if (
            typeof value === 'string' &&
            !new RegExp(rule.value).test(value)
          ) {
            errors.push(
              rule.message || `${field.label || field.name} format is invalid`
            )
          }
          break
      }
    }
  }

  return { valid: errors.length === 0, errors }
}

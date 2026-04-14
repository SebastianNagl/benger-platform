/**
 * Dynamic annotation types - Issue #220 Phase 4
 * Label Studio-style configuration-driven annotation
 */

export interface AnnotationConfig {
  // Core configuration
  id: string
  version: string
  title?: string
  description?: string

  // Interface configuration
  interfaces: AnnotationInterface[]

  // Data bindings
  data?: {
    [key: string]: {
      source: string // Path to data field
      type: 'text' | 'image' | 'audio' | 'video' | 'html'
    }
  }

  // Output configuration
  results?: {
    [key: string]: {
      type: string
      toName?: string
      required?: boolean
    }
  }
}

export interface AnnotationInterface {
  id: string
  type: AnnotationComponentType
  name: string
  toName?: string // Data binding

  // Component-specific properties
  properties?: Record<string, any>

  // Visual configuration
  style?: Record<string, string>

  // Validation rules
  validation?: {
    required?: boolean
    min?: number
    max?: number
    pattern?: string
    custom?: string // Custom validation function
  }

  // Conditional display
  when?: {
    field: string
    operator: 'equals' | 'contains' | 'exists' | 'empty'
    value?: any
  }
}

export type AnnotationComponentType =
  // Text annotation
  | 'text'
  | 'textarea'
  | 'richtextarea'
  // Classification
  | 'choices'
  | 'rating'
  | 'ranker'
  // Entity recognition
  | 'labels'
  | 'relations'
  | 'taxonomy'
  // Bounding boxes
  | 'rectangle'
  | 'polygon'
  | 'keypoint'
  // Time series
  | 'timeseries'
  | 'timeline'
  // Custom
  | 'custom'

export interface AnnotationResult {
  id: string
  type: string
  value: any
  from_name: string
  to_name?: string
  created_at?: string
  updated_at?: string

  // Additional metadata
  meta?: Record<string, any>
}

export interface AnnotationTemplate {
  id: string
  name: string
  description: string
  category: string
  config: AnnotationConfig
  preview_data?: any
  tags?: string[]
  created_at?: string
  is_public?: boolean
}

// German legal annotation presets
export const LEGAL_ANNOTATION_PRESETS = {
  qa: {
    name: 'Question Answering',
    config: {
      interfaces: [
        {
          id: 'question',
          type: 'text',
          name: 'question',
          properties: {
            label: 'Rechtsfrage',
            placeholder: 'Geben Sie die rechtliche Frage ein...',
          },
        },
        {
          id: 'answer',
          type: 'textarea',
          name: 'answer',
          properties: {
            label: 'Antwort',
            rows: 10,
            placeholder: 'Ihre rechtliche Einschätzung...',
          },
        },
        {
          id: 'confidence',
          type: 'rating',
          name: 'confidence',
          properties: {
            label: 'Vertrauensniveau',
            max: 5,
          },
        },
      ],
    },
  },

  entity_recognition: {
    name: 'Legal Entity Recognition',
    config: {
      interfaces: [
        {
          id: 'text_display',
          type: 'text',
          name: 'text',
          toName: 'document',
          properties: {
            readonly: true,
          },
        },
        {
          id: 'entity_labels',
          type: 'labels',
          name: 'label',
          toName: 'text',
          properties: {
            choices: [
              { value: 'PERSON', label: 'Person' },
              { value: 'ORG', label: 'Organisation' },
              { value: 'LAW', label: 'Gesetz' },
              { value: 'COURT', label: 'Gericht' },
              { value: 'DATE', label: 'Datum' },
              { value: 'MONEY', label: 'Geldbetrag' },
            ],
          },
        },
      ],
    },
  },

  document_classification: {
    name: 'Document Classification',
    config: {
      interfaces: [
        {
          id: 'doc_type',
          type: 'choices',
          name: 'document_type',
          properties: {
            label: 'Dokumenttyp',
            choices: [
              'Urteil',
              'Beschluss',
              'Verordnung',
              'Gesetz',
              'Vertrag',
              'Gutachten',
            ],
            multiple: false,
          },
        },
        {
          id: 'legal_area',
          type: 'taxonomy',
          name: 'legal_area',
          properties: {
            label: 'Rechtsgebiet',
            taxonomy: [
              {
                value: 'zivilrecht',
                label: 'Zivilrecht',
                children: [
                  { value: 'vertragsrecht', label: 'Vertragsrecht' },
                  { value: 'sachenrecht', label: 'Sachenrecht' },
                  { value: 'familienrecht', label: 'Familienrecht' },
                ],
              },
              {
                value: 'strafrecht',
                label: 'Strafrecht',
                children: [
                  { value: 'btm', label: 'Betäubungsmittel' },
                  {
                    value: 'wirtschaftsstrafrecht',
                    label: 'Wirtschaftsstrafrecht',
                  },
                ],
              },
            ],
          },
        },
      ],
    },
  },
}

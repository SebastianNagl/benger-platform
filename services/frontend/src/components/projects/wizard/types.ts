import { EvaluationConfig } from '@/lib/api/evaluation-types'

export interface WizardFeatures {
  annotation: boolean
  dataImport: boolean
  llmGeneration: boolean
  evaluation: boolean
}

export interface ConditionalInstruction {
  id: string
  content: string
  weight: number
  ai_allowed?: boolean
}

export interface ModelConfig {
  temperature?: number
  max_tokens?: number
  reasoning_budget?: number
}

export interface LabelingTemplate {
  id: string
  name: string
  description: string
  icon: string
  category: string
  config: string
}

export interface ProjectSettings {
  assignment_mode: 'open' | 'manual' | 'auto'
  maximum_annotations: number
  min_annotations_per_task: number
  randomize_task_order: boolean
  require_confirm_before_submit: boolean
  annotation_time_limit_enabled: boolean
  annotation_time_limit_seconds: number | null
  strict_timer_enabled: boolean
}

export interface GenerationParameters {
  temperature: number
  max_tokens: number
  batch_size: number
}

export type WizardVisibility = 'private' | 'organization' | 'public'
export type WizardPublicRole = 'ANNOTATOR' | 'CONTRIBUTOR'

export interface WizardData {
  // Step 1: Project Info
  title: string
  description: string
  features: WizardFeatures
  visibility: WizardVisibility
  publicRole: WizardPublicRole
  // Orgs to assign when visibility === 'organization'. Lets the user
  // override the X-Organization-Context header (e.g. when wizard is opened
  // on a no-org subdomain and they want to publish into a specific org).
  organizationIds: string[]

  // Labeling Setup (if annotation)
  labelingConfig: LabelingTemplate | null

  // Annotation Instructions (if annotation)
  instructions: string
  conditionalInstructions: ConditionalInstruction[]
  show_instruction: boolean
  instructions_always_visible: boolean
  show_skip_button: boolean

  // Data Import (if dataImport)
  pastedData: string
  selectedFile: File | null
  dataColumns: string[]

  // Models (if llmGeneration)
  selectedModelIds: string[]
  modelConfigs: Record<string, ModelConfig>
  generationParameters: GenerationParameters

  // Prompts (if llmGeneration)
  promptTemplate: string
  systemPrompt: string
  instructionPrompt: string

  // Evaluation (if evaluation)
  evaluationConfigs: EvaluationConfig[]
  immediate_evaluation_enabled: boolean

  // Settings (always)
  settings: ProjectSettings
}

export interface WizardStepDef {
  id: string
  name: string
  description: string
}

export const INITIAL_WIZARD_DATA: WizardData = {
  title: '',
  description: '',
  features: {
    annotation: false,
    dataImport: false,
    llmGeneration: false,
    evaluation: false,
  },
  visibility: 'private',
  publicRole: 'ANNOTATOR',
  organizationIds: [],
  labelingConfig: null,
  instructions: '',
  conditionalInstructions: [],
  show_instruction: true,
  instructions_always_visible: false,
  show_skip_button: true,
  pastedData: '',
  selectedFile: null,
  dataColumns: [],
  selectedModelIds: [],
  modelConfigs: {},
  generationParameters: {
    temperature: 0.7,
    max_tokens: 4096,
    batch_size: 10,
  },
  promptTemplate: 'custom',
  systemPrompt: '',
  instructionPrompt: '',
  evaluationConfigs: [],
  immediate_evaluation_enabled: false,
  settings: {
    assignment_mode: 'open',
    maximum_annotations: 0,
    min_annotations_per_task: 1,
    randomize_task_order: false,
    require_confirm_before_submit: true,
    annotation_time_limit_enabled: false,
    annotation_time_limit_seconds: null,
    strict_timer_enabled: false,
  },
}

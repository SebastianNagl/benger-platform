import { EvaluationConfig } from '@/lib/api/evaluation-types'

export interface WizardFeatures {
  annotation: boolean
  dataImport: boolean
  llmGeneration: boolean
  evaluation: boolean
  // Extended-edition hook: the experimental KI-Generator step. The checkbox
  // row is rendered by the ProjectWizardSyntheticEntry slot (community builds
  // register nothing, so this can never become true there).
  synthetic: boolean
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
  // Reveal the full task data (incl. Musterlösung) to the solver after submit.
  annotator_full_visibility_after_submit: boolean
  annotation_time_limit_enabled: boolean
  annotation_time_limit_seconds: number | null
  strict_timer_enabled: boolean
  // Timed access window (ISO 8601 UTC, or null when unset).
  window_start_at: string | null
  window_end_at: string | null
}

export interface GenerationParameters {
  temperature: number
  max_tokens: number
  batch_size: number
  // Phase 6.6: per-run seed for variance studies. 42 keeps the
  // historical determinism behavior; researchers running multi-seed
  // studies bump this between runs.
  seed: number
}

export type WizardVisibility = 'private' | 'organization' | 'public'
export type WizardPublicRole = 'ANNOTATOR' | 'CONTRIBUTOR'

export type WizardProjectKind = 'generic' | 'exam' | 'flashcard_collection'

export interface WizardData {
  // Step 1: Project Info
  title: string
  description: string
  // Project type — locked after creation (maps to the write-once `kind`).
  projectKind: WizardProjectKind
  // Emoji shown in lists / headers; empty = kind-derived fallback.
  icon: string
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

  // KI-Generator (if synthetic): the in-flight generation job, kept in the
  // wizard state so the step can resume polling after a step change (the
  // step component unmounts between steps; without this the finished
  // result would be silently lost).
  syntheticJobId: string | null

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
  projectKind: 'generic',
  icon: '',
  description: '',
  features: {
    annotation: false,
    dataImport: false,
    llmGeneration: false,
    evaluation: false,
    synthetic: false,
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
  // Seeded with DEFAULT_MODEL_ID by StepModels once the catalog loads —
  // not here, because a static seed would carry the id into a project's
  // generation config even on a deployment whose catalog lacks it.
  selectedModelIds: [],
  modelConfigs: {},
  generationParameters: {
    temperature: 0.7,
    max_tokens: 4096,
    batch_size: 10,
    seed: 42,
  },
  promptTemplate: 'custom',
  systemPrompt: '',
  instructionPrompt: '',
  evaluationConfigs: [],
  immediate_evaluation_enabled: false,
  syntheticJobId: null,
  settings: {
    assignment_mode: 'open',
    maximum_annotations: 0,
    min_annotations_per_task: 1,
    randomize_task_order: false,
    require_confirm_before_submit: true,
    annotator_full_visibility_after_submit: false,
    annotation_time_limit_enabled: false,
    annotation_time_limit_seconds: null,
    strict_timer_enabled: false,
    window_start_at: null,
    window_end_at: null,
  },
}

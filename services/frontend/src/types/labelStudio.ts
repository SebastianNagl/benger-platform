/**
 * TypeScript types for Label Studio aligned structures
 *
 * These types represent the new project-based architecture that follows
 * Label Studio patterns while preserving BenGER's LLM capabilities.
 */

// Project types
export interface Project {
  id: string
  title: string
  description?: string
  created_by: string | number
  created_by_name?: string
  organization_id: string
  organization?: {
    id: string
    name: string
  }
  organizations?: Array<{
    id: string
    name: string
  }>

  // Label Studio fields
  label_config?: string
  generation_structure?: string
  instructions?: string
  expert_instruction?: string
  show_instruction: boolean
  instructions_always_visible: boolean
  conditional_instructions?: Array<{ id: string; content: string; weight: number; ai_allowed?: boolean }> | null
  show_skip_button: boolean
  show_submit_button: boolean
  require_comment_on_skip: boolean
  require_confirm_before_submit: boolean
  skip_queue?: 'requeue_for_me' | 'requeue_for_others' | 'ignore_skipped'
  questionnaire_enabled: boolean
  questionnaire_config: string | null
  enable_empty_annotation: boolean
  // Note: Removed in migrations 411540fa6c40 and 95726e4be27e:
  // show_annotation_history, show_ground_truth_first, show_overlap_first,
  // overlap_cohort_percentage, color, sampling
  maximum_annotations: number
  min_annotations_to_start_training: number
  assignment_mode?: 'open' | 'manual' | 'auto'
  randomize_task_order?: boolean

  // Review & Korrektur
  review_enabled?: boolean
  review_mode?: 'in_place' | 'independent' | 'both'
  allow_self_review?: boolean
  korrektur_enabled?: boolean
  korrektur_config?: Array<{ value: string; background: string }>

  // Timer (extended feature)
  annotation_time_limit_enabled?: boolean
  annotation_time_limit_seconds?: number | null
  strict_timer_enabled?: boolean

  // Immediate evaluation (extended feature)
  immediate_evaluation_enabled?: boolean

  // Per-project feature visibility flags (D4 from korrektur rework). Pure UI
  // gate — when false, the corresponding ConfigCard on the project detail
  // page is hidden; data and APIs stay untouched. Default true server-side.
  enable_annotation?: boolean
  enable_generation?: boolean
  enable_evaluation?: boolean

  // Total Generation rows for this project — feeds the Statistiken tile
  // when > 0; computed by routers/projects/helpers.calculate_generation_stats.
  generation_count?: number

  // BenGER specific
  llm_model_ids?: string[]
  generation_config?: GenerationConfig
  evaluation_config?: Record<string, any>

  // Statistics (renamed to match API)
  num_tasks: number
  num_annotations: number
  task_count?: number // Legacy support
  annotation_count?: number // Legacy support
  min_annotations_per_task?: number // Minimum annotations required per task
  completed_tasks_count?: number // Number of tasks that meet min requirement
  progress_percentage?: number // Server-calculated progress (0-100)

  // Generation-related fields for /generation page
  generation_prompts_ready?: boolean // Whether all tasks have required prompts
  generation_config_ready?: boolean // Whether project has generation_structure config
  generation_models_count?: number // Number of configured models
  generation_completed?: boolean // Whether generation is complete for all tasks/models

  // Status
  is_published: boolean
  is_archived: boolean

  // Visibility and access control
  is_private?: boolean
  is_public?: boolean
  public_role?: 'ANNOTATOR' | 'CONTRIBUTOR' | null
  organization_ids?: string[]

  // Timestamps
  created_at: string
  updated_at?: string
}

export interface ProjectCreate {
  title: string
  description?: string
  label_config?: string
  generation_structure?: string
  expert_instruction?: string
  show_instruction?: boolean
  show_skip_button?: boolean
  enable_empty_annotation?: boolean
  llm_model_ids?: string[]
  is_private?: boolean
  is_public?: boolean
  public_role?: 'ANNOTATOR' | 'CONTRIBUTOR' | null
}

export interface ProjectUpdate extends Partial<ProjectCreate> {
  is_published?: boolean
  is_archived?: boolean
  generation_structure?: string
  instructions?: string
  show_submit_button?: boolean
  require_comment_on_skip?: boolean
  require_confirm_before_submit?: boolean
  // Note: color and sampling removed in migration 95726e4be27e
  maximum_annotations?: number
  min_annotations_per_task?: number
  assignment_mode?: 'open' | 'manual' | 'auto'
  is_public?: boolean
  public_role?: 'ANNOTATOR' | 'CONTRIBUTOR' | null
  organization_ids?: string[]
  instructions_always_visible?: boolean
  conditional_instructions?: Array<{ id: string; content: string; weight: number; ai_allowed?: boolean }> | null
  review_enabled?: boolean
  review_mode?: 'in_place' | 'independent' | 'both'
  allow_self_review?: boolean
  korrektur_enabled?: boolean
  korrektur_config?: Array<{ value: string; background: string }>
}

// Task Assignment types
export interface TaskAssignment {
  id: string
  task_id: number
  user_id: string
  user_name?: string
  user_email?: string
  assigned_by: string
  status: 'assigned' | 'in_progress' | 'completed' | 'skipped'
  priority: number
  due_date?: string
  notes?: string
  assigned_at: string
  started_at?: string
  completed_at?: string
}

export interface AssignTasksRequest {
  task_ids: string[]
  user_ids: string[]
  distribution: 'manual' | 'round_robin' | 'random' | 'load_balanced'
  priority?: number
  due_date?: string
  notes?: string
}

// Task types
export interface Task {
  id: string
  inner_id?: number
  project_id: string
  data: Record<string, any> // Flexible JSON data
  meta?: Record<string, any>
  is_labeled: boolean
  total_annotations: number
  cancelled_annotations: number
  total_generations: number

  // BenGER specific
  llm_responses?: Record<string, any>
  llm_evaluations?: Record<string, any>

  created_at: string
  updated_at?: string

  // Tagging system (Issue #262)
  tags?: string[]

  // Task assignments - users assigned to this task
  assignments?: TaskAssignment[]
}

// Annotation types
export interface Annotation {
  id: string
  task_id: number
  project_id: string
  completed_by: string
  result: AnnotationResult[]
  draft?: AnnotationResult[]
  was_cancelled: boolean
  ground_truth: boolean
  lead_time?: number // seconds
  prediction_scores?: Record<string, number>
  created_at: string
  metadata?: Record<string, any>
  updated_at?: string
}

export interface AnnotationCreate {
  result: AnnotationResult[]
  draft?: AnnotationResult[]
  was_cancelled?: boolean
  lead_time?: number
  // Enhanced timing (Issue #1208)
  active_duration_ms?: number
  focused_duration_ms?: number
  tab_switches?: number
  instruction_variant?: string
}

export interface AnnotationResult {
  value: any
  from_name: string
  to_name: string
  type: string
  // Additional fields based on annotation type
  [key: string]: any
}

// Prediction types
export interface Prediction {
  id: string
  task_id: number
  model_version?: string
  result: AnnotationResult[]
  score?: number
  model_name?: string
  model_backend?: string
  created_at: string
}

// Import/Export types
export interface ImportResult {
  created: number
  total: number
  project_id: string
  failed?: number
  errors?: string[]
}

export interface ExportOptions {
  format: 'json' | 'csv' | 'tsv' | 'coco' | 'conll'
  include_annotations?: boolean
  include_predictions?: boolean
  filters?: Record<string, any>
}

// Label configuration types
export interface LabelConfig {
  controls: LabelControl[]
}

export interface LabelControl {
  name: string
  type: 'Labels' | 'TextArea' | 'Choices' | 'Rating' | 'Number'
  to_name?: string
  required?: boolean
  placeholder?: string
  rows?: number
  choices?: string[]
  labels?: LabelOption[]
  min?: number
  max?: number
}

export interface LabelOption {
  value: string
  background?: string
  hotkey?: string
}

// API response types
export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  pages: number
}

// LLM specific types (BenGER features)
export interface LLMGenerationConfig {
  model_ids?: string[]
  prompt_template?: string
  temperature?: number
  max_tokens?: number
  task_ids?: number[]
}

// Generation Config Types (Issue #762)
export interface PromptStructure {
  name: string
  description?: string
  system_prompt: string | Record<string, any>
  instruction_prompt: string | Record<string, any>
  evaluation_prompt?: string | Record<string, any>
}

export interface GenerationConfig {
  selected_configuration?: {
    models?: string[]
    active_structures?: string[]
    prompts?: {
      system?: string
      instruction?: string
    }
    parameters?: {
      temperature?: number
      max_tokens?: number
      batch_size?: number
    }
    presentation_mode?: string
    model_configs?: Record<string, any>
  }
  prompt_structures?: Record<string, PromptStructure>
  detected_data_types?: string[]
  available_options?: Record<string, any>
}

export interface LLMResponse {
  model_id: string
  response: string
  metadata?: Record<string, any>
  created_at: string
}

export interface LLMEvaluation {
  model_id: string
  scores: Record<string, number>
  details?: Record<string, any>
  created_at: string
}

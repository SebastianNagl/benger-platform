/**
 * Type definitions for BenGER API responses
 */

// Re-export defaults types
export type { DefaultConfig, DefaultPrompts } from './admin-defaults'

// Role type definitions for clarity
export type OrganizationRole = 'ORG_ADMIN' | 'CONTRIBUTOR' | 'ANNOTATOR'

export interface User {
  id: string
  username: string
  email: string
  email_verified?: boolean
  email_verified_by_id?: string | null
  email_verified_at?: string | null
  email_verification_method?: 'self' | 'admin' | 'system' | null
  name: string
  full_name?: string // Full display name
  role?: OrganizationRole // User's current role context
  is_superadmin: boolean // Global superadmin flag
  is_active: boolean
  created_at: string

  // Pseudonymization fields (Issue #790, GDPR-compliant)
  pseudonym?: string // Unique pseudonym for privacy protection
  use_pseudonym?: boolean // Privacy preference: true = show pseudonym, false = show real name

  // Notification and timezone preferences
  timezone?: string
  enable_quiet_hours?: boolean
  quiet_hours_start?: string
  quiet_hours_end?: string
  enable_email_digest?: boolean
  digest_frequency?: string
  digest_time?: string
  digest_days?: string
  last_digest_sent?: string

  // Demographic fields
  age?: number
  job?: string
  years_of_experience?: number

  // Legal expertise fields
  legal_expertise_level?: string
  german_proficiency?: string
  degree_program_type?: string
  current_semester?: number
  legal_specializations?: string[]

  // German state exam fields
  german_state_exams_count?: number
  german_state_exams_data?: Array<{
    location: string
    date: string
    grade: string
  }>

  // Gender (Issue #1206)
  gender?: string

  // Subjective competence (Issue #1206)
  subjective_competence_civil?: number
  subjective_competence_public?: number
  subjective_competence_criminal?: number

  // Objective grades (Issue #1206)
  grade_zwischenpruefung?: number
  grade_vorgeruecktenubung?: number
  grade_first_staatsexamen?: number
  grade_second_staatsexamen?: number

  // Psychometric scales (Issue #1206)
  ati_s_scores?: Record<string, number>
  ptt_a_scores?: Record<string, number>
  ki_experience_scores?: Record<string, number>

  // Mandatory profile tracking (Issue #1206)
  mandatory_profile_completed?: boolean
  profile_confirmed_at?: string
}

export interface AuthResponse {
  access_token: string
  refresh_token?: string
  token_type: string
  expires_in: number
  user: User
}

export interface Organization {
  id: string
  name: string
  display_name: string
  slug: string
  description?: string
  settings?: Record<string, any>
  is_active: boolean
  created_at: string
  updated_at?: string
  member_count?: number
  role?: OrganizationRole // User's role in this organization
}

export interface OrganizationCreate {
  name: string
  display_name: string
  slug: string
  description?: string
  settings?: Record<string, any>
}

export interface OrganizationUpdate {
  name?: string
  display_name?: string
  description?: string
  settings?: Record<string, any>
  is_active?: boolean
}

export interface OrganizationMember {
  id: string
  user_id: string
  organization_id: string
  role: OrganizationRole
  is_active: boolean
  joined_at: string
  user_name?: string
  user_email?: string
  email_verified?: boolean
  email_verification_method?: 'self' | 'admin' | 'system' | null
}

export interface Invitation {
  id: string
  organization_id: string
  email: string
  role: OrganizationRole
  token: string
  invited_by: string
  expires_at: string
  accepted_at: string | null
  is_accepted: boolean
  created_at: string
  organization_name?: string
  inviter_name?: string
}

export interface InvitationCreate {
  email: string
  role: OrganizationRole
}

export interface Task {
  id: string
  name: string
  description: string
  annotation_guidelines?: string // Issue #181: Optional annotation guidelines
  template_id: string // Issue #219: Primary template identifier
  template_data?: Record<string, any> // Issue #219: Template-specific configuration
  data?: Record<string, any> // Issue #220: Flexible data for Label Studio style import
  task_type: string // Deprecated: Derived from template
  template?: string // Deprecated: Use template_id instead
  visibility: string
  created_by: string // User ID of the task creator
  created_by_name?: string // Display name of the task creator (from User.name)
  created_at: string
  updated_at?: string
  evaluation_types?: EvaluationType[]
  model_ids?: string[]
  organization_ids?: string[]
  organizations?: Organization[]
  annotation_count?: number
  task_count?: number
}

// Lightweight version for lists and dashboard
export interface TaskSummary {
  id: string
  name: string
  description: string
  task_type: string
  visibility: string
  created_by: string // User ID of the task creator
  created_by_name?: string // Display name of the task creator (from User.name)
  created_at: string
  updated_at?: string
  organization_ids?: string[]
  annotation_count?: number
  task_count?: number
}

export interface TaskCreate {
  name: string
  description: string
  annotation_guidelines?: string // Issue #181: Optional annotation guidelines
  template_id: string // Issue #219: Primary template identifier (required)
  template_data?: Record<string, any> // Issue #219: Template-specific configuration
  data?: Record<string, any> // Issue #220: Flexible data for Label Studio style import
  label_config?: string // Issue #220: Display configuration for flexible tasks
  task_type?: string // Deprecated: Use template_id instead (backend derives this from template)
  template?: string // Deprecated: Use template_id instead
  visibility?: string
  evaluation_type_ids?: string[]
  organization_ids?: string[]
}

export interface TaskUpdate {
  description?: string
  annotation_guidelines?: string // Issue #181: Optional annotation guidelines
  name?: string
  task_type?: string
  template?: string
  organization_ids?: string[]
  visibility?: string
  evaluation_type_ids?: string[]
  model_ids?: string[]
}

export interface TaskData {
  id: string
  data: Record<string, unknown>
  annotations: Record<string, unknown>[]
  predictions: Record<string, unknown>[]
  is_labeled?: boolean
  created_at?: string
  updated_at?: string
}

export interface EvaluationRequest {
  task_id: string
  model_id: string
  metrics: string[]
}

export interface EvaluationResult {
  id: string
  task_id: string
  model_id: string
  metrics: Record<string, number>
  created_at: string
  status?: string
  samples_evaluated?: number
  error_message?: string
  completed_at?: string
}

export interface UploadResponse {
  message: string
  task_id: string
  uploaded_items: number
  data_id?: string
  status?: string
}

export interface AddPromptsRequest {
  prompts: Array<{
    prompt: string
    expected_output?: string
    metadata?: {
      temperature?: number
      max_tokens?: number
      prompt_type?: string
      context?: string
    }
  }>
}

export interface AddPromptsResponse {
  success: boolean
  added_count: number
  message: string
  prompt_count?: number
}

export interface UploadedDataResponse {
  id: string
  name: string
  size: number
  upload_date: string
  format: string
  document_count: number
  description?: string
  task_id?: string
}

export interface SyntheticDataGenerationRequest {
  task_id: string
  count: number
  selected_data: string[]
  selected_task: string
  selected_model: string
  text_input: string
}

export interface SyntheticDataGenerationResponse {
  id: string
  status: string
  count: number
  message: string
}

export interface SyntheticDataGenerationHistory {
  id: string
  source_data_ids: string[]
  target_task_id: string
  instructions: string
  status: string
  generated_count: number
  error_message?: string
  created_at: string
  completed_at?: string
}

export interface LLMModel {
  id: string
  name: string
  description: string
  provider: string
  capabilities: string[]
}

export interface ParameterConstraints {
  temperature?: {
    supported: boolean
    required_value?: number
    default?: number
    min?: number
    max?: number
    reason?: string
  }
  max_tokens?: {
    default: number
  }
  top_p?: {
    supported?: boolean
    conflicts_with?: string[]
  }
  unsupported_params?: string[]
  reproducibility_impact?: string
  benchmark_notes?: string
}

export interface LLMModelResponse {
  id: string
  name: string
  description?: string
  provider: string
  model_type: string
  capabilities: string[]
  config_schema?: Record<string, any>
  default_config?: Record<string, any>
  parameter_constraints?: ParameterConstraints | null
  is_active: boolean
  created_at: string | null
  updated_at?: string | null
}

export interface ProjectEvaluationConfigCreate {
  task_id: string
  llm_model_ids: string[]
  evaluation_type_ids: string[]
  model_configs?: Record<string, Record<string, any>>
}

export interface ProjectEvaluationConfigResponse {
  id: string
  task_id: string
  llm_model_ids: string[]
  evaluation_type_ids: string[]
  model_configs?: Record<string, Record<string, any>>
  is_active: boolean
  created_by: string
  created_at: string
  updated_at?: string
}

export interface BatchEvaluationRequest {
  config_id: string
  force_rerun?: boolean
}

export interface BatchEvaluationResponse {
  config_id: string
  task_id: string
  evaluation_ids: string[]
  status: string
  message: string
  started_at: string
}

export interface ProjectType {
  id: string
  name: string
  description?: string
  default_template?: string
  supported_metrics: string[]
  model_config_schema?: Record<string, any>
  is_active: boolean
}

export interface EvaluationType {
  id: string
  name: string
  description?: string
  category: string
  higher_is_better: boolean
  value_range?: { min: number; max: number } | null
  applicable_task_types: string[]
  is_active: boolean
}

// Human Evaluation Types
export interface HumanEvaluationConfigCreate {
  project_id?: string
  task_id?: string
  session_type?: string // 'likert' or 'preference'
  field_name?: string
  dimensions?: string[]
  evaluator_count?: number
  blinding_enabled?: boolean
  include_human_responses?: boolean
}

export interface HumanEvaluationConfigResponse {
  project_id: string
  human_methods: Record<string, any[]>
  available_dimensions: string[]
  evaluation_config?: Record<string, any>
  status?: 'active' | 'pending' | 'completed'
  evaluator_count?: number
  blinding_enabled?: boolean
  evaluation_project_id?: string
}

export interface HumanEvaluationSetupResponse {
  id: string
  project_id: string
  evaluator_id: string
  session_type: string
  items_evaluated: number
  total_items: number | null
  status: string
  session_config: Record<string, any> | null
  created_at: string
}

export interface HumanEvaluationResultSummary {
  session_id: string
  project_id: string
  total_responses: number
  total_evaluations: number
  results: Array<{
    response_id: string
    anonymous_model_name: string
    actual_model_id?: string
    response_type: string
    evaluation_count: number
    scores: {
      correctness_mean: number
      correctness_std: number
      completeness_mean: number
      completeness_std: number
      style_mean: number
      style_std: number
      usability_mean: number
      usability_std: number
    }
    raw_scores: {
      correctness: number[]
      completeness: number[]
      style: number[]
      usability: number[]
    }
  }>
  inter_rater_reliability: {
    cronbach_alpha_by_criterion?: Record<string, number | null>
    overall_cronbach_alpha?: number | null
    note?: string
    error?: string
  }
}

// Prompt types removed in Issue #759 - use generation_structure in project settings instead

// Feature Flag Types
export interface FeatureFlag {
  id: string
  name: string
  description?: string
  is_enabled: boolean
  target_criteria?: Record<string, any>
  rollout_percentage: number
  created_by: string
  created_at: string
  updated_at?: string
}

export interface FeatureFlagCreate {
  name: string
  description?: string
  is_enabled: boolean
  target_criteria?: Record<string, any>
  rollout_percentage: number
}

export interface FeatureFlagUpdate {
  description?: string
  is_enabled?: boolean
  target_criteria?: Record<string, any>
  rollout_percentage?: number
}

export interface FeatureFlagStatus {
  flag_name: string
  is_enabled: boolean
  source: 'user_override' | 'org_override' | 'global' | 'default'
}

// User and organization feature flag overrides removed
// Feature flags are global and controlled only by superadmins

// Missing types that are expected by various components
export interface EvaluationUpdate {
  id: string
  status?: string
  progress?: number
  results?: Record<string, any>
  metrics?: Record<string, number>
  error_message?: string
}

export interface GenerationResponse {
  id: string
  status: string
  progress?: number
  results?: Record<string, any>
  error_message?: string
}

export interface InvitationResponse {
  id: string
  email: string
  role: OrganizationRole
  status: string
  organization_name?: string
  inviter_name?: string
  created_at: string
  expires_at: string
}

export interface NotificationResponse {
  id: string
  title: string
  message: string
  type: string
  read: boolean
  created_at: string
  updated_at?: string
}

export interface NotificationUpdate {
  read?: boolean
  archived?: boolean
}

export interface OrganizationMemberUpdate {
  role?: OrganizationRole
  is_active?: boolean
}

export interface OrganizationResponse {
  id: string
  name: string
  slug: string
  description?: string
  member_count?: number
  created_at: string
  updated_at?: string
}

// Annotation Status Types
export type AnnotationStatus =
  | 'pending'
  | 'in_progress'
  | 'completed'
  | 'rejected'
  | 'skipped'
export type NativeAnnotationStatus =
  | 'pending'
  | 'in_progress'
  | 'completed'
  | 'rejected'
  | 'skipped'

// Annotation Data Types
export interface AnnotationData {
  [key: string]: any
}

export interface Annotation {
  id: string
  task_id: string
  annotator_id: string
  annotator_name?: string
  data: AnnotationData
  metadata?: Record<string, any>
  status: AnnotationStatus
  created_at: string
  updated_at?: string
  project?: {
    id: string
    name: string
  }
  completion_percentage?: number
  lead_time_seconds?: number
  completed_by?: string
}

// Annotation Field Configuration Types
export interface AnnotationFieldConfig {
  type: string
  label: string
  required?: boolean
  validation?: {
    min?: number
    max?: number
    pattern?: string
    message?: string
  }
  options?: Array<{
    value: string
    label: string
  }>
}

// Task Template Types
export interface TaskTemplate {
  id: string
  name: string
  description?: string
  version: string
  category: string
  fields: TaskTemplateField[]
  display_config: Record<string, any>
  settings?: Record<string, any>
  validation?: Record<string, any>
  created_at: string
  updated_at?: string
}

export interface TaskTemplateField {
  name: string
  label: string
  type: string
  source?: string
  required: boolean
  display: Record<string, any>
}

export interface TaskTemplateCreate {
  name: string
  description?: string
  category: string
  fields: TaskTemplateField[]
  display_config: Record<string, any>
}

// Annotation Template Types
export interface AnnotationTemplate {
  id: string
  name: string
  description?: string
  template_type: AnnotationTemplateType
  configuration: Record<string, any>
  created_at: string
  updated_at?: string
}

export interface AnnotationTemplateCreate {
  name: string
  description?: string
  template_type: AnnotationTemplateType
  configuration: Record<string, any>
}

export type AnnotationTemplateType =
  | 'qa'
  | 'qar'
  | 'classification'
  | 'sequence_labeling'
  | 'pdf_sequence_labeling'

// Field Types for Templates
export type FieldType =
  | 'text'
  | 'textarea'
  | 'number'
  | 'select'
  | 'multi_select'
  | 'radio'
  | 'checkbox'
  | 'date'
  | 'time'
  | 'datetime'
  | 'file'
  | 'image'
  | 'url'
  | 'email'
  | 'phone'
  | 'color'
  | 'range'
  | 'rating'
  | 'boolean'
  | 'pdf_sequence_labeling'
  | 'relationship_mapping'
  | 'hierarchical_structure'

// Annotation Statistics Types
export interface AnnotatorStats {
  user_id: string
  annotation_count: number
}

export interface AnnotationStatistics {
  total_items: number
  annotated_items: number
  submitted_items: number
  approved_items: number
  rejected_items: number
  draft_items: number
  completion_percentage: number
  average_time_per_item: number | null
  annotators: AnnotatorStats[]
}

// Global Tasks/Data API Types
export interface TaskProject {
  id: string
  title: string
  organization: string | null
}

export interface TaskResponseItem {
  id: string
  project_id: string
  project: TaskProject
  data: unknown
  meta: Record<string, unknown>
  is_labeled: boolean
  assigned_to: User | null
  created_at: string
  updated_at: string | null
  annotations_count: number
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  pages: number
}

// Mandatory Profile Types (Issue #1206)
export interface MandatoryProfileStatus {
  mandatory_profile_completed: boolean
  confirmation_due: boolean
  confirmation_due_date?: string
  missing_fields: string[]
}

export interface ProfileConfirmationResponse {
  success: boolean
  confirmed_at: string
  message: string
}

export interface ProfileHistoryEntry {
  id: string
  changed_at: string
  change_type: string
  snapshot: Record<string, any>
  changed_fields: string[]
}

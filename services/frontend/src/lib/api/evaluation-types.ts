/**
 * Evaluation Configuration Types
 *
 * Supports N:M field mapping where multiple prediction fields can be
 * evaluated against multiple reference fields with different metrics.
 *
 * Issue #483 - Phase 8: Evaluation Mapping
 */

/**
 * Special field values for bulk selection
 */
export const FIELD_SPECIFIERS = {
  ALL_MODEL: '__all_model__',
  ALL_HUMAN: '__all_human__',
} as const

export type FieldSpecifier =
  (typeof FIELD_SPECIFIERS)[keyof typeof FIELD_SPECIFIERS]

/**
 * Custom criteria definition for LLM-as-Judge
 * Allows users to define their own evaluation criteria with rubrics
 * Issue #1083 - Custom LLM Judge Prompts
 */
export interface CustomCriteriaDefinition {
  /** Human-readable name for the criterion */
  name: string
  /** Description of what this criterion evaluates */
  description: string
  /** Scoring rubric (1-5 scale) explaining each score level */
  rubric: string
}

/**
 * Available template variables for custom prompts
 * These can be inserted into custom_prompt_template
 */
export const PROMPT_TEMPLATE_VARIABLES = [
  { key: '{context}', description: 'Task context / input text', aliases: ['{input}'] },
  {
    key: '{ground_truth}',
    description: 'Reference / ground truth answer',
    aliases: ['{reference}'],
  },
  {
    key: '{prediction}',
    description: 'Model response to evaluate',
    aliases: ['{response}', '{candidate}'],
  },
  { key: '{criterion_name}', description: 'Name of the evaluation criterion', aliases: [] },
  {
    key: '{criterion_description}',
    description: 'Description of the criterion',
    aliases: [],
  },
  { key: '{rubric}', description: 'Scoring rubric (1-5 scale)', aliases: [] },
] as const

/**
 * Metric-specific parameters
 */
export interface MetricParameters {
  // For BLEU
  max_order?: number
  weights?: number[]
  smoothing?: 'method1' | 'method2' | 'method3' | 'method4'

  // For ROUGE
  variant?: 'rouge1' | 'rouge2' | 'rougeL' | 'rougeLsum'
  use_stemmer?: boolean

  // For METEOR
  alpha?: number
  beta?: number
  gamma?: number

  // For chrF
  char_order?: number
  word_order?: number

  // For LLM-as-Judge
  dimensions?: string[]
  judge_model?: string
  answer_type?: string
  /** Custom prompt template with template variables (Issue #1083) */
  custom_prompt_template?: string
  /** Custom criteria definitions (Issue #1083) */
  custom_criteria?: Record<string, CustomCriteriaDefinition>
  /** Custom field mappings - maps template variables to task data fields (e.g., {"domain": "$context.jurisdiction"}) */
  field_mappings?: Record<string, string>

  // For FactCC
  method?: 'summac' | 'factcc'

  // For semantic similarity
  model?: string

  // Generic parameters
  [key: string]: any
}

/**
 * Individual evaluation configuration
 * Represents a single evaluation setup with metric, fields, and parameters
 */
export interface EvaluationConfig {
  /** Unique identifier for this evaluation */
  id: string

  /** Metric to use (e.g., "rouge", "bleu", "llm_judge", "bertscore") */
  metric: string

  /** Display name for UI */
  display_name?: string

  /** Metric-specific parameters */
  metric_parameters?: MetricParameters

  /**
   * Fields to evaluate (prediction fields)
   * Can include special values: "__all_model__", "__all_human__"
   * or specific field names
   */
  prediction_fields: string[]

  /**
   * Reference fields to compare against
   * Supports multiple reference fields for comparison
   */
  reference_fields: string[]

  /** Whether this evaluation is enabled */
  enabled: boolean

  /** Creation timestamp */
  created_at?: string
}

/**
 * Project-level evaluation configuration
 * Contains all configured evaluations for a project
 */
export interface ProjectEvaluationConfig {
  /** List of configured evaluations */
  evaluations: EvaluationConfig[]

  /** Configuration version for cache invalidation */
  config_version?: string

  /** Last modification timestamp */
  last_updated?: string
}

/**
 * Available fields for evaluation mapping
 */
export interface AvailableEvaluationFields {
  /** Model response fields from LLM generations */
  model_response_fields: string[]

  /** Human annotation fields */
  human_annotation_fields: string[]

  /** All fields (combined) */
  all_fields: string[]

  /** Reference/ground truth fields */
  reference_fields: string[]
}

/**
 * Metric category for grouping in UI
 */
export interface MetricCategory {
  name: string
  description: string
  metrics: string[]
}

/**
 * Available metric with metadata
 */
export interface AvailableMetric {
  name: string
  display_name: string
  description: string
  category: string
  status: 'stable' | 'beta' | 'coming-soon'
  supports_parameters: boolean
  parameter_schema?: Record<string, any>
}

/**
 * LLM-as-Judge specific configuration for multi-field evaluation
 */
export interface LLMJudgeConfig {
  judge_model: string
  dimensions: string[]
  custom_prompt?: string
}

/**
 * Judge configuration for unified evaluation endpoint
 * Used when llm_judge_* metrics are selected
 */
export interface JudgeConfig {
  /** Provider: openai, anthropic, google, deepinfra, grok, mistral, cohere */
  provider:
    | 'openai'
    | 'anthropic'
    | 'google'
    | 'deepinfra'
    | 'grok'
    | 'mistral'
    | 'cohere'
  /** Model ID (e.g., gpt-4o, claude-3-5-sonnet-20241022) */
  model: string
  /** Temperature (0.0 recommended for reproducibility) */
  temperature?: number
}

/**
 * Request body for running automated evaluation
 */
export interface AutomatedEvaluationRequest {
  project_id: string
  force_rerun?: boolean
  batch_size?: number
  label_config_version?: string
  /** Required if llm_judge_* metrics are selected */
  judge_config?: JudgeConfig
}

/**
 * All available LLM Judge dimensions (default text-based criteria)
 */
export const LLM_JUDGE_DIMENSIONS = [
  'helpfulness',
  'correctness',
  'fluency',
  'coherence',
  'relevance',
  'safety',
  'accuracy',
] as const

export type LLMJudgeDimension = (typeof LLM_JUDGE_DIMENSIONS)[number]

/**
 * Type-specific LLM Judge dimensions
 */
export const TYPE_SPECIFIC_DIMENSIONS = {
  // For spans/NER
  boundary_accuracy: 'Boundary Accuracy',
  label_accuracy: 'Label Accuracy',
  coverage: 'Entity Coverage',
  span_precision: 'Span Precision',
  // For choices/classification
  accuracy: 'Selection Accuracy',
  reasoning: 'Reasoning Quality',
  set_accuracy: 'Set Accuracy (Multi-select)',
  partial_credit: 'Partial Credit Score',
  // For numeric/rating
  precision: 'Numeric Precision',
  scale_appropriateness: 'Scale Appropriateness',
  magnitude_accuracy: 'Magnitude Accuracy',
} as const

export type TypeSpecificDimension = keyof typeof TYPE_SPECIFIC_DIMENSIONS

/**
 * Field type information from API (used for auto-detection)
 */
export interface FieldTypeInfo {
  /** Answer type (e.g., span_selection, choices, long_text, rating) */
  type: string
  /** Label Studio tag (e.g., Labels, Choices, TextArea, Rating) */
  tag: string
  /** Recommended LLM Judge criteria for this answer type */
  recommended_criteria: string[]
}

/**
 * API response for field types endpoint
 */
export interface FieldTypesResponse {
  project_id: string
  field_types: Record<string, FieldTypeInfo>
}

/**
 * LLM Judge template configuration for each answer type
 */
export interface LLMJudgeTemplate {
  /** Human-readable name */
  name: string
  /** Description of when to use this template */
  description: string
  /** Default criteria for this answer type */
  criteria: string[]
  /** Hint text for UI */
  hint?: string
}

/**
 * Pre-built LLM Judge templates for different answer types
 * Maps answer_type to template configuration
 */
export const LLM_JUDGE_TEMPLATES: Record<string, LLMJudgeTemplate> = {
  text: {
    name: 'Free-form Text',
    description:
      'Evaluate quality, correctness, and coherence of text responses',
    criteria: [
      'helpfulness',
      'correctness',
      'fluency',
      'coherence',
      'relevance',
    ],
    hint: 'Best for essays, summaries, explanations, and open-ended responses',
  },
  short_text: {
    name: 'Short Text',
    description: 'Evaluate brief text responses',
    criteria: ['correctness', 'relevance'],
    hint: 'Best for short answers, fill-in-the-blank',
  },
  long_text: {
    name: 'Long Text',
    description: 'Evaluate detailed text responses',
    criteria: [
      'helpfulness',
      'correctness',
      'fluency',
      'coherence',
      'relevance',
    ],
    hint: 'Best for essays, detailed explanations',
  },
  choices: {
    name: 'Classification (Single Choice)',
    description: 'Evaluate if the correct single choice was selected',
    criteria: ['accuracy', 'reasoning'],
    hint: 'Best for single-choice questions, yes/no, binary decisions',
  },
  single_choice: {
    name: 'Single Choice',
    description: 'Evaluate single selection from options',
    criteria: ['accuracy', 'reasoning'],
    hint: 'Best for radio button selections',
  },
  binary: {
    name: 'Binary Choice',
    description: 'Evaluate yes/no or true/false selections',
    criteria: ['accuracy'],
    hint: 'Best for yes/no, true/false questions',
  },
  multiple_choice: {
    name: 'Multiple Choice (Multi-select)',
    description: 'Evaluate selection of multiple correct items',
    criteria: ['set_accuracy', 'partial_credit', 'reasoning'],
    hint: 'Best for checkbox selections, multiple correct answers',
  },
  span_selection: {
    name: 'Named Entity Recognition (NER)',
    description: 'Evaluate entity boundaries AND labels (strictest mode)',
    criteria: ['boundary_accuracy', 'label_accuracy', 'coverage'],
    hint: 'Evaluates both WHERE spans are and WHAT they are labeled',
  },
  rating: {
    name: 'Rating Scale',
    description: 'Evaluate numeric rating predictions (e.g., 1-5 stars)',
    criteria: ['precision', 'scale_appropriateness'],
    hint: 'Best for star ratings, Likert scales',
  },
  numeric: {
    name: 'Numeric Value',
    description: 'Evaluate numeric predictions',
    criteria: ['precision', 'magnitude_accuracy'],
    hint: 'Best for numerical answers, measurements',
  },
}

/**
 * Default prompt templates for LLM-as-Judge evaluation
 * These match the backend templates in llm_judge_prompts.py
 * Issue #1083 - Custom LLM Judge Prompts
 */
export const DEFAULT_PROMPT_TEMPLATES: Record<
  string,
  { name: string; template: string }
> = {
  text: {
    name: 'Free-form Text Evaluation',
    template: `You are an expert evaluator assessing the quality of an AI-generated text response.

## Task Context
{context}

## Reference Answer (Ground Truth)
{ground_truth}

## Model Response to Evaluate
{prediction}

## Evaluation Criterion: {criterion_name}
{criterion_description}

### Scoring Rubric
{rubric}

## Instructions
1. Carefully compare the model response to the reference answer
2. Assess the response according to the criterion above
3. Provide your score and a brief justification

Respond in JSON format:
{
    "score": <integer 1-5>,
    "justification": "<brief explanation of your score>"
}`,
  },
  choices: {
    name: 'Classification/Selection Evaluation',
    template: `You are an expert evaluator assessing a classification/selection prediction.

## Task Context
{context}

## Correct Answer(s)
{ground_truth}

## Model's Selection
{prediction}

## Evaluation Criterion: {criterion_name}
{criterion_description}

### Scoring Rubric
{rubric}

## Instructions
1. Compare the model's selection against the correct answer(s)
2. For single-choice: check for exact match
3. For multi-choice: evaluate both precision and recall
4. Consider if partial credit is appropriate

Respond in JSON format:
{
    "score": <integer 1-5>,
    "justification": "<explanation focusing on which choices match/differ>"
}`,
  },
  span_selection: {
    name: 'NER/Span Annotation Evaluation',
    template: `You are an expert evaluator assessing Named Entity Recognition (NER) / span annotations.

## Source Text
{context}

## Reference Annotations (Ground Truth)
{ground_truth}

## Model Annotations (Prediction)
{prediction}

## Evaluation Criterion: {criterion_name}
{criterion_description}

### Scoring Rubric
{rubric}

## Instructions
Evaluate the model's span annotations considering:
1. **Boundary Accuracy**: Are the character start/end positions correct?
2. **Label Accuracy**: Are the assigned entity labels correct?
3. **Coverage**: Are all entities from the reference found?
4. **Precision**: Are there spurious/incorrect spans?

Respond in JSON format:
{
    "score": <integer 1-5>,
    "justification": "<specific analysis of span quality>"
}`,
  },
  numeric: {
    name: 'Numeric/Rating Evaluation',
    template: `You are an expert evaluator assessing a numeric/rating prediction.

## Task Context
{context}

## Reference Value
{ground_truth}

## Model's Prediction
{prediction}

## Evaluation Criterion: {criterion_name}
{criterion_description}

### Scoring Rubric
{rubric}

## Instructions
1. Compare the predicted numeric value to the reference
2. Consider the scale and context of the measurement
3. Evaluate if the prediction is within acceptable tolerance
4. For ratings: consider if adjacent values are acceptable

Respond in JSON format:
{
    "score": <integer 1-5>,
    "justification": "<analysis of the numeric difference>"
}`,
  },
}

/**
 * Get display name for a dimension/criterion
 */
export function getDimensionDisplayName(dimension: string): string {
  // Check type-specific dimensions first
  if (dimension in TYPE_SPECIFIC_DIMENSIONS) {
    return TYPE_SPECIFIC_DIMENSIONS[dimension as TypeSpecificDimension]
  }
  // Fall back to capitalizing
  return (
    dimension.charAt(0).toUpperCase() + dimension.slice(1).replace(/_/g, ' ')
  )
}

/**
 * Helper function to check if a field specifier is a special value
 */
export function isSpecialFieldValue(value: string): value is FieldSpecifier {
  return (
    value === FIELD_SPECIFIERS.ALL_MODEL || value === FIELD_SPECIFIERS.ALL_HUMAN
  )
}

/**
 * Helper function to get display name for field specifiers
 */
export function getFieldDisplayName(field: string): string {
  switch (field) {
    case FIELD_SPECIFIERS.ALL_MODEL:
      return 'All model responses'
    case FIELD_SPECIFIERS.ALL_HUMAN:
      return 'All human annotations'
    default:
      return field
  }
}

/**
 * Helper to generate a unique evaluation ID
 */
export function generateEvaluationId(metric: string): string {
  const timestamp = Date.now().toString(36)
  const random = Math.random().toString(36).substring(2, 6)
  return `${metric}-${timestamp}-${random}`
}

/**
 * Metric definitions with categories
 */
export const METRIC_DEFINITIONS: Record<string, AvailableMetric> = {
  // Lexical Metrics
  bleu: {
    name: 'bleu',
    display_name: 'BLEU',
    description: 'Bilingual Evaluation Understudy (n-gram precision)',
    category: 'Lexical Metrics',
    status: 'stable',
    supports_parameters: true,
    parameter_schema: {
      max_order: {
        type: 'number',
        min: 1,
        max: 4,
        default: 4,
        description: 'Maximum n-gram order',
      },
      smoothing: {
        type: 'select',
        options: ['method1', 'method2', 'method3', 'method4'],
        default: 'method1',
        description: 'Smoothing method',
      },
    },
  },
  rouge: {
    name: 'rouge',
    display_name: 'ROUGE',
    description: 'Recall-Oriented Understudy for Gisting Evaluation',
    category: 'Lexical Metrics',
    status: 'stable',
    supports_parameters: true,
    parameter_schema: {
      variant: {
        type: 'select',
        options: ['rouge1', 'rouge2', 'rougeL', 'rougeLsum'],
        default: 'rougeL',
        description: 'ROUGE variant',
      },
      use_stemmer: {
        type: 'boolean',
        default: true,
        description: 'Apply word stemming',
      },
    },
  },
  meteor: {
    name: 'meteor',
    display_name: 'METEOR',
    description: 'Metric for Evaluation of Translation with Explicit Ordering',
    category: 'Lexical Metrics',
    status: 'stable',
    supports_parameters: true,
    parameter_schema: {
      alpha: {
        type: 'number',
        min: 0,
        max: 1,
        step: 0.1,
        default: 0.9,
        description: 'Weight for precision',
      },
      beta: {
        type: 'number',
        min: 0,
        max: 10,
        step: 0.5,
        default: 3.0,
        description: 'Weight for recall',
      },
      gamma: {
        type: 'number',
        min: 0,
        max: 1,
        step: 0.1,
        default: 0.5,
        description: 'Fragmentation penalty',
      },
    },
  },
  chrf: {
    name: 'chrf',
    display_name: 'chrF',
    description: 'Character-level F-score (language-agnostic)',
    category: 'Lexical Metrics',
    status: 'stable',
    supports_parameters: true,
    parameter_schema: {
      char_order: {
        type: 'number',
        min: 1,
        max: 10,
        default: 6,
        description: 'Character n-gram order',
      },
      word_order: {
        type: 'number',
        min: 0,
        max: 4,
        default: 0,
        description: 'Word n-gram order (0 = char-only)',
      },
      beta: {
        type: 'number',
        min: 1,
        max: 5,
        step: 0.5,
        default: 2,
        description: 'Recall weight vs precision',
      },
    },
  },
  exact_match: {
    name: 'exact_match',
    display_name: 'Exact Match',
    description: 'Exact string matching',
    category: 'Lexical Metrics',
    status: 'stable',
    supports_parameters: false,
  },

  // Semantic Metrics
  bertscore: {
    name: 'bertscore',
    display_name: 'BERTScore',
    description: 'BERT-based semantic similarity',
    category: 'Semantic Metrics',
    status: 'stable',
    supports_parameters: false,
  },
  moverscore: {
    name: 'moverscore',
    display_name: 'MoverScore',
    description: "Earth Mover's Distance on embeddings",
    category: 'Semantic Metrics',
    status: 'stable',
    supports_parameters: false,
  },
  semantic_similarity: {
    name: 'semantic_similarity',
    display_name: 'Semantic Similarity',
    description: 'Cosine similarity of sentence embeddings',
    category: 'Semantic Metrics',
    status: 'stable',
    supports_parameters: false,
  },

  // Factuality Metrics
  factcc: {
    name: 'factcc',
    display_name: 'FactCC',
    description: 'Factual consistency checking',
    category: 'Factuality Metrics',
    status: 'stable',
    supports_parameters: true,
    parameter_schema: {
      method: {
        type: 'select',
        options: ['summac', 'factcc'],
        default: 'summac',
      },
    },
  },
  qags: {
    name: 'qags',
    display_name: 'QAGS',
    description: 'Question Answering-based summarization quality',
    category: 'Factuality Metrics',
    status: 'stable',
    supports_parameters: false,
  },
  coherence: {
    name: 'coherence',
    display_name: 'Coherence',
    description: 'Text coherence and logical flow',
    category: 'Factuality Metrics',
    status: 'stable',
    supports_parameters: false,
  },

  // Classification Metrics
  accuracy: {
    name: 'accuracy',
    display_name: 'Accuracy',
    description: 'Percentage of correct predictions',
    category: 'Classification Metrics',
    status: 'stable',
    supports_parameters: false,
  },
  precision: {
    name: 'precision',
    display_name: 'Precision',
    description: 'True positives / (True positives + False positives)',
    category: 'Classification Metrics',
    status: 'stable',
    supports_parameters: false,
  },
  recall: {
    name: 'recall',
    display_name: 'Recall',
    description: 'True positives / (True positives + False negatives)',
    category: 'Classification Metrics',
    status: 'stable',
    supports_parameters: false,
  },
  f1: {
    name: 'f1',
    display_name: 'F1 Score',
    description: 'Harmonic mean of precision and recall',
    category: 'Classification Metrics',
    status: 'stable',
    supports_parameters: false,
  },

  // LLM-as-Judge - Two consolidated options
  llm_judge_classic: {
    name: 'llm_judge_classic',
    display_name: 'Classic LLM Judge',
    description: 'Evaluate using predefined dimensions (Helpfulness, Correctness, Fluency, etc.)',
    category: 'LLM-as-Judge',
    status: 'stable',
    supports_parameters: true,
  },
  llm_judge_custom: {
    name: 'llm_judge_custom',
    display_name: 'Custom LLM Judge',
    description: 'Create a fully custom evaluation with your own prompt and criteria',
    category: 'LLM-as-Judge',
    status: 'stable',
    supports_parameters: true,
  },
}

/**
 * Grouped metrics by category for UI display
 */
export const GROUPED_METRICS: MetricCategory[] = [
  {
    name: 'Lexical Metrics',
    description: 'String and surface-level matching',
    metrics: ['exact_match', 'bleu', 'rouge', 'meteor', 'chrf'],
  },
  {
    name: 'Semantic Metrics',
    description: 'Embedding-based semantic comparison',
    metrics: ['semantic_similarity', 'bertscore', 'moverscore'],
  },
  {
    name: 'Factuality Metrics',
    description: 'Content quality and factual accuracy',
    metrics: ['factcc', 'qags', 'coherence'],
  },
  {
    name: 'Classification Metrics',
    description: 'For categorical predictions',
    metrics: ['accuracy', 'precision', 'recall', 'f1'],
  },
  {
    name: 'LLM-as-Judge',
    description: 'AI model-based evaluation (requires judge_config)',
    metrics: [
      'llm_judge_classic',
      'llm_judge_custom',
    ],
  },
]

// =============================================================================
// Extension points for extended metrics
// =============================================================================

const _extendedMetrics: Record<string, AvailableMetric> = {}
const _extendedGroups: MetricCategory[] = []

/**
 * Register an additional metric definition (called by @benger/extended).
 */
export function registerMetric(key: string, definition: AvailableMetric) {
  _extendedMetrics[key] = definition
}

/**
 * Register an additional metric group for UI display (called by @benger/extended).
 */
export function registerMetricGroup(group: MetricCategory) {
  _extendedGroups.push(group)
}

/**
 * Get all metric definitions (core + extended).
 */
export function getMetricDefinitions(): Record<string, AvailableMetric> {
  return { ...METRIC_DEFINITIONS, ..._extendedMetrics }
}

/**
 * Get all metric groups (core + extended).
 */
export function getGroupedMetrics(): MetricCategory[] {
  return [...GROUPED_METRICS, ..._extendedGroups]
}
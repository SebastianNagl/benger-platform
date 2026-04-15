/**
 * Generation Template
 *
 * Long-form text generation tasks for comprehensive legal analysis and document creation.
 * Open-ended text generation tasks with customizable prompts.
 *
 * Issue #216: Implement Unified Task Configuration and Display System
 */

import { TaskTemplate } from '@/types/taskTemplate'

export const generationTemplate: TaskTemplate = {
  id: 'generation',
  name: 'Text Generation',
  version: '1.0',
  description: 'Open-ended text generation tasks with customizable prompts',
  category: 'generation',

  fields: [
    {
      name: 'context_document',
      label: 'Context Document',
      type: 'text_area',
      source: 'task_data',
      required: true,
      display: {
        creation: 'editable',
        annotation: 'readonly',
        table: 'hidden',
      },
      validation: [
        { type: 'minLength', value: 100 },
        { type: 'maxLength', value: 20000 },
      ],
      placeholder: 'Provide the context document or source material',
    },
    {
      name: 'system_prompt',
      label: 'System Prompt',
      type: 'text_area',
      source: 'task_data',
      required: true,
      display: {
        creation: 'editable',
        annotation: 'readonly',
        table: 'hidden',
      },
      validation: [
        { type: 'minLength', value: 20 },
        { type: 'maxLength', value: 2000 },
      ],
      placeholder: 'Define the system prompt that guides the generation task',
    },
    {
      name: 'instructions',
      label: 'Task Instructions',
      type: 'text_area',
      source: 'task_data',
      required: true,
      display: {
        creation: 'editable',
        annotation: 'readonly',
        table: 'column',
      },
      validation: [
        { type: 'minLength', value: 50 },
        { type: 'maxLength', value: 3000 },
      ],
      placeholder: 'Provide specific instructions for the generation task',
    },
    {
      name: 'expected_length',
      label: 'Expected Length (words)',
      type: 'number',
      source: 'task_data',
      required: false,
      display: {
        creation: 'editable',
        annotation: 'readonly',
        table: 'hidden',
      },
      validation: [
        { type: 'min', value: 10 },
        { type: 'max', value: 10000 },
      ],
      placeholder: 'Expected word count for the generated text',
    },
    {
      name: 'generation_type',
      label: 'Generation Type',
      type: 'radio',
      source: 'task_data',
      required: true,
      display: {
        creation: 'editable',
        annotation: 'readonly',
        table: 'column',
      },
      choices: [
        'summary',
        'analysis',
        'opinion',
        'creative_writing',
        'technical_document',
        'legal_brief',
        'other',
      ],
    },
    {
      name: 'generated_text',
      label: 'Generated Text',
      type: 'rich_text',
      source: 'annotation',
      required: true,
      display: {
        creation: 'hidden',
        annotation: 'editable',
        table: 'hidden',
      },
      validation: [
        { type: 'minLength', value: 50 },
        { type: 'maxLength', value: 50000 },
      ],
      placeholder:
        'Generate the requested text here with rich formatting support',
    },
    {
      name: 'quality_assessment',
      label: 'Quality Assessment',
      type: 'checkbox',
      source: 'annotation',
      required: false,
      display: {
        creation: 'hidden',
        annotation: 'editable',
        table: 'column',
      },
      choices: [
        'factually_accurate',
        'well_structured',
        'coherent_flow',
        'appropriate_tone',
        'meets_requirements',
        'creative_approach',
        'comprehensive_coverage',
      ],
    },
    {
      name: 'coherence_score',
      label: 'Coherence Score',
      type: 'rating',
      source: 'annotation',
      required: true,
      display: {
        creation: 'hidden',
        annotation: 'editable',
        table: 'column',
      },
      validation: [
        { type: 'min', value: 1 },
        { type: 'max', value: 10 },
      ],
      metadata: {
        labels: {
          1: 'Poor',
          3: 'Below Average',
          5: 'Average',
          7: 'Good',
          10: 'Excellent',
        },
      },
    },
    {
      name: 'relevance_score',
      label: 'Relevance Score',
      type: 'rating',
      source: 'annotation',
      required: true,
      display: {
        creation: 'hidden',
        annotation: 'editable',
        table: 'column',
      },
      validation: [
        { type: 'min', value: 1 },
        { type: 'max', value: 10 },
      ],
      metadata: {
        labels: {
          1: 'Irrelevant',
          3: 'Somewhat Relevant',
          5: 'Relevant',
          7: 'Highly Relevant',
          10: 'Perfect Match',
        },
      },
    },
    {
      name: 'creativity_score',
      label: 'Creativity Score',
      type: 'rating',
      source: 'annotation',
      required: false,
      display: {
        creation: 'hidden',
        annotation: 'editable',
        table: 'column',
      },
      validation: [
        { type: 'min', value: 1 },
        { type: 'max', value: 10 },
      ],
      metadata: {
        labels: {
          1: 'Not Creative',
          3: 'Somewhat Creative',
          5: 'Creative',
          7: 'Very Creative',
          10: 'Exceptionally Creative',
        },
      },
    },
    {
      name: 'word_count',
      label: 'Actual Word Count',
      type: 'number',
      source: 'annotation',
      required: false,
      display: {
        creation: 'hidden',
        annotation: 'editable',
        table: 'column',
      },
      validation: [
        { type: 'min', value: 0 },
        { type: 'max', value: 50000 },
      ],
    },
    {
      name: 'improvement_suggestions',
      label: 'Improvement Suggestions',
      type: 'text_area',
      source: 'annotation',
      required: false,
      display: {
        creation: 'hidden',
        annotation: 'editable',
        table: 'hidden',
      },
      validation: [{ type: 'maxLength', value: 2000 }],
      placeholder: 'Provide suggestions for improving the generated text',
    },
  ],

  display_config: {
    table_columns: [
      'instructions',
      'generation_type',
      'coherence_score',
      'relevance_score',
      'word_count',
    ],
    answer_display: {
      fields: [
        'generated_text',
        'quality_assessment',
        'improvement_suggestions',
      ],
      separator: 'divider',
    },
    column_widths: {
      instructions: 300,
      generation_type: 150,
      coherence_score: 120,
      relevance_score: 120,
      word_count: 100,
    },
  },

  llm_config: {
    prompt_template: `Generate text based on the following requirements:

Context: {{context_document}}

System Prompt: {{system_prompt}}

Instructions: {{instructions}}

{{#expected_length}}
Expected Length: {{expected_length}} words
{{/expected_length}}

Type: {{generation_type}}

Please generate high-quality text that meets these requirements.`,
    response_parser: 'generationParser',
  },

  evaluation_config: {
    metrics: [
      { name: 'bleu', type: 'bleu' },
      { name: 'rouge_l', type: 'rouge' },
      { name: 'semantic_similarity', type: 'custom' },
      { name: 'coherence', type: 'custom' },
      { name: 'length_appropriateness', type: 'custom' },
    ],
    requires_reference: false,
    threshold: 0.6,
  },

  metadata: {
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    tags: ['generation', 'creative', 'analysis'],
  },
}

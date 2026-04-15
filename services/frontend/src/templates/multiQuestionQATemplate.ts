/**
 * Multi-Question QA Template
 *
 * Supports multiple question-answer pairs in a single task.
 * Allows adding questions during creation with corresponding answers.
 *
 * Issue #216: Implement Unified Task Configuration and Display System
 */

import { TaskTemplate } from '@/types/taskTemplate'

export const multiQuestionQATemplate: TaskTemplate = {
  id: 'multi_qa',
  name: 'Multi-Question QA',
  version: '1.0',
  description:
    'Create tasks with multiple question-answer pairs. Add questions during creation and provide answers.',
  category: 'qa',

  fields: [
    {
      name: 'questions',
      label: 'Questions',
      type: 'text_area',
      source: 'task_data',
      required: false,
      display: {
        creation: 'editable',
        annotation: 'readonly',
        table: 'column',
      },
      validation: [{ type: 'maxLength', value: 5000 }],
      placeholder:
        'Enter questions (one per line). You can add more questions later during annotation.',
      metadata: {
        multiline: true,
        hint: 'Enter each question on a new line. Questions are optional during creation.',
      },
    },
    {
      name: 'initial_answers',
      label: 'Initial Answers (Optional)',
      type: 'text_area',
      source: 'task_data',
      required: false,
      display: {
        creation: 'editable',
        annotation: 'readonly',
        table: 'hidden',
      },
      condition: {
        type: 'exists',
        field: 'questions',
      },
      validation: [{ type: 'maxLength', value: 5000 }],
      placeholder:
        'Provide answers for the questions above (one per line, matching the order)',
      metadata: {
        multiline: true,
        hint: 'If you provide questions, you can optionally provide initial answers.',
      },
    },
    {
      name: 'context',
      label: 'Context (Optional)',
      type: 'text_area',
      source: 'task_data',
      required: false,
      display: {
        creation: 'editable',
        annotation: 'readonly',
        table: 'hidden',
      },
      validation: [{ type: 'maxLength', value: 5000 }],
      placeholder: 'Provide background context that applies to all questions',
    },
    {
      name: 'answers',
      label: 'Answers',
      type: 'text_area',
      source: 'annotation',
      required: true,
      display: {
        creation: 'hidden',
        annotation: 'editable',
        table: 'column',
      },
      validation: [
        { type: 'minLength', value: 1 },
        { type: 'maxLength', value: 5000 },
      ],
      placeholder: 'Provide answers for each question (one per line)',
      metadata: {
        multiline: true,
        hint: 'Answer each question on a new line, in the same order as the questions.',
      },
    },
    {
      name: 'confidence_scores',
      label: 'Confidence Scores',
      type: 'text',
      source: 'annotation',
      required: false,
      display: {
        creation: 'hidden',
        annotation: 'editable',
        table: 'hidden',
      },
      validation: [{ type: 'pattern', value: '^[1-5](,[1-5])*$' }],
      placeholder: 'Rate confidence for each answer (1-5, comma-separated)',
      metadata: {
        hint: 'Example: 4,5,3 for three answers with confidence levels 4, 5, and 3',
      },
    },
    {
      name: 'explanations',
      label: 'Explanations (Optional)',
      type: 'text_area',
      source: 'annotation',
      required: false,
      display: {
        creation: 'hidden',
        annotation: 'editable',
        table: 'hidden',
      },
      validation: [{ type: 'maxLength', value: 3000 }],
      placeholder: 'Provide explanations for your answers (optional)',
      metadata: {
        multiline: true,
      },
    },
  ],

  display_config: {
    table_columns: ['questions', 'answers'],
    answer_display: {
      fields: ['answers', 'explanations'],
      separator: 'divider',
    },
    column_widths: {
      questions: 350,
      answers: 350,
    },
  },

  llm_config: {
    prompt_template: `Answer the following questions based on the provided context:

{{#context}}
Context: {{context}}
{{/context}}

Questions:
{{questions}}

Provide clear, accurate answers for each question.`,
    response_parser: 'multiLineParser',
  },

  evaluation_config: {
    metrics: [
      { name: 'exact_match', type: 'accuracy' },
      { name: 'f1', type: 'f1' },
      { name: 'per_question_accuracy', type: 'custom' },
    ],
    requires_reference: true,
    threshold: 0.7,
  },

  metadata: {
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    tags: ['qa', 'multi-question', 'batch'],
  },
}

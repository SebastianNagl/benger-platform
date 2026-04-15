/**
 * Multiple Choice Question Template
 *
 * Four-option multiple choice questions for standardized legal assessments.
 * Single or multiple correct answers from predefined options.
 *
 * Issue #216: Implement Unified Task Configuration and Display System
 */

import { TaskTemplate } from '@/types/taskTemplate'

export const multipleChoiceTemplate: TaskTemplate = {
  id: 'multiple_choice',
  name: 'Multiple Choice',
  version: '1.0',
  description: 'Single or multiple correct answers from predefined options',
  category: 'multiple_choice',

  fields: [
    {
      name: 'question',
      label: 'Question',
      type: 'text_area',
      source: 'task_data',
      required: true,
      display: {
        creation: 'editable',
        annotation: 'readonly',
        table: 'column',
      },
      validation: [
        { type: 'minLength', value: 20 },
        { type: 'maxLength', value: 1500 },
      ],
      placeholder: 'Enter the multiple choice question',
    },
    {
      name: 'question_context',
      label: 'Context/Background',
      type: 'text_area',
      source: 'task_data',
      required: false,
      display: {
        creation: 'editable',
        annotation: 'readonly',
        table: 'hidden',
      },
      validation: [{ type: 'maxLength', value: 3000 }],
      placeholder: 'Provide context or background information if needed',
    },
    {
      name: 'option_a',
      label: 'Option A',
      type: 'text_area',
      source: 'task_data',
      required: true,
      display: {
        creation: 'editable',
        annotation: 'readonly',
        table: 'hidden',
      },
      validation: [
        { type: 'minLength', value: 1 },
        { type: 'maxLength', value: 500 },
      ],
      placeholder: 'Enter option A',
    },
    {
      name: 'option_b',
      label: 'Option B',
      type: 'text_area',
      source: 'task_data',
      required: true,
      display: {
        creation: 'editable',
        annotation: 'readonly',
        table: 'hidden',
      },
      validation: [
        { type: 'minLength', value: 1 },
        { type: 'maxLength', value: 500 },
      ],
      placeholder: 'Enter option B',
    },
    {
      name: 'option_c',
      label: 'Option C',
      type: 'text_area',
      source: 'task_data',
      required: true,
      display: {
        creation: 'editable',
        annotation: 'readonly',
        table: 'hidden',
      },
      validation: [
        { type: 'minLength', value: 1 },
        { type: 'maxLength', value: 500 },
      ],
      placeholder: 'Enter option C',
    },
    {
      name: 'option_d',
      label: 'Option D',
      type: 'text_area',
      source: 'task_data',
      required: true,
      display: {
        creation: 'editable',
        annotation: 'readonly',
        table: 'hidden',
      },
      validation: [
        { type: 'minLength', value: 1 },
        { type: 'maxLength', value: 500 },
      ],
      placeholder: 'Enter option D',
    },
    {
      name: 'selected_answer',
      label: 'Selected Answer',
      type: 'radio',
      source: 'annotation',
      required: true,
      display: {
        creation: 'hidden',
        annotation: 'editable',
        table: 'column',
      },
      choices: ['A', 'B', 'C', 'D'],
    },
    {
      name: 'confidence',
      label: 'Confidence Level',
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
        { type: 'max', value: 5 },
      ],
      metadata: {
        labels: {
          1: 'Very Low',
          2: 'Low',
          3: 'Medium',
          4: 'High',
          5: 'Very High',
        },
      },
    },
    {
      name: 'reasoning',
      label: 'Reasoning (Optional)',
      type: 'text_area',
      source: 'annotation',
      required: false,
      display: {
        creation: 'hidden',
        annotation: 'editable',
        table: 'hidden',
      },
      validation: [{ type: 'maxLength', value: 1000 }],
      placeholder: 'Explain your reasoning for choosing this answer',
    },
    {
      name: 'eliminated_options',
      label: 'Eliminated Options',
      type: 'checkbox',
      source: 'annotation',
      required: false,
      display: {
        creation: 'hidden',
        annotation: 'editable',
        table: 'hidden',
      },
      choices: ['A', 'B', 'C', 'D'],
    },
    {
      name: 'time_spent',
      label: 'Time Spent (seconds)',
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
        { type: 'max', value: 3600 },
      ],
    },
  ],

  display_config: {
    table_columns: ['question', 'selected_answer', 'confidence', 'time_spent'],
    answer_display: {
      fields: ['selected_answer', 'reasoning'],
      separator: 'divider',
    },
    column_widths: {
      question: 350,
      selected_answer: 100,
      confidence: 120,
      time_spent: 120,
    },
  },

  llm_config: {
    prompt_template: `Answer the following multiple choice question:

Question: {{question}}

{{#question_context}}
Context: {{question_context}}
{{/question_context}}

Options:
A) {{option_a}}
B) {{option_b}}
C) {{option_c}}
D) {{option_d}}

Select the best answer and provide your reasoning.`,
    response_parser: 'multipleChoiceParser',
  },

  evaluation_config: {
    metrics: [
      { name: 'accuracy', type: 'accuracy' },
      { name: 'exact_match', type: 'accuracy' },
      { name: 'choice_distribution', type: 'custom' },
      { name: 'confidence_correlation', type: 'custom' },
    ],
    requires_reference: true,
    threshold: 0.8,
  },

  metadata: {
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    tags: ['mcq', 'options'],
  },
}

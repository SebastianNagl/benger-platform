/**
 * QA (Question & Answer) Template
 *
 * Simple question-answer pairs for testing comprehension and factual knowledge.
 *
 * Issue #216: Implement Unified Task Configuration and Display System
 */

import { TaskTemplate } from '@/types/taskTemplate'

export const qaTemplate: TaskTemplate = {
  id: 'qa',
  name: 'Question & Answer',
  version: '1.0',
  description:
    'Simple question-answer pairs for testing comprehension and factual knowledge',
  category: 'qa',

  fields: [
    {
      name: 'question',
      label: 'Question (Optional)',
      type: 'text_area',
      source: 'task_data',
      required: false,
      display: {
        creation: 'editable',
        annotation: 'readonly',
        table: 'column',
      },
      validation: [{ type: 'maxLength', value: 1000 }],
      placeholder:
        'Enter the question to be answered (you can add more questions later)',
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
      placeholder: 'Provide background context if needed',
    },
    {
      name: 'reference_answer',
      label: 'Reference Answer (Optional)',
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
        field: 'question',
      },
      validation: [{ type: 'maxLength', value: 2000 }],
      placeholder: 'Provide a reference answer for this question (optional)',
    },
    {
      name: 'answer',
      label: 'Answer',
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
        { type: 'maxLength', value: 2000 },
      ],
      placeholder: 'Provide a clear and concise answer',
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
      name: 'explanation',
      label: 'Explanation (Optional)',
      type: 'text_area',
      source: 'annotation',
      required: false,
      display: {
        creation: 'hidden',
        annotation: 'editable',
        table: 'hidden',
      },
      validation: [{ type: 'maxLength', value: 1000 }],
      placeholder: 'Provide reasoning or explanation for your answer',
    },
  ],

  display_config: {
    table_columns: ['question', 'answer', 'confidence'],
    answer_display: {
      fields: ['answer', 'explanation'],
      separator: 'divider',
    },
    column_widths: {
      question: 300,
      answer: 250,
      confidence: 120,
    },
  },

  llm_config: {
    prompt_template: `Answer the following question based on the provided context:

Question: {{question}}
{{#context}}
Context: {{context}}
{{/context}}

Provide a clear, accurate answer.`,
    response_parser: 'defaultParser',
  },

  evaluation_config: {
    metrics: [
      { name: 'exact_match', type: 'accuracy' },
      { name: 'f1', type: 'f1' },
      { name: 'semantic_similarity', type: 'custom' },
    ],
    requires_reference: true,
    threshold: 0.7,
  },

  metadata: {
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    tags: ['qa', 'factual'],
  },
}

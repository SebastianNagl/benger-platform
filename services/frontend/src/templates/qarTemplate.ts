/**
 * QAR (Question & Reasoning) Template
 *
 * Complex questions requiring detailed reasoning and explanation of thought process.
 * Legal case analysis, complex reasoning tasks, and legal problem solving.
 *
 * Issue #216: Implement Unified Task Configuration and Display System
 */

import { TaskTemplate } from '@/types/taskTemplate'

export const qarTemplate: TaskTemplate = {
  id: 'qa_reasoning',
  name: 'Question & Reasoning',
  version: '1.0',
  description:
    'Complex questions requiring detailed reasoning and explanation of thought process',
  category: 'qa_reasoning',

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
        { type: 'maxLength', value: 2000 },
      ],
      placeholder: 'Enter the complex question requiring reasoning',
    },
    {
      name: 'case_context',
      label: 'Legal Case Context',
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
        { type: 'maxLength', value: 10000 },
      ],
      placeholder:
        'Provide the legal case context, facts, and relevant background',
    },
    {
      name: 'applicable_law',
      label: 'Applicable Law/Statute',
      type: 'text_area',
      source: 'task_data',
      required: false,
      display: {
        creation: 'editable',
        annotation: 'readonly',
        table: 'hidden',
      },
      validation: [{ type: 'maxLength', value: 3000 }],
      placeholder: 'Specify relevant laws, statutes, or legal principles',
    },
    {
      name: 'initial_analysis',
      label: 'Initial Analysis',
      type: 'text_area',
      source: 'annotation',
      required: true,
      display: {
        creation: 'hidden',
        annotation: 'editable',
        table: 'hidden',
      },
      validation: [
        { type: 'minLength', value: 100 },
        { type: 'maxLength', value: 3000 },
      ],
      placeholder: 'Provide your initial analysis of the legal issue',
    },
    {
      name: 'reasoning_steps',
      label: 'Reasoning Steps',
      type: 'text_area',
      source: 'annotation',
      required: true,
      display: {
        creation: 'hidden',
        annotation: 'editable',
        table: 'hidden',
      },
      validation: [
        { type: 'minLength', value: 150 },
        { type: 'maxLength', value: 4000 },
      ],
      placeholder: 'Break down your reasoning into clear, logical steps',
    },
    {
      name: 'legal_precedents',
      label: 'Legal Precedents',
      type: 'text_area',
      source: 'annotation',
      required: false,
      display: {
        creation: 'hidden',
        annotation: 'editable',
        table: 'hidden',
      },
      validation: [{ type: 'maxLength', value: 2000 }],
      placeholder: 'Cite relevant legal precedents or case law',
    },
    {
      name: 'counterarguments',
      label: 'Counterarguments',
      type: 'text_area',
      source: 'annotation',
      required: false,
      display: {
        creation: 'hidden',
        annotation: 'editable',
        table: 'hidden',
      },
      validation: [{ type: 'maxLength', value: 2000 }],
      placeholder: 'Consider alternative perspectives or counterarguments',
    },
    {
      name: 'final_answer',
      label: 'Final Answer',
      type: 'text_area',
      source: 'annotation',
      required: true,
      display: {
        creation: 'hidden',
        annotation: 'editable',
        table: 'column',
      },
      validation: [
        { type: 'minLength', value: 50 },
        { type: 'maxLength', value: 1500 },
      ],
      placeholder: 'Provide your final, well-reasoned answer',
    },
    {
      name: 'reasoning_quality',
      label: 'Reasoning Quality',
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
          1: 'Poor',
          2: 'Fair',
          3: 'Good',
          4: 'Strong',
          5: 'Excellent',
        },
      },
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
  ],

  display_config: {
    table_columns: [
      'question',
      'final_answer',
      'reasoning_quality',
      'confidence',
    ],
    answer_display: {
      fields: ['initial_analysis', 'reasoning_steps', 'final_answer'],
      separator: 'divider',
    },
    column_widths: {
      question: 300,
      final_answer: 250,
      reasoning_quality: 120,
      confidence: 120,
    },
  },

  llm_config: {
    prompt_template: `Analyze the following legal case and provide detailed reasoning:

Question: {{question}}

Case Context: {{case_context}}

{{#applicable_law}}
Applicable Law: {{applicable_law}}
{{/applicable_law}}

Provide:
1. Initial analysis of the legal issue
2. Step-by-step reasoning process
3. Consideration of relevant precedents
4. Final reasoned conclusion

Your response should demonstrate clear legal reasoning and analysis.`,
    response_parser: 'qarAnalysisParser',
  },

  evaluation_config: {
    metrics: [
      { name: 'exact_match', type: 'accuracy' },
      { name: 'f1', type: 'f1' },
      { name: 'semantic_similarity', type: 'custom' },
      { name: 'answer_relevance', type: 'custom' },
      { name: 'reasoning_quality', type: 'custom' },
    ],
    requires_reference: true,
    threshold: 0.75,
  },

  metadata: {
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    tags: ['qar', 'legal', 'reasoning'],
  },
}

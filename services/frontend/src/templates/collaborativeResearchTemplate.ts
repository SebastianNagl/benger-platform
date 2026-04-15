/**
 * Collaborative Research Template
 *
 * Demonstrates advanced collaborative features with real-time updates,
 * progress tracking, and team coordination.
 *
 * Issue #218: ize Annotation System with Label Studio-Inspired Architecture
 */

import { TaskTemplate } from '@/types/taskTemplate'

export const collaborativeResearchTemplate: TaskTemplate = {
  id: 'collaborative-research',
  name: 'Research Analysis',
  version: '1.0',
  description: 'Multi-annotator research analysis with real-time collaboration',
  category: 'research',

  fields: [
    {
      name: 'research_paper_url',
      label: 'Research Paper URL',
      type: 'url',
      source: 'task_data',
      required: true,
      display: {
        creation: 'editable',
        annotation: 'readonly',
        table: 'column',
      },
      validation: [
        {
          type: 'pattern',
          value: '^https?://.+',
          message: 'Must be a valid URL',
        },
      ],
      placeholder: 'https://example.com/paper.pdf',
    },
    {
      name: 'paper_title',
      label: 'Paper Title',
      type: 'text',
      source: 'task_data',
      required: true,
      display: {
        creation: 'editable',
        annotation: 'readonly',
        table: 'column',
      },
      validation: [
        { type: 'minLength', value: 5 },
        { type: 'maxLength', value: 200 },
      ],
    },
    {
      name: 'research_domain',
      label: 'Research Domain',
      type: 'radio',
      source: 'task_data',
      required: true,
      display: {
        creation: 'editable',
        annotation: 'readonly',
        table: 'column',
      },
      choices: [
        'computer_science',
        'biology',
        'physics',
        'chemistry',
        'medicine',
        'psychology',
        'economics',
        'social_sciences',
      ],
    },
    {
      name: 'methodology_assessment',
      label: 'Methodology Assessment',
      type: 'checkbox',
      source: 'annotation',
      required: true,
      display: {
        creation: 'hidden',
        annotation: 'editable',
        table: 'column',
      },
      choices: [
        'clearly_described',
        'reproducible',
        'appropriate_controls',
        'sufficient_sample_size',
        'proper_statistical_analysis',
        'ethical_considerations',
      ],
    },
    {
      name: 'research_quality',
      label: 'Research Quality Score',
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
      name: 'key_findings',
      label: 'Key Findings',
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
        { type: 'maxLength', value: 2000 },
      ],
      placeholder: 'Summarize the main findings and their significance',
    },
    {
      name: 'limitations_identified',
      label: 'Limitations Identified',
      type: 'text_area',
      source: 'annotation',
      required: false,
      display: {
        creation: 'hidden',
        annotation: 'editable',
        table: 'hidden',
      },
      validation: [{ type: 'maxLength', value: 1500 }],
      placeholder: 'List any limitations or weaknesses in the research',
    },
    {
      name: 'future_research',
      label: 'Future Research Directions',
      type: 'text_area',
      source: 'annotation',
      required: false,
      display: {
        creation: 'hidden',
        annotation: 'editable',
        table: 'hidden',
      },
      validation: [{ type: 'maxLength', value: 1000 }],
      placeholder: 'Suggest areas for future investigation',
    },
    {
      name: 'peer_review_score',
      label: 'Peer Review Score',
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
          1: 'Reject',
          2: 'Major Revisions',
          3: 'Minor Revisions',
          4: 'Accept with Changes',
          5: 'Accept as Is',
        },
      },
    },
    {
      name: 'reviewer_expertise',
      label: 'Reviewer Expertise Level',
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
          1: 'Novice',
          2: 'Basic',
          3: 'Intermediate',
          4: '',
          5: 'Expert',
        },
      },
    },
  ],

  display_config: {
    table_columns: [
      'paper_title',
      'research_domain',
      'research_quality',
      'peer_review_score',
      'reviewer_expertise',
    ],
    answer_display: {
      fields: [
        'key_findings',
        'methodology_assessment',
        'limitations_identified',
      ],
      separator: 'divider',
    },
    column_widths: {
      paper_title: 300,
      research_domain: 150,
      research_quality: 120,
      peer_review_score: 130,
      reviewer_expertise: 130,
    },
  },

  llm_config: {
    prompt_template: `Analyze this research paper for peer review:

Title: {{paper_title}}
URL: {{research_paper_url}}
Domain: {{research_domain}}

Provide a comprehensive review covering:
1. Methodology strengths and weaknesses
2. Significance of findings
3. Overall quality assessment
4. Recommendation for publication

Focus on technical accuracy and research contribution.`,
    response_parser: 'researchAnalysisParser',
  },

  evaluation_config: {
    metrics: [
      { name: 'inter_rater_reliability', type: 'accuracy' },
      { name: 'expertise_consistency', type: 'custom' },
      { name: 'review_quality', type: 'custom' },
    ],
    requires_reference: false,
    threshold: 0.8,
  },

  metadata: {
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    tags: ['research', 'peer-review', 'academic'],
  },
}

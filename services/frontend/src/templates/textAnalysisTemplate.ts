/**
 * Text Analysis Template
 *
 * Demonstrates the annotation system with various field types
 * and enhanced functionality.
 *
 * Issue #218: ize Annotation System with Label Studio-Inspired Architecture
 */

import { TaskTemplate } from '@/types/taskTemplate'

export const textAnalysisTemplate: TaskTemplate = {
  id: 'text-analysis',
  name: 'Text Analysis',
  version: '1.0',
  description: 'Text analysis with highlighting and categorization',
  category: 'text-analysis',

  fields: [
    {
      name: 'source_text',
      label: 'Source Text',
      type: 'text_area',
      source: 'task_data',
      required: true,
      display: {
        creation: 'editable',
        annotation: 'readonly',
        table: 'hidden',
      },
      validation: [
        { type: 'minLength', value: 10 },
        { type: 'maxLength', value: 5000 },
      ],
      placeholder: 'Enter the text to be analyzed',
    },
    {
      name: 'text_category',
      label: 'Text Category',
      type: 'radio',
      source: 'task_data',
      required: true,
      display: {
        creation: 'editable',
        annotation: 'readonly',
        table: 'column',
      },
      choices: [
        'news_article',
        'academic_paper',
        'blog_post',
        'social_media',
        'legal_document',
        'other',
      ],
    },
    {
      name: 'key_phrases',
      label: 'Key Phrases',
      type: 'text_highlight',
      source: 'annotation',
      required: true,
      display: {
        creation: 'hidden',
        annotation: 'editable',
        table: 'column',
      },
      metadata: {
        categories: [
          {
            id: 'entity',
            label: 'Named Entity',
            color: '#3B82F6',
            shortcut: 'e',
          },
          {
            id: 'concept',
            label: 'Key Concept',
            color: '#10B981',
            shortcut: 'c',
          },
          {
            id: 'opinion',
            label: 'Opinion/Sentiment',
            color: '#F59E0B',
            shortcut: 'o',
          },
          {
            id: 'fact',
            label: 'Factual Statement',
            color: '#8B5CF6',
            shortcut: 'f',
          },
          {
            id: 'question',
            label: 'Question/Issue',
            color: '#EF4444',
            shortcut: 'q',
          },
        ],
        allow_overlapping: false,
        max_selections: 20,
      },
      placeholder: 'Highlight important phrases and categorize them',
    },
    {
      name: 'sentiment_analysis',
      label: 'Overall Sentiment',
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
          1: 'Very Negative',
          2: 'Negative',
          3: 'Neutral',
          4: 'Positive',
          5: 'Very Positive',
        },
      },
    },
    {
      name: 'topics_identified',
      label: 'Topics Identified',
      type: 'checkbox',
      source: 'annotation',
      required: false,
      display: {
        creation: 'hidden',
        annotation: 'editable',
        table: 'column',
      },
      choices: [
        'politics',
        'technology',
        'health',
        'economics',
        'environment',
        'education',
        'entertainment',
        'sports',
      ],
    },
    {
      name: 'complexity_score',
      label: 'Text Complexity Score',
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
    },
    {
      name: 'analysis_notes',
      label: 'Analysis Notes',
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
        { type: 'maxLength', value: 1000 },
      ],
      placeholder: 'Provide detailed analysis notes with formatting support',
    },
    {
      name: 'confidence_level',
      label: 'Annotator Confidence',
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
    },
  ],

  display_config: {
    table_columns: [
      'text_category',
      'sentiment_analysis',
      'complexity_score',
      'confidence_level',
    ],
    answer_display: {
      fields: ['analysis_notes', 'key_phrases', 'topics_identified'],
      separator: 'divider',
    },
    column_widths: {
      text_category: 150,
      sentiment_analysis: 120,
      complexity_score: 120,
      confidence_level: 130,
    },
  },

  llm_config: {
    prompt_template: `Analyze the following text and provide insights on:
1. Sentiment and emotional tone
2. Key concepts and entities
3. Overall complexity and readability
4. Main topics covered

Text: {{source_text}}

Provide a structured analysis with specific examples.`,
    response_parser: 'textAnalysisParser',
  },

  evaluation_config: {
    metrics: [
      { name: 'agreement', type: 'accuracy' },
      { name: 'consistency', type: 'custom' },
    ],
    requires_reference: false,
    threshold: 0.7,
  },

  metadata: {
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    tags: ['text', 'sentiment', 'nlp'],
  },
}

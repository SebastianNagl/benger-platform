/**
 * Multi-Modal Analysis Template
 *
 * Demonstrates advanced field types including file uploads, rich text,
 * and complex validation for multi-modal content analysis.
 *
 * Issue #218: ize Annotation System with Label Studio-Inspired Architecture
 */

import { TaskTemplate } from '@/types/taskTemplate'

export const multiModalAnalysisTemplate: TaskTemplate = {
  id: 'multi-modal-analysis',
  name: 'Multi-Modal Analysis',
  version: '1.0',
  description: 'Analysis of text, images, and documents with file upload',
  category: 'multi-modal',

  fields: [
    {
      name: 'content_title',
      label: 'Content Title',
      type: 'text',
      source: 'task_data',
      required: true,
      display: {
        creation: 'editable',
        annotation: 'readonly',
        table: 'column',
      },
      validation: [
        { type: 'minLength', value: 3 },
        { type: 'maxLength', value: 150 },
      ],
    },
    {
      name: 'content_type',
      label: 'Content Type',
      type: 'radio',
      source: 'task_data',
      required: true,
      display: {
        creation: 'editable',
        annotation: 'readonly',
        table: 'column',
      },
      choices: [
        'article_with_images',
        'infographic',
        'presentation',
        'video_transcript',
        'social_media_post',
        'mixed_media',
      ],
    },
    {
      name: 'primary_text',
      label: 'Primary Text Content',
      type: 'text_area',
      source: 'task_data',
      required: true,
      display: {
        creation: 'editable',
        annotation: 'readonly',
        table: 'hidden',
      },
      validation: [
        { type: 'minLength', value: 50 },
        { type: 'maxLength', value: 10000 },
      ],
      placeholder: 'Enter the main text content to be analyzed',
    },
    {
      name: 'supporting_document',
      label: 'Supporting Document',
      type: 'file_upload',
      source: 'task_data',
      required: false,
      display: {
        creation: 'editable',
        annotation: 'readonly',
        table: 'hidden',
      },
      metadata: {
        accepted_types: ['pdf', 'docx', 'jpg', 'png', 'svg'],
        max_file_size: 50 * 1024 * 1024, // 50MB
      },
    },
    {
      name: 'content_themes',
      label: 'Content Themes',
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
            id: 'main_theme',
            label: 'Main Theme',
            color: '#3B82F6',
            shortcut: 'm',
          },
          {
            id: 'supporting_point',
            label: 'Supporting Point',
            color: '#10B981',
            shortcut: 's',
          },
          {
            id: 'evidence',
            label: 'Evidence/Data',
            color: '#F59E0B',
            shortcut: 'e',
          },
          {
            id: 'conclusion',
            label: 'Conclusion',
            color: '#8B5CF6',
            shortcut: 'c',
          },
          {
            id: 'counterargument',
            label: 'Counterargument',
            color: '#EF4444',
            shortcut: 'a',
          },
        ],
        allow_overlapping: true,
        max_selections: 30,
      },
      placeholder: 'Highlight different thematic elements in the text',
    },
    {
      name: 'content_quality',
      label: 'Content Quality Dimensions',
      type: 'checkbox',
      source: 'annotation',
      required: true,
      display: {
        creation: 'hidden',
        annotation: 'editable',
        table: 'column',
      },
      choices: [
        'well_structured',
        'clear_writing',
        'factually_accurate',
        'engaging_narrative',
        'appropriate_visuals',
        'credible_sources',
        'logical_flow',
        'actionable_insights',
      ],
    },
    {
      name: 'visual_text_integration',
      label: 'Visual-Text Integration Score',
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
          1: 'No Integration',
          3: 'Basic Integration',
          5: 'Good Integration',
          7: 'Strong Integration',
          10: 'Perfect Synergy',
        },
      },
    },
    {
      name: 'accessibility_score',
      label: 'Accessibility Score',
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
          1: 'Poor Accessibility',
          2: 'Limited Accessibility',
          3: 'Moderate Accessibility',
          4: 'Good Accessibility',
          5: 'Excellent Accessibility',
        },
      },
    },
    {
      name: 'detailed_analysis',
      label: 'Detailed Analysis',
      type: 'rich_text',
      source: 'annotation',
      required: true,
      display: {
        creation: 'hidden',
        annotation: 'editable',
        table: 'hidden',
      },
      validation: [
        { type: 'minLength', value: 200 },
        { type: 'maxLength', value: 3000 },
      ],
      placeholder:
        'Provide a comprehensive analysis using rich text formatting (bold, italic, lists, etc.)',
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
      validation: [{ type: 'maxLength', value: 1500 }],
      placeholder:
        'Suggest specific improvements for content, structure, or presentation',
    },
    {
      name: 'overall_rating',
      label: 'Overall Content Rating',
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
      name: 'analysis_date',
      label: 'Analysis Date',
      type: 'date',
      source: 'annotation',
      required: true,
      display: {
        creation: 'hidden',
        annotation: 'editable',
        table: 'column',
      },
      defaultValue: new Date().toISOString().split('T')[0],
    },
  ],

  display_config: {
    table_columns: [
      'content_title',
      'content_type',
      'visual_text_integration',
      'accessibility_score',
      'overall_rating',
      'analysis_date',
    ],
    answer_display: {
      fields: ['detailed_analysis', 'content_themes', 'content_quality'],
      separator: 'divider',
    },
    column_widths: {
      content_title: 250,
      content_type: 150,
      visual_text_integration: 140,
      accessibility_score: 130,
      overall_rating: 120,
      analysis_date: 120,
    },
  },

  llm_config: {
    prompt_template: `Analyze this multi-modal content comprehensively:

Title: {{content_title}}
Type: {{content_type}}
Text Content: {{primary_text}}

Evaluate:
1. Content structure and clarity
2. Visual-text integration effectiveness
3. Accessibility considerations
4. Overall quality and impact
5. Areas for improvement

Provide specific examples and actionable recommendations.`,
    response_parser: 'multiModalAnalysisParser',
  },

  evaluation_config: {
    metrics: [
      { name: 'content_quality_agreement', type: 'accuracy' },
      { name: 'theme_identification_consistency', type: 'f1' },
      { name: 'rating_reliability', type: 'custom' },
    ],
    requires_reference: false,
    threshold: 0.75,
  },

  metadata: {
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    tags: ['multi-modal', 'content', 'accessibility'],
  },
}

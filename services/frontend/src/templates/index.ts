/**
 * Task Templates for BenGER System
 *
 * Collection of templates for all task types including original task types
 * (QA, QAR, MCQ, Generation) and specialized templates for advanced use cases.
 *
 * Issue #216: Implement Unified Task Configuration and Display System
 */

// Original task types
export { generationTemplate } from './generationTemplate'
export { multiQuestionQATemplate } from './multiQuestionQATemplate'
export { multipleChoiceTemplate } from './multipleChoiceTemplate'
export { qaTemplate } from './qaTemplate'
export { qarTemplate } from './qarTemplate'

//  templates
export { collaborativeResearchTemplate } from './collaborativeResearchTemplate'
export { multiModalAnalysisTemplate } from './multiModalAnalysisTemplate'
export { textAnalysisTemplate } from './textAnalysisTemplate'

import { TaskTemplate } from '@/types/taskTemplate'
import { collaborativeResearchTemplate } from './collaborativeResearchTemplate'
import { generationTemplate } from './generationTemplate'
import { multiModalAnalysisTemplate } from './multiModalAnalysisTemplate'
import { multiQuestionQATemplate } from './multiQuestionQATemplate'
import { multipleChoiceTemplate } from './multipleChoiceTemplate'
import { qaTemplate } from './qaTemplate'
import { qarTemplate } from './qarTemplate'
import { textAnalysisTemplate } from './textAnalysisTemplate'

/**
 * Complete collection of templates for all task types
 */
export const demoTemplates: TaskTemplate[] = [
  // Original task types (prioritized for compatibility)
  qaTemplate,
  qarTemplate,
  multipleChoiceTemplate,
  generationTemplate,
  multiQuestionQATemplate,
  //  templates
  textAnalysisTemplate,
  collaborativeResearchTemplate,
  multiModalAnalysisTemplate,
]

/**
 * Templates organized by category for easy access
 */
export const templatesByCategory = {
  // Original task types
  qa: [qaTemplate, multiQuestionQATemplate],
  qa_reasoning: [qarTemplate],
  multiple_choice: [multipleChoiceTemplate],
  generation: [generationTemplate],
  //  templates
  'text-analysis': [textAnalysisTemplate],
  research: [collaborativeResearchTemplate],
  'multi-modal': [multiModalAnalysisTemplate],
}

/**
 * Templates organized by complexity level
 */
export const templatesByComplexity = {
  basic: [qaTemplate, multipleChoiceTemplate, textAnalysisTemplate],
  intermediate: [
    qarTemplate,
    generationTemplate,
    collaborativeResearchTemplate,
    multiModalAnalysisTemplate,
  ],
  advanced: [],
}

/**
 * Templates that demonstrate specific features
 */
export const templatesByFeature = {
  'question-answer': [qaTemplate, qarTemplate],
  'multiple-choice': [multipleChoiceTemplate],
  'text-generation': [generationTemplate],
  'text-highlighting': [
    textAnalysisTemplate,
    multiModalAnalysisTemplate,
  ],
  'file-upload': [multiModalAnalysisTemplate],
  'rich-text': [multiModalAnalysisTemplate, generationTemplate],
  'real-time-collaboration': [collaborativeResearchTemplate],
  accessibility: [multiModalAnalysisTemplate],
  'multi-rating': [collaborativeResearchTemplate, multiModalAnalysisTemplate],
}

/**
 * Get template by ID
 */
export function getTemplateById(id: string): TaskTemplate | undefined {
  return demoTemplates.find((template) => template.id === id)
}

/**
 * Get templates by category
 */
export function getTemplatesByCategory(category: string): TaskTemplate[] {
  return demoTemplates.filter((template) => template.category === category)
}

/**
 * Get templates that demonstrate a specific feature
 */
export function getTemplatesByFeature(
  feature: keyof typeof templatesByFeature
): TaskTemplate[] {
  return templatesByFeature[feature] || []
}

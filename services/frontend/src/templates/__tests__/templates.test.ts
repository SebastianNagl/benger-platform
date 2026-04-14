/**
 * Tests for Task Templates
 *
 * Validates template structure, data integrity, and utility functions
 * for all task templates in the BenGER system.
 */

import { TaskTemplate } from '@/types/taskTemplate'
import { collaborativeResearchTemplate } from '../collaborativeResearchTemplate'
import { generationTemplate } from '../generationTemplate'
import {
  demoTemplates,
  getTemplateById,
  getTemplatesByCategory,
  getTemplatesByFeature,
  templatesByCategory,
  templatesByComplexity,
  templatesByFeature,
} from '../index'
import { multiModalAnalysisTemplate } from '../multiModalAnalysisTemplate'
import { multipleChoiceTemplate } from '../multipleChoiceTemplate'
import { multiQuestionQATemplate } from '../multiQuestionQATemplate'
import { qaTemplate } from '../qaTemplate'
import { qarTemplate } from '../qarTemplate'
import { textAnalysisTemplate } from '../textAnalysisTemplate'

// All templates for iteration
const allTemplates: TaskTemplate[] = [
  qaTemplate,
  qarTemplate,
  multipleChoiceTemplate,
  generationTemplate,
  multiQuestionQATemplate,
  textAnalysisTemplate,
  collaborativeResearchTemplate,
  multiModalAnalysisTemplate,
]

describe('Task Templates', () => {
  describe('Template Structure Validation', () => {
    it.each(allTemplates.map((t) => [t.id, t]))(
      '%s should have required top-level properties',
      (_id, template) => {
        expect(template.id).toBeDefined()
        expect(typeof template.id).toBe('string')
        expect(template.name).toBeDefined()
        expect(typeof template.name).toBe('string')
        expect(template.version).toBeDefined()
        expect(template.description).toBeDefined()
        expect(template.category).toBeDefined()
        expect(template.fields).toBeDefined()
        expect(Array.isArray(template.fields)).toBe(true)
        expect(template.fields.length).toBeGreaterThan(0)
      }
    )

    it.each(allTemplates.map((t) => [t.id, t]))(
      '%s should have valid fields with required properties',
      (_id, template) => {
        for (const field of template.fields) {
          expect(field.name).toBeDefined()
          expect(typeof field.name).toBe('string')
          expect(field.label).toBeDefined()
          expect(field.type).toBeDefined()
          expect(field.source).toBeDefined()
          expect(['task_data', 'annotation', 'generated', 'computed']).toContain(
            field.source
          )
          expect(typeof field.required).toBe('boolean')
          expect(field.display).toBeDefined()
          expect(field.display.creation).toBeDefined()
          expect(field.display.annotation).toBeDefined()
          expect(field.display.table).toBeDefined()
        }
      }
    )

    it.each(allTemplates.map((t) => [t.id, t]))(
      '%s should have unique field names',
      (_id, template) => {
        const names = template.fields.map((f) => f.name)
        const uniqueNames = new Set(names)
        expect(uniqueNames.size).toBe(names.length)
      }
    )

    it.each(allTemplates.map((t) => [t.id, t]))(
      '%s should have display_config with table_columns',
      (_id, template) => {
        expect(template.display_config).toBeDefined()
        expect(template.display_config.table_columns).toBeDefined()
        expect(Array.isArray(template.display_config.table_columns)).toBe(true)
        expect(template.display_config.table_columns.length).toBeGreaterThan(0)
      }
    )

    it.each(allTemplates.map((t) => [t.id, t]))(
      '%s should have metadata with timestamps',
      (_id, template) => {
        expect(template.metadata).toBeDefined()
        expect(template.metadata.created_at).toBeDefined()
        expect(template.metadata.updated_at).toBeDefined()
      }
    )
  })

  describe('Individual Template Verification', () => {
    it('qaTemplate should have correct id and category', () => {
      expect(qaTemplate.id).toBe('qa')
      expect(qaTemplate.category).toBe('qa')
      expect(qaTemplate.name).toBe('Question & Answer')
    })

    it('qaTemplate should have question, answer, and confidence fields', () => {
      const fieldNames = qaTemplate.fields.map((f) => f.name)
      expect(fieldNames).toContain('question')
      expect(fieldNames).toContain('answer')
      expect(fieldNames).toContain('confidence')
    })

    it('qaTemplate answer field should be required and annotation source', () => {
      const answerField = qaTemplate.fields.find((f) => f.name === 'answer')
      expect(answerField).toBeDefined()
      expect(answerField!.required).toBe(true)
      expect(answerField!.source).toBe('annotation')
    })

    it('qarTemplate should have correct id and reasoning field', () => {
      expect(qarTemplate.id).toBe('qa_reasoning')
      expect(qarTemplate.category).toBe('qa_reasoning')
      const fieldNames = qarTemplate.fields.map((f) => f.name)
      expect(fieldNames).toContain('reasoning_steps')
    })

    it('multipleChoiceTemplate should have correct id and choices field', () => {
      expect(multipleChoiceTemplate.id).toBe('multiple_choice')
      expect(multipleChoiceTemplate.category).toBe('multiple_choice')
      const fieldNames = multipleChoiceTemplate.fields.map((f) => f.name)
      expect(fieldNames).toContain('selected_answer')
    })

    it('generationTemplate should have correct id and generation fields', () => {
      expect(generationTemplate.id).toBe('generation')
      expect(generationTemplate.category).toBe('generation')
      const fieldNames = generationTemplate.fields.map((f) => f.name)
      expect(fieldNames).toContain('context_document')
    })

    it('multiQuestionQATemplate should have correct id', () => {
      expect(multiQuestionQATemplate.id).toBe('multi_qa')
      expect(multiQuestionQATemplate.category).toBe('qa')
    })

    it('textAnalysisTemplate should have correct id and category', () => {
      expect(textAnalysisTemplate.id).toBe('text-analysis')
      expect(textAnalysisTemplate.category).toBe('text-analysis')
    })

    it('collaborativeResearchTemplate should have correct id and URL field', () => {
      expect(collaborativeResearchTemplate.id).toBe('collaborative-research')
      expect(collaborativeResearchTemplate.category).toBe('research')
      const fieldNames = collaborativeResearchTemplate.fields.map((f) => f.name)
      expect(fieldNames).toContain('research_paper_url')
    })

    it('multiModalAnalysisTemplate should have correct id and file field', () => {
      expect(multiModalAnalysisTemplate.id).toBe('multi-modal-analysis')
      expect(multiModalAnalysisTemplate.category).toBe('multi-modal')
    })
  })

  describe('Field Validation Rules', () => {
    it.each(allTemplates.map((t) => [t.id, t]))(
      '%s fields with validation should have valid rule types',
      (_id, template) => {
        for (const field of template.fields) {
          if (field.validation) {
            for (const rule of field.validation) {
              expect([
                'required',
                'minLength',
                'maxLength',
                'min',
                'max',
                'pattern',
                'custom',
              ]).toContain(rule.type)
            }
          }
        }
      }
    )

    it('qaTemplate confidence field should have min/max validation', () => {
      const confidence = qaTemplate.fields.find((f) => f.name === 'confidence')
      expect(confidence).toBeDefined()
      expect(confidence!.validation).toBeDefined()
      const minRule = confidence!.validation!.find((r) => r.type === 'min')
      const maxRule = confidence!.validation!.find((r) => r.type === 'max')
      expect(minRule).toBeDefined()
      expect(maxRule).toBeDefined()
      expect(minRule!.value).toBe(1)
      expect(maxRule!.value).toBe(5)
    })
  })

  describe('LLM Config', () => {
    it.each(allTemplates.map((t) => [t.id, t]))(
      '%s should have llm_config with prompt_template',
      (_id, template) => {
        if (template.llm_config) {
          expect(template.llm_config.prompt_template).toBeDefined()
          expect(typeof template.llm_config.prompt_template).toBe('string')
          expect(template.llm_config.prompt_template.length).toBeGreaterThan(0)
        }
      }
    )
  })

  describe('Evaluation Config', () => {
    it.each(allTemplates.map((t) => [t.id, t]))(
      '%s should have evaluation_config with metrics',
      (_id, template) => {
        if (template.evaluation_config) {
          expect(template.evaluation_config.metrics).toBeDefined()
          expect(Array.isArray(template.evaluation_config.metrics)).toBe(true)
        }
      }
    )
  })

  describe('Display Config', () => {
    it.each(allTemplates.map((t) => [t.id, t]))(
      '%s table_columns should reference actual field names',
      (_id, template) => {
        const fieldNames = template.fields.map((f) => f.name)
        for (const col of template.display_config.table_columns) {
          expect(fieldNames).toContain(col)
        }
      }
    )

    it.each(allTemplates.map((t) => [t.id, t]))(
      '%s should have column_widths for table columns',
      (_id, template) => {
        if (template.display_config.column_widths) {
          for (const col of template.display_config.table_columns) {
            expect(template.display_config.column_widths[col]).toBeDefined()
            expect(typeof template.display_config.column_widths[col]).toBe('number')
          }
        }
      }
    )
  })
})

describe('Template Index Exports', () => {
  describe('demoTemplates', () => {
    it('should contain all 8 templates', () => {
      expect(demoTemplates).toHaveLength(8)
    })

    it('should have unique IDs', () => {
      const ids = demoTemplates.map((t) => t.id)
      expect(new Set(ids).size).toBe(ids.length)
    })

    it('should include all template types', () => {
      const ids = demoTemplates.map((t) => t.id)
      expect(ids).toContain('qa')
      expect(ids).toContain('qa_reasoning')
      expect(ids).toContain('multiple_choice')
      expect(ids).toContain('generation')
      expect(ids).toContain('multi_qa')
      expect(ids).toContain('text-analysis')
      expect(ids).toContain('collaborative-research')
      expect(ids).toContain('multi-modal-analysis')
    })
  })

  describe('templatesByCategory', () => {
    it('should have qa category with correct templates', () => {
      expect(templatesByCategory.qa).toHaveLength(2)
      expect(templatesByCategory.qa).toContain(qaTemplate)
      expect(templatesByCategory.qa).toContain(multiQuestionQATemplate)
    })

    it('should have qa_reasoning category', () => {
      expect(templatesByCategory.qa_reasoning).toHaveLength(1)
      expect(templatesByCategory.qa_reasoning).toContain(qarTemplate)
    })

    it('should have multiple_choice category', () => {
      expect(templatesByCategory.multiple_choice).toHaveLength(1)
      expect(templatesByCategory.multiple_choice).toContain(multipleChoiceTemplate)
    })

    it('should have generation category', () => {
      expect(templatesByCategory.generation).toHaveLength(1)
      expect(templatesByCategory.generation).toContain(generationTemplate)
    })

    it('should have text-analysis category', () => {
      expect(templatesByCategory['text-analysis']).toHaveLength(1)
    })

    it('should have research category', () => {
      expect(templatesByCategory.research).toHaveLength(1)
    })

    it('should have multi-modal category', () => {
      expect(templatesByCategory['multi-modal']).toHaveLength(1)
    })
  })

  describe('templatesByComplexity', () => {
    it('should have basic templates', () => {
      expect(templatesByComplexity.basic).toHaveLength(3)
    })

    it('should have intermediate templates', () => {
      expect(templatesByComplexity.intermediate).toHaveLength(4)
    })

    it('should have empty advanced array', () => {
      expect(templatesByComplexity.advanced).toHaveLength(0)
    })
  })

  describe('templatesByFeature', () => {
    it('should have question-answer feature', () => {
      expect(templatesByFeature['question-answer']).toHaveLength(2)
    })

    it('should have multiple-choice feature', () => {
      expect(templatesByFeature['multiple-choice']).toHaveLength(1)
    })

    it('should have text-generation feature', () => {
      expect(templatesByFeature['text-generation']).toHaveLength(1)
    })

    it('should have text-highlighting feature', () => {
      expect(templatesByFeature['text-highlighting']).toHaveLength(2)
    })

    it('should have file-upload feature', () => {
      expect(templatesByFeature['file-upload']).toHaveLength(1)
    })

    it('should have rich-text feature', () => {
      expect(templatesByFeature['rich-text']).toHaveLength(2)
    })

    it('should have real-time-collaboration feature', () => {
      expect(templatesByFeature['real-time-collaboration']).toHaveLength(1)
    })

    it('should have accessibility feature', () => {
      expect(templatesByFeature.accessibility).toHaveLength(1)
    })

    it('should have multi-rating feature', () => {
      expect(templatesByFeature['multi-rating']).toHaveLength(2)
    })
  })

  describe('getTemplateById', () => {
    it('should find template by valid ID', () => {
      expect(getTemplateById('qa')).toBe(qaTemplate)
      expect(getTemplateById('qa_reasoning')).toBe(qarTemplate)
      expect(getTemplateById('generation')).toBe(generationTemplate)
      expect(getTemplateById('multiple_choice')).toBe(multipleChoiceTemplate)
      expect(getTemplateById('multi_qa')).toBe(multiQuestionQATemplate)
      expect(getTemplateById('text-analysis')).toBe(textAnalysisTemplate)
      expect(getTemplateById('collaborative-research')).toBe(
        collaborativeResearchTemplate
      )
      expect(getTemplateById('multi-modal-analysis')).toBe(
        multiModalAnalysisTemplate
      )
    })

    it('should return undefined for invalid ID', () => {
      expect(getTemplateById('nonexistent')).toBeUndefined()
      expect(getTemplateById('')).toBeUndefined()
    })
  })

  describe('getTemplatesByCategory', () => {
    it('should return templates for valid category', () => {
      const qaTemplates = getTemplatesByCategory('qa')
      expect(qaTemplates.length).toBeGreaterThan(0)
      qaTemplates.forEach((t) => {
        expect(t.category).toBe('qa')
      })
    })

    it('should return empty array for invalid category', () => {
      expect(getTemplatesByCategory('nonexistent')).toHaveLength(0)
    })
  })

  describe('getTemplatesByFeature', () => {
    it('should return templates for valid feature', () => {
      const templates = getTemplatesByFeature('question-answer')
      expect(templates.length).toBeGreaterThan(0)
    })

    it('should return empty array for unknown feature', () => {
      const templates = getTemplatesByFeature(
        'nonexistent' as keyof typeof templatesByFeature
      )
      expect(templates).toHaveLength(0)
    })
  })
})

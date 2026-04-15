/**
 * Tests for annotation type exports
 */

import { LEGAL_ANNOTATION_PRESETS } from '../annotation'

describe('LEGAL_ANNOTATION_PRESETS', () => {
  it('should have qa preset', () => {
    expect(LEGAL_ANNOTATION_PRESETS.qa).toBeDefined()
    expect(LEGAL_ANNOTATION_PRESETS.qa.name).toBe('Question Answering')
    expect(LEGAL_ANNOTATION_PRESETS.qa.config.interfaces).toHaveLength(3)
  })

  it('should have entity_recognition preset', () => {
    expect(LEGAL_ANNOTATION_PRESETS.entity_recognition).toBeDefined()
    expect(LEGAL_ANNOTATION_PRESETS.entity_recognition.name).toBe(
      'Legal Entity Recognition'
    )
    expect(
      LEGAL_ANNOTATION_PRESETS.entity_recognition.config.interfaces
    ).toHaveLength(2)
  })

  it('should have document_classification preset', () => {
    expect(LEGAL_ANNOTATION_PRESETS.document_classification).toBeDefined()
    expect(LEGAL_ANNOTATION_PRESETS.document_classification.name).toBe(
      'Document Classification'
    )
    expect(
      LEGAL_ANNOTATION_PRESETS.document_classification.config.interfaces
    ).toHaveLength(2)
  })

  it('qa preset should have correct interface types', () => {
    const interfaces = LEGAL_ANNOTATION_PRESETS.qa.config.interfaces
    const types = interfaces.map((i: any) => i.type)
    expect(types).toContain('text')
    expect(types).toContain('textarea')
    expect(types).toContain('rating')
  })

  it('entity_recognition should have labels with legal entity types', () => {
    const labelInterface =
      LEGAL_ANNOTATION_PRESETS.entity_recognition.config.interfaces.find(
        (i: any) => i.type === 'labels'
      )
    expect(labelInterface).toBeDefined()
    const choices = (labelInterface as any).properties.choices
    expect(choices.length).toBeGreaterThan(0)
    const values = choices.map((c: any) => c.value)
    expect(values).toContain('PERSON')
    expect(values).toContain('LAW')
    expect(values).toContain('COURT')
  })

  it('document_classification should have taxonomy with legal areas', () => {
    const taxonomyInterface =
      LEGAL_ANNOTATION_PRESETS.document_classification.config.interfaces.find(
        (i: any) => i.type === 'taxonomy'
      )
    expect(taxonomyInterface).toBeDefined()
    const taxonomy = (taxonomyInterface as any).properties.taxonomy
    expect(taxonomy.length).toBeGreaterThan(0)
    const topLevelValues = taxonomy.map((t: any) => t.value)
    expect(topLevelValues).toContain('zivilrecht')
    expect(topLevelValues).toContain('strafrecht')
  })
})

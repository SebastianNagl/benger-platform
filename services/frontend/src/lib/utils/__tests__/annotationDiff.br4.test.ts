/**
 * @jest-environment jsdom
 *
 * Branch coverage: annotationDiff.ts
 * Targets: L60-61 (orig.to_name || rev.to_name fallback),
 *          L75 (added field - !orig && rev branch)
 */

import { computeAnnotationDiff } from '../annotationDiff'

describe('annotationDiff br4 - uncovered branches', () => {
  it('detects removed fields (line 66-74, orig && !rev)', () => {
    const original = [
      { from_name: 'field1', to_name: 'text', type: 'choices', value: { choices: ['A'] } },
    ]
    const review: any[] = []

    const result = computeAnnotationDiff(original as any, review)
    const removedField = result.fields.find((f) => f.from_name === 'field1')
    expect(removedField).toBeTruthy()
    expect(removedField?.status).toBe('removed')
  })

  it('detects added fields (line 75-82, !orig && rev)', () => {
    const original: any[] = []
    const review = [
      { from_name: 'newField', to_name: 'text', type: 'choices', value: { choices: ['B'] } },
    ]

    const result = computeAnnotationDiff(original, review as any)
    const addedField = result.fields.find((f) => f.from_name === 'newField')
    expect(addedField).toBeTruthy()
    expect(addedField?.status).toBe('added')
  })

  it('detects modified fields (line 56-65)', () => {
    const original = [
      { from_name: 'field1', to_name: 'text', type: 'choices', value: { choices: ['A'] } },
    ]
    const review = [
      { from_name: 'field1', to_name: 'text', type: 'choices', value: { choices: ['B'] } },
    ]

    const result = computeAnnotationDiff(original as any, review as any)
    const modifiedField = result.fields.find((f) => f.from_name === 'field1')
    expect(modifiedField).toBeTruthy()
    expect(modifiedField?.status).toBe('modified')
  })

  it('detects unchanged fields', () => {
    const original = [
      { from_name: 'field1', to_name: 'text', type: 'choices', value: { choices: ['A'] } },
    ]
    const review = [
      { from_name: 'field1', to_name: 'text', type: 'choices', value: { choices: ['A'] } },
    ]

    const result = computeAnnotationDiff(original as any, review as any)
    const unchangedField = result.fields.find((f) => f.from_name === 'field1')
    expect(unchangedField).toBeTruthy()
    expect(unchangedField?.status).toBe('unchanged')
  })

  it('uses fallback to_name and type from rev (line 60-61)', () => {
    const original = [
      { from_name: 'field1', to_name: '', type: '', value: 'orig' },
    ]
    const review = [
      { from_name: 'field1', to_name: 'fallback_name', type: 'fallback_type', value: 'rev' },
    ]

    const result = computeAnnotationDiff(original as any, review as any)
    const field = result.fields.find((f) => f.from_name === 'field1')
    expect(field).toBeTruthy()
  })

  it('summary counts are correct', () => {
    const original = [
      { from_name: 'kept', to_name: 'text', type: 'choices', value: 'same' },
      { from_name: 'removed_field', to_name: 'text', type: 'choices', value: 'gone' },
    ]
    const review = [
      { from_name: 'kept', to_name: 'text', type: 'choices', value: 'same' },
      { from_name: 'new_field', to_name: 'text', type: 'choices', value: 'new' },
    ]

    const result = computeAnnotationDiff(original as any, review as any)
    expect(result.summary.unchanged).toBe(1)
    expect(result.summary.removed).toBe(1)
    expect(result.summary.added).toBe(1)
    expect(result.summary.total).toBe(3)
  })
})

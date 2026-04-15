/**
 * @jest-environment jsdom
 *
 * Branch coverage: annotationStatus.ts
 * Targets: L148 (getItemAnnotationStatus with id ?? 0),
 *          L177 (findNextUnannotatedItem returns null)
 */

import {
  getAnnotationStatistics,
  findNextUnannotatedItem,
  getItemAnnotationStatus,
} from '../annotationStatus'

describe('annotationStatus br4 - uncovered branches', () => {
  it('getAnnotationStatistics with empty items', () => {
    const result = getAnnotationStatistics([], [])
    expect(result.total).toBe(0)
    expect(result.completed).toBe(0)
  })

  it('findNextUnannotatedItem returns null when no items', () => {
    const result = findNextUnannotatedItem([], [])
    expect(result).toBeNull()
  })

  it('getItemAnnotationStatus handles undefined id (line 148 ?? 0)', () => {
    // Should handle undefined id gracefully
    const status = getItemAnnotationStatus(undefined as any, [])
    expect(typeof status).toBe('string')
  })

  it('getAnnotationStatistics counts items with undefined ids', () => {
    const items = [
      { id: undefined },
      { id: 3 },
    ]
    const result = getAnnotationStatistics(items as any, [])
    expect(result.total).toBe(2)
  })
})

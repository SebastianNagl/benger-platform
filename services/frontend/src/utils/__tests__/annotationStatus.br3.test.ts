/**
 * @jest-environment jsdom
 *
 * Branch coverage: annotationStatus.ts
 * Targets: br11[1] L148 (completed || 0), br13[1] L155, br14[1] L156, br17[1] L177
 */

import {
  findNextUnannotatedItem,
  getAnnotationStatistics,
} from '../annotationStatus'

describe('annotationStatus branch coverage', () => {
  it('getAnnotationStatistics with zero counts for each status', () => {
    // items with no annotations -> all not_started, completed=0, inProgress=0
    const items = [{ id: 1 }, { id: 2 }]
    const annotations: any[] = []
    const stats = getAnnotationStatistics(items, annotations)
    expect(stats.completed).toBe(0)
    expect(stats.inProgress).toBe(0)
    expect(stats.notStarted).toBe(2)
  })

  it('getAnnotationStatistics with mixed statuses', () => {
    const items = [{ id: 1 }, { id: 2 }, { id: 3 }]
    const annotations: any[] = [
      { id: 'a1', item_id: '1', status: 'submitted' },
      { id: 'a2', item_id: '2', status: 'draft' },
    ]
    const stats = getAnnotationStatistics(items, annotations)
    expect(stats.completed).toBe(1)
    expect(stats.inProgress).toBe(1)
    expect(stats.notStarted).toBe(1)
  })

  it('findNextUnannotatedItem returns null when all completed', () => {
    const items = [{ id: 1 }]
    const annotations: any[] = [
      { id: 'a1', item_id: '1', status: 'submitted' },
    ]
    expect(findNextUnannotatedItem(items, annotations)).toBeNull()
  })
})

/**
 * Branch coverage tests for annotationStatus.ts
 *
 * Targets: normalizeItemId with undefined/null, getUserAnnotationStatus
 * with draft-only vs submitted, getItemAnnotationStatus with approved status,
 * areAllItemsAnnotated with empty items, getAnnotationStatistics edge cases,
 * findNextUnannotatedItem when all completed.
 */

import {
  normalizeItemId,
  getItemAnnotations,
  getItemAnnotationStatus,
  getItemDisplayStatus,
  areAllItemsAnnotated,
  getAnnotationStatistics,
  findNextUnannotatedItem,
  getUserAnnotationStatus,
  ANNOTATION_STATUS,
  DISPLAY_STATUS,
  Annotation,
  TaskItem,
} from '../annotationStatus'

describe('normalizeItemId', () => {
  it('should return empty string for undefined', () => {
    expect(normalizeItemId(undefined)).toBe('')
  })

  it('should return empty string for null', () => {
    expect(normalizeItemId(null as any)).toBe('')
  })

  it('should convert number to string', () => {
    expect(normalizeItemId(42)).toBe('42')
  })

  it('should return string as-is', () => {
    expect(normalizeItemId('abc')).toBe('abc')
  })
})

describe('getItemAnnotations', () => {
  const annotations: Annotation[] = [
    { id: '1', item_id: '10', status: 'submitted' },
    { id: '2', item_id: '10', status: 'draft' },
    { id: '3', item_id: '20', status: 'submitted' },
  ]

  it('should filter annotations by item id', () => {
    expect(getItemAnnotations(10, annotations)).toHaveLength(2)
    expect(getItemAnnotations('20', annotations)).toHaveLength(1)
  })

  it('should return empty for non-matching item', () => {
    expect(getItemAnnotations('999', annotations)).toHaveLength(0)
  })
})

describe('getItemAnnotationStatus', () => {
  it('should return NOT_STARTED for no annotations', () => {
    expect(getItemAnnotationStatus('1', [])).toBe(ANNOTATION_STATUS.NOT_STARTED)
  })

  it('should return COMPLETED for submitted annotation', () => {
    const anns: Annotation[] = [{ id: '1', item_id: '1', status: 'submitted' }]
    expect(getItemAnnotationStatus('1', anns)).toBe(ANNOTATION_STATUS.COMPLETED)
  })

  it('should return COMPLETED for approved annotation', () => {
    const anns: Annotation[] = [{ id: '1', item_id: '1', status: 'approved' }]
    expect(getItemAnnotationStatus('1', anns)).toBe(ANNOTATION_STATUS.COMPLETED)
  })

  it('should return IN_PROGRESS for draft-only annotation', () => {
    const anns: Annotation[] = [{ id: '1', item_id: '1', status: 'draft' }]
    expect(getItemAnnotationStatus('1', anns)).toBe(ANNOTATION_STATUS.IN_PROGRESS)
  })

  it('should return NOT_STARTED for annotation with unknown status', () => {
    const anns: Annotation[] = [{ id: '1', item_id: '1', status: 'unknown' as any }]
    expect(getItemAnnotationStatus('1', anns)).toBe(ANNOTATION_STATUS.NOT_STARTED)
  })
})

describe('getItemDisplayStatus', () => {
  it('should return ANNOTATED for submitted', () => {
    const anns: Annotation[] = [{ id: '1', item_id: '1', status: 'submitted' }]
    expect(getItemDisplayStatus('1', anns)).toBe(DISPLAY_STATUS.ANNOTATED)
  })

  it('should return NOT_ANNOTATED for draft only', () => {
    const anns: Annotation[] = [{ id: '1', item_id: '1', status: 'draft' }]
    expect(getItemDisplayStatus('1', anns)).toBe(DISPLAY_STATUS.NOT_ANNOTATED)
  })

  it('should return NOT_ANNOTATED for no annotations', () => {
    expect(getItemDisplayStatus('1', [])).toBe(DISPLAY_STATUS.NOT_ANNOTATED)
  })
})

describe('areAllItemsAnnotated', () => {
  it('should return false for empty items', () => {
    expect(areAllItemsAnnotated([], [])).toBe(false)
  })

  it('should return true when all items have submitted annotations', () => {
    const items: TaskItem[] = [{ id: '1' }, { id: '2' }]
    const anns: Annotation[] = [
      { id: 'a1', item_id: '1', status: 'submitted' },
      { id: 'a2', item_id: '2', status: 'approved' },
    ]
    expect(areAllItemsAnnotated(items, anns)).toBe(true)
  })

  it('should return false when some items lack annotations', () => {
    const items: TaskItem[] = [{ id: '1' }, { id: '2' }]
    const anns: Annotation[] = [{ id: 'a1', item_id: '1', status: 'submitted' }]
    expect(areAllItemsAnnotated(items, anns)).toBe(false)
  })

  it('should use default id 0 for items without id', () => {
    const items: TaskItem[] = [{}]
    const anns: Annotation[] = [{ id: 'a1', item_id: '0', status: 'submitted' }]
    expect(areAllItemsAnnotated(items, anns)).toBe(true)
  })
})

describe('getAnnotationStatistics', () => {
  it('should return zeros for empty items', () => {
    const stats = getAnnotationStatistics([], [])
    expect(stats.total).toBe(0)
    expect(stats.percentageComplete).toBe(0)
  })

  it('should calculate correct statistics', () => {
    const items: TaskItem[] = [{ id: '1' }, { id: '2' }, { id: '3' }]
    const anns: Annotation[] = [
      { id: 'a1', item_id: '1', status: 'submitted' },
      { id: 'a2', item_id: '2', status: 'draft' },
    ]
    const stats = getAnnotationStatistics(items, anns)
    expect(stats.total).toBe(3)
    expect(stats.completed).toBe(1)
    expect(stats.inProgress).toBe(1)
    expect(stats.notStarted).toBe(1)
    expect(stats.percentageComplete).toBe(33)
  })
})

describe('findNextUnannotatedItem', () => {
  it('should return first unannotated item', () => {
    const items: TaskItem[] = [{ id: '1' }, { id: '2' }, { id: '3' }]
    const anns: Annotation[] = [{ id: 'a1', item_id: '1', status: 'submitted' }]
    const next = findNextUnannotatedItem(items, anns)
    expect(next?.id).toBe('2')
  })

  it('should return null when all annotated', () => {
    const items: TaskItem[] = [{ id: '1' }]
    const anns: Annotation[] = [{ id: 'a1', item_id: '1', status: 'submitted' }]
    expect(findNextUnannotatedItem(items, anns)).toBeNull()
  })

  it('should return draft item as next (not completed)', () => {
    const items: TaskItem[] = [{ id: '1' }]
    const anns: Annotation[] = [{ id: 'a1', item_id: '1', status: 'draft' }]
    expect(findNextUnannotatedItem(items, anns)?.id).toBe('1')
  })
})

describe('getUserAnnotationStatus', () => {
  it('should return NOT_STARTED when user has no annotations', () => {
    const anns: Annotation[] = [
      { id: '1', item_id: '1', status: 'submitted', user_id: 'other' },
    ]
    expect(getUserAnnotationStatus('me', '1', anns)).toBe(ANNOTATION_STATUS.NOT_STARTED)
  })

  it('should return COMPLETED when user has submitted annotation', () => {
    const anns: Annotation[] = [
      { id: '1', item_id: '1', status: 'submitted', user_id: 'me' },
    ]
    expect(getUserAnnotationStatus('me', '1', anns)).toBe(ANNOTATION_STATUS.COMPLETED)
  })

  it('should return COMPLETED when user has approved annotation', () => {
    const anns: Annotation[] = [
      { id: '1', item_id: '1', status: 'approved', user_id: 'me' },
    ]
    expect(getUserAnnotationStatus('me', '1', anns)).toBe(ANNOTATION_STATUS.COMPLETED)
  })

  it('should return IN_PROGRESS when user has draft annotation', () => {
    const anns: Annotation[] = [
      { id: '1', item_id: '1', status: 'draft', user_id: 'me' },
    ]
    expect(getUserAnnotationStatus('me', '1', anns)).toBe(ANNOTATION_STATUS.IN_PROGRESS)
  })

  it('should return NOT_STARTED for unknown annotation status', () => {
    const anns: Annotation[] = [
      { id: '1', item_id: '1', status: 'pending' as any, user_id: 'me' },
    ]
    expect(getUserAnnotationStatus('me', '1', anns)).toBe(ANNOTATION_STATUS.NOT_STARTED)
  })
})

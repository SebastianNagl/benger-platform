/**
 * Tests for unified annotation status utilities (Issue #134)
 * These tests ensure consistent annotation status calculation across views
 */

import {
  ANNOTATION_STATUS,
  areAllItemsAnnotated,
  DISPLAY_STATUS,
  findNextUnannotatedItem,
  getAnnotationStatistics,
  getItemAnnotations,
  getItemAnnotationStatus,
  getItemDisplayStatus,
  getUserAnnotationStatus,
  normalizeItemId,
} from '../annotationStatus'

import type { Annotation, TaskItem } from '../annotationStatus'

describe('Annotation Status Utilities', () => {
  // Test data
  const mockAnnotations: Annotation[] = [
    { id: '1', item_id: '1', status: 'submitted', user_id: 'user1' },
    { id: '2', item_id: '1', status: 'draft', user_id: 'user2' },
    { id: '3', item_id: '2', status: 'approved', user_id: 'user1' },
    { id: '4', item_id: '3', status: 'draft', user_id: 'user1' },
    { id: '5', item_id: '4', status: 'draft', user_id: 'user2' },
  ]

  const mockItems: TaskItem[] = [
    { id: '1', question: 'Question 1' },
    { id: '2', question: 'Question 2' },
    { id: '3', question: 'Question 3' },
    { id: '4', question: 'Question 4' },
    { id: '5', question: 'Question 5' },
  ]

  describe('normalizeItemId', () => {
    it('should convert numbers to strings', () => {
      expect(normalizeItemId(123)).toBe('123')
    })

    it('should keep strings as strings', () => {
      expect(normalizeItemId('abc')).toBe('abc')
    })

    it('should handle undefined and null', () => {
      expect(normalizeItemId(undefined)).toBe('')
      expect(normalizeItemId(null)).toBe('')
    })
  })

  describe('getItemAnnotations', () => {
    it('should return annotations for specific item ID', () => {
      const annotations = getItemAnnotations('1', mockAnnotations)
      expect(annotations).toHaveLength(2)
      expect(annotations.every((a) => a.item_id === '1')).toBe(true)
    })

    it('should handle numeric item IDs', () => {
      const annotations = getItemAnnotations(1, mockAnnotations)
      expect(annotations).toHaveLength(2)
    })

    it('should return empty array for non-existent item', () => {
      const annotations = getItemAnnotations('999', mockAnnotations)
      expect(annotations).toHaveLength(0)
    })
  })

  describe('getItemAnnotationStatus', () => {
    it('should return completed for items with submitted annotations', () => {
      const status = getItemAnnotationStatus('1', mockAnnotations)
      expect(status).toBe(ANNOTATION_STATUS.COMPLETED)
    })

    it('should return completed for items with approved annotations', () => {
      const status = getItemAnnotationStatus('2', mockAnnotations)
      expect(status).toBe(ANNOTATION_STATUS.COMPLETED)
    })

    it('should return in_progress for items with only draft annotations', () => {
      const status = getItemAnnotationStatus('3', mockAnnotations)
      expect(status).toBe(ANNOTATION_STATUS.IN_PROGRESS)
    })

    it('should return not_started for items with no annotations', () => {
      const status = getItemAnnotationStatus('5', mockAnnotations)
      expect(status).toBe(ANNOTATION_STATUS.NOT_STARTED)
    })

    it('should handle numeric item IDs', () => {
      const status = getItemAnnotationStatus(1, mockAnnotations)
      expect(status).toBe(ANNOTATION_STATUS.COMPLETED)
    })
  })

  describe('getItemDisplayStatus', () => {
    it('should return Annotated for completed items', () => {
      const status = getItemDisplayStatus('1', mockAnnotations)
      expect(status).toBe(DISPLAY_STATUS.ANNOTATED)
    })

    it('should return Not Annotated for incomplete items', () => {
      const status = getItemDisplayStatus('3', mockAnnotations)
      expect(status).toBe(DISPLAY_STATUS.NOT_ANNOTATED)
    })

    it('should return Not Annotated for items with no annotations', () => {
      const status = getItemDisplayStatus('5', mockAnnotations)
      expect(status).toBe(DISPLAY_STATUS.NOT_ANNOTATED)
    })
  })

  describe('areAllItemsAnnotated', () => {
    it('should return true when all items are completed', () => {
      const completedItems: TaskItem[] = [
        { id: '1', question: 'Q1' },
        { id: '2', question: 'Q2' },
      ]
      const result = areAllItemsAnnotated(completedItems, mockAnnotations)
      expect(result).toBe(true)
    })

    it('should return false when some items are not completed', () => {
      const result = areAllItemsAnnotated(mockItems, mockAnnotations)
      expect(result).toBe(false)
    })

    it('should return false for empty items array', () => {
      const result = areAllItemsAnnotated([], mockAnnotations)
      expect(result).toBe(false)
    })
  })

  describe('getAnnotationStatistics', () => {
    it('should calculate correct statistics', () => {
      const stats = getAnnotationStatistics(mockItems, mockAnnotations)

      expect(stats.total).toBe(5)
      expect(stats.completed).toBe(2) // items 1 and 2
      expect(stats.inProgress).toBe(2) // items 3 and 4
      expect(stats.notStarted).toBe(1) // item 5
      expect(stats.percentageComplete).toBe(40) // 2/5 * 100
    })

    it('should handle empty items array', () => {
      const stats = getAnnotationStatistics([], mockAnnotations)

      expect(stats.total).toBe(0)
      expect(stats.completed).toBe(0)
      expect(stats.inProgress).toBe(0)
      expect(stats.notStarted).toBe(0)
      expect(stats.percentageComplete).toBe(0)
    })
  })

  describe('findNextUnannotatedItem', () => {
    it('should find first incomplete item', () => {
      const nextItem = findNextUnannotatedItem(mockItems, mockAnnotations)
      expect(nextItem).toBeTruthy()
      expect(nextItem?.id).toBe('3') // First item with draft status
    })

    it('should return null when all items are completed', () => {
      const completedItems: TaskItem[] = [
        { id: '1', question: 'Q1' },
        { id: '2', question: 'Q2' },
      ]
      const nextItem = findNextUnannotatedItem(completedItems, mockAnnotations)
      expect(nextItem).toBeNull()
    })

    it('should return first item when no annotations exist', () => {
      const nextItem = findNextUnannotatedItem(mockItems, [])
      expect(nextItem).toBeTruthy()
      expect(nextItem?.id).toBe('1')
    })
  })

  describe('getUserAnnotationStatus', () => {
    it('should return completed for user with submitted annotation', () => {
      const status = getUserAnnotationStatus('user1', '1', mockAnnotations)
      expect(status).toBe(ANNOTATION_STATUS.COMPLETED)
    })

    it('should return in_progress for user with draft annotation', () => {
      const status = getUserAnnotationStatus('user2', '1', mockAnnotations)
      expect(status).toBe(ANNOTATION_STATUS.IN_PROGRESS)
    })

    it('should return not_started for user with no annotations', () => {
      const status = getUserAnnotationStatus('user3', '1', mockAnnotations)
      expect(status).toBe(ANNOTATION_STATUS.NOT_STARTED)
    })

    it('should handle numeric item IDs', () => {
      const status = getUserAnnotationStatus('user1', 1, mockAnnotations)
      expect(status).toBe(ANNOTATION_STATUS.COMPLETED)
    })
  })

  describe('Status Consistency (Issue #134 Fix)', () => {
    it('should produce consistent results between task overview and data dashboard', () => {
      // Test the specific scenario described in Issue #134
      const items: TaskItem[] = [
        { id: '1', question: 'Question 1' },
        { id: '2', question: 'Question 2' },
        { id: '3', question: 'Question 3' },
      ]

      const annotations: Annotation[] = [
        { id: '1', item_id: '1', status: 'submitted', user_id: 'user1' },
        { id: '2', item_id: '2', status: 'submitted', user_id: 'user1' },
        { id: '3', item_id: '3', status: 'draft', user_id: 'user1' },
      ]

      // Task overview logic: "All items annotated!" should be false
      const allAnnotated = areAllItemsAnnotated(items, annotations)
      expect(allAnnotated).toBe(false)

      // Data dashboard logic: individual item status should match
      expect(getItemDisplayStatus('1', annotations)).toBe(
        DISPLAY_STATUS.ANNOTATED
      )
      expect(getItemDisplayStatus('2', annotations)).toBe(
        DISPLAY_STATUS.ANNOTATED
      )
      expect(getItemDisplayStatus('3', annotations)).toBe(
        DISPLAY_STATUS.NOT_ANNOTATED
      )

      // Both views should agree on overall completion
      const stats = getAnnotationStatistics(items, annotations)
      expect(stats.completed).toBe(2)
      expect(stats.inProgress).toBe(1)
      expect(allAnnotated).toBe(false) // Not all completed, so allAnnotated should be false
    })

    it('should handle ID type consistency (string vs number)', () => {
      const items: TaskItem[] = [
        { id: 1, question: 'Question 1' }, // numeric ID
        { id: '2', question: 'Question 2' }, // string ID
      ]

      const annotations: Annotation[] = [
        { id: '1', item_id: '1', status: 'submitted', user_id: 'user1' },
        { id: '2', item_id: '2', status: 'submitted', user_id: 'user1' },
      ]

      // Both should be recognized as annotated regardless of ID type
      expect(getItemDisplayStatus(1, annotations)).toBe(
        DISPLAY_STATUS.ANNOTATED
      )
      expect(getItemDisplayStatus('2', annotations)).toBe(
        DISPLAY_STATUS.ANNOTATED
      )
      expect(areAllItemsAnnotated(items, annotations)).toBe(true)
    })
  })
})

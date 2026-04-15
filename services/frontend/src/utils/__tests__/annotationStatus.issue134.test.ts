/**
 * Tests for Issue #134: Fix inconsistent annotation status display
 *
 * These tests verify that the annotation status calculations are consistent
 * between task overview and data dashboard views.
 */

import {
  ANNOTATION_STATUS,
  areAllItemsAnnotated,
  DISPLAY_STATUS,
  findNextUnannotatedItem,
  getAnnotationStatistics,
  getItemAnnotationStatus,
  getItemDisplayStatus,
  getUserAnnotationStatus,
  type Annotation,
  type TaskItem,
} from '../annotationStatus'

describe('Issue #134: Annotation Status Synchronization', () => {
  // Test data setup
  const mockItems: TaskItem[] = [
    { id: '1', question: 'Question 1' },
    { id: '2', question: 'Question 2' },
    { id: '3', question: 'Question 3' },
  ]

  const mockAnnotations: Annotation[] = [
    { id: 'a1', item_id: '1', status: 'submitted', user_id: 'user1' },
    { id: 'a2', item_id: '2', status: 'draft', user_id: 'user1' },
    // No annotation for item 3
  ]

  describe('Task Overview vs Data Dashboard Consistency', () => {
    test('should return consistent status for same item across different views', () => {
      // Test item 1 (submitted annotation)
      const item1DetailedStatus = getItemAnnotationStatus('1', mockAnnotations)
      const item1DisplayStatus = getItemDisplayStatus('1', mockAnnotations)

      expect(item1DetailedStatus).toBe(ANNOTATION_STATUS.COMPLETED)
      expect(item1DisplayStatus).toBe(DISPLAY_STATUS.ANNOTATED)

      // Test item 2 (draft annotation)
      const item2DetailedStatus = getItemAnnotationStatus('2', mockAnnotations)
      const item2DisplayStatus = getItemDisplayStatus('2', mockAnnotations)

      expect(item2DetailedStatus).toBe(ANNOTATION_STATUS.IN_PROGRESS)
      expect(item2DisplayStatus).toBe(DISPLAY_STATUS.NOT_ANNOTATED)

      // Test item 3 (no annotation)
      const item3DetailedStatus = getItemAnnotationStatus('3', mockAnnotations)
      const item3DisplayStatus = getItemDisplayStatus('3', mockAnnotations)

      expect(item3DetailedStatus).toBe(ANNOTATION_STATUS.NOT_STARTED)
      expect(item3DisplayStatus).toBe(DISPLAY_STATUS.NOT_ANNOTATED)
    })

    test('should have consistent "All items annotated" logic between views', () => {
      // Test with partial annotations (should NOT be all annotated)
      const allAnnotated = areAllItemsAnnotated(mockItems, mockAnnotations)
      expect(allAnnotated).toBe(false)

      // Test with all items having submitted/approved annotations
      const completeAnnotations: Annotation[] = [
        { id: 'a1', item_id: '1', status: 'submitted', user_id: 'user1' },
        { id: 'a2', item_id: '2', status: 'approved', user_id: 'user1' },
        { id: 'a3', item_id: '3', status: 'submitted', user_id: 'user2' },
      ]

      const allAnnotatedComplete = areAllItemsAnnotated(
        mockItems,
        completeAnnotations
      )
      expect(allAnnotatedComplete).toBe(true)

      // Verify this matches individual item checks
      mockItems.forEach((item) => {
        const itemStatus = getItemAnnotationStatus(
          item.id!,
          completeAnnotations
        )
        expect(itemStatus).toBe(ANNOTATION_STATUS.COMPLETED)

        const displayStatus = getItemDisplayStatus(
          item.id!,
          completeAnnotations
        )
        expect(displayStatus).toBe(DISPLAY_STATUS.ANNOTATED)
      })
    })

    test('should handle mixed annotation states consistently', () => {
      const mixedAnnotations: Annotation[] = [
        { id: 'a1', item_id: '1', status: 'submitted', user_id: 'user1' },
        { id: 'a2', item_id: '1', status: 'draft', user_id: 'user2' }, // Multiple users on same item
        { id: 'a3', item_id: '2', status: 'draft', user_id: 'user1' },
        // Item 3 has no annotations
      ]

      // Item 1 should be completed (has submitted annotation despite also having draft)
      expect(getItemAnnotationStatus('1', mixedAnnotations)).toBe(
        ANNOTATION_STATUS.COMPLETED
      )
      expect(getItemDisplayStatus('1', mixedAnnotations)).toBe(
        DISPLAY_STATUS.ANNOTATED
      )

      // Item 2 should be in progress (only draft)
      expect(getItemAnnotationStatus('2', mixedAnnotations)).toBe(
        ANNOTATION_STATUS.IN_PROGRESS
      )
      expect(getItemDisplayStatus('2', mixedAnnotations)).toBe(
        DISPLAY_STATUS.NOT_ANNOTATED
      )

      // Item 3 should be not started (no annotations)
      expect(getItemAnnotationStatus('3', mixedAnnotations)).toBe(
        ANNOTATION_STATUS.NOT_STARTED
      )
      expect(getItemDisplayStatus('3', mixedAnnotations)).toBe(
        DISPLAY_STATUS.NOT_ANNOTATED
      )

      // Overall should not be all annotated
      expect(areAllItemsAnnotated(mockItems, mixedAnnotations)).toBe(false)
    })
  })

  describe('Statistics Consistency', () => {
    test('should provide consistent statistics across views', () => {
      const stats = getAnnotationStatistics(mockItems, mockAnnotations)

      expect(stats.total).toBe(3)
      expect(stats.completed).toBe(1) // Item 1 is submitted
      expect(stats.inProgress).toBe(1) // Item 2 is draft
      expect(stats.notStarted).toBe(1) // Item 3 has no annotations
      expect(stats.percentageComplete).toBe(33) // 1/3 = 33%

      // Verify these match individual item status checks
      let completedCount = 0
      let inProgressCount = 0
      let notStartedCount = 0

      mockItems.forEach((item) => {
        const status = getItemAnnotationStatus(item.id!, mockAnnotations)
        if (status === ANNOTATION_STATUS.COMPLETED) completedCount++
        else if (status === ANNOTATION_STATUS.IN_PROGRESS) inProgressCount++
        else if (status === ANNOTATION_STATUS.NOT_STARTED) notStartedCount++
      })

      expect(completedCount).toBe(stats.completed)
      expect(inProgressCount).toBe(stats.inProgress)
      expect(notStartedCount).toBe(stats.notStarted)
    })
  })

  describe('Next Unannotated Item Consistency', () => {
    test('should find the same next unannotated item across views', () => {
      const nextItem = findNextUnannotatedItem(mockItems, mockAnnotations)

      // Should find item 2 (in progress) or item 3 (not started)
      // The function should return the first non-completed item
      expect(nextItem).toBeDefined()
      expect(nextItem?.id).toBe('2') // Item 2 is first non-completed item

      // With all items completed, should return null
      const completeAnnotations: Annotation[] = [
        { id: 'a1', item_id: '1', status: 'submitted', user_id: 'user1' },
        { id: 'a2', item_id: '2', status: 'approved', user_id: 'user1' },
        { id: 'a3', item_id: '3', status: 'submitted', user_id: 'user2' },
      ]

      const nextItemComplete = findNextUnannotatedItem(
        mockItems,
        completeAnnotations
      )
      expect(nextItemComplete).toBeNull()
    })
  })

  describe('User-Specific Status Consistency', () => {
    test('should provide consistent user-specific status across views', () => {
      const user1Status1 = getUserAnnotationStatus(
        'user1',
        '1',
        mockAnnotations
      )
      const user1Status2 = getUserAnnotationStatus(
        'user1',
        '2',
        mockAnnotations
      )
      const user1Status3 = getUserAnnotationStatus(
        'user1',
        '3',
        mockAnnotations
      )

      expect(user1Status1).toBe(ANNOTATION_STATUS.COMPLETED) // Has submitted
      expect(user1Status2).toBe(ANNOTATION_STATUS.IN_PROGRESS) // Has draft
      expect(user1Status3).toBe(ANNOTATION_STATUS.NOT_STARTED) // No annotation

      // Test user that doesn't exist
      const user2Status1 = getUserAnnotationStatus(
        'user2',
        '1',
        mockAnnotations
      )
      expect(user2Status1).toBe(ANNOTATION_STATUS.NOT_STARTED)
    })
  })

  describe('Edge Cases', () => {
    test('should handle empty items and annotations consistently', () => {
      const emptyItems: TaskItem[] = []
      const emptyAnnotations: Annotation[] = []

      expect(areAllItemsAnnotated(emptyItems, emptyAnnotations)).toBe(false)
      expect(getAnnotationStatistics(emptyItems, emptyAnnotations)).toEqual({
        total: 0,
        notStarted: 0,
        inProgress: 0,
        completed: 0,
        percentageComplete: 0,
      })
      expect(findNextUnannotatedItem(emptyItems, emptyAnnotations)).toBeNull()
    })

    test('should handle ID type consistency (string vs number)', () => {
      const numericItems: TaskItem[] = [
        { id: 1, question: 'Question 1' },
        { id: 2, question: 'Question 2' },
      ]

      const stringAnnotations: Annotation[] = [
        { id: 'a1', item_id: '1', status: 'submitted', user_id: 'user1' },
      ]

      // Should handle string/number ID mismatches consistently
      expect(getItemAnnotationStatus(1, stringAnnotations)).toBe(
        ANNOTATION_STATUS.COMPLETED
      )
      expect(getItemAnnotationStatus('1', stringAnnotations)).toBe(
        ANNOTATION_STATUS.COMPLETED
      )
      expect(getItemDisplayStatus(1, stringAnnotations)).toBe(
        DISPLAY_STATUS.ANNOTATED
      )
      expect(getItemDisplayStatus('1', stringAnnotations)).toBe(
        DISPLAY_STATUS.ANNOTATED
      )
    })

    test('should handle undefined/null IDs consistently', () => {
      const itemsWithUndefinedId: TaskItem[] = [
        { id: undefined, question: 'Question with undefined ID' },
        { question: 'Question without ID' },
      ]

      // Should handle gracefully without throwing errors
      expect(() =>
        getItemAnnotationStatus(undefined as any, mockAnnotations)
      ).not.toThrow()
      expect(() =>
        areAllItemsAnnotated(itemsWithUndefinedId, mockAnnotations)
      ).not.toThrow()

      expect(getItemAnnotationStatus(undefined as any, mockAnnotations)).toBe(
        ANNOTATION_STATUS.NOT_STARTED
      )
    })
  })

  describe('Real-world Scenario Tests', () => {
    test('should handle the specific Issue #134 scenario', () => {
      // Scenario: Task overview shows "All items annotated!" but data dashboard shows individual items as "Not Annotated"

      // This was likely caused by different status calculation logic
      // With unified utilities, both should return the same result

      const realWorldItems: TaskItem[] = [
        { id: 'item-1', question: 'Legal question 1' },
        { id: 'item-2', question: 'Legal question 2' },
        { id: 'item-3', question: 'Legal question 3' },
      ]

      const realWorldAnnotations: Annotation[] = [
        {
          id: 'ann-1',
          item_id: 'item-1',
          status: 'submitted',
          user_id: 'annotator1',
        },
        {
          id: 'ann-2',
          item_id: 'item-2',
          status: 'draft',
          user_id: 'annotator1',
        },
        // item-3 has no annotations
      ]

      // Task overview logic: Check if all items are annotated
      const taskOverviewResult = areAllItemsAnnotated(
        realWorldItems,
        realWorldAnnotations
      )

      // Data dashboard logic: Check individual item status
      const item1Status = getItemDisplayStatus('item-1', realWorldAnnotations)
      const item2Status = getItemDisplayStatus('item-2', realWorldAnnotations)
      const item3Status = getItemDisplayStatus('item-3', realWorldAnnotations)

      // These should be consistent
      expect(taskOverviewResult).toBe(false) // Not all annotated
      expect(item1Status).toBe(DISPLAY_STATUS.ANNOTATED) // Submitted
      expect(item2Status).toBe(DISPLAY_STATUS.NOT_ANNOTATED) // Draft only
      expect(item3Status).toBe(DISPLAY_STATUS.NOT_ANNOTATED) // No annotation

      // If task overview says "All items annotated!", all individual items should show "Annotated"
      const allAnnotated = [item1Status, item2Status, item3Status].every(
        (status) => status === DISPLAY_STATUS.ANNOTATED
      )

      expect(taskOverviewResult).toBe(allAnnotated) // Should match!
    })
  })
})

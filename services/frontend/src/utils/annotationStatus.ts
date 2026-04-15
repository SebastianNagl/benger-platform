/**
 * Unified annotation status utilities for consistent status calculation
 * across task overview and data dashboard views.
 *
 * This module fixes Issue #134 by providing a single source of truth
 * for annotation status calculations.
 */

export interface Annotation {
  id: string
  item_id: string
  status: 'draft' | 'submitted' | 'approved'
  user_id?: string
  created_at?: string
  updated_at?: string
}

export interface TaskItem {
  id?: string | number
  question?: string
  answer?: string
  [key: string]: any
}

/**
 * Status values used consistently across the application
 */
export const ANNOTATION_STATUS = {
  NOT_STARTED: 'not_started',
  IN_PROGRESS: 'in_progress',
  COMPLETED: 'completed',
} as const

export const DISPLAY_STATUS = {
  NOT_ANNOTATED: 'Not Annotated',
  ANNOTATED: 'Annotated',
} as const

/**
 * Normalize item ID to string for consistent comparison
 */
export function normalizeItemId(itemId: string | number | undefined): string {
  if (itemId === undefined || itemId === null) {
    return ''
  }
  return itemId.toString()
}

/**
 * Get all annotations for a specific item
 */
export function getItemAnnotations(
  itemId: string | number,
  annotations: Annotation[]
): Annotation[] {
  const normalizedItemId = normalizeItemId(itemId)
  return annotations.filter(
    (a) => normalizeItemId(a.item_id) === normalizedItemId
  )
}

/**
 * Calculate detailed annotation status for an item
 * Returns: 'not_started', 'in_progress', or 'completed'
 */
export function getItemAnnotationStatus(
  itemId: string | number,
  annotations: Annotation[]
): string {
  const itemAnnotations = getItemAnnotations(itemId, annotations)

  if (itemAnnotations.length === 0) {
    return ANNOTATION_STATUS.NOT_STARTED
  }

  // Check for submitted or approved annotations (completed)
  const hasSubmitted = itemAnnotations.some(
    (a) => a.status === 'submitted' || a.status === 'approved'
  )

  if (hasSubmitted) {
    return ANNOTATION_STATUS.COMPLETED
  }

  // Check for draft annotations (in progress)
  const hasDraft = itemAnnotations.some((a) => a.status === 'draft')

  if (hasDraft) {
    return ANNOTATION_STATUS.IN_PROGRESS
  }

  return ANNOTATION_STATUS.NOT_STARTED
}

/**
 * Calculate display-friendly annotation status for data dashboard
 * Returns: 'Annotated' or 'Not Annotated'
 */
export function getItemDisplayStatus(
  itemId: string | number,
  annotations: Annotation[]
): string {
  const itemAnnotations = getItemAnnotations(itemId, annotations)
  const hasSubmitted = itemAnnotations.some(
    (a) => a.status === 'submitted' || a.status === 'approved'
  )

  return hasSubmitted ? DISPLAY_STATUS.ANNOTATED : DISPLAY_STATUS.NOT_ANNOTATED
}

/**
 * Check if all items in a task are completely annotated
 * This is used for the "All items annotated!" message in task overview
 */
export function areAllItemsAnnotated(
  items: TaskItem[],
  annotations: Annotation[]
): boolean {
  if (items.length === 0) {
    return false
  }

  return items.every((item) => {
    const status = getItemAnnotationStatus(item.id ?? 0, annotations)
    return status === ANNOTATION_STATUS.COMPLETED
  })
}

/**
 * Get annotation statistics for a task
 */
export function getAnnotationStatistics(
  items: TaskItem[],
  annotations: Annotation[]
) {
  if (items.length === 0) {
    return {
      total: 0,
      notStarted: 0,
      inProgress: 0,
      completed: 0,
      percentageComplete: 0,
    }
  }

  const statusCounts = items.reduce(
    (counts, item) => {
      const status = getItemAnnotationStatus(item.id ?? 0, annotations)
      counts[status] = (counts[status] || 0) + 1
      return counts
    },
    {} as Record<string, number>
  )

  const completed = statusCounts[ANNOTATION_STATUS.COMPLETED] || 0
  const inProgress = statusCounts[ANNOTATION_STATUS.IN_PROGRESS] || 0
  const notStarted = statusCounts[ANNOTATION_STATUS.NOT_STARTED] || 0

  return {
    total: items.length,
    notStarted,
    inProgress,
    completed,
    percentageComplete: Math.round((completed / items.length) * 100),
  }
}

/**
 * Find the next unannotated item for the annotation workflow
 */
export function findNextUnannotatedItem(
  items: TaskItem[],
  annotations: Annotation[]
): TaskItem | null {
  return (
    items.find((item) => {
      const status = getItemAnnotationStatus(item.id ?? 0, annotations)
      return status !== ANNOTATION_STATUS.COMPLETED
    }) || null
  )
}

/**
 * Get user-specific annotation status for an item
 */
export function getUserAnnotationStatus(
  userId: string,
  itemId: string | number,
  annotations: Annotation[]
): string {
  const itemAnnotations = getItemAnnotations(itemId, annotations)
  const userAnnotations = itemAnnotations.filter((a) => a.user_id === userId)

  if (userAnnotations.length === 0) {
    return ANNOTATION_STATUS.NOT_STARTED
  }

  const hasSubmitted = userAnnotations.some(
    (a) => a.status === 'submitted' || a.status === 'approved'
  )

  if (hasSubmitted) {
    return ANNOTATION_STATUS.COMPLETED
  }

  const hasDraft = userAnnotations.some((a) => a.status === 'draft')

  return hasDraft
    ? ANNOTATION_STATUS.IN_PROGRESS
    : ANNOTATION_STATUS.NOT_STARTED
}

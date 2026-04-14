/**
 * Task Type Adapter
 *
 * Provides conversion functions between API Task type and labelStudio Task type
 * to resolve type mismatches throughout the application.
 *
 * Issue #371: Fix remaining TypeScript errors in frontend
 */

import { Task as ApiTask } from '@/lib/api/types'
import { Task as LabelStudioTask } from '@/types/labelStudio'

/**
 * Convert API Task to LabelStudio Task format
 * Adds missing properties with sensible defaults
 */
export function apiTaskToLabelStudio(task: ApiTask): LabelStudioTask {
  return {
    ...task,
    // Add labelStudio specific properties
    project_id: 0, // Not available in API task
    is_labeled: (task.annotation_count || 0) > 0,
    total_annotations: task.annotation_count || 0,
    cancelled_annotations: 0, // Not available in API task
    total_generations: 0, // Not available in API task
    meta: {}, // Not available in API task
    data: task.template_data || {},
    // Keep all other properties from API task
  } as unknown as LabelStudioTask
}

/**
 * Convert LabelStudio Task to API Task format
 * Removes labelStudio specific properties
 */
export function labelStudioTaskToApi(task: LabelStudioTask): ApiTask {
  const {
    is_labeled,
    total_annotations,
    cancelled_annotations,
    total_generations,
    meta,
    ...apiTask
  } = task as any

  return {
    ...apiTask,
    template_data: task.data || {},
    annotation_count: total_annotations || 0,
  } as ApiTask
}

/**
 * Convert array of API Tasks to LabelStudio Tasks
 */
export function apiTasksToLabelStudio(tasks: ApiTask[]): LabelStudioTask[] {
  return tasks.map(apiTaskToLabelStudio)
}

/**
 * Convert array of LabelStudio Tasks to API Tasks
 */
export function labelStudioTasksToApi(tasks: LabelStudioTask[]): ApiTask[] {
  return tasks.map(labelStudioTaskToApi)
}

/**
 * Type guard to check if task is LabelStudio format
 */
export function isLabelStudioTask(task: any): task is LabelStudioTask {
  return 'is_labeled' in task && 'total_annotations' in task
}

/**
 * Type guard to check if task is API format
 */
export function isApiTask(task: any): task is ApiTask {
  return 'annotation_count' in task && !('is_labeled' in task)
}

/**
 * Safe task conversion that checks type before converting
 */
export function ensureLabelStudioTask(
  task: ApiTask | LabelStudioTask
): LabelStudioTask {
  if (isLabelStudioTask(task)) {
    return task
  }
  return apiTaskToLabelStudio(task as ApiTask)
}

/**
 * Safe task conversion that checks type before converting
 */
export function ensureApiTask(task: ApiTask | LabelStudioTask): ApiTask {
  if (isApiTask(task)) {
    return task
  }
  return labelStudioTaskToApi(task as LabelStudioTask)
}

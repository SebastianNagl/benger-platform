/**
 * Helper utilities for extracting and formatting data columns from task data
 */

import { Task } from '@/lib/api/types'

export interface DataColumn {
  key: string
  label: string
  type: 'text' | 'number' | 'boolean' | 'date' | 'object' | 'array'
  priority: number
}

/**
 * Priority field names that should appear first in columns
 */
const PRIORITY_FIELDS = [
  'name',
  'title',
  'question',
  'prompt',
  'text',
  'fallnummer',
  'case_name',
  'id',
  'label',
  'description',
]

/**
 * Detect the type of a value for proper formatting
 */
export function detectValueType(value: any): DataColumn['type'] {
  if (value === null || value === undefined) return 'text'
  if (typeof value === 'boolean') return 'boolean'
  if (typeof value === 'number') return 'number'
  if (typeof value === 'string') {
    // Check if it's a date string
    if (/^\d{4}-\d{2}-\d{2}/.test(value)) return 'date'
    return 'text'
  }
  if (Array.isArray(value)) return 'array'
  if (typeof value === 'object') return 'object'
  return 'text'
}

/**
 * Extract data columns from a set of tasks
 * @param tasks Array of tasks to analyze
 * @param maxColumns Maximum number of columns to return (default 15)
 * @returns Array of column definitions
 */
export function extractDataColumns(
  tasks: Task[],
  maxColumns = 15
): DataColumn[] {
  if (!tasks || tasks.length === 0) return []

  // Collect all unique fields from first few tasks
  const fieldMap = new Map<string, DataColumn>()
  const samplTasks = tasks.slice(0, Math.min(5, tasks.length))

  samplTasks.forEach((task) => {
    if (!(task as any).data || typeof (task as any).data !== 'object') return

    Object.entries((task as any).data).forEach(([key, value]) => {
      // Skip complex nested objects and arrays for table display
      const valueType = detectValueType(value)
      if (valueType === 'object' || valueType === 'array') {
        // Only include if it's a simple array of primitives
        if (valueType === 'array' && Array.isArray(value)) {
          const isSimpleArray = value.every(
            (item) =>
              typeof item === 'string' ||
              typeof item === 'number' ||
              typeof item === 'boolean'
          )
          if (!isSimpleArray) return
        } else {
          return
        }
      }

      if (!fieldMap.has(key)) {
        const priority = PRIORITY_FIELDS.indexOf(key.toLowerCase())
        fieldMap.set(key, {
          key,
          label: formatFieldLabel(key),
          type: valueType,
          priority: priority >= 0 ? priority : 999,
        })
      }
    })
  })

  // Sort by priority and then alphabetically
  const columns = Array.from(fieldMap.values()).sort((a, b) => {
    if (a.priority !== b.priority) return a.priority - b.priority
    return a.key.localeCompare(b.key)
  })

  return columns.slice(0, maxColumns)
}

/**
 * Format a field name into a readable label
 * @param fieldName The field name to format
 * @returns Formatted label
 */
export function formatFieldLabel(fieldName: string): string {
  // Convert snake_case or camelCase to Title Case
  return fieldName
    .replace(/_/g, ' ')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .split(' ')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(' ')
}

/**
 * Format a value for display in a table cell
 * @param value The value to format
 * @param type The type of the value
 * @param maxLength Maximum length for text values (default 50)
 * @returns Formatted string for display
 */
export function formatCellValue(
  value: any,
  type: DataColumn['type'],
  maxLength = 50
): { display: string; full: string; truncated: boolean } {
  if (value === null || value === undefined) {
    return { display: '-', full: '-', truncated: false }
  }

  switch (type) {
    case 'boolean':
      return {
        display: value ? '✓' : '✗',
        full: value ? 'true' : 'false',
        truncated: false,
      }

    case 'number':
      const numStr =
        typeof value === 'number' ? value.toLocaleString() : String(value)
      return { display: numStr, full: numStr, truncated: false }

    case 'date':
      try {
        const date = new Date(value)
        const display = date.toLocaleDateString()
        const full = date.toLocaleString()
        return { display, full, truncated: false }
      } catch {
        return formatCellValue(value, 'text', maxLength)
      }

    case 'array':
      const arrayStr = Array.isArray(value) ? value.join(', ') : String(value)
      if (arrayStr.length > maxLength) {
        return {
          display: arrayStr.substring(0, maxLength) + '...',
          full: arrayStr,
          truncated: true,
        }
      }
      return { display: arrayStr, full: arrayStr, truncated: false }

    case 'text':
    default:
      const textStr = String(value)
      if (textStr.length > maxLength) {
        return {
          display: textStr.substring(0, maxLength) + '...',
          full: textStr,
          truncated: true,
        }
      }
      return { display: textStr, full: textStr, truncated: false }
  }
}

/**
 * Get a single display value from task data (fallback for when columns are disabled)
 * @param task The task to get display value from
 * @returns Display string
 */
export function getTaskDisplayValue(task: Task): string {
  if (!(task as any).data) return `Task ${task.id}`

  // Check priority fields first
  for (const field of PRIORITY_FIELDS) {
    if (
      (task as any).data[field] &&
      typeof (task as any).data[field] === 'string'
    ) {
      return (task as any).data[field]
    }
  }

  // Fall back to first string value
  const firstStringValue = Object.values((task as any).data).find(
    (v) => typeof v === 'string'
  )
  if (firstStringValue) return firstStringValue as string

  return `Task ${task.id}`
}

/**
 * Check if tasks have consistent data structure
 * @param tasks Array of tasks to check
 * @returns true if all tasks have similar data fields
 */
export function hasConsistentDataStructure(tasks: Task[]): boolean {
  if (tasks.length < 2) return true

  const firstTaskKeys = new Set(Object.keys(tasks[0].data || {}))

  return tasks.slice(1, Math.min(10, tasks.length)).every((task) => {
    const taskKeys = new Set(Object.keys((task as any).data || {}))
    // Check if at least 70% of keys match
    const intersection = new Set(
      [...firstTaskKeys].filter((x) => taskKeys.has(x))
    )
    return intersection.size >= firstTaskKeys.size * 0.7
  })
}

/**
 * Extract metadata columns from a set of tasks
 * @param tasks Array of tasks to analyze
 * @param maxColumns Maximum number of columns to return (default 10)
 * @returns Array of column definitions
 */
export function extractMetadataColumns(
  tasks: Task[],
  maxColumns = 10
): DataColumn[] {
  if (!tasks || tasks.length === 0) return []

  // Collect all unique metadata fields from first few tasks
  const fieldMap = new Map<string, DataColumn>()
  const sampleTasks = tasks.slice(0, Math.min(10, tasks.length))

  sampleTasks.forEach((task) => {
    if (!(task as any).meta || typeof (task as any).meta !== 'object') return

    Object.entries((task as any).meta).forEach(([key, value]) => {
      // Skip complex nested objects for table display
      const valueType = detectValueType(value)
      if (valueType === 'object') {
        // Skip complex objects but allow arrays
        return
      }

      if (!fieldMap.has(key)) {
        // Common metadata fields that should appear first
        const metaPriorityFields = [
          'tags',
          'status',
          'priority',
          'category',
          'source',
        ]
        const priority = metaPriorityFields.indexOf(key.toLowerCase())

        fieldMap.set(key, {
          key,
          label: formatFieldLabel(key),
          type: valueType,
          priority: priority >= 0 ? priority : 999,
        })
      }
    })
  })

  // Sort by priority and then alphabetically
  const columns = Array.from(fieldMap.values()).sort((a, b) => {
    if (a.priority !== b.priority) return a.priority - b.priority
    return a.key.localeCompare(b.key)
  })

  return columns.slice(0, maxColumns)
}

/**
 * Check if tasks have consistent metadata structure
 * @param tasks Array of tasks to check
 * @returns true if all tasks have similar metadata fields
 */
export function hasConsistentMetadataStructure(tasks: Task[]): boolean {
  if (tasks.length < 2) return true

  // Get metadata keys from tasks that have metadata
  const tasksWithMeta = tasks.filter(
    (t) => (t as any).meta && Object.keys((t as any).meta).length > 0
  )
  if (tasksWithMeta.length < 2) return true

  const firstTaskKeys = new Set(
    Object.keys((tasksWithMeta[0] as any).meta || {})
  )

  return tasksWithMeta
    .slice(1, Math.min(10, tasksWithMeta.length))
    .every((task) => {
      const taskKeys = new Set(Object.keys((task as any).meta || {}))
      // Check if at least 60% of keys match (metadata can be more varied)
      const intersection = new Set(
        [...firstTaskKeys].filter((x) => taskKeys.has(x))
      )
      return intersection.size >= firstTaskKeys.size * 0.6
    })
}

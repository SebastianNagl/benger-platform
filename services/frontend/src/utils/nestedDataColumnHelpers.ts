/**
 * Enhanced helper utilities for extracting and formatting nested data columns from task data
 */

import { Task } from '@/lib/api/types'
import { flattenJson, getNestedValue } from './jsonUtils'

export interface NestedDataColumn {
  key: string // Dot notation path (e.g., "prompts.prompt_clean")
  label: string
  type: 'text' | 'number' | 'boolean' | 'date' | 'object' | 'array'
  priority: number
  isNested: boolean
  depth: number // Nesting depth for visual indication
}

/**
 * Priority field patterns that should appear first in columns
 */
const PRIORITY_FIELD_PATTERNS = [
  /^(name|title|question|prompt|text|label|description|id)$/i,
  /^(fallnummer|case_name|fall|case)$/i,
  /\.(prompt|question|text|title|name)$/i, // Nested priority fields
  /^area$/i,
  /^number/i,
  /binary_solution/i,
  /reasoning/i,
]

/**
 * Fields to exclude from display
 */
const EXCLUDED_FIELDS: string[] = [
  // No fields excluded by default - users can control via column selector
]

/**
 * Get priority score for a field
 */
function getFieldPriority(fieldPath: string): number {
  for (let i = 0; i < PRIORITY_FIELD_PATTERNS.length; i++) {
    if (PRIORITY_FIELD_PATTERNS[i].test(fieldPath)) {
      return i
    }
  }
  return 999
}

/**
 * Detect the type of a value for proper formatting
 */
export function detectValueType(value: any): NestedDataColumn['type'] {
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
 * Format a nested field path into a readable label
 */
export function formatNestedFieldLabel(fieldPath: string): string {
  // Split by dots and array brackets
  const parts = fieldPath.split(/\.|\[|\]/).filter(Boolean)

  // Format each part
  const formattedParts = parts.map((part, index) => {
    // Check if it's a number (array index)
    if (!isNaN(Number(part))) {
      return `[${part}]`
    }

    // Format field name
    const formatted = part
      .replace(/_/g, ' ')
      .replace(/([a-z])([A-Z])/g, '$1 $2')
      .split(' ')
      .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
      .join(' ')

    // Add separator for nested fields
    if (index > 0 && isNaN(Number(parts[index - 1]))) {
      return `› ${formatted}`
    }

    return formatted
  })

  return formattedParts.join(' ')
}

/**
 * Extract nested data columns from a set of tasks
 * @param tasks Array of tasks to analyze
 * @param maxColumns Maximum number of columns to return (default 20)
 * @param includeNested Whether to include nested fields (default true)
 * @returns Array of column definitions
 */
export function extractNestedDataColumns(
  tasks: Task[],
  maxColumns = 20,
  includeNested = true
): NestedDataColumn[] {
  if (!tasks || tasks.length === 0) return []

  // Collect all unique fields from first few tasks
  const fieldMap = new Map<string, NestedDataColumn>()
  const sampleTasks = tasks.slice(0, Math.min(10, tasks.length))

  sampleTasks.forEach((task) => {
    if (!(task as any).data || typeof (task as any).data !== 'object') return

    const taskData = (task as any).data

    if (includeNested) {
      // Flatten the data to get all nested paths
      const flattened = flattenJson(taskData, '', 3) // Limit depth to 3 for UI

      Object.entries(flattened).forEach(([path, value]) => {
        // Skip excluded fields
        if (EXCLUDED_FIELDS.includes(path)) return

        // Don't skip any nested fields - we want to see all data
        // Users can hide columns they don't want via the column selector

        if (!fieldMap.has(path)) {
          const depth = (path.match(/\./g) || []).length
          fieldMap.set(path, {
            key: path,
            label: formatNestedFieldLabel(path),
            type: detectValueType(value),
            priority: getFieldPriority(path),
            isNested: path.includes('.'),
            depth,
          })
        }
      })
    } else {
      // Only top-level fields
      Object.entries(taskData).forEach(([key, value]) => {
        const valueType = detectValueType(value)

        // Skip complex objects if not including nested
        if (valueType === 'object' && !includeNested) return

        if (!fieldMap.has(key)) {
          fieldMap.set(key, {
            key,
            label: formatNestedFieldLabel(key),
            type: valueType,
            priority: getFieldPriority(key),
            isNested: false,
            depth: 0,
          })
        }
      })
    }
  })

  // Sort by priority, then depth, then alphabetically
  const columns = Array.from(fieldMap.values()).sort((a, b) => {
    if (a.priority !== b.priority) return a.priority - b.priority
    if (a.depth !== b.depth) return a.depth - b.depth
    return a.key.localeCompare(b.key)
  })

  return columns.slice(0, maxColumns)
}

/**
 * Get value from task data using nested path
 */
export function getTaskNestedValue(task: Task, path: string): any {
  if (!(task as any).data) return undefined
  return getNestedValue((task as any).data, path)
}

/**
 * Format a value for display in a table cell
 */
export function formatNestedCellValue(
  value: any,
  type: NestedDataColumn['type'],
  maxLength = 100
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
        return formatNestedCellValue(value, 'text', maxLength)
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

    case 'object':
      const objStr = JSON.stringify(value, null, 2)
      const preview =
        objStr.length > 50 ? objStr.substring(0, 50) + '...' : objStr
      return {
        display: preview,
        full: objStr,
        truncated: objStr.length > 50,
      }

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
 * Get display value from task with nested field support
 */
export function getTaskDisplayValueNested(task: Task): string {
  if (!(task as any).data) return `Task ${task.id}`

  const data = (task as any).data

  // Priority fields to check (including nested)
  const priorityPaths = [
    'fall', // Direct field
    'prompts.prompt_clean', // Nested field
    'question',
    'text',
    'title',
    'name',
    'area',
    'number/name',
  ]

  // Check priority fields first
  for (const path of priorityPaths) {
    const value = getNestedValue(data, path)
    if (value && typeof value === 'string') {
      // Return truncated version for display
      return value.length > 150 ? value.substring(0, 150) + '...' : value
    }
  }

  // Fall back to first string value
  const flattened = flattenJson(data, '', 2)
  const firstString = Object.values(flattened).find(
    (v) => typeof v === 'string' && v.length > 0
  )

  if (firstString) {
    const str = firstString as string
    return str.length > 150 ? str.substring(0, 150) + '...' : str
  }

  return `Task ${task.id}`
}

/**
 * Check if tasks have consistent nested data structure
 */
export function hasConsistentNestedStructure(tasks: Task[]): boolean {
  if (tasks.length < 2) return true

  const firstTaskPaths = new Set<string>()
  const firstData = (tasks[0] as any).data
  if (firstData) {
    const flattened = flattenJson(firstData, '', 2)
    Object.keys(flattened).forEach((path) => firstTaskPaths.add(path))
  }

  // Check a sample of tasks
  return tasks.slice(1, Math.min(10, tasks.length)).every((task) => {
    const taskPaths = new Set<string>()
    const data = (task as any).data
    if (data) {
      const flattened = flattenJson(data, '', 2)
      Object.keys(flattened).forEach((path) => taskPaths.add(path))
    }

    // Check if at least 60% of paths match
    const intersection = new Set(
      [...firstTaskPaths].filter((x) => taskPaths.has(x))
    )
    return intersection.size >= firstTaskPaths.size * 0.6
  })
}

/**
 * Column configuration storage key
 */
const COLUMN_CONFIG_KEY = 'benger_task_columns_config'

/**
 * Save column configuration to localStorage
 */
export function saveColumnConfig(projectId: string, columns: string[]) {
  try {
    const stored = localStorage.getItem(COLUMN_CONFIG_KEY)
    const config = stored ? JSON.parse(stored) : {}
    config[projectId] = columns
    localStorage.setItem(COLUMN_CONFIG_KEY, JSON.stringify(config))
  } catch (error) {
    console.error('Failed to save column config:', error)
  }
}

/**
 * Load column configuration from localStorage
 */
export function loadColumnConfig(projectId: string): string[] | null {
  try {
    const stored = localStorage.getItem(COLUMN_CONFIG_KEY)
    if (!stored) return null
    const config = JSON.parse(stored)
    return config[projectId] || null
  } catch (error) {
    console.error('Failed to load column config:', error)
    return null
  }
}

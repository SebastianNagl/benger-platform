/**
 * Utility functions for accessing nested data using field paths
 * Issue #220: Support flexible data structures with dynamic field access
 */

/**
 * Get value from nested object using dot notation path
 * @param data - The data object to traverse
 * @param path - Dot notation path (e.g., "user.name" or "items[0].value")
 * @param defaultValue - Default value if path not found
 * @returns The value at the path or defaultValue
 *
 * @example
 * const data = { user: { name: "John" }, items: [{ value: 42 }] }
 * getValueByPath(data, "user.name") // "John"
 * getValueByPath(data, "items[0].value") // 42
 * getValueByPath(data, "missing.path", "default") // "default"
 */
export function getValueByPath(
  data: any,
  path: string | undefined,
  defaultValue: any = undefined
): any {
  if (!data || !path) return defaultValue

  // Handle array notation: convert "items[0]" to "items.0"
  const normalizedPath = path.replace(/\[(\d+)\]/g, '.$1')

  const segments = normalizedPath.split('.')
  let current = data

  for (const segment of segments) {
    if (current === null || current === undefined) {
      return defaultValue
    }

    // Handle array index
    if (!isNaN(Number(segment))) {
      current = current[Number(segment)]
    } else {
      current = current[segment]
    }
  }

  return current !== undefined ? current : defaultValue
}

/**
 * Set value in nested object using dot notation path
 * @param data - The data object to modify
 * @param path - Dot notation path
 * @param value - Value to set
 * @returns Modified data object
 */
export function setValueByPath(data: any, path: string, value: any): any {
  if (!path) return data

  const normalizedPath = path.replace(/\[(\d+)\]/g, '.$1')
  const segments = normalizedPath.split('.')
  const lastSegment = segments.pop()!

  let current = data

  // Create nested structure if needed
  for (const segment of segments) {
    if (!current[segment]) {
      // Create array or object based on next segment
      const nextSegment = segments[segments.indexOf(segment) + 1] || lastSegment
      current[segment] = !isNaN(Number(nextSegment)) ? [] : {}
    }
    current = current[segment]
  }

  // Set the value
  if (!isNaN(Number(lastSegment))) {
    current[Number(lastSegment)] = value
  } else {
    current[lastSegment] = value
  }

  return data
}

/**
 * Check if a path exists in the data
 * @param data - The data object to check
 * @param path - Dot notation path
 * @returns True if path exists
 */
export function hasPath(data: any, path: string): boolean {
  return getValueByPath(data, path) !== undefined
}

/**
 * Get all leaf paths from an object (for auto-discovery)
 * @param obj - Object to traverse
 * @param prefix - Path prefix
 * @returns Array of paths to all leaf values
 */
export function getAllPaths(obj: any, prefix = ''): string[] {
  const paths: string[] = []

  if (obj === null || obj === undefined) {
    return paths
  }

  if (typeof obj !== 'object' || obj instanceof Date) {
    return prefix ? [prefix] : []
  }

  if (Array.isArray(obj)) {
    obj.forEach((item, index) => {
      paths.push(...getAllPaths(item, `${prefix}[${index}]`))
    })
  } else {
    Object.keys(obj).forEach((key) => {
      const newPath = prefix ? `${prefix}.${key}` : key
      paths.push(...getAllPaths(obj[key], newPath))
    })
  }

  return paths
}

/**
 * Format a value for display based on its type
 * @param value - Value to format
 * @returns Formatted string representation
 */
export function formatValue(value: any): string {
  if (value === null || value === undefined) {
    return ''
  }

  if (typeof value === 'boolean') {
    return value ? 'Yes' : 'No'
  }

  if (value instanceof Date) {
    return value.toLocaleDateString()
  }

  if (Array.isArray(value)) {
    return value.map(formatValue).join(', ')
  }

  if (typeof value === 'object') {
    return JSON.stringify(value, null, 2)
  }

  return String(value)
}

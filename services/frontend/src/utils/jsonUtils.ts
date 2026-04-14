/**
 * JSON utility functions for handling nested data structures
 */

/**
 * Flatten a nested JSON object using dot notation
 * @param obj Object to flatten
 * @param prefix Prefix for nested keys
 * @param maxDepth Maximum depth to flatten (default 5)
 * @returns Flattened object with dot notation keys
 */
export function flattenJson(
  obj: any,
  prefix = '',
  maxDepth = 5,
  currentDepth = 0
): Record<string, any> {
  const flattened: Record<string, any> = {}

  // Prevent infinite recursion
  if (currentDepth >= maxDepth) {
    if (prefix) {
      flattened[prefix] = obj
    }
    return flattened
  }

  // Handle null or undefined
  if (obj === null || obj === undefined) {
    if (prefix) {
      flattened[prefix] = obj
    }
    return flattened
  }

  // Handle primitives
  if (typeof obj !== 'object') {
    if (prefix) {
      flattened[prefix] = obj
    }
    return flattened
  }

  // Handle arrays
  if (Array.isArray(obj)) {
    if (obj.length === 0) {
      flattened[prefix] = []
    } else if (obj.every((item) => typeof item !== 'object' || item === null)) {
      // Simple array of primitives - keep as is
      flattened[prefix] = obj
    } else {
      // Array of objects - flatten each with index
      obj.forEach((item, index) => {
        const newKey = prefix ? `${prefix}[${index}]` : `[${index}]`
        Object.assign(
          flattened,
          flattenJson(item, newKey, maxDepth, currentDepth + 1)
        )
      })
    }
    return flattened
  }

  // Handle objects
  for (const key in obj) {
    if (Object.prototype.hasOwnProperty.call(obj, key)) {
      const value = obj[key]
      const newKey = prefix ? `${prefix}.${key}` : key

      if (value === null || value === undefined) {
        flattened[newKey] = value
      } else if (typeof value !== 'object') {
        flattened[newKey] = value
      } else if (Array.isArray(value)) {
        // Handle arrays specially
        if (value.length === 0) {
          flattened[newKey] = []
        } else if (
          value.every((item) => typeof item !== 'object' || item === null)
        ) {
          // Simple array - keep as is
          flattened[newKey] = value
        } else {
          // Complex array - flatten
          Object.assign(
            flattened,
            flattenJson(value, newKey, maxDepth, currentDepth + 1)
          )
        }
      } else {
        // Nested object - recurse
        Object.assign(
          flattened,
          flattenJson(value, newKey, maxDepth, currentDepth + 1)
        )
      }
    }
  }

  return flattened
}

/**
 * Get nested value from object using dot notation path
 * @param obj Object to get value from
 * @param path Dot notation path (e.g., "prompts.prompt_clean")
 * @returns Value at path or undefined
 */
export function getNestedValue(obj: any, path: string): any {
  if (!obj || !path) return undefined

  // Handle array notation
  const pathParts = path.split(/\.|\[|\]/).filter(Boolean)

  return pathParts.reduce((current, key) => {
    if (current === null || current === undefined) return undefined

    // Handle numeric keys for arrays
    if (!isNaN(Number(key)) && Array.isArray(current)) {
      return current[Number(key)]
    }

    return current[key]
  }, obj)
}

/**
 * Extract all unique field paths from an array of objects
 * @param objects Array of objects to analyze
 * @param maxDepth Maximum depth to analyze
 * @returns Array of unique field paths
 */
export function extractFieldPaths(objects: any[], maxDepth = 5): string[] {
  const pathSet = new Set<string>()

  objects.forEach((obj) => {
    const flattened = flattenJson(obj, '', maxDepth)
    Object.keys(flattened).forEach((path) => pathSet.add(path))
  })

  return Array.from(pathSet).sort()
}

/**
 * Check if value matches search query (case-insensitive)
 * @param value Value to check
 * @param query Search query
 * @returns True if value contains query
 */
export function valueMatchesQuery(value: any, query: string): boolean {
  if (!query) return true

  const searchLower = query.toLowerCase()

  if (value === null || value === undefined) {
    return false
  }

  if (typeof value === 'string') {
    return value.toLowerCase().includes(searchLower)
  }

  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value).toLowerCase().includes(searchLower)
  }

  if (Array.isArray(value)) {
    // Check if any array element matches
    return value.some((item) => valueMatchesQuery(item, query))
  }

  if (typeof value === 'object') {
    // Check if any object value matches
    return Object.values(value).some((v) => valueMatchesQuery(v, query))
  }

  return false
}

/**
 * Search for query in nested object
 * @param obj Object to search in
 * @param query Search query
 * @returns True if any value in object matches query
 */
export function searchInNestedObject(obj: any, query: string): boolean {
  if (!query) return true

  const flattened = flattenJson(obj)
  return Object.values(flattened).some((value) =>
    valueMatchesQuery(value, query)
  )
}

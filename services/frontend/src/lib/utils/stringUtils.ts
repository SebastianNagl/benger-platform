/**
 * String utility functions
 */

/**
 * Calculate Levenshtein distance between two strings
 * The minimum number of single-character edits required to change one word into the other
 */
export function levenshteinDistance(s1: string, s2: string): number {
  const len1 = s1.length
  const len2 = s2.length
  const matrix: number[][] = []

  // Initialize matrix
  for (let i = 0; i <= len1; i++) {
    matrix[i] = [i]
  }

  for (let j = 0; j <= len2; j++) {
    matrix[0][j] = j
  }

  // Calculate distances
  for (let i = 1; i <= len1; i++) {
    for (let j = 1; j <= len2; j++) {
      if (s1[i - 1] === s2[j - 1]) {
        matrix[i][j] = matrix[i - 1][j - 1]
      } else {
        matrix[i][j] = Math.min(
          matrix[i - 1][j - 1] + 1, // substitution
          matrix[i][j - 1] + 1, // insertion
          matrix[i - 1][j] + 1 // deletion
        )
      }
    }
  }

  return matrix[len1][len2]
}

/**
 * Calculate similarity score between two strings (0-1)
 */
export function stringSimilarity(s1: string, s2: string): number {
  const distance = levenshteinDistance(s1.toLowerCase(), s2.toLowerCase())
  const maxLength = Math.max(s1.length, s2.length)
  return maxLength === 0 ? 1 : 1 - distance / maxLength
}

/**
 * Convert string to camelCase
 */
export function toCamelCase(str: string): string {
  return str
    .toLowerCase()
    .replace(/[^a-zA-Z0-9]+(.)/g, (_, chr) => chr.toUpperCase())
    .replace(/^./, (chr) => chr.toLowerCase())
}

/**
 * Convert string to snake_case
 */
export function toSnakeCase(str: string): string {
  return str
    .replace(/([A-Z])/g, '_$1')
    .toLowerCase()
    .replace(/^_/, '')
    .replace(/[^a-zA-Z0-9]+/g, '_')
    .replace(/_+/g, '_')
    .replace(/_$/, '')
}

/**
 * Convert string to kebab-case
 */
export function toKebabCase(str: string): string {
  return str
    .replace(/([A-Z])/g, '-$1')
    .toLowerCase()
    .replace(/^-/, '')
    .replace(/[^a-zA-Z0-9]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/-$/, '')
}

/**
 * Truncate string with ellipsis
 */
export function truncate(str: string, maxLength: number): string {
  if (str.length <= maxLength) return str
  return str.substring(0, maxLength - 3) + '...'
}

/**
 * Escape string for use in RegExp
 */
export function escapeRegExp(str: string): string {
  return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/**
 * Remove diacritics from string
 */
export function removeDiacritics(str: string): string {
  return str.normalize('NFD').replace(/[\u0300-\u036f]/g, '')
}

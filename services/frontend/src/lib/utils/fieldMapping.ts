/**
 * Smart field mapping with fuzzy matching
 * Issue #220: Automatically map imported fields to template fields
 */

import { levenshteinDistance } from './stringUtils'

export interface FieldMapping {
  source: string // Field name from imported data
  target: string // Field name in template/system
  confidence: number // 0-1 confidence score
  type?: 'exact' | 'fuzzy' | 'semantic' | 'manual'
}

export interface MappingSuggestion {
  mappings: FieldMapping[]
  unmappedSource: string[]
  unmappedTarget: string[]
  quality: 'high' | 'medium' | 'low'
}

// Common field name variations for German legal data
const FIELD_SYNONYMS: Record<string, string[]> = {
  // German legal terms
  case: ['fall', 'case_description', 'beschreibung'],
  case_name: ['fallnummer', 'fall_nummer', 'case_number', 'aktenzeichen'],
  question: ['frage', 'rechtsfrage', 'prompt', 'fragestellung'],
  answer: ['antwort', 'lösung', 'solution', 'urteil'],
  reasoning: ['begründung', 'erklärung', 'explanation', 'rechtliche_würdigung'],
  area: ['rechtsgebiet', 'bereich', 'area_of_law', 'fachgebiet'],
  court: ['gericht', 'instanz', 'court_name'],
  date: ['datum', 'entscheidungsdatum', 'date_decided'],

  // Common variations
  id: ['identifier', 'nummer', 'number', 'key'],
  name: ['title', 'bezeichnung', 'titel'],
  description: ['beschreibung', 'details', 'text'],
  type: ['typ', 'art', 'category', 'kategorie'],
  status: ['zustand', 'state', 'stand'],
  created: ['erstellt', 'created_at', 'angelegt'],
  updated: ['aktualisiert', 'updated_at', 'geändert'],
  tags: ['schlagwörter', 'keywords', 'labels'],
}

// Inverse mapping for reverse lookups
const SYNONYM_TO_CANONICAL: Map<string, string> = new Map()
Object.entries(FIELD_SYNONYMS).forEach(([canonical, synonyms]) => {
  synonyms.forEach((synonym) => {
    SYNONYM_TO_CANONICAL.set(synonym.toLowerCase(), canonical)
  })
})

/**
 * Generate field mapping suggestions
 */
export function suggestFieldMappings(
  sourceFields: string[],
  targetFields: string[],
  existingData?: any[]
): MappingSuggestion {
  const mappings: FieldMapping[] = []
  const usedTargets = new Set<string>()
  const mappedSources = new Set<string>()

  // Step 1: Exact matches
  sourceFields.forEach((source) => {
    const sourceLower = source.toLowerCase()
    const exactMatch = targetFields.find(
      (target) =>
        target.toLowerCase() === sourceLower && !usedTargets.has(target)
    )

    if (exactMatch) {
      mappings.push({
        source,
        target: exactMatch,
        confidence: 1.0,
        type: 'exact',
      })
      usedTargets.add(exactMatch)
      mappedSources.add(source)
    }
  })

  // Step 2: Synonym matches
  sourceFields.forEach((source) => {
    if (mappedSources.has(source)) return

    const sourceLower = source.toLowerCase()
    const canonical = SYNONYM_TO_CANONICAL.get(sourceLower)

    if (canonical) {
      // Find target that matches canonical or is a synonym
      const targetMatch = targetFields.find((target) => {
        if (usedTargets.has(target)) return false
        const targetLower = target.toLowerCase()
        return (
          targetLower === canonical ||
          FIELD_SYNONYMS[canonical]?.includes(targetLower)
        )
      })

      if (targetMatch) {
        mappings.push({
          source,
          target: targetMatch,
          confidence: 0.9,
          type: 'semantic',
        })
        usedTargets.add(targetMatch)
        mappedSources.add(source)
      }
    }
  })

  // Step 3: Fuzzy matching
  sourceFields.forEach((source) => {
    if (mappedSources.has(source)) return

    let bestMatch: { target: string; score: number } | null = null

    targetFields.forEach((target) => {
      if (usedTargets.has(target)) return

      const score = calculateSimilarity(source, target)
      if (score > 0.7 && (!bestMatch || score > bestMatch.score)) {
        bestMatch = { target, score }
      }
    })

    if (bestMatch !== null) {
      const match = bestMatch as { target: string; score: number }
      mappings.push({
        source,
        target: match.target,
        confidence: match.score,
        type: 'fuzzy',
      })
      usedTargets.add(match.target)
      mappedSources.add(source)
    }
  })

  // Step 4: Content-based matching (if sample data provided)
  if (existingData && existingData.length > 0) {
    sourceFields.forEach((source) => {
      if (mappedSources.has(source)) return

      const sourceValues = existingData
        .map((row) => row[source])
        .filter((v) => v !== null && v !== undefined)
        .slice(0, 5)

      if (sourceValues.length === 0) return

      // Try to match based on value patterns
      const bestMatch = findMatchByContent(
        sourceValues,
        targetFields,
        usedTargets
      )

      if (bestMatch) {
        mappings.push({
          source,
          target: bestMatch.target,
          confidence: bestMatch.confidence,
          type: 'semantic',
        })
        usedTargets.add(bestMatch.target)
        mappedSources.add(source)
      }
    })
  }

  // Calculate unmapped fields
  const unmappedSource = sourceFields.filter((f) => !mappedSources.has(f))
  const unmappedTarget = targetFields.filter((f) => !usedTargets.has(f))

  // Determine mapping quality
  const mappingRate =
    mappings.length / Math.max(sourceFields.length, targetFields.length)
  const avgConfidence =
    mappings.length > 0
      ? mappings.reduce((sum, m) => sum + m.confidence, 0) / mappings.length
      : 0

  let quality: 'high' | 'medium' | 'low'
  if (mappingRate > 0.8 && avgConfidence > 0.8) {
    quality = 'high'
  } else if (mappingRate > 0.5 || avgConfidence > 0.7) {
    quality = 'medium'
  } else {
    quality = 'low'
  }

  return {
    mappings,
    unmappedSource,
    unmappedTarget,
    quality,
  }
}

/**
 * Calculate similarity between two field names
 */
function calculateSimilarity(source: string, target: string): number {
  const s1 = normalizeFieldName(source)
  const s2 = normalizeFieldName(target)

  // Check if one contains the other
  if (s1.includes(s2) || s2.includes(s1)) {
    return 0.85
  }

  // Calculate edit distance
  const distance = levenshteinDistance(s1, s2)
  const maxLength = Math.max(s1.length, s2.length)
  const similarity = 1 - distance / maxLength

  // Boost score if they share common parts
  const commonParts = getCommonParts(s1, s2)
  if (commonParts.length > 2) {
    return Math.min(1, similarity + 0.1)
  }

  return similarity
}

/**
 * Normalize field name for comparison
 */
function normalizeFieldName(name: string): string {
  return name
    .toLowerCase()
    .replace(/[_\-\s]+/g, '') // Remove separators
    .replace(/^(the|der|die|das|ein|eine)\s+/i, '') // Remove articles
    .replace(/\s+(id|name|type|date|at|by)$/i, '') // Remove common suffixes
}

/**
 * Get common parts between two strings
 */
function getCommonParts(s1: string, s2: string): string[] {
  const parts1 = s1.split(/[_\-\s]+/)
  const parts2 = s2.split(/[_\-\s]+/)

  return parts1.filter((part) =>
    parts2.some((p) => p === part || levenshteinDistance(p, part) <= 1)
  )
}

/**
 * Find field match based on content analysis
 */
function findMatchByContent(
  values: any[],
  targetFields: string[],
  usedTargets: Set<string>
): { target: string; confidence: number } | null {
  // Detect patterns in values
  const patterns = detectValuePatterns(values)

  for (const target of targetFields) {
    if (usedTargets.has(target)) continue

    // Match based on detected patterns
    if (patterns.isDate && target.toLowerCase().includes('date')) {
      return { target, confidence: 0.8 }
    }
    if (patterns.isNumeric && target.toLowerCase().includes('number')) {
      return { target, confidence: 0.75 }
    }
    if (
      patterns.isBoolean &&
      target.toLowerCase().match(/status|active|enabled/)
    ) {
      return { target, confidence: 0.75 }
    }
    if (
      patterns.isLongText &&
      target.toLowerCase().match(/description|text|content/)
    ) {
      return { target, confidence: 0.7 }
    }
  }

  return null
}

/**
 * Detect patterns in sample values
 */
function detectValuePatterns(values: any[]): {
  isDate: boolean
  isNumeric: boolean
  isBoolean: boolean
  isLongText: boolean
  averageLength: number
} {
  const dateRegex = /^\d{4}-\d{2}-\d{2}|\d{2}[./-]\d{2}[./-]\d{2,4}/

  let dateCount = 0
  let numericCount = 0
  let booleanCount = 0
  let totalLength = 0

  values.forEach((value) => {
    if (
      value instanceof Date ||
      (typeof value === 'string' && dateRegex.test(value))
    ) {
      dateCount++
    } else if (typeof value === 'number' || !isNaN(Number(value))) {
      numericCount++
    } else if (
      typeof value === 'boolean' ||
      ['true', 'false', 'ja', 'nein'].includes(String(value).toLowerCase())
    ) {
      booleanCount++
    }

    totalLength += String(value).length
  })

  const avgLength = totalLength / values.length

  return {
    isDate: dateCount > values.length * 0.7,
    isNumeric: numericCount > values.length * 0.7,
    isBoolean: booleanCount > values.length * 0.7,
    isLongText: avgLength > 100,
    averageLength: avgLength,
  }
}

/**
 * Apply field mappings to data
 */
export function applyFieldMappings(
  data: any[],
  mappings: FieldMapping[]
): any[] {
  return data.map((row) => {
    const mappedRow: any = {}

    // Apply mappings
    mappings.forEach((mapping) => {
      if (mapping.source in row) {
        mappedRow[mapping.target] = row[mapping.source]
      }
    })

    // Include unmapped fields with prefix
    Object.entries(row).forEach(([key, value]) => {
      if (!mappings.some((m) => m.source === key)) {
        mappedRow[`_unmapped_${key}`] = value
      }
    })

    return mappedRow
  })
}

// Using levenshteinDistance from stringUtils

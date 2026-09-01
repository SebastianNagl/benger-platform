/**
 * Shared client-side parsing for project data imports.
 *
 * Single source of truth for the two import surfaces (project-creation wizard
 * step 2 and the project-page ImportDataModal): format detection, column
 * extraction for the detected-columns chips, parsing pasted/uploaded content
 * into Label-Studio-shaped task rows, and assembling the nested-import
 * envelope File handed to `projectsAPI.runNestedImportJob`.
 */

export type ImportFormat = 'json' | 'csv' | 'tsv' | 'txt'

/** Auxiliary arrays of the bulk-export envelope that round-trip through the
 *  nested import (judge scores, human-eval sessions, korrektur threads, …). */
const ENVELOPE_EXTRA_KEYS = [
  'evaluation_runs',
  'human_evaluation_configs',
  'human_evaluation_sessions',
  'human_evaluation_results',
  'preference_rankings',
  'likert_scale_evaluations',
  'korrektur_comments',
] as const

/**
 * Determine the import format. The file extension wins when it names a known
 * format; otherwise the content is sniffed (`{`/`[` → json, tab in the first
 * line → tsv, comma in the first line → csv, else txt).
 */
export function detectFormat(content: string, filename?: string): ImportFormat {
  const ext = filename?.split('.').pop()?.toLowerCase()
  if (ext === 'json' || ext === 'csv' || ext === 'tsv' || ext === 'txt') {
    return ext
  }
  const trimmed = content.trim()
  if (trimmed.startsWith('{') || trimmed.startsWith('[')) return 'json'
  const firstLine = trimmed.split('\n')[0] ?? ''
  if (firstLine.includes('\t')) return 'tsv'
  if (firstLine.includes(',')) return 'csv'
  return 'txt'
}

/** Extract column names from a data string (JSON keys or CSV/TSV headers). */
export function extractColumns(content: string): string[] {
  const trimmed = content.trim()
  if (!trimmed) return []

  try {
    if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
      const parsed = JSON.parse(trimmed)
      const firstItem = Array.isArray(parsed)
        ? parsed[0]
        : parsed.qa_samples?.[0] || parsed.questions?.[0] || parsed
      if (firstItem && typeof firstItem === 'object') {
        return Object.keys(firstItem)
      }
    } else if (trimmed.includes('\t')) {
      const firstLine = trimmed.split('\n')[0]
      return firstLine
        .split('\t')
        .map((h) => h.trim().replace(/^["']|["']$/g, ''))
        .filter(Boolean)
    } else if (trimmed.includes(',') && trimmed.split('\n')[0]?.includes(',')) {
      const firstLine = trimmed.split('\n')[0]
      return firstLine
        .split(',')
        .map((h) => h.trim().replace(/^["']|["']$/g, ''))
        .filter(Boolean)
    }
  } catch {
    // ignore parse errors
  }
  return []
}

/** Label Studio alignment: wrap the item in a `data` field unless it already
 *  carries an object-valued `data` field (then it is used as-is). */
function wrapRow(item: any): any {
  if (item && item.data && typeof item.data === 'object') {
    return item
  }
  return { data: item }
}

/**
 * Parse import content into Label-Studio-shaped rows plus auxiliary extras.
 *
 * JSON handles: plain array; `qa_samples` wrapper; `questions` wrapper
 * (`q.question_data || q` per item); the bulk-export envelope
 * (`{tasks, evaluation_runs, …}` → tasks become rows, the auxiliary arrays go
 * to `extras`); any other single object becomes one row. CSV/TSV split on the
 * header row (surrounding quotes stripped) and yield `{data: {header: value}}`
 * per line. TXT yields `{data: {text: line}}` per non-empty line.
 */
export function parseImportData(
  content: string,
  format: ImportFormat
): { rows: any[]; extras: Record<string, unknown> } {
  try {
    if (format === 'json') {
      let parsed: any
      try {
        parsed = JSON.parse(content)
      } catch (jsonError: any) {
        throw new Error(`Invalid JSON format: ${jsonError.message}`)
      }

      let dataArray: any[]
      const extras: Record<string, unknown> = {}
      if (Array.isArray(parsed)) {
        dataArray = parsed
      } else if (Array.isArray(parsed.qa_samples)) {
        dataArray = parsed.qa_samples
      } else if (Array.isArray(parsed.questions)) {
        dataArray = parsed.questions.map((q: any) => q.question_data || q)
      } else if (Array.isArray(parsed.tasks)) {
        // Bulk-export envelope: tasks become rows; forward the auxiliary
        // arrays so evaluations/korrektur round-trip into the target project.
        for (const k of ENVELOPE_EXTRA_KEYS) {
          if (Array.isArray(parsed[k])) extras[k] = parsed[k]
        }
        dataArray = parsed.tasks
      } else {
        dataArray = [parsed]
      }

      return { rows: dataArray.map(wrapRow), extras }
    } else if (format === 'csv' || format === 'tsv') {
      const delimiter = format === 'csv' ? ',' : '\t'
      const lines = content.trim().split('\n')
      if (lines.length === 0 || !lines[0].trim()) {
        return { rows: [], extras: {} }
      }

      const headers = lines[0]
        .split(delimiter)
        .map((h) => h.trim().replace(/^["']|["']$/g, ''))

      const rows = lines.slice(1).map((line) => {
        const values = line
          .split(delimiter)
          .map((v) => v.trim().replace(/^["']|["']$/g, ''))
        const obj: any = {}
        headers.forEach((header, index) => {
          obj[header] = values[index] || ''
        })
        return { data: obj }
      })
      return { rows, extras: {} }
    } else {
      // Plain text: each non-empty line becomes a task.
      const rows = content
        .trim()
        .split('\n')
        .filter((line) => line.trim())
        .map((line) => ({ data: { text: line.trim() } }))
      return { rows, extras: {} }
    }
  } catch (error: any) {
    if (error.message && error.message.includes('Invalid JSON')) {
      throw error
    }
    throw new Error(
      `Failed to parse ${format.toUpperCase()} data: ${error.message || error}`
    )
  }
}

/**
 * Assemble the nested-import envelope File uploaded to object storage via
 * `projectsAPI.runNestedImportJob`.
 */
export function buildImportFile(
  rows: any[],
  extras: Record<string, unknown> = {}
): File {
  return new File(
    [JSON.stringify({ data: rows, ...extras })],
    `import-${Date.now()}.json`,
    { type: 'application/json' }
  )
}

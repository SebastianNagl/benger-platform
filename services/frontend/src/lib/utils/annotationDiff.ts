/**
 * Annotation Diff Utilities
 *
 * Computes differences between two annotation result arrays
 * for displaying side-by-side review comparisons.
 */

import { AnnotationResult } from '@/types/labelStudio'

export interface FieldDiff {
  from_name: string
  to_name: string
  type: string
  status: 'added' | 'removed' | 'modified' | 'unchanged'
  originalValue: any
  reviewValue: any
}

export interface AnnotationDiffResult {
  fields: FieldDiff[]
  summary: {
    total: number
    added: number
    removed: number
    modified: number
    unchanged: number
  }
}

/**
 * Compare two annotation result arrays and produce a diff.
 * Results are matched by from_name.
 */
export function computeAnnotationDiff(
  original: AnnotationResult[],
  review: AnnotationResult[]
): AnnotationDiffResult {
  const fields: FieldDiff[] = []
  const originalMap = new Map<string, AnnotationResult>()
  const reviewMap = new Map<string, AnnotationResult>()

  for (const r of original) {
    originalMap.set(r.from_name, r)
  }
  for (const r of review) {
    reviewMap.set(r.from_name, r)
  }

  // All unique field names
  const allKeys = new Set([...originalMap.keys(), ...reviewMap.keys()])

  for (const key of allKeys) {
    const orig = originalMap.get(key)
    const rev = reviewMap.get(key)

    if (orig && rev) {
      const isEqual = deepEqual(orig.value, rev.value)
      fields.push({
        from_name: key,
        to_name: orig.to_name || rev.to_name,
        type: orig.type || rev.type,
        status: isEqual ? 'unchanged' : 'modified',
        originalValue: orig.value,
        reviewValue: rev.value,
      })
    } else if (orig && !rev) {
      fields.push({
        from_name: key,
        to_name: orig.to_name,
        type: orig.type,
        status: 'removed',
        originalValue: orig.value,
        reviewValue: null,
      })
    } else if (!orig && rev) {
      fields.push({
        from_name: key,
        to_name: rev.to_name,
        type: rev.type,
        status: 'added',
        originalValue: null,
        reviewValue: rev.value,
      })
    }
  }

  const summary = {
    total: fields.length,
    added: fields.filter((f) => f.status === 'added').length,
    removed: fields.filter((f) => f.status === 'removed').length,
    modified: fields.filter((f) => f.status === 'modified').length,
    unchanged: fields.filter((f) => f.status === 'unchanged').length,
  }

  return { fields, summary }
}

/**
 * Compute highlight/span diff between two sets of spans.
 */
export interface SpanDiffItem {
  status: 'added' | 'removed' | 'common'
  span: { id: string; start: number; end: number; text: string; labels: string[] }
  source: 'original' | 'review' | 'both'
}

export function computeHighlightDiff(
  originalSpans: any[],
  reviewSpans: any[]
): SpanDiffItem[] {
  const results: SpanDiffItem[] = []

  const origSet = new Set(
    originalSpans.map((s) => `${s.start}:${s.end}:${s.labels?.join(',')}`)
  )
  const revSet = new Set(
    reviewSpans.map((s) => `${s.start}:${s.end}:${s.labels?.join(',')}`)
  )

  for (const span of originalSpans) {
    const key = `${span.start}:${span.end}:${span.labels?.join(',')}`
    if (revSet.has(key)) {
      results.push({ status: 'common', span, source: 'both' })
    } else {
      results.push({ status: 'removed', span, source: 'original' })
    }
  }

  for (const span of reviewSpans) {
    const key = `${span.start}:${span.end}:${span.labels?.join(',')}`
    if (!origSet.has(key)) {
      results.push({ status: 'added', span, source: 'review' })
    }
  }

  return results.sort((a, b) => a.span.start - b.span.start)
}

/**
 * Compute line-by-line diff for markdown/text content.
 */
export interface LineDiff {
  status: 'added' | 'removed' | 'unchanged'
  line: string
  lineNumber?: number
}

export function computeLineDiff(
  originalText: string,
  reviewText: string
): LineDiff[] {
  const origLines = originalText.split('\n')
  const revLines = reviewText.split('\n')
  const results: LineDiff[] = []

  // Simple LCS-based diff
  const lcs = computeLCS(origLines, revLines)
  let oi = 0
  let ri = 0
  let li = 0

  while (li < lcs.length) {
    // Add removed lines (in original but not in LCS match)
    while (oi < origLines.length && origLines[oi] !== lcs[li]) {
      results.push({ status: 'removed', line: origLines[oi], lineNumber: oi + 1 })
      oi++
    }
    // Add added lines (in review but not in LCS match)
    while (ri < revLines.length && revLines[ri] !== lcs[li]) {
      results.push({ status: 'added', line: revLines[ri], lineNumber: ri + 1 })
      ri++
    }
    // Common line
    results.push({ status: 'unchanged', line: lcs[li] })
    oi++
    ri++
    li++
  }

  // Remaining lines
  while (oi < origLines.length) {
    results.push({ status: 'removed', line: origLines[oi], lineNumber: oi + 1 })
    oi++
  }
  while (ri < revLines.length) {
    results.push({ status: 'added', line: revLines[ri], lineNumber: ri + 1 })
    ri++
  }

  return results
}

/**
 * Compute comment diff between two comment arrays.
 */
export interface CommentDiffItem {
  status: 'added' | 'removed' | 'common'
  comment: { id: string; type: string; text: string; start?: number; end?: number }
  source: 'original' | 'review' | 'both'
}

export function computeCommentDiff(
  originalComments: any[],
  reviewComments: any[]
): CommentDiffItem[] {
  const results: CommentDiffItem[] = []
  const origIds = new Set(originalComments.map((c) => c.id))
  const revIds = new Set(reviewComments.map((c) => c.id))

  for (const comment of originalComments) {
    if (revIds.has(comment.id)) {
      results.push({ status: 'common', comment, source: 'both' })
    } else {
      results.push({ status: 'removed', comment, source: 'original' })
    }
  }

  for (const comment of reviewComments) {
    if (!origIds.has(comment.id)) {
      results.push({ status: 'added', comment, source: 'review' })
    }
  }

  return results
}

// --- Helpers ---

function deepEqual(a: any, b: any): boolean {
  return JSON.stringify(a) === JSON.stringify(b)
}

function computeLCS(a: string[], b: string[]): string[] {
  const m = a.length
  const n = b.length
  const dp: number[][] = Array.from({ length: m + 1 }, () =>
    new Array(n + 1).fill(0)
  )

  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      if (a[i - 1] === b[j - 1]) {
        dp[i][j] = dp[i - 1][j - 1] + 1
      } else {
        dp[i][j] = Math.max(dp[i - 1][j], dp[i][j - 1])
      }
    }
  }

  // Backtrack to find LCS
  const result: string[] = []
  let i = m
  let j = n
  while (i > 0 && j > 0) {
    if (a[i - 1] === b[j - 1]) {
      result.unshift(a[i - 1])
      i--
      j--
    } else if (dp[i - 1][j] > dp[i][j - 1]) {
      i--
    } else {
      j--
    }
  }

  return result
}

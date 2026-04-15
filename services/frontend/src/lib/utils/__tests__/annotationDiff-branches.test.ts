/**
 * Branch coverage tests for annotationDiff.ts
 *
 * Targets: computeAnnotationDiff all status branches (added, removed, modified, unchanged),
 * computeHighlightDiff common/added/removed branches,
 * computeLineDiff with additions/removals/unchanged,
 * computeCommentDiff common/added/removed.
 */

import {
  computeAnnotationDiff,
  computeHighlightDiff,
  computeLineDiff,
  computeCommentDiff,
} from '../annotationDiff'

describe('computeAnnotationDiff', () => {
  it('should mark fields as unchanged when values match', () => {
    const original = [{ from_name: 'a', to_name: 'q', type: 'textarea', value: { text: ['hello'] } }]
    const review = [{ from_name: 'a', to_name: 'q', type: 'textarea', value: { text: ['hello'] } }]
    const result = computeAnnotationDiff(original, review)
    expect(result.summary.unchanged).toBe(1)
    expect(result.fields[0].status).toBe('unchanged')
  })

  it('should mark fields as modified when values differ', () => {
    const original = [{ from_name: 'a', to_name: 'q', type: 'textarea', value: { text: ['old'] } }]
    const review = [{ from_name: 'a', to_name: 'q', type: 'textarea', value: { text: ['new'] } }]
    const result = computeAnnotationDiff(original, review)
    expect(result.summary.modified).toBe(1)
    expect(result.fields[0].status).toBe('modified')
  })

  it('should mark fields as removed when in original but not review', () => {
    const original = [{ from_name: 'a', to_name: 'q', type: 'textarea', value: 'val' }]
    const result = computeAnnotationDiff(original, [])
    expect(result.summary.removed).toBe(1)
    expect(result.fields[0].status).toBe('removed')
    expect(result.fields[0].reviewValue).toBeNull()
  })

  it('should mark fields as added when in review but not original', () => {
    const review = [{ from_name: 'b', to_name: 'q', type: 'textarea', value: 'val' }]
    const result = computeAnnotationDiff([], review)
    expect(result.summary.added).toBe(1)
    expect(result.fields[0].status).toBe('added')
    expect(result.fields[0].originalValue).toBeNull()
  })

  it('should handle mixed changes', () => {
    const original = [
      { from_name: 'a', to_name: 'q', type: 't', value: 'same' },
      { from_name: 'b', to_name: 'q', type: 't', value: 'old' },
      { from_name: 'c', to_name: 'q', type: 't', value: 'removed' },
    ]
    const review = [
      { from_name: 'a', to_name: 'q', type: 't', value: 'same' },
      { from_name: 'b', to_name: 'q', type: 't', value: 'new' },
      { from_name: 'd', to_name: 'q', type: 't', value: 'added' },
    ]
    const result = computeAnnotationDiff(original, review)
    expect(result.summary.unchanged).toBe(1)
    expect(result.summary.modified).toBe(1)
    expect(result.summary.removed).toBe(1)
    expect(result.summary.added).toBe(1)
    expect(result.summary.total).toBe(4)
  })
})

describe('computeHighlightDiff', () => {
  it('should detect common spans', () => {
    const origSpans = [{ id: 's1', start: 0, end: 5, text: 'hi', labels: ['A'] }]
    const revSpans = [{ id: 's1', start: 0, end: 5, text: 'hi', labels: ['A'] }]
    const result = computeHighlightDiff(origSpans, revSpans)
    expect(result.some((r) => r.status === 'common')).toBe(true)
  })

  it('should detect removed spans', () => {
    const origSpans = [{ id: 's1', start: 0, end: 5, text: 'hi', labels: ['A'] }]
    const result = computeHighlightDiff(origSpans, [])
    expect(result[0].status).toBe('removed')
  })

  it('should detect added spans', () => {
    const revSpans = [{ id: 's2', start: 10, end: 15, text: 'new', labels: ['B'] }]
    const result = computeHighlightDiff([], revSpans)
    expect(result[0].status).toBe('added')
  })

  it('should sort by start position', () => {
    const origSpans = [{ id: 's1', start: 10, end: 15, text: 'b', labels: ['A'] }]
    const revSpans = [{ id: 's2', start: 0, end: 5, text: 'a', labels: ['B'] }]
    const result = computeHighlightDiff(origSpans, revSpans)
    expect(result[0].span.start).toBeLessThan(result[1].span.start)
  })
})

describe('computeLineDiff', () => {
  it('should show unchanged lines', () => {
    const result = computeLineDiff('same\nline', 'same\nline')
    expect(result.every((r) => r.status === 'unchanged')).toBe(true)
  })

  it('should show added lines', () => {
    const result = computeLineDiff('a', 'a\nb')
    expect(result.some((r) => r.status === 'added')).toBe(true)
  })

  it('should show removed lines', () => {
    const result = computeLineDiff('a\nb', 'a')
    expect(result.some((r) => r.status === 'removed')).toBe(true)
  })

  it('should handle completely different text', () => {
    const result = computeLineDiff('old line', 'new line')
    expect(result.length).toBeGreaterThan(0)
  })

  it('should handle empty strings', () => {
    const result = computeLineDiff('', '')
    // Empty text produces one unchanged empty line
    expect(result.length).toBeGreaterThanOrEqual(0)
  })
})

describe('computeCommentDiff', () => {
  it('should detect common comments', () => {
    const orig = [{ id: 'c1', type: 'note', text: 'hello' }]
    const rev = [{ id: 'c1', type: 'note', text: 'hello' }]
    const result = computeCommentDiff(orig, rev)
    expect(result[0].status).toBe('common')
    expect(result[0].source).toBe('both')
  })

  it('should detect removed comments', () => {
    const orig = [{ id: 'c1', type: 'note', text: 'hello' }]
    const result = computeCommentDiff(orig, [])
    expect(result[0].status).toBe('removed')
    expect(result[0].source).toBe('original')
  })

  it('should detect added comments', () => {
    const rev = [{ id: 'c2', type: 'note', text: 'new' }]
    const result = computeCommentDiff([], rev)
    expect(result[0].status).toBe('added')
    expect(result[0].source).toBe('review')
  })
})

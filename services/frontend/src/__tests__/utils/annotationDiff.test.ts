/**
 * Unit tests for annotation diff utilities
 */

import {
  computeAnnotationDiff,
  computeHighlightDiff,
  computeLineDiff,
  computeCommentDiff,
} from '../../lib/utils/annotationDiff'
import { AnnotationResult } from '../../types/labelStudio'

describe('computeAnnotationDiff', () => {
  it('should return empty diff for two empty arrays', () => {
    const result = computeAnnotationDiff([], [])

    expect(result.fields).toHaveLength(0)
    expect(result.summary).toEqual({
      total: 0,
      added: 0,
      removed: 0,
      modified: 0,
      unchanged: 0,
    })
  })

  it('should detect unchanged fields', () => {
    const original: AnnotationResult[] = [
      { from_name: 'label', to_name: 'text', type: 'choices', value: { choices: ['A'] } },
    ]
    const review: AnnotationResult[] = [
      { from_name: 'label', to_name: 'text', type: 'choices', value: { choices: ['A'] } },
    ]

    const result = computeAnnotationDiff(original, review)

    expect(result.fields).toHaveLength(1)
    expect(result.fields[0].status).toBe('unchanged')
    expect(result.summary.unchanged).toBe(1)
  })

  it('should detect modified fields', () => {
    const original: AnnotationResult[] = [
      { from_name: 'label', to_name: 'text', type: 'choices', value: { choices: ['A'] } },
    ]
    const review: AnnotationResult[] = [
      { from_name: 'label', to_name: 'text', type: 'choices', value: { choices: ['B'] } },
    ]

    const result = computeAnnotationDiff(original, review)

    expect(result.fields).toHaveLength(1)
    expect(result.fields[0].status).toBe('modified')
    expect(result.fields[0].originalValue).toEqual({ choices: ['A'] })
    expect(result.fields[0].reviewValue).toEqual({ choices: ['B'] })
    expect(result.summary.modified).toBe(1)
  })

  it('should detect added fields', () => {
    const original: AnnotationResult[] = []
    const review: AnnotationResult[] = [
      { from_name: 'notes', to_name: 'text', type: 'textarea', value: { text: ['hello'] } },
    ]

    const result = computeAnnotationDiff(original, review)

    expect(result.fields).toHaveLength(1)
    expect(result.fields[0].status).toBe('added')
    expect(result.fields[0].originalValue).toBeNull()
    expect(result.fields[0].reviewValue).toEqual({ text: ['hello'] })
    expect(result.summary.added).toBe(1)
  })

  it('should detect removed fields', () => {
    const original: AnnotationResult[] = [
      { from_name: 'notes', to_name: 'text', type: 'textarea', value: { text: ['hello'] } },
    ]
    const review: AnnotationResult[] = []

    const result = computeAnnotationDiff(original, review)

    expect(result.fields).toHaveLength(1)
    expect(result.fields[0].status).toBe('removed')
    expect(result.fields[0].originalValue).toEqual({ text: ['hello'] })
    expect(result.fields[0].reviewValue).toBeNull()
    expect(result.summary.removed).toBe(1)
  })

  it('should handle mixed changes across multiple fields', () => {
    const original: AnnotationResult[] = [
      { from_name: 'label', to_name: 'text', type: 'choices', value: { choices: ['A'] } },
      { from_name: 'notes', to_name: 'text', type: 'textarea', value: { text: ['note'] } },
      { from_name: 'removed_field', to_name: 'text', type: 'rating', value: { rating: 3 } },
    ]
    const review: AnnotationResult[] = [
      { from_name: 'label', to_name: 'text', type: 'choices', value: { choices: ['A'] } },
      { from_name: 'notes', to_name: 'text', type: 'textarea', value: { text: ['updated note'] } },
      { from_name: 'new_field', to_name: 'text', type: 'number', value: { number: 42 } },
    ]

    const result = computeAnnotationDiff(original, review)

    expect(result.summary.total).toBe(4)
    expect(result.summary.unchanged).toBe(1)
    expect(result.summary.modified).toBe(1)
    expect(result.summary.removed).toBe(1)
    expect(result.summary.added).toBe(1)
  })

  it('should match fields by from_name', () => {
    const original: AnnotationResult[] = [
      { from_name: 'a', to_name: 'text', type: 'choices', value: { choices: ['X'] } },
      { from_name: 'b', to_name: 'text', type: 'choices', value: { choices: ['Y'] } },
    ]
    const review: AnnotationResult[] = [
      { from_name: 'b', to_name: 'text', type: 'choices', value: { choices: ['Z'] } },
      { from_name: 'a', to_name: 'text', type: 'choices', value: { choices: ['X'] } },
    ]

    const result = computeAnnotationDiff(original, review)

    const fieldA = result.fields.find((f) => f.from_name === 'a')
    const fieldB = result.fields.find((f) => f.from_name === 'b')
    expect(fieldA?.status).toBe('unchanged')
    expect(fieldB?.status).toBe('modified')
  })

  it('should handle angabe type with spans and comments', () => {
    const angabeValue = {
      spans: [
        { id: 's1', start: 0, end: 10, text: 'hello', labels: ['Wichtig'] },
      ],
      comments: [
        { id: 'c1', type: 'general', text: 'A comment' },
      ],
    }
    const original: AnnotationResult[] = [
      { from_name: 'angabe', to_name: 'sachverhalt', type: 'angabe', value: angabeValue },
    ]
    const review: AnnotationResult[] = [
      { from_name: 'angabe', to_name: 'sachverhalt', type: 'angabe', value: angabeValue },
    ]

    const result = computeAnnotationDiff(original, review)

    expect(result.fields).toHaveLength(1)
    expect(result.fields[0].status).toBe('unchanged')
    expect(result.fields[0].type).toBe('angabe')
  })
})

describe('computeHighlightDiff', () => {
  it('should return empty array for two empty span arrays', () => {
    const result = computeHighlightDiff([], [])
    expect(result).toHaveLength(0)
  })

  it('should detect common spans', () => {
    const spans = [
      { id: 's1', start: 0, end: 10, text: 'hello', labels: ['Wichtig'] },
    ]

    const result = computeHighlightDiff(spans, spans)

    expect(result).toHaveLength(1)
    expect(result[0].status).toBe('common')
    expect(result[0].source).toBe('both')
  })

  it('should detect removed spans', () => {
    const original = [
      { id: 's1', start: 0, end: 10, text: 'hello', labels: ['Wichtig'] },
    ]

    const result = computeHighlightDiff(original, [])

    expect(result).toHaveLength(1)
    expect(result[0].status).toBe('removed')
    expect(result[0].source).toBe('original')
  })

  it('should detect added spans', () => {
    const review = [
      { id: 's2', start: 5, end: 15, text: 'world', labels: ['Norm'] },
    ]

    const result = computeHighlightDiff([], review)

    expect(result).toHaveLength(1)
    expect(result[0].status).toBe('added')
    expect(result[0].source).toBe('review')
  })

  it('should handle mixed span changes', () => {
    const original = [
      { id: 's1', start: 0, end: 10, text: 'common', labels: ['Wichtig'] },
      { id: 's2', start: 20, end: 30, text: 'removed', labels: ['Norm'] },
    ]
    const review = [
      { id: 's1', start: 0, end: 10, text: 'common', labels: ['Wichtig'] },
      { id: 's3', start: 40, end: 50, text: 'added', labels: ['Sonstiges'] },
    ]

    const result = computeHighlightDiff(original, review)

    const common = result.filter((r) => r.status === 'common')
    const removed = result.filter((r) => r.status === 'removed')
    const added = result.filter((r) => r.status === 'added')
    expect(common).toHaveLength(1)
    expect(removed).toHaveLength(1)
    expect(added).toHaveLength(1)
  })

  it('should match spans by start:end:labels key', () => {
    const original = [
      { id: 's1', start: 0, end: 10, text: 'hello', labels: ['Wichtig'] },
    ]
    const review = [
      { id: 's2', start: 0, end: 10, text: 'hello', labels: ['Wichtig'] },
    ]

    const result = computeHighlightDiff(original, review)

    // Different IDs but same position/labels should be common
    expect(result).toHaveLength(1)
    expect(result[0].status).toBe('common')
  })

  it('should treat different labels as different spans', () => {
    const original = [
      { id: 's1', start: 0, end: 10, text: 'hello', labels: ['Wichtig'] },
    ]
    const review = [
      { id: 's1', start: 0, end: 10, text: 'hello', labels: ['Norm'] },
    ]

    const result = computeHighlightDiff(original, review)

    // Same position but different labels = removed + added
    expect(result).toHaveLength(2)
    const removed = result.find((r) => r.status === 'removed')
    const added = result.find((r) => r.status === 'added')
    expect(removed).toBeDefined()
    expect(added).toBeDefined()
  })

  it('should sort results by start position', () => {
    const original = [
      { id: 's1', start: 30, end: 40, text: 'later', labels: ['A'] },
    ]
    const review = [
      { id: 's2', start: 5, end: 15, text: 'earlier', labels: ['B'] },
    ]

    const result = computeHighlightDiff(original, review)

    expect(result[0].span.start).toBeLessThan(result[1].span.start)
  })
})

describe('computeLineDiff', () => {
  it('should return unchanged for identical texts', () => {
    const text = 'line 1\nline 2\nline 3'
    const result = computeLineDiff(text, text)

    expect(result).toHaveLength(3)
    expect(result.every((d) => d.status === 'unchanged')).toBe(true)
  })

  it('should detect added lines', () => {
    const original = 'line 1\nline 3'
    const review = 'line 1\nline 2\nline 3'

    const result = computeLineDiff(original, review)

    const added = result.filter((d) => d.status === 'added')
    expect(added).toHaveLength(1)
    expect(added[0].line).toBe('line 2')
  })

  it('should detect removed lines', () => {
    const original = 'line 1\nline 2\nline 3'
    const review = 'line 1\nline 3'

    const result = computeLineDiff(original, review)

    const removed = result.filter((d) => d.status === 'removed')
    expect(removed).toHaveLength(1)
    expect(removed[0].line).toBe('line 2')
  })

  it('should handle completely different texts', () => {
    const original = 'alpha\nbeta'
    const review = 'gamma\ndelta'

    const result = computeLineDiff(original, review)

    const removed = result.filter((d) => d.status === 'removed')
    const added = result.filter((d) => d.status === 'added')
    expect(removed).toHaveLength(2)
    expect(added).toHaveLength(2)
  })

  it('should handle empty original text', () => {
    const result = computeLineDiff('', 'new line')

    const added = result.filter((d) => d.status === 'added')
    expect(added).toHaveLength(1)
    expect(added[0].line).toBe('new line')
  })

  it('should handle empty review text', () => {
    const result = computeLineDiff('old line', '')

    const removed = result.filter((d) => d.status === 'removed')
    expect(removed).toHaveLength(1)
    expect(removed[0].line).toBe('old line')
  })

  it('should handle mixed additions and removals in markdown', () => {
    const original = '# Title\n\nParagraph one.\n\nParagraph two.'
    const review = '# Title\n\nParagraph one.\n\nNew paragraph.\n\nParagraph three.'

    const result = computeLineDiff(original, review)

    const unchanged = result.filter((d) => d.status === 'unchanged')
    const removed = result.filter((d) => d.status === 'removed')
    const added = result.filter((d) => d.status === 'added')

    // "# Title", "", "Paragraph one.", "" should be unchanged
    expect(unchanged.length).toBeGreaterThanOrEqual(3)
    // "Paragraph two." removed
    expect(removed.length).toBeGreaterThanOrEqual(1)
    // "New paragraph.", "", "Paragraph three." added
    expect(added.length).toBeGreaterThanOrEqual(1)
  })
})

describe('computeCommentDiff', () => {
  it('should return empty array for two empty comment arrays', () => {
    const result = computeCommentDiff([], [])
    expect(result).toHaveLength(0)
  })

  it('should detect common comments by ID', () => {
    const comments = [
      { id: 'c1', type: 'general', text: 'A comment' },
    ]

    const result = computeCommentDiff(comments, comments)

    expect(result).toHaveLength(1)
    expect(result[0].status).toBe('common')
    expect(result[0].source).toBe('both')
  })

  it('should detect removed comments', () => {
    const original = [
      { id: 'c1', type: 'general', text: 'Old comment' },
    ]

    const result = computeCommentDiff(original, [])

    expect(result).toHaveLength(1)
    expect(result[0].status).toBe('removed')
    expect(result[0].source).toBe('original')
  })

  it('should detect added comments', () => {
    const review = [
      { id: 'c2', type: 'anchored', text: 'New comment', start: 0, end: 10 },
    ]

    const result = computeCommentDiff([], review)

    expect(result).toHaveLength(1)
    expect(result[0].status).toBe('added')
    expect(result[0].source).toBe('review')
  })

  it('should handle mixed comment changes', () => {
    const original = [
      { id: 'c1', type: 'general', text: 'Common' },
      { id: 'c2', type: 'anchored', text: 'Removed', start: 0, end: 5 },
    ]
    const review = [
      { id: 'c1', type: 'general', text: 'Common' },
      { id: 'c3', type: 'general', text: 'Added' },
    ]

    const result = computeCommentDiff(original, review)

    const common = result.filter((r) => r.status === 'common')
    const removed = result.filter((r) => r.status === 'removed')
    const added = result.filter((r) => r.status === 'added')
    expect(common).toHaveLength(1)
    expect(removed).toHaveLength(1)
    expect(added).toHaveLength(1)
  })
})

/**
 * Branch coverage tests for dataBinding.ts
 *
 * Targets uncovered branches in: buildAnnotationResult, mapLegacyAnnotation,
 * parseSpanAnnotations, convertToLabelStudioFormat, convertFromLabelStudioFormat,
 * validateTaskDataFields, resolveDataBinding.
 */

import {
  buildAnnotationResult,
  mapLegacyAnnotation,
  parseSpanAnnotations,
  convertToLabelStudioFormat,
  convertFromLabelStudioFormat,
  validateTaskDataFields,
  resolveDataBinding,
  resolvePropsDataBindings,
  buildSpanAnnotationResult,
} from '../dataBinding'

describe('buildAnnotationResult', () => {
  it('should format TextArea value', () => {
    const result = buildAnnotationResult('answer', 'TextArea', 'my text', 'question')
    expect(result.value).toEqual({ text: ['my text'] })
    expect(result.type).toBe('textarea')
  })

  it('should format Choices value with single string', () => {
    const result = buildAnnotationResult('choice', 'Choices', 'option1', 'question')
    expect(result.value).toEqual({ choices: ['option1'] })
  })

  it('should format Choices value with array', () => {
    const result = buildAnnotationResult('choice', 'Choices', ['a', 'b'], 'question')
    expect(result.value).toEqual({ choices: ['a', 'b'] })
  })

  it('should use lowercase type for unknown component types', () => {
    const result = buildAnnotationResult('custom', 'CustomType', 42, 'target')
    expect(result.type).toBe('customtype')
    expect(result.value).toBe(42)
  })

  it('should map known types like Rating', () => {
    const result = buildAnnotationResult('rating', 'Rating', 5, 'target')
    expect(result.type).toBe('rating')
  })

  it('should map Number type', () => {
    const result = buildAnnotationResult('num', 'Number', 42, 'target')
    expect(result.type).toBe('number')
  })

  })
})

describe('mapLegacyAnnotation', () => {
  it('should map short_answer field', () => {
    const result = mapLegacyAnnotation('short_answer', 'my answer')
    expect(result).not.toBeNull()
    expect(result!.type).toBe('textarea')
    expect(result!.from_name).toBe('short_answer')
    expect(result!.to_name).toBe('question')
  })

  it('should map reasoning field', () => {
    const result = mapLegacyAnnotation('reasoning', 'because...')
    expect(result).not.toBeNull()
    expect(result!.type).toBe('textarea')
  })

  it('should map confidence field as choices', () => {
    const result = mapLegacyAnnotation('confidence', 'high')
    expect(result).not.toBeNull()
    expect(result!.type).toBe('choices')
    expect(result!.value).toEqual({ choices: ['high'] })
  })

  it('should return null for unknown fields', () => {
    expect(mapLegacyAnnotation('unknown_field', 'val')).toBeNull()
  })
})

describe('parseSpanAnnotations', () => {
  it('should return empty array for null result', () => {
    expect(parseSpanAnnotations(null)).toEqual([])
  })

  it('should return empty array for result with no value', () => {
    expect(parseSpanAnnotations({ value: null, from_name: 'l', to_name: 't', type: 'labels' })).toEqual([])
  })

  it('should parse new format with spans array', () => {
    const result = parseSpanAnnotations({
      value: {
        spans: [
          { id: 's1', start: 0, end: 5, text: 'hello', labels: ['PERSON'] },
        ],
      },
      from_name: 'label',
      to_name: 'text',
      type: 'labels',
    })
    expect(result).toHaveLength(1)
    expect(result[0].id).toBe('s1')
    expect(result[0].labels).toEqual(['PERSON'])
  })

  it('should parse span with missing fields using defaults', () => {
    const result = parseSpanAnnotations({
      value: {
        spans: [{ /* no id, start, end, text, labels */ }],
      },
      from_name: 'label',
      to_name: 'text',
      type: 'labels',
    })
    expect(result).toHaveLength(1)
    expect(result[0].start).toBe(0)
    expect(result[0].end).toBe(0)
    expect(result[0].text).toBe('')
    expect(result[0].labels).toEqual([])
    expect(result[0].id).toMatch(/^span-/)
  })

  it('should parse legacy format with single span', () => {
    const result = parseSpanAnnotations({
      id: 'legacy-1',
      value: { start: 10, end: 20, text: 'John', labels: ['NAME'] },
      from_name: 'label',
      to_name: 'text',
      type: 'labels',
    })
    expect(result).toHaveLength(1)
    expect(result[0].id).toBe('legacy-1')
    expect(result[0].start).toBe(10)
    expect(result[0].end).toBe(20)
  })

  it('should parse legacy format without id using generated id', () => {
    const result = parseSpanAnnotations({
      value: { start: 0, end: 5, text: 'hi' },
      from_name: 'l',
      to_name: 't',
      type: 'labels',
    })
    expect(result).toHaveLength(1)
    expect(result[0].id).toMatch(/^span-/)
    expect(result[0].labels).toEqual([])
  })

  it('should return empty array for value without spans or start', () => {
    const result = parseSpanAnnotations({
      value: { something: 'else' },
      from_name: 'l',
      to_name: 't',
      type: 'labels',
    })
    expect(result).toEqual([])
  })
})

describe('convertToLabelStudioFormat', () => {
  it('should flatten span annotations into separate results', () => {
    const input = [
      {
        from_name: 'label',
        to_name: 'text',
        type: 'labels',
        value: {
          spans: [
            { id: 's1', start: 0, end: 5, text: 'hello', labels: ['A'] },
            { id: 's2', start: 10, end: 15, text: 'world', labels: ['B'] },
          ],
        },
      },
    ]

    const result = convertToLabelStudioFormat(input)
    expect(result).toHaveLength(2)
    expect(result[0].id).toBe('s1')
    expect(result[0].value.start).toBe(0)
    expect(result[1].id).toBe('s2')
    expect(result[1].value.start).toBe(10)
  })

  it('should pass through non-span annotations unchanged', () => {
    const input = [
      {
        from_name: 'answer',
        to_name: 'question',
        type: 'textarea',
        value: { text: ['answer'] },
      },
    ]

    const result = convertToLabelStudioFormat(input)
    expect(result).toEqual(input)
  })

  it('should pass through labels without spans (no spans array)', () => {
    const input = [
      {
        from_name: 'label',
        to_name: 'text',
        type: 'labels',
        value: { choices: ['A'] },
      },
    ]

    const result = convertToLabelStudioFormat(input)
    expect(result).toEqual(input)
  })
})

describe('convertFromLabelStudioFormat', () => {
  it('should consolidate Label Studio span annotations by from_name:to_name', () => {
    const input = [
      { from_name: 'label', to_name: 'text', type: 'labels', value: { start: 0, end: 5, text: 'hello', labels: ['A'] }, id: 's1' },
      { from_name: 'label', to_name: 'text', type: 'labels', value: { start: 10, end: 15, text: 'world', labels: ['B'] }, id: 's2' },
    ]

    const result = convertFromLabelStudioFormat(input)
    expect(result).toHaveLength(1)
    expect(result[0].type).toBe('labels')
    expect(result[0].value.spans).toHaveLength(2)
  })

  it('should pass through annotations already in BenGER format', () => {
    const input = [
      {
        from_name: 'label',
        to_name: 'text',
        type: 'labels',
        value: { spans: [{ id: 's1', start: 0, end: 5, text: 'hi', labels: ['A'] }] },
      },
    ]

    const result = convertFromLabelStudioFormat(input)
    expect(result).toHaveLength(1)
    expect(result[0].value.spans).toHaveLength(1)
  })

  it('should pass through non-labels annotations', () => {
    const input = [
      { from_name: 'answer', to_name: 'q', type: 'textarea', value: { text: ['ans'] } },
    ]

    const result = convertFromLabelStudioFormat(input)
    expect(result).toEqual(input)
  })

  it('should generate span ids when not provided', () => {
    const input = [
      { from_name: 'l', to_name: 't', type: 'labels', value: { start: 0, end: 5 } },
    ]

    const result = convertFromLabelStudioFormat(input)
    expect(result[0].value.spans[0].id).toMatch(/^span-/)
  })
})

describe('validateTaskDataFields', () => {
  it('should validate fields present at root level', () => {
    const result = validateTaskDataFields(['text', 'question'], { text: 'hi', question: 'why?' })
    expect(result.valid).toBe(true)
    expect(result.missingFields).toEqual([])
  })

  it('should validate fields present inside data property', () => {
    const result = validateTaskDataFields(['text'], { data: { text: 'nested' } })
    expect(result.valid).toBe(true)
  })

  it('should report missing fields', () => {
    const result = validateTaskDataFields(['text', 'missing'], { text: 'hi' })
    expect(result.valid).toBe(false)
    expect(result.missingFields).toEqual(['missing'])
  })

  it('should treat null values as missing', () => {
    const result = validateTaskDataFields(['field'], { field: null })
    expect(result.valid).toBe(false)
  })

  it('should handle non-object data property', () => {
    const result = validateTaskDataFields(['field'], { data: 'not-object' })
    expect(result.valid).toBe(false)
  })
})

describe('resolveDataBinding', () => {
  it('should return non-string values unchanged', () => {
    expect(resolveDataBinding(42, {})).toBe(42)
    expect(resolveDataBinding(null, {})).toBeNull()
    expect(resolveDataBinding(true, {})).toBe(true)
  })

  it('should return strings not starting with $ unchanged', () => {
    expect(resolveDataBinding('plain text', {})).toBe('plain text')
  })

  it('should resolve $field from root', () => {
    expect(resolveDataBinding('$text', { text: 'hello' })).toBe('hello')
  })

  it('should resolve $field from data property when not at root', () => {
    expect(resolveDataBinding('$text', { data: { text: 'nested' } })).toBe('nested')
  })

  it('should resolve nested dot paths', () => {
    expect(resolveDataBinding('$a.b.c', { a: { b: { c: 'deep' } } })).toBe('deep')
  })

  it('should return undefined for non-existent paths', () => {
    expect(resolveDataBinding('$nonexistent', {})).toBeUndefined()
  })
})

describe('resolvePropsDataBindings', () => {
  it('should resolve all data bindings in props', () => {
    const result = resolvePropsDataBindings(
      { value: '$text', name: 'myName', static: 'literal' },
      { text: 'resolved' }
    )
    expect(result.value).toBe('resolved')
    expect(result.name).toBe('myName')
    expect(result.static).toBe('literal')
  })
})

describe('buildSpanAnnotationResult', () => {
  it('should build span annotation result with spans array', () => {
    const result = buildSpanAnnotationResult('label', 'text', [
      { id: 's1', start: 0, end: 5, text: 'hello', labels: ['A'] },
    ])
    expect(result.type).toBe('labels')
    expect(result.from_name).toBe('label')
    expect(result.to_name).toBe('text')
    expect(result.value.spans).toHaveLength(1)
  })
})

/**
 * Branch coverage tests for dataColumnHelpers.ts
 *
 * Targets: detectValueType all branches, extractDataColumns with complex arrays,
 * formatCellValue all type branches, getTaskDisplayValue fallback paths,
 * hasConsistentDataStructure, extractMetadataColumns, hasConsistentMetadataStructure.
 */

import {
  detectValueType,
  extractDataColumns,
  formatFieldLabel,
  formatCellValue,
  getTaskDisplayValue,
  hasConsistentDataStructure,
  extractMetadataColumns,
  hasConsistentMetadataStructure,
} from '../dataColumnHelpers'

describe('detectValueType', () => {
  it('should return text for null', () => expect(detectValueType(null)).toBe('text'))
  it('should return text for undefined', () => expect(detectValueType(undefined)).toBe('text'))
  it('should return boolean for true', () => expect(detectValueType(true)).toBe('boolean'))
  it('should return boolean for false', () => expect(detectValueType(false)).toBe('boolean'))
  it('should return number for 42', () => expect(detectValueType(42)).toBe('number'))
  it('should return number for 0', () => expect(detectValueType(0)).toBe('number'))
  it('should return date for ISO string', () => expect(detectValueType('2024-01-15T00:00:00Z')).toBe('date'))
  it('should return text for regular string', () => expect(detectValueType('hello')).toBe('text'))
  it('should return array for arrays', () => expect(detectValueType([1, 2])).toBe('array'))
  it('should return object for objects', () => expect(detectValueType({ a: 1 })).toBe('object'))
})

describe('extractDataColumns', () => {
  it('should return empty for no tasks', () => {
    expect(extractDataColumns([])).toEqual([])
  })

  it('should extract columns from task data', () => {
    const tasks = [{ id: '1', data: { question: 'why?', answer: 'because' } }] as any
    const cols = extractDataColumns(tasks)
    expect(cols.length).toBeGreaterThan(0)
    expect(cols.some((c: any) => c.key === 'question')).toBe(true)
  })

  it('should skip complex nested objects', () => {
    const tasks = [{ id: '1', data: { nested: { deep: 'value' } } }] as any
    const cols = extractDataColumns(tasks)
    expect(cols.some((c: any) => c.key === 'nested')).toBe(false)
  })

  it('should include simple arrays', () => {
    const tasks = [{ id: '1', data: { tags: ['a', 'b'] } }] as any
    const cols = extractDataColumns(tasks)
    expect(cols.some((c: any) => c.key === 'tags')).toBe(true)
  })

  it('should skip complex arrays of objects', () => {
    const tasks = [{ id: '1', data: { items: [{ a: 1 }] } }] as any
    const cols = extractDataColumns(tasks)
    expect(cols.some((c: any) => c.key === 'items')).toBe(false)
  })

  it('should skip tasks without data', () => {
    const tasks = [{ id: '1' }] as any
    const cols = extractDataColumns(tasks)
    expect(cols).toEqual([])
  })

  it('should prioritize known fields', () => {
    const tasks = [{ id: '1', data: { question: 'q', zzz_field: 'z' } }] as any
    const cols = extractDataColumns(tasks)
    expect(cols[0].key).toBe('question')
  })

  it('should respect maxColumns limit', () => {
    const data: Record<string, string> = {}
    for (let i = 0; i < 20; i++) data[`field${i}`] = 'value'
    const tasks = [{ id: '1', data }] as any
    const cols = extractDataColumns(tasks, 5)
    expect(cols.length).toBe(5)
  })
})

describe('formatFieldLabel', () => {
  it('should convert snake_case', () => {
    expect(formatFieldLabel('my_field')).toBe('My Field')
  })
  it('should convert camelCase', () => {
    expect(formatFieldLabel('myField')).toBe('My Field')
  })
})

describe('formatCellValue', () => {
  it('should return dash for null', () => {
    expect(formatCellValue(null, 'text')).toEqual({ display: '-', full: '-', truncated: false })
  })

  it('should format boolean true', () => {
    const r = formatCellValue(true, 'boolean')
    expect(r.display).toContain('✓')
    expect(r.full).toBe('true')
  })

  it('should format boolean false', () => {
    const r = formatCellValue(false, 'boolean')
    expect(r.display).toContain('✗')
  })

  it('should format number', () => {
    const r = formatCellValue(1234, 'number')
    expect(r.display).toContain('1')
  })

  it('should format string number', () => {
    const r = formatCellValue('42', 'number')
    expect(r.display).toBe('42')
  })

  it('should format date', () => {
    const r = formatCellValue('2024-01-15', 'date')
    expect(r.truncated).toBe(false)
  })

  it('should handle invalid date by producing some output', () => {
    const r = formatCellValue('not-a-date', 'date')
    // new Date('not-a-date') produces "Invalid Date" which triggers catch
    // The catch branch calls formatCellValue recursively with 'text' type
    expect(r.display).toBeTruthy()
  })

  it('should format array', () => {
    const r = formatCellValue(['a', 'b', 'c'], 'array')
    expect(r.display).toBe('a, b, c')
  })

  it('should truncate long array', () => {
    const longArr = Array.from({ length: 100 }, (_, i) => `item${i}`)
    const r = formatCellValue(longArr, 'array', 20)
    expect(r.truncated).toBe(true)
  })

  it('should format non-array as string for array type', () => {
    const r = formatCellValue('not-array', 'array')
    expect(r.display).toBe('not-array')
  })

  it('should truncate long text', () => {
    const r = formatCellValue('a'.repeat(100), 'text', 50)
    expect(r.truncated).toBe(true)
    expect(r.display.endsWith('...')).toBe(true)
  })

  it('should not truncate short text', () => {
    const r = formatCellValue('short', 'text')
    expect(r.truncated).toBe(false)
  })
})

describe('getTaskDisplayValue', () => {
  it('should return Task id when no data', () => {
    expect(getTaskDisplayValue({ id: '5' } as any)).toBe('Task 5')
  })

  it('should return priority field value', () => {
    expect(getTaskDisplayValue({ id: '1', data: { question: 'Why?' } } as any)).toBe('Why?')
  })

  it('should fall back to first string value', () => {
    expect(getTaskDisplayValue({ id: '1', data: { custom: 'hello' } } as any)).toBe('hello')
  })

  it('should skip non-string priority fields', () => {
    expect(getTaskDisplayValue({ id: '1', data: { question: 42, custom: 'fallback' } } as any)).toBe('fallback')
  })

  it('should return Task id when data has no strings', () => {
    expect(getTaskDisplayValue({ id: '1', data: { num: 42 } } as any)).toBe('Task 1')
  })
})

describe('hasConsistentDataStructure', () => {
  it('should return true for single task', () => {
    expect(hasConsistentDataStructure([{ id: '1', data: { a: 1 } }] as any)).toBe(true)
  })

  it('should return true for consistent tasks', () => {
    const tasks = [
      { id: '1', data: { a: 1, b: 2 } },
      { id: '2', data: { a: 3, b: 4 } },
    ] as any
    expect(hasConsistentDataStructure(tasks)).toBe(true)
  })

  it('should return false for inconsistent tasks', () => {
    const tasks = [
      { id: '1', data: { a: 1, b: 2, c: 3, d: 4, e: 5 } },
      { id: '2', data: { x: 1 } },
    ] as any
    expect(hasConsistentDataStructure(tasks)).toBe(false)
  })
})

describe('extractMetadataColumns', () => {
  it('should return empty for no tasks', () => {
    expect(extractMetadataColumns([])).toEqual([])
  })

  it('should extract metadata columns', () => {
    const tasks = [{ id: '1', meta: { tags: ['a'], status: 'done' } }] as any
    const cols = extractMetadataColumns(tasks)
    expect(cols.some((c: any) => c.key === 'status')).toBe(true)
  })

  it('should skip complex objects in metadata', () => {
    const tasks = [{ id: '1', meta: { nested: { deep: 'val' } } }] as any
    const cols = extractMetadataColumns(tasks)
    expect(cols.some((c: any) => c.key === 'nested')).toBe(false)
  })

  it('should skip tasks without meta', () => {
    const tasks = [{ id: '1' }] as any
    expect(extractMetadataColumns(tasks)).toEqual([])
  })
})

describe('hasConsistentMetadataStructure', () => {
  it('should return true for single task', () => {
    expect(hasConsistentMetadataStructure([{ id: '1', meta: { a: 1 } }] as any)).toBe(true)
  })

  it('should return true when fewer than 2 tasks have meta', () => {
    const tasks = [
      { id: '1', meta: { a: 1 } },
      { id: '2' }, // no meta
    ] as any
    expect(hasConsistentMetadataStructure(tasks)).toBe(true)
  })

  it('should return true for consistent metadata', () => {
    const tasks = [
      { id: '1', meta: { a: 1, b: 2 } },
      { id: '2', meta: { a: 3, b: 4 } },
    ] as any
    expect(hasConsistentMetadataStructure(tasks)).toBe(true)
  })

  it('should return false for inconsistent metadata', () => {
    const tasks = [
      { id: '1', meta: { a: 1, b: 2, c: 3, d: 4, e: 5 } },
      { id: '2', meta: { x: 1 } },
    ] as any
    expect(hasConsistentMetadataStructure(tasks)).toBe(false)
  })
})

/**
 * @jest-environment jsdom
 *
 * Branch coverage: nestedDataColumnHelpers.ts
 * Targets: detectValueType boolean/date/array/object, extractNestedDataColumns includeNested=false,
 *          formatNestedCellValue boolean/number/date/array/object, getTaskDisplayValueNested,
 *          hasConsistentNestedStructure, saveColumnConfig/loadColumnConfig
 */

import {
  extractNestedDataColumns,
  formatNestedCellValue,
  getTaskDisplayValueNested,
  hasConsistentNestedStructure,
  loadColumnConfig,
  saveColumnConfig,
} from '../nestedDataColumnHelpers'

describe('nestedDataColumnHelpers branch coverage', () => {
  it('extractNestedDataColumns with includeNested=false skips objects', () => {
    const tasks = [
      { id: '1', data: { text: 'hello', nested: { deep: 1 } } },
    ] as any[]
    const cols = extractNestedDataColumns(tasks, 20, false)
    expect(cols.some((c) => c.key === 'text')).toBe(true)
  })

  it('extractNestedDataColumns with missing data', () => {
    const tasks = [{ id: '1' }] as any[]
    const cols = extractNestedDataColumns(tasks, 20, true)
    expect(cols).toEqual([])
  })

  it('formatNestedCellValue boolean true', () => {
    const result = formatNestedCellValue(true, 'boolean')
    expect(result.full).toBe('true')
  })

  it('formatNestedCellValue boolean false', () => {
    const result = formatNestedCellValue(false, 'boolean')
    expect(result.full).toBe('false')
  })

  it('formatNestedCellValue number', () => {
    const result = formatNestedCellValue(42, 'number')
    expect(result.display).toContain('42')
  })

  it('formatNestedCellValue date', () => {
    const result = formatNestedCellValue('2024-01-15', 'date')
    expect(result.truncated).toBe(false)
  })

  it('formatNestedCellValue array with truncation', () => {
    const longArray = Array.from({ length: 50 }, (_, i) => `item${i}`)
    const result = formatNestedCellValue(longArray, 'array', 10)
    expect(result.truncated).toBe(true)
  })

  it('formatNestedCellValue array short', () => {
    const result = formatNestedCellValue(['a', 'b'], 'array')
    expect(result.display).toBe('a, b')
    expect(result.truncated).toBe(false)
  })

  it('formatNestedCellValue object', () => {
    const result = formatNestedCellValue({ a: 1 }, 'object')
    expect(result.full).toContain('"a"')
  })

  it('formatNestedCellValue null', () => {
    const result = formatNestedCellValue(null, 'text')
    expect(result.display).toBe('-')
  })

  it('formatNestedCellValue text truncated', () => {
    const long = 'a'.repeat(200)
    const result = formatNestedCellValue(long, 'text', 100)
    expect(result.truncated).toBe(true)
  })

  it('getTaskDisplayValueNested with no data', () => {
    const result = getTaskDisplayValueNested({ id: '1' } as any)
    expect(result).toBe('Task 1')
  })

  it('getTaskDisplayValueNested with priority field', () => {
    const result = getTaskDisplayValueNested({
      id: '1',
      data: { question: 'What is law?' },
    } as any)
    expect(result).toBe('What is law?')
  })

  it('getTaskDisplayValueNested fallback to first string', () => {
    const result = getTaskDisplayValueNested({
      id: '1',
      data: { count: 5, custom_field: 'some text' },
    } as any)
    expect(result).toBe('some text')
  })

  it('getTaskDisplayValueNested with no strings returns Task id', () => {
    const result = getTaskDisplayValueNested({
      id: '1',
      data: { count: 5, flag: true },
    } as any)
    expect(result).toBe('Task 1')
  })

  it('getTaskDisplayValueNested truncates long values', () => {
    const result = getTaskDisplayValueNested({
      id: '1',
      data: { question: 'x'.repeat(200) },
    } as any)
    expect(result.length).toBeLessThan(200)
    expect(result).toContain('...')
  })

  it('hasConsistentNestedStructure with single task', () => {
    expect(hasConsistentNestedStructure([{ id: '1' }] as any[])).toBe(true)
  })

  it('hasConsistentNestedStructure with matching tasks', () => {
    const tasks = [
      { id: '1', data: { a: 1, b: 2 } },
      { id: '2', data: { a: 3, b: 4 } },
    ] as any[]
    expect(hasConsistentNestedStructure(tasks)).toBe(true)
  })

  it('hasConsistentNestedStructure with mismatching tasks', () => {
    const tasks = [
      { id: '1', data: { a: 1, b: 2, c: 3 } },
      { id: '2', data: { x: 1, y: 2, z: 3 } },
    ] as any[]
    expect(hasConsistentNestedStructure(tasks)).toBe(false)
  })

  it('hasConsistentNestedStructure with tasks missing data', () => {
    const tasks = [
      { id: '1', data: { a: 1 } },
      { id: '2' },
    ] as any[]
    const result = hasConsistentNestedStructure(tasks)
    expect(typeof result).toBe('boolean')
  })

  it('saveColumnConfig and loadColumnConfig roundtrip', () => {
    saveColumnConfig('proj1', ['col1', 'col2'])
    expect(loadColumnConfig('proj1')).toEqual(['col1', 'col2'])
  })

  it('loadColumnConfig returns null for unknown project', () => {
    saveColumnConfig('proj1', ['col1'])
    expect(loadColumnConfig('proj2')).toBeNull()
  })

  it('loadColumnConfig returns null when nothing stored', () => {
    localStorage.removeItem('benger_task_columns_config')
    expect(loadColumnConfig('proj1')).toBeNull()
  })
})

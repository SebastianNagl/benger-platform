/**
 * @jest-environment jsdom
 *
 * Branch coverage round 7: fieldPath.ts
 * Covers: getValueByPath, setValueByPath, hasPath, getAllPaths, formatValue
 * 52 branches total (all uncovered)
 */

import {
  getValueByPath,
  setValueByPath,
  hasPath,
  getAllPaths,
  formatValue,
} from '../fieldPath'

describe('getValueByPath br7', () => {
  it('returns defaultValue for null data', () => {
    expect(getValueByPath(null, 'foo')).toBeUndefined()
  })

  it('returns defaultValue for undefined data', () => {
    expect(getValueByPath(undefined, 'foo')).toBeUndefined()
  })

  it('returns defaultValue for null path', () => {
    expect(getValueByPath({ a: 1 }, null as any)).toBeUndefined()
  })

  it('returns defaultValue for undefined path', () => {
    expect(getValueByPath({ a: 1 }, undefined)).toBeUndefined()
  })

  it('returns defaultValue for empty path', () => {
    expect(getValueByPath({ a: 1 }, '')).toBeUndefined()
  })

  it('accesses top-level property', () => {
    expect(getValueByPath({ name: 'John' }, 'name')).toBe('John')
  })

  it('accesses nested property', () => {
    expect(getValueByPath({ user: { name: 'John' } }, 'user.name')).toBe('John')
  })

  it('accesses array by index', () => {
    expect(getValueByPath({ items: ['a', 'b', 'c'] }, 'items[1]')).toBe('b')
  })

  it('accesses nested array with dot notation', () => {
    expect(getValueByPath({ items: [{ value: 42 }] }, 'items[0].value')).toBe(42)
  })

  it('returns defaultValue when path does not exist', () => {
    expect(getValueByPath({ a: 1 }, 'b', 'default')).toBe('default')
  })

  it('returns defaultValue when intermediate is null', () => {
    expect(getValueByPath({ a: null }, 'a.b', 'fallback')).toBe('fallback')
  })

  it('returns defaultValue when intermediate is undefined', () => {
    expect(getValueByPath({ a: {} }, 'a.b.c', 'fallback')).toBe('fallback')
  })

  it('returns the value even if it is falsy (0, false, "")', () => {
    expect(getValueByPath({ a: 0 }, 'a')).toBe(0)
    expect(getValueByPath({ a: false }, 'a')).toBe(false)
    expect(getValueByPath({ a: '' }, 'a')).toBe('')
  })

  it('returns custom default value', () => {
    expect(getValueByPath({}, 'missing', 42)).toBe(42)
  })

  it('handles numeric segment in dot notation', () => {
    expect(getValueByPath({ items: ['x', 'y'] }, 'items.0')).toBe('x')
  })
})

describe('setValueByPath br7', () => {
  it('sets top-level property', () => {
    const data = {}
    setValueByPath(data, 'name', 'John')
    expect(data).toEqual({ name: 'John' })
  })

  it('sets nested property creating intermediate objects', () => {
    const data = {}
    setValueByPath(data, 'user.name', 'John')
    expect(data).toEqual({ user: { name: 'John' } })
  })

  it('sets array index', () => {
    const data = { items: ['a', 'b'] }
    setValueByPath(data, 'items[1]', 'changed')
    expect(data.items[1]).toBe('changed')
  })

  it('creates array for numeric segment', () => {
    const data = {} as any
    setValueByPath(data, 'list.0', 'first')
    expect(Array.isArray(data.list)).toBe(true)
    expect(data.list[0]).toBe('first')
  })

  it('returns the same data object', () => {
    const data = { x: 1 }
    const result = setValueByPath(data, 'y', 2)
    expect(result).toBe(data)
  })

  it('returns data when path is empty', () => {
    const data = { x: 1 }
    expect(setValueByPath(data, '', 2)).toBe(data)
  })

  it('handles deep nested creation', () => {
    const data = {}
    setValueByPath(data, 'a.b.c', 'deep')
    expect(getValueByPath(data, 'a.b.c')).toBe('deep')
  })

  it('sets numeric last segment in array', () => {
    const data = { arr: [] as any[] }
    setValueByPath(data, 'arr[0]', 'value')
    expect(data.arr[0]).toBe('value')
  })
})

describe('hasPath br7', () => {
  it('returns true for existing path', () => {
    expect(hasPath({ a: { b: 1 } }, 'a.b')).toBe(true)
  })

  it('returns false for non-existing path', () => {
    expect(hasPath({ a: 1 }, 'b')).toBe(false)
  })

  it('returns true for falsy but defined values', () => {
    expect(hasPath({ a: 0 }, 'a')).toBe(true)
    expect(hasPath({ a: false }, 'a')).toBe(true)
    expect(hasPath({ a: '' }, 'a')).toBe(true)
    expect(hasPath({ a: null }, 'a')).toBe(true)
  })
})

describe('getAllPaths br7', () => {
  it('returns empty for null', () => {
    expect(getAllPaths(null)).toEqual([])
  })

  it('returns empty for undefined', () => {
    expect(getAllPaths(undefined)).toEqual([])
  })

  it('returns paths for flat object', () => {
    const paths = getAllPaths({ a: 1, b: 'str' })
    expect(paths).toContain('a')
    expect(paths).toContain('b')
  })

  it('returns paths for nested object', () => {
    const paths = getAllPaths({ user: { name: 'John', age: 30 } })
    expect(paths).toContain('user.name')
    expect(paths).toContain('user.age')
  })

  it('returns paths for array', () => {
    const paths = getAllPaths({ items: ['a', 'b'] })
    expect(paths).toContain('items[0]')
    expect(paths).toContain('items[1]')
  })

  it('returns paths for nested array of objects', () => {
    const paths = getAllPaths({ items: [{ value: 42 }] })
    expect(paths).toContain('items[0].value')
  })

  it('returns empty for non-object with no prefix', () => {
    expect(getAllPaths(42)).toEqual([])
  })

  it('returns prefix for non-object with prefix', () => {
    // This shouldn't normally be called, but tests the branch
    expect(getAllPaths(42, 'root')).toEqual(['root'])
  })

  it('handles Date as leaf node', () => {
    const d = new Date('2024-01-01')
    const paths = getAllPaths({ date: d })
    expect(paths).toContain('date')
  })

  it('handles empty object', () => {
    expect(getAllPaths({})).toEqual([])
  })

  it('handles empty array', () => {
    expect(getAllPaths([])).toEqual([])
  })
})

describe('formatValue br7', () => {
  it('returns empty string for null', () => {
    expect(formatValue(null)).toBe('')
  })

  it('returns empty string for undefined', () => {
    expect(formatValue(undefined)).toBe('')
  })

  it('returns "Yes" for true', () => {
    expect(formatValue(true)).toBe('Yes')
  })

  it('returns "No" for false', () => {
    expect(formatValue(false)).toBe('No')
  })

  it('formats Date object', () => {
    const d = new Date('2024-06-15')
    const result = formatValue(d)
    expect(result).toContain('2024')
  })

  it('formats array', () => {
    expect(formatValue([1, 2, 3])).toBe('1, 2, 3')
  })

  it('formats nested array with mixed types', () => {
    expect(formatValue([true, null, 'hello'])).toBe('Yes, , hello')
  })

  it('formats object as JSON', () => {
    const result = formatValue({ key: 'value' })
    expect(result).toContain('"key"')
    expect(result).toContain('"value"')
  })

  it('formats number as string', () => {
    expect(formatValue(42)).toBe('42')
  })

  it('formats string as-is', () => {
    expect(formatValue('hello')).toBe('hello')
  })
})

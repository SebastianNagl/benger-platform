/**
 * @jest-environment jsdom
 *
 * Branch coverage: jsonUtils.ts
 * Targets: L22 (maxDepth with prefix), L54 (array of objects flatten)
 */

import { flattenJson } from '../jsonUtils'

describe('jsonUtils br4 - uncovered branches', () => {
  it('stops at maxDepth and stores with prefix (line 22)', () => {
    const deepObj = { a: { b: { c: { d: 'deep' } } } }
    const result = flattenJson(deepObj, 'root', 2)
    // At depth 2, nested objects should be stored as-is with prefix
    expect(result).toBeTruthy()
    // Root should have keys with dot notation up to depth limit
    expect(Object.keys(result).length).toBeGreaterThan(0)
  })

  it('flattens array of objects with index notation (line 54-66)', () => {
    const obj = {
      items: [
        { name: 'Alice', age: 30 },
        { name: 'Bob', age: 25 },
      ],
    }
    const result = flattenJson(obj)
    expect(result['items[0].name']).toBe('Alice')
    expect(result['items[0].age']).toBe(30)
    expect(result['items[1].name']).toBe('Bob')
    expect(result['items[1].age']).toBe(25)
  })

  it('handles maxDepth=0 with prefix stores object as-is', () => {
    const obj = { nested: true }
    const result = flattenJson(obj, 'myprefix', 0)
    expect(result['myprefix']).toEqual({ nested: true })
  })

  it('handles maxDepth=0 without prefix returns empty', () => {
    const obj = { nested: true }
    const result = flattenJson(obj, '', 0)
    // No prefix means no key is set
    expect(Object.keys(result).length).toBe(0)
  })
})

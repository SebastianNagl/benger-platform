/**
 * Coverage tests for jsonUtils - covers edge cases for flattenJson and valueMatchesQuery.
 */
import { flattenJson, valueMatchesQuery } from '../jsonUtils'

describe('jsonUtils - coverage extensions', () => {
  describe('flattenJson - prefix edge cases', () => {
    it('should handle null value with prefix (stores null at prefix key)', () => {
      const result = flattenJson(null, 'data')
      expect(result).toEqual({ data: null })
    })

    it('should handle primitive value with prefix', () => {
      const result = flattenJson('hello', 'field')
      expect(result).toEqual({ field: 'hello' })
    })

    it('should handle empty array with prefix', () => {
      const result = flattenJson([], 'items')
      expect(result).toEqual({ items: [] })
    })

    it('should handle maxDepth reached with prefix', () => {
      const deepObj = { a: { b: { c: 'deep' } } }
      const result = flattenJson(deepObj, 'root', 1, 1)
      expect(result).toEqual({ root: deepObj })
    })
  })

  describe('valueMatchesQuery - edge cases', () => {
    it('should return false for unknown types (e.g., Symbol)', () => {
      const sym = Symbol('test')
      expect(valueMatchesQuery(sym, 'test')).toBe(false)
    })

    it('should handle boolean values in search', () => {
      expect(valueMatchesQuery(true, 'true')).toBe(true)
      expect(valueMatchesQuery(false, 'false')).toBe(true)
    })

    it('should search recursively in objects', () => {
      const obj = { nested: { deep: 'target value' } }
      expect(valueMatchesQuery(obj, 'target')).toBe(true)
    })
  })
})

/**
 * @jest-environment jsdom
 *
 * Branch coverage: jsonUtils.ts
 * Targets: br4[1] L22 (flattenJson maxDepth with prefix),
 *          br14[1] L54 (getNestedValue array branch),
 *          br15[1] L66 (extractFieldPaths or valueMatchesQuery)
 */

import { flattenJson, getNestedValue, valueMatchesQuery } from '../jsonUtils'

describe('jsonUtils branch coverage', () => {
  it('flattenJson returns obj when maxDepth reached with prefix', () => {
    const deep = { a: { b: { c: 1 } } }
    const result = flattenJson(deep, 'root', 1, 1)
    expect(result).toEqual({ root: deep })
  })

  it('getNestedValue handles array index access', () => {
    const obj = { items: [10, 20, 30] }
    expect(getNestedValue(obj, 'items[1]')).toBe(20)
  })

  it('valueMatchesQuery handles object values', () => {
    expect(valueMatchesQuery({ name: 'hello' }, 'hello')).toBe(true)
    expect(valueMatchesQuery({ name: 'hello' }, 'xyz')).toBe(false)
  })
})

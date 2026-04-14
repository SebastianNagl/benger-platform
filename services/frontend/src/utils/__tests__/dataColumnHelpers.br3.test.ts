/**
 * @jest-environment jsdom
 *
 * Branch coverage: dataColumnHelpers.ts
 * Targets: br37[1] L219 (data || {}), br51[1] L303, br52[1] L309
 */

import { hasConsistentDataStructure, hasConsistentMetadataStructure } from '../dataColumnHelpers'

describe('dataColumnHelpers branch coverage', () => {
  it('hasConsistentDataStructure with tasks missing data property', () => {
    const tasks = [
      { id: '1', data: { text: 'a' } },
      { id: '2' }, // no data -> data || {} branch
    ] as any[]
    const result = hasConsistentDataStructure(tasks)
    expect(typeof result).toBe('boolean')
  })

  it('hasConsistentMetadataStructure with tasks missing meta', () => {
    const tasks = [
      { id: '1', meta: { tag: 'a' } },
      { id: '2', meta: { tag: 'b' } },
      { id: '3' }, // no meta
    ] as any[]
    const result = hasConsistentMetadataStructure(tasks)
    expect(typeof result).toBe('boolean')
  })

  it('hasConsistentMetadataStructure with meta having different keys', () => {
    const tasks = [
      { id: '1', meta: { a: 1, b: 2, c: 3 } },
      { id: '2', meta: { x: 1, y: 2, z: 3 } },
    ] as any[]
    const result = hasConsistentMetadataStructure(tasks)
    expect(result).toBe(false)
  })
})

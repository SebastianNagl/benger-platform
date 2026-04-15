/**
 * @jest-environment jsdom
 *
 * Branch coverage round 7: variantHash.ts
 * Covers: selectVariant - all branches (empty, single, totalWeight<=0,
 *         normal selection, last fallback)
 * 10 branches total (all uncovered)
 */

import { selectVariant } from '../variantHash'

describe('selectVariant br7', () => {
  it('returns null for empty variants array', () => {
    expect(selectVariant('user1', 'task1', [])).toBeNull()
  })

  it('returns null for null/undefined variants', () => {
    expect(selectVariant('user1', 'task1', null as any)).toBeNull()
    expect(selectVariant('user1', 'task1', undefined as any)).toBeNull()
  })

  it('returns single variant id for one-element array', () => {
    const variants = [{ id: 'only', weight: 50 }]
    expect(selectVariant('user1', 'task1', variants)).toBe('only')
  })

  it('returns first variant id when totalWeight is 0', () => {
    const variants = [
      { id: 'a', weight: 0 },
      { id: 'b', weight: 0 },
    ]
    expect(selectVariant('user1', 'task1', variants)).toBe('a')
  })

  it('returns first variant id when totalWeight is negative', () => {
    const variants = [
      { id: 'a', weight: -5 },
      { id: 'b', weight: -3 },
    ]
    expect(selectVariant('user1', 'task1', variants)).toBe('a')
  })

  it('deterministically selects variant based on userId + taskId', () => {
    const variants = [
      { id: 'control', weight: 50 },
      { id: 'treatment', weight: 50 },
    ]
    const result1 = selectVariant('user1', 'task1', variants)
    const result2 = selectVariant('user1', 'task1', variants)
    expect(result1).toBe(result2) // Same input always gives same output
    expect(['control', 'treatment']).toContain(result1)
  })

  it('different inputs may produce different results', () => {
    const variants = [
      { id: 'a', weight: 50 },
      { id: 'b', weight: 50 },
    ]
    // With enough different inputs, we should get both variants
    const results = new Set<string>()
    for (let i = 0; i < 100; i++) {
      const result = selectVariant(`user${i}`, 'task1', variants)
      if (result) results.add(result)
    }
    expect(results.size).toBe(2)
  })

  it('respects weights - heavily weighted variant selected more often', () => {
    const variants = [
      { id: 'heavy', weight: 99 },
      { id: 'light', weight: 1 },
    ]
    let heavyCount = 0
    for (let i = 0; i < 100; i++) {
      if (selectVariant(`user${i}`, `task${i}`, variants) === 'heavy') {
        heavyCount++
      }
    }
    expect(heavyCount).toBeGreaterThan(80) // Should be overwhelmingly heavy
  })

  it('handles three variants with equal weights', () => {
    const variants = [
      { id: 'a', weight: 33 },
      { id: 'b', weight: 33 },
      { id: 'c', weight: 34 },
    ]
    const results = new Set<string>()
    for (let i = 0; i < 200; i++) {
      const result = selectVariant(`u${i}`, `t${i}`, variants)
      if (result) results.add(result)
    }
    expect(results.size).toBe(3)
  })
})

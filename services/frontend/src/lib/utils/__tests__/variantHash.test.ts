/**
 * Tests for deterministic variant selection (conditional instructions).
 */

import { selectVariant } from '../variantHash'

describe('selectVariant', () => {
  it('returns null for empty variants array', () => {
    expect(selectVariant('user1', 'task1', [])).toBeNull()
  })

  it('returns null for undefined/null variants', () => {
    expect(selectVariant('user1', 'task1', undefined as any)).toBeNull()
    expect(selectVariant('user1', 'task1', null as any)).toBeNull()
  })

  it('returns the single variant id for 1-element array', () => {
    const variants = [{ id: 'only', weight: 50 }]
    expect(selectVariant('user1', 'task1', variants)).toBe('only')
  })

  it('is deterministic: same inputs produce same output', () => {
    const variants = [
      { id: 'a', weight: 50 },
      { id: 'b', weight: 50 },
    ]
    const result1 = selectVariant('user-123', 'task-456', variants)
    const result2 = selectVariant('user-123', 'task-456', variants)
    const result3 = selectVariant('user-123', 'task-456', variants)
    expect(result1).toBe(result2)
    expect(result2).toBe(result3)
  })

  it('returns different results for different userId+taskId combinations', () => {
    const variants = [
      { id: 'a', weight: 50 },
      { id: 'b', weight: 50 },
    ]
    // With enough different inputs, we should see both variants
    const results = new Set<string>()
    for (let i = 0; i < 100; i++) {
      const result = selectVariant(`user-${i}`, 'task-1', variants)
      if (result) results.add(result)
    }
    expect(results.size).toBe(2)
  })

  it('handles 0 total weight by returning first variant', () => {
    const variants = [
      { id: 'a', weight: 0 },
      { id: 'b', weight: 0 },
    ]
    expect(selectVariant('user1', 'task1', variants)).toBe('a')
  })

  it('produces roughly 50/50 distribution for equal weights', () => {
    const variants = [
      { id: 'a', weight: 50 },
      { id: 'b', weight: 50 },
    ]
    const counts: Record<string, number> = { a: 0, b: 0 }
    const N = 1000
    for (let i = 0; i < N; i++) {
      const result = selectVariant(`user-${i}`, `task-${i % 50}`, variants)
      if (result) counts[result]++
    }
    // With 1000 samples, each should be roughly 500 (+/- 15%)
    expect(counts.a).toBeGreaterThan(N * 0.35)
    expect(counts.a).toBeLessThan(N * 0.65)
    expect(counts.b).toBeGreaterThan(N * 0.35)
    expect(counts.b).toBeLessThan(N * 0.65)
  })

  it('produces roughly 70/30 distribution for 70/30 weights', () => {
    const variants = [
      { id: 'a', weight: 70 },
      { id: 'b', weight: 30 },
    ]
    const counts: Record<string, number> = { a: 0, b: 0 }
    const N = 1000
    for (let i = 0; i < N; i++) {
      const result = selectVariant(`user-${i}`, `task-${i % 50}`, variants)
      if (result) counts[result]++
    }
    // 'a' should be ~70% (+/- 15%)
    expect(counts.a).toBeGreaterThan(N * 0.55)
    expect(counts.a).toBeLessThan(N * 0.85)
    // 'b' should be ~30% (+/- 15%)
    expect(counts.b).toBeGreaterThan(N * 0.15)
    expect(counts.b).toBeLessThan(N * 0.45)
  })

  it('handles three variants with different weights', () => {
    const variants = [
      { id: 'a', weight: 60 },
      { id: 'b', weight: 30 },
      { id: 'c', weight: 10 },
    ]
    const counts: Record<string, number> = { a: 0, b: 0, c: 0 }
    const N = 1000
    for (let i = 0; i < N; i++) {
      const result = selectVariant(`u-${i}`, `t-${i % 100}`, variants)
      if (result) counts[result]++
    }
    // All three variants should be selected at least once
    expect(counts.a).toBeGreaterThan(0)
    expect(counts.b).toBeGreaterThan(0)
    expect(counts.c).toBeGreaterThan(0)
    // 'a' should be the most common
    expect(counts.a).toBeGreaterThan(counts.b)
    expect(counts.b).toBeGreaterThan(counts.c)
  })

  it('always returns a valid variant id', () => {
    const variants = [
      { id: 'x', weight: 1 },
      { id: 'y', weight: 1 },
    ]
    for (let i = 0; i < 100; i++) {
      const result = selectVariant(`u${i}`, `t${i}`, variants)
      expect(['x', 'y']).toContain(result)
    }
  })
})

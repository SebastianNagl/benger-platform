/**
 * Tests for BoxPlotChart utility function calculateBoxPlotStats
 */

import { calculateBoxPlotStats } from '../BoxPlotChart'

describe('calculateBoxPlotStats', () => {
  it('should return null for empty array', () => {
    expect(calculateBoxPlotStats([], 'empty')).toBeNull()
  })

  it('should calculate stats for a simple dataset', () => {
    const scores = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    const result = calculateBoxPlotStats(scores, 'test')

    expect(result).not.toBeNull()
    expect(result!.name).toBe('test')
    expect(result!.count).toBe(10)
    expect(result!.mean).toBeCloseTo(0.55, 1)
    expect(result!.q1).toBeDefined()
    expect(result!.median).toBeDefined()
    expect(result!.q3).toBeDefined()
    expect(result!.min).toBeDefined()
    expect(result!.max).toBeDefined()
  })

  it('should calculate correct quartiles', () => {
    const scores = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
    const result = calculateBoxPlotStats(scores, 'quartiles')!

    // q1 = sorted[floor(12*0.25)] = sorted[3] = 4
    expect(result.q1).toBe(4)
    // median = sorted[floor(12*0.5)] = sorted[6] = 7
    expect(result.median).toBe(7)
    // q3 = sorted[floor(12*0.75)] = sorted[9] = 10
    expect(result.q3).toBe(10)
  })

  it('should detect outliers', () => {
    // Create a dataset with clear outliers
    const scores = [0, 0, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 20, 20, 100]
    const result = calculateBoxPlotStats(scores, 'outliers')!

    expect(result.outliers).toBeDefined()
    expect(result.outliers!.length).toBeGreaterThan(0)
  })

  it('should handle single element', () => {
    const result = calculateBoxPlotStats([0.5], 'single')!

    expect(result.name).toBe('single')
    expect(result.count).toBe(1)
    expect(result.mean).toBe(0.5)
    expect(result.min).toBe(0.5)
    expect(result.max).toBe(0.5)
  })

  it('should handle identical values', () => {
    const scores = [0.5, 0.5, 0.5, 0.5]
    const result = calculateBoxPlotStats(scores, 'identical')!

    expect(result.q1).toBe(0.5)
    expect(result.median).toBe(0.5)
    expect(result.q3).toBe(0.5)
    expect(result.mean).toBe(0.5)
  })

  it('should sort input data correctly', () => {
    const scores = [0.9, 0.1, 0.5, 0.3, 0.7]
    const result = calculateBoxPlotStats(scores, 'unsorted')!

    // Min whisker should be <= q1
    expect(result.min).toBeLessThanOrEqual(result.q1)
    // q1 should be <= median
    expect(result.q1).toBeLessThanOrEqual(result.median)
    // median should be <= q3
    expect(result.median).toBeLessThanOrEqual(result.q3)
    // q3 should be <= max whisker
    expect(result.q3).toBeLessThanOrEqual(result.max)
  })
})

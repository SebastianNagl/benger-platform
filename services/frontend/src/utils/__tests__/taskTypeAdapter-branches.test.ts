/**
 * Branch coverage tests for taskTypeAdapter.ts
 *
 * Targets: isLabelStudioTask, isApiTask, ensureLabelStudioTask,
 * ensureApiTask, labelStudioTaskToApi conversion.
 */

import {
  apiTaskToLabelStudio,
  labelStudioTaskToApi,
  apiTasksToLabelStudio,
  labelStudioTasksToApi,
  isLabelStudioTask,
  isApiTask,
  ensureLabelStudioTask,
  ensureApiTask,
} from '../taskTypeAdapter'

describe('apiTaskToLabelStudio', () => {
  it('should convert API task to LabelStudio format', () => {
    const apiTask = { id: '1', annotation_count: 3, template_data: { q: 'why?' } } as any
    const result = apiTaskToLabelStudio(apiTask)
    expect(result.is_labeled).toBe(true)
    expect(result.total_annotations).toBe(3)
    expect(result.data).toEqual({ q: 'why?' })
  })

  it('should set is_labeled to false when annotation_count is 0', () => {
    const apiTask = { id: '1', annotation_count: 0, template_data: {} } as any
    const result = apiTaskToLabelStudio(apiTask)
    expect(result.is_labeled).toBe(false)
  })

  it('should handle missing annotation_count', () => {
    const apiTask = { id: '1', template_data: {} } as any
    const result = apiTaskToLabelStudio(apiTask)
    expect(result.is_labeled).toBe(false)
    expect(result.total_annotations).toBe(0)
  })

  it('should handle missing template_data', () => {
    const apiTask = { id: '1' } as any
    const result = apiTaskToLabelStudio(apiTask)
    expect(result.data).toEqual({})
  })
})

describe('labelStudioTaskToApi', () => {
  it('should convert LabelStudio task to API format', () => {
    const lsTask = {
      id: '1',
      data: { q: 'why?' },
      is_labeled: true,
      total_annotations: 2,
      cancelled_annotations: 0,
      total_generations: 0,
      meta: {},
    } as any
    const result = labelStudioTaskToApi(lsTask)
    expect(result.template_data).toEqual({ q: 'why?' })
    expect(result.annotation_count).toBe(2)
  })

  it('should handle missing total_annotations', () => {
    const lsTask = { id: '1', data: {} } as any
    const result = labelStudioTaskToApi(lsTask)
    expect(result.annotation_count).toBe(0)
  })
})

describe('batch conversions', () => {
  it('apiTasksToLabelStudio should convert array', () => {
    const tasks = [{ id: '1', annotation_count: 1, template_data: {} }] as any
    const result = apiTasksToLabelStudio(tasks)
    expect(result).toHaveLength(1)
    expect(result[0].is_labeled).toBe(true)
  })

  it('labelStudioTasksToApi should convert array', () => {
    const tasks = [{ id: '1', data: {}, is_labeled: true, total_annotations: 1 }] as any
    const result = labelStudioTasksToApi(tasks)
    expect(result).toHaveLength(1)
  })
})

describe('isLabelStudioTask', () => {
  it('should return true for LS task', () => {
    expect(isLabelStudioTask({ is_labeled: true, total_annotations: 1 })).toBe(true)
  })
  it('should return false for API task', () => {
    expect(isLabelStudioTask({ annotation_count: 1 })).toBe(false)
  })
})

describe('isApiTask', () => {
  it('should return true for API task', () => {
    expect(isApiTask({ annotation_count: 1 })).toBe(true)
  })
  it('should return false for LS task', () => {
    expect(isApiTask({ annotation_count: 1, is_labeled: true })).toBe(false)
  })
})

describe('ensureLabelStudioTask', () => {
  it('should return as-is if already LS task', () => {
    const lsTask = { id: '1', is_labeled: true, total_annotations: 1 } as any
    expect(ensureLabelStudioTask(lsTask)).toBe(lsTask)
  })
  it('should convert API task', () => {
    const apiTask = { id: '1', annotation_count: 1, template_data: {} } as any
    const result = ensureLabelStudioTask(apiTask)
    expect(result.is_labeled).toBe(true)
  })
})

describe('ensureApiTask', () => {
  it('should return as-is if already API task', () => {
    const apiTask = { id: '1', annotation_count: 1 } as any
    expect(ensureApiTask(apiTask)).toBe(apiTask)
  })
  it('should convert LS task', () => {
    const lsTask = { id: '1', is_labeled: true, total_annotations: 2, data: {} } as any
    const result = ensureApiTask(lsTask)
    expect(result.annotation_count).toBe(2)
  })
})

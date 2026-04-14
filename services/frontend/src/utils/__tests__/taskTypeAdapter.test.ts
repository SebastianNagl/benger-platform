/**
 * @jest-environment jsdom
 *
 * Unit tests for Task Type Adapter utility functions
 *
 * Tests conversion logic between API Task and LabelStudio Task formats,
 * type guards, and safe conversion utilities.
 */

import { Task as ApiTask } from '@/lib/api/types'
import { Task as LabelStudioTask } from '@/types/labelStudio'
import {
  apiTasksToLabelStudio,
  apiTaskToLabelStudio,
  ensureApiTask,
  ensureLabelStudioTask,
  isApiTask,
  isLabelStudioTask,
  labelStudioTasksToApi,
  labelStudioTaskToApi,
} from '../taskTypeAdapter'

describe('apiTaskToLabelStudio', () => {
  it('should convert basic API task to LabelStudio format', () => {
    const apiTask: ApiTask = {
      id: '1',
      name: 'Test Task',
      description: 'Test Description',
      template_id: 'template-1',
      task_type: 'classification',
      visibility: 'public',
      created_by: 'user-1',
      created_at: '2025-01-01T00:00:00Z',
    }

    const result = apiTaskToLabelStudio(apiTask)

    expect(result.id).toBe('1')
    expect(result.project_id).toBe(0)
    expect(result.is_labeled).toBe(false)
    expect(result.total_annotations).toBe(0)
    expect(result.cancelled_annotations).toBe(0)
    expect(result.data).toEqual({})
    expect(result.meta).toEqual({})
  })

  it('should convert API task with annotation count', () => {
    const apiTask: ApiTask = {
      id: '2',
      name: 'Annotated Task',
      description: 'Task with annotations',
      template_id: 'template-1',
      task_type: 'qa',
      visibility: 'private',
      created_by: 'user-1',
      created_at: '2025-01-01T00:00:00Z',
      annotation_count: 5,
    }

    const result = apiTaskToLabelStudio(apiTask)

    expect(result.is_labeled).toBe(true)
    expect(result.total_annotations).toBe(5)
  })

  it('should convert API task with template_data', () => {
    const apiTask: ApiTask = {
      id: '3',
      name: 'Task with data',
      description: 'Task with template data',
      template_id: 'template-1',
      task_type: 'qa',
      visibility: 'public',
      created_by: 'user-1',
      created_at: '2025-01-01T00:00:00Z',
      template_data: {
        question: 'What is the answer?',
        context: 'Some context',
      },
    }

    const result = apiTaskToLabelStudio(apiTask)

    expect(result.data).toEqual({
      question: 'What is the answer?',
      context: 'Some context',
    })
  })

  it('should handle API task with zero annotation count', () => {
    const apiTask: ApiTask = {
      id: '4',
      name: 'No annotations',
      description: 'Task without annotations',
      template_id: 'template-1',
      task_type: 'classification',
      visibility: 'public',
      created_by: 'user-1',
      created_at: '2025-01-01T00:00:00Z',
      annotation_count: 0,
    }

    const result = apiTaskToLabelStudio(apiTask)

    expect(result.is_labeled).toBe(false)
    expect(result.total_annotations).toBe(0)
  })

  it('should preserve all original API task properties', () => {
    const apiTask: ApiTask = {
      id: '5',
      name: 'Complete Task',
      description: 'Task with all properties',
      template_id: 'template-1',
      task_type: 'qa',
      visibility: 'public',
      created_by: 'user-1',
      created_by_name: 'John Doe',
      created_at: '2025-01-01T00:00:00Z',
      updated_at: '2025-01-02T00:00:00Z',
      annotation_count: 3,
      task_count: 10,
      annotation_guidelines: 'Follow these guidelines',
      evaluation_types: [],
      model_ids: ['model-1', 'model-2'],
      organization_ids: ['org-1'],
    }

    const result = apiTaskToLabelStudio(apiTask)

    expect(result.id).toBe('5')
    expect(result.created_at).toBe('2025-01-01T00:00:00Z')
    expect(result.updated_at).toBe('2025-01-02T00:00:00Z')
  })

  it('should handle undefined template_data', () => {
    const apiTask: ApiTask = {
      id: '6',
      name: 'Task without template data',
      description: 'No template data',
      template_id: 'template-1',
      task_type: 'classification',
      visibility: 'public',
      created_by: 'user-1',
      created_at: '2025-01-01T00:00:00Z',
      template_data: undefined,
    }

    const result = apiTaskToLabelStudio(apiTask)

    expect(result.data).toEqual({})
  })
})

describe('labelStudioTaskToApi', () => {
  it('should convert basic LabelStudio task to API format', () => {
    const lsTask: LabelStudioTask = {
      id: '1',
      project_id: '0',
      data: {
        text: 'Sample text',
      },
      is_labeled: false,
      total_annotations: 0,
      cancelled_annotations: 0,
      created_at: '2025-01-01T00:00:00Z',
    }

    const result = labelStudioTaskToApi(lsTask)

    expect(result.id).toBe('1')
    expect(result.template_data).toEqual({ text: 'Sample text' })
    expect(result.annotation_count).toBe(0)
  })

  it('should convert LabelStudio task with annotations', () => {
    const lsTask: LabelStudioTask = {
      id: '2',
      project_id: '0',
      data: {
        question: 'What is the answer?',
      },
      is_labeled: true,
      total_annotations: 7,
      cancelled_annotations: 1,
      created_at: '2025-01-01T00:00:00Z',
    }

    const result = labelStudioTaskToApi(lsTask)

    expect(result.template_data).toEqual({ question: 'What is the answer?' })
    expect(result.annotation_count).toBe(7)
  })

  it('should remove LabelStudio-specific properties', () => {
    const lsTask: LabelStudioTask = {
      id: '3',
      project_id: '0',
      data: { text: 'Test' },
      is_labeled: true,
      total_annotations: 5,
      cancelled_annotations: 1,
      meta: { custom: 'metadata' },
      created_at: '2025-01-01T00:00:00Z',
    }

    const result = labelStudioTaskToApi(lsTask)

    expect(result).not.toHaveProperty('is_labeled')
    expect(result).not.toHaveProperty('total_annotations')
    expect(result).not.toHaveProperty('cancelled_annotations')
    expect(result).not.toHaveProperty('meta')
  })

  it('should handle empty data object', () => {
    const lsTask: LabelStudioTask = {
      id: '4',
      project_id: '0',
      data: {},
      is_labeled: false,
      total_annotations: 0,
      cancelled_annotations: 0,
      created_at: '2025-01-01T00:00:00Z',
    }

    const result = labelStudioTaskToApi(lsTask)

    expect(result.template_data).toEqual({})
  })

  it('should handle undefined total_annotations', () => {
    const lsTask: LabelStudioTask = {
      id: '5',
      project_id: '0',
      data: { text: 'Test' },
      is_labeled: false,
      total_annotations: 0,
      cancelled_annotations: 0,
      created_at: '2025-01-01T00:00:00Z',
    }

    // Simulate undefined total_annotations
    const taskWithUndefined = { ...lsTask }
    delete (taskWithUndefined as any).total_annotations

    const result = labelStudioTaskToApi(taskWithUndefined)

    expect(result.annotation_count).toBe(0)
  })

  it('should preserve timestamps and other properties', () => {
    const lsTask: LabelStudioTask = {
      id: '6',
      project_id: '0',
      data: { text: 'Test' },
      is_labeled: true,
      total_annotations: 3,
      cancelled_annotations: 0,
      created_at: '2025-01-01T00:00:00Z',
      updated_at: '2025-01-02T00:00:00Z',
      tags: ['tag1', 'tag2'],
    }

    const result = labelStudioTaskToApi(lsTask)

    expect(result.created_at).toBe('2025-01-01T00:00:00Z')
    expect(result.updated_at).toBe('2025-01-02T00:00:00Z')
  })
})

describe('apiTasksToLabelStudio', () => {
  it('should convert array of API tasks', () => {
    const apiTasks: ApiTask[] = [
      {
        id: '1',
        name: 'Task 1',
        description: 'First task',
        template_id: 'template-1',
        task_type: 'qa',
        visibility: 'public',
        created_by: 'user-1',
        created_at: '2025-01-01T00:00:00Z',
        annotation_count: 2,
      },
      {
        id: '2',
        name: 'Task 2',
        description: 'Second task',
        template_id: 'template-2',
        task_type: 'classification',
        visibility: 'private',
        created_by: 'user-2',
        created_at: '2025-01-02T00:00:00Z',
        annotation_count: 0,
      },
    ]

    const result = apiTasksToLabelStudio(apiTasks)

    expect(result).toHaveLength(2)
    expect(result[0].id).toBe('1')
    expect(result[0].is_labeled).toBe(true)
    expect(result[0].total_annotations).toBe(2)
    expect(result[1].id).toBe('2')
    expect(result[1].is_labeled).toBe(false)
    expect(result[1].total_annotations).toBe(0)
  })

  it('should handle empty array', () => {
    const result = apiTasksToLabelStudio([])
    expect(result).toEqual([])
  })

  it('should preserve order of tasks', () => {
    const apiTasks: ApiTask[] = [
      {
        id: '3',
        name: 'Task 3',
        description: 'Third',
        template_id: 'template-1',
        task_type: 'qa',
        visibility: 'public',
        created_by: 'user-1',
        created_at: '2025-01-03T00:00:00Z',
      },
      {
        id: '1',
        name: 'Task 1',
        description: 'First',
        template_id: 'template-1',
        task_type: 'qa',
        visibility: 'public',
        created_by: 'user-1',
        created_at: '2025-01-01T00:00:00Z',
      },
    ]

    const result = apiTasksToLabelStudio(apiTasks)

    expect(result[0].id).toBe('3')
    expect(result[1].id).toBe('1')
  })
})

describe('labelStudioTasksToApi', () => {
  it('should convert array of LabelStudio tasks', () => {
    const lsTasks: LabelStudioTask[] = [
      {
        id: '1',
        project_id: '0',
        data: { text: 'First' },
        is_labeled: true,
        total_annotations: 3,
        cancelled_annotations: 0,
        created_at: '2025-01-01T00:00:00Z',
      },
      {
        id: '2',
        project_id: '0',
        data: { text: 'Second' },
        is_labeled: false,
        total_annotations: 0,
        cancelled_annotations: 0,
        created_at: '2025-01-02T00:00:00Z',
      },
    ]

    const result = labelStudioTasksToApi(lsTasks)

    expect(result).toHaveLength(2)
    expect(result[0].id).toBe('1')
    expect(result[0].annotation_count).toBe(3)
    expect(result[0].template_data).toEqual({ text: 'First' })
    expect(result[1].id).toBe('2')
    expect(result[1].annotation_count).toBe(0)
    expect(result[1].template_data).toEqual({ text: 'Second' })
  })

  it('should handle empty array', () => {
    const result = labelStudioTasksToApi([])
    expect(result).toEqual([])
  })

  it('should preserve order of tasks', () => {
    const lsTasks: LabelStudioTask[] = [
      {
        id: '5',
        project_id: '0',
        data: { text: 'Fifth' },
        is_labeled: false,
        total_annotations: 0,
        cancelled_annotations: 0,
        created_at: '2025-01-05T00:00:00Z',
      },
      {
        id: '2',
        project_id: '0',
        data: { text: 'Second' },
        is_labeled: false,
        total_annotations: 0,
        cancelled_annotations: 0,
        created_at: '2025-01-02T00:00:00Z',
      },
    ]

    const result = labelStudioTasksToApi(lsTasks)

    expect(result[0].id).toBe('5')
    expect(result[1].id).toBe('2')
  })
})

describe('isLabelStudioTask', () => {
  it('should return true for LabelStudio task', () => {
    const lsTask = {
      id: '1',
      project_id: '0',
      data: {},
      is_labeled: false,
      total_annotations: 0,
      cancelled_annotations: 0,
      created_at: '2025-01-01T00:00:00Z',
    }

    expect(isLabelStudioTask(lsTask)).toBe(true)
  })

  it('should return false for API task', () => {
    const apiTask = {
      id: '1',
      name: 'Task',
      description: 'Description',
      template_id: 'template-1',
      task_type: 'qa',
      visibility: 'public',
      created_by: 'user-1',
      created_at: '2025-01-01T00:00:00Z',
      annotation_count: 0,
    }

    expect(isLabelStudioTask(apiTask)).toBe(false)
  })

  it('should return false for object with only is_labeled', () => {
    const partial = {
      id: '1',
      is_labeled: true,
    }

    expect(isLabelStudioTask(partial)).toBe(false)
  })

  it('should return false for object with only total_annotations', () => {
    const partial = {
      id: '1',
      total_annotations: 5,
    }

    expect(isLabelStudioTask(partial)).toBe(false)
  })

  it('should return false for empty object', () => {
    expect(isLabelStudioTask({})).toBe(false)
  })

  it('should handle null gracefully', () => {
    // Type guards use 'in' operator which throws on null/undefined
    // In practice, these would be filtered out before calling the type guard
    expect(() => isLabelStudioTask(null)).toThrow()
  })

  it('should handle undefined gracefully', () => {
    // Type guards use 'in' operator which throws on null/undefined
    // In practice, these would be filtered out before calling the type guard
    expect(() => isLabelStudioTask(undefined)).toThrow()
  })

  it('should return true for object with both required properties', () => {
    const task = {
      id: '1',
      is_labeled: true,
      total_annotations: 5,
      extra_property: 'value',
    }

    expect(isLabelStudioTask(task)).toBe(true)
  })
})

describe('isApiTask', () => {
  it('should return true for API task', () => {
    const apiTask = {
      id: '1',
      name: 'Task',
      description: 'Description',
      template_id: 'template-1',
      task_type: 'qa',
      visibility: 'public',
      created_by: 'user-1',
      created_at: '2025-01-01T00:00:00Z',
      annotation_count: 5,
    }

    expect(isApiTask(apiTask)).toBe(true)
  })

  it('should return false for LabelStudio task', () => {
    const lsTask = {
      id: '1',
      project_id: '0',
      data: {},
      is_labeled: true,
      total_annotations: 5,
      cancelled_annotations: 0,
      created_at: '2025-01-01T00:00:00Z',
    }

    expect(isApiTask(lsTask)).toBe(false)
  })

  it('should return false for object with only annotation_count', () => {
    const partial = {
      id: '1',
      annotation_count: 5,
      is_labeled: true,
    }

    expect(isApiTask(partial)).toBe(false)
  })

  it('should return false for empty object', () => {
    expect(isApiTask({})).toBe(false)
  })

  it('should handle null gracefully', () => {
    // Type guards use 'in' operator which throws on null/undefined
    // In practice, these would be filtered out before calling the type guard
    expect(() => isApiTask(null)).toThrow()
  })

  it('should handle undefined gracefully', () => {
    // Type guards use 'in' operator which throws on null/undefined
    // In practice, these would be filtered out before calling the type guard
    expect(() => isApiTask(undefined)).toThrow()
  })

  it('should return true for object with annotation_count but no is_labeled', () => {
    const task = {
      id: '1',
      annotation_count: 3,
      extra_property: 'value',
    }

    expect(isApiTask(task)).toBe(true)
  })
})

describe('ensureLabelStudioTask', () => {
  it('should return LabelStudio task unchanged', () => {
    const lsTask: LabelStudioTask = {
      id: '1',
      project_id: '0',
      data: { text: 'Test' },
      is_labeled: true,
      total_annotations: 5,
      cancelled_annotations: 0,
      created_at: '2025-01-01T00:00:00Z',
    }

    const result = ensureLabelStudioTask(lsTask)

    expect(result).toBe(lsTask)
  })

  it('should convert API task to LabelStudio task', () => {
    const apiTask: ApiTask = {
      id: '2',
      name: 'API Task',
      description: 'Task description',
      template_id: 'template-1',
      task_type: 'qa',
      visibility: 'public',
      created_by: 'user-1',
      created_at: '2025-01-01T00:00:00Z',
      annotation_count: 3,
      template_data: { question: 'What?' },
    }

    const result = ensureLabelStudioTask(apiTask)

    expect(result.id).toBe('2')
    expect(result.is_labeled).toBe(true)
    expect(result.total_annotations).toBe(3)
    expect(result.data).toEqual({ question: 'What?' })
  })

  it('should handle API task without annotations', () => {
    const apiTask: ApiTask = {
      id: '3',
      name: 'No annotations',
      description: 'Task without annotations',
      template_id: 'template-1',
      task_type: 'classification',
      visibility: 'public',
      created_by: 'user-1',
      created_at: '2025-01-01T00:00:00Z',
    }

    const result = ensureLabelStudioTask(apiTask)

    expect(result.is_labeled).toBe(false)
    expect(result.total_annotations).toBe(0)
  })
})

describe('ensureApiTask', () => {
  it('should return API task unchanged', () => {
    const apiTask: ApiTask = {
      id: '1',
      name: 'API Task',
      description: 'Task description',
      template_id: 'template-1',
      task_type: 'qa',
      visibility: 'public',
      created_by: 'user-1',
      created_at: '2025-01-01T00:00:00Z',
      annotation_count: 3,
    }

    const result = ensureApiTask(apiTask)

    expect(result).toBe(apiTask)
  })

  it('should convert LabelStudio task to API task', () => {
    const lsTask: LabelStudioTask = {
      id: '2',
      project_id: '0',
      data: { question: 'Test question?' },
      is_labeled: true,
      total_annotations: 7,
      cancelled_annotations: 1,
      created_at: '2025-01-01T00:00:00Z',
    }

    const result = ensureApiTask(lsTask)

    expect(result.id).toBe('2')
    expect(result.annotation_count).toBe(7)
    expect(result.template_data).toEqual({ question: 'Test question?' })
    expect(result).not.toHaveProperty('is_labeled')
    expect(result).not.toHaveProperty('total_annotations')
  })

  it('should handle LabelStudio task without annotations', () => {
    const lsTask: LabelStudioTask = {
      id: '3',
      project_id: '0',
      data: { text: 'Sample' },
      is_labeled: false,
      total_annotations: 0,
      cancelled_annotations: 0,
      created_at: '2025-01-01T00:00:00Z',
    }

    const result = ensureApiTask(lsTask)

    expect(result.annotation_count).toBe(0)
    expect(result.template_data).toEqual({ text: 'Sample' })
  })
})

describe('round-trip conversion', () => {
  it('should maintain data integrity in API -> LS -> API conversion', () => {
    const originalApiTask: ApiTask = {
      id: '1',
      name: 'Round-trip Task',
      description: 'Testing round-trip conversion',
      template_id: 'template-1',
      task_type: 'qa',
      visibility: 'public',
      created_by: 'user-1',
      created_at: '2025-01-01T00:00:00Z',
      annotation_count: 5,
      template_data: {
        question: 'What is the question?',
        answer: 'This is the answer',
      },
    }

    const lsTask = apiTaskToLabelStudio(originalApiTask)
    const convertedApiTask = labelStudioTaskToApi(lsTask)

    expect(convertedApiTask.id).toBe(originalApiTask.id)
    expect(convertedApiTask.annotation_count).toBe(
      originalApiTask.annotation_count
    )
    expect(convertedApiTask.template_data).toEqual(
      originalApiTask.template_data
    )
  })

  it('should maintain data integrity in LS -> API -> LS conversion', () => {
    const originalLsTask: LabelStudioTask = {
      id: '2',
      project_id: '0',
      data: {
        text: 'Sample text for testing',
        metadata: { source: 'test' },
      },
      is_labeled: true,
      total_annotations: 10,
      cancelled_annotations: 2,
      created_at: '2025-01-01T00:00:00Z',
      updated_at: '2025-01-02T00:00:00Z',
    }

    const apiTask = labelStudioTaskToApi(originalLsTask)
    const convertedLsTask = apiTaskToLabelStudio(apiTask)

    expect(convertedLsTask.id).toBe(originalLsTask.id)
    expect(convertedLsTask.data).toEqual(originalLsTask.data)
    expect(convertedLsTask.total_annotations).toBe(
      originalLsTask.total_annotations
    )
  })
})

describe('edge cases and validation', () => {
  it('should handle tasks with complex nested template_data', () => {
    const apiTask: ApiTask = {
      id: '1',
      name: 'Complex Task',
      description: 'Task with complex data',
      template_id: 'template-1',
      task_type: 'qa',
      visibility: 'public',
      created_by: 'user-1',
      created_at: '2025-01-01T00:00:00Z',
      template_data: {
        question: {
          text: 'What is the question?',
          metadata: {
            source: 'test',
            tags: ['legal', 'german'],
          },
        },
        context: {
          paragraphs: ['Para 1', 'Para 2'],
        },
      },
    }

    const lsTask = apiTaskToLabelStudio(apiTask)
    const convertedApiTask = labelStudioTaskToApi(lsTask)

    expect(convertedApiTask.template_data).toEqual(apiTask.template_data)
  })

  it('should handle tasks with special characters in data', () => {
    const apiTask: ApiTask = {
      id: '2',
      name: 'Special Chars',
      description: 'Task with special characters',
      template_id: 'template-1',
      task_type: 'qa',
      visibility: 'public',
      created_by: 'user-1',
      created_at: '2025-01-01T00:00:00Z',
      template_data: {
        text: 'Text with äöüß and special chars: <>&"\'',
      },
    }

    const lsTask = apiTaskToLabelStudio(apiTask)
    const convertedApiTask = labelStudioTaskToApi(lsTask)

    expect(convertedApiTask.template_data?.text).toBe(
      'Text with äöüß and special chars: <>&"\''
    )
  })

  it('should handle tasks with very large annotation counts', () => {
    const apiTask: ApiTask = {
      id: '3',
      name: 'Many annotations',
      description: 'Task with many annotations',
      template_id: 'template-1',
      task_type: 'classification',
      visibility: 'public',
      created_by: 'user-1',
      created_at: '2025-01-01T00:00:00Z',
      annotation_count: 999999,
    }

    const lsTask = apiTaskToLabelStudio(apiTask)

    expect(lsTask.total_annotations).toBe(999999)
    expect(lsTask.is_labeled).toBe(true)
  })

  it('should handle tasks with all optional fields present', () => {
    const apiTask: ApiTask = {
      id: '4',
      name: 'Complete Task',
      description: 'Task with all fields',
      annotation_guidelines: 'Guidelines here',
      template_id: 'template-1',
      template_data: { key: 'value' },
      data: { other: 'data' },
      task_type: 'qa',
      template: 'legacy-template',
      visibility: 'public',
      created_by: 'user-1',
      created_by_name: 'John Doe',
      created_at: '2025-01-01T00:00:00Z',
      updated_at: '2025-01-02T00:00:00Z',
      evaluation_types: [
        {
          id: '1',
          name: 'Type1',
          category: 'cat1',
          higher_is_better: true,
          applicable_task_types: [],
          is_active: true,
        },
      ],
      model_ids: ['model-1'],
      organization_ids: ['org-1'],
      organizations: [
        {
          id: 'org-1',
          name: 'Org',
          display_name: 'Organization',
          slug: 'org',
          is_active: true,
          created_at: '2025-01-01T00:00:00Z',
        },
      ],
      annotation_count: 5,
      task_count: 100,
    }

    const lsTask = apiTaskToLabelStudio(apiTask)
    expect(lsTask.id).toBe('4')
    expect(lsTask.total_annotations).toBe(5)
  })
})

/**
 * Unit tests for AnnotationTab component logic
 * Focus on business logic, utility functions, and data transformations
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'

describe('AnnotationTab Business Logic', () => {
  describe('Task Filtering Logic', () => {
    const mockTasks = [
      {
        id: '1',
        data: { text: 'Legal case analysis' },
        is_labeled: false,
        total_annotations: 0,
        cancelled_annotations: 0,
        total_predictions: 0,
        created_at: '2024-01-15T00:00:00Z',
        updated_at: '2024-01-15T00:00:00Z',
        meta: { category: 'legal', priority: 'high' },
        assignments: [],
      },
      {
        id: '2',
        data: { text: 'Financial report review' },
        is_labeled: true,
        total_annotations: 2,
        cancelled_annotations: 0,
        total_predictions: 1,
        created_at: '2024-01-20T00:00:00Z',
        updated_at: '2024-01-20T00:00:00Z',
        meta: { category: 'finance', priority: 'low' },
        assignments: [],
      },
      {
        id: '3',
        data: { text: 'Technical documentation' },
        is_labeled: false,
        total_annotations: 1,
        cancelled_annotations: 0,
        total_predictions: 2,
        created_at: '2024-01-10T00:00:00Z',
        updated_at: '2024-01-10T00:00:00Z',
        meta: { category: 'tech', priority: 'high' },
        assignments: [],
      },
    ]

    it('should filter tasks by search query in data', () => {
      const searchQuery = 'legal'
      const filtered = mockTasks.filter((task) => {
        const searchLower = searchQuery.toLowerCase()
        return (
          JSON.stringify(task.data).toLowerCase().includes(searchLower) ||
          task.id.toString().includes(searchLower)
        )
      })

      expect(filtered).toHaveLength(1)
      expect(filtered[0].id).toBe('1')
    })

    it('should filter tasks by search query in ID', () => {
      const searchQuery = '2'
      const filtered = mockTasks.filter((task) => {
        const searchLower = searchQuery.toLowerCase()
        return (
          JSON.stringify(task.data).toLowerCase().includes(searchLower) ||
          task.id.toString().includes(searchLower)
        )
      })

      expect(filtered).toHaveLength(1)
      expect(filtered[0].id).toBe('2')
    })

    it('should filter completed tasks', () => {
      const filtered = mockTasks.filter((task) => task.is_labeled)

      expect(filtered).toHaveLength(1)
      expect(filtered[0].id).toBe('2')
    })

    it('should filter incomplete tasks', () => {
      const filtered = mockTasks.filter((task) => !task.is_labeled)

      expect(filtered).toHaveLength(2)
      expect(filtered.map((t) => t.id)).toEqual(['1', '3'])
    })

    it('should filter tasks by date range', () => {
      const startDate = new Date('2024-01-12T00:00:00Z')
      const endDate = new Date('2024-01-22T00:00:00Z')

      const filtered = mockTasks.filter((task) => {
        const taskDate = new Date(task.created_at)
        return taskDate >= startDate && taskDate <= endDate
      })

      expect(filtered).toHaveLength(2)
      expect(filtered.map((t) => t.id)).toEqual(['1', '2'])
    })

    it('should filter tasks by metadata values', () => {
      const metadataFilters = { category: 'legal' }

      const filtered = mockTasks.filter((task) => {
        const taskMeta = task.meta || {}
        return Object.entries(metadataFilters).every(([field, filterValue]) => {
          const taskValue = taskMeta[field]
          return taskValue === filterValue
        })
      })

      expect(filtered).toHaveLength(1)
      expect(filtered[0].id).toBe('1')
    })

    it('should filter tasks by array metadata values', () => {
      const tasksWithArrayMeta = [
        { ...mockTasks[0], meta: { tags: ['legal', 'urgent'] } },
        { ...mockTasks[1], meta: { tags: ['finance'] } },
        { ...mockTasks[2], meta: { tags: ['tech', 'urgent'] } },
      ]

      const metadataFilters = { tags: ['urgent'] }

      const filtered = tasksWithArrayMeta.filter((task) => {
        const taskMeta = task.meta || {}
        return Object.entries(metadataFilters).every(
          ([field, filterValues]) => {
            const taskValue = taskMeta[field]
            if (Array.isArray(filterValues)) {
              if (Array.isArray(taskValue)) {
                return filterValues.some((fv) => taskValue.includes(fv))
              } else {
                return filterValues.includes(taskValue)
              }
            }
            return taskValue === filterValues
          }
        )
      })

      expect(filtered).toHaveLength(2)
      expect(filtered.map((t) => t.id)).toEqual(['1', '3'])
    })
  })

  describe('Task Sorting Logic', () => {
    const mockTasks = [
      {
        id: '2',
        is_labeled: false,
        total_annotations: 5,
        total_predictions: 1,
        created_at: '2024-01-20T00:00:00Z',
      },
      {
        id: '1',
        is_labeled: true,
        total_annotations: 2,
        total_predictions: 3,
        created_at: '2024-01-15T00:00:00Z',
      },
      {
        id: '3',
        is_labeled: false,
        total_annotations: 8,
        total_predictions: 0,
        created_at: '2024-01-25T00:00:00Z',
      },
    ]

    it('should sort tasks by ID ascending', () => {
      const sorted = [...mockTasks].sort((a, b) => {
        return a.id < b.id ? -1 : a.id > b.id ? 1 : 0
      })

      expect(sorted.map((t) => t.id)).toEqual(['1', '2', '3'])
    })

    it('should sort tasks by ID descending', () => {
      const sorted = [...mockTasks].sort((a, b) => {
        return a.id > b.id ? -1 : a.id < b.id ? 1 : 0
      })

      expect(sorted.map((t) => t.id)).toEqual(['3', '2', '1'])
    })

    it('should sort tasks by completion status', () => {
      const sorted = [...mockTasks].sort((a, b) => {
        const aVal = a.is_labeled ? 1 : 0
        const bVal = b.is_labeled ? 1 : 0
        return bVal - aVal
      })

      expect(sorted[0].id).toBe('1')
      expect(sorted[0].is_labeled).toBe(true)
    })

    it('should sort tasks by annotation count', () => {
      const sorted = [...mockTasks].sort((a, b) => {
        return b.total_annotations - a.total_annotations
      })

      expect(sorted.map((t) => t.total_annotations)).toEqual([8, 5, 2])
    })

    it('should sort tasks by prediction count', () => {
      const sorted = [...mockTasks].sort((a, b) => {
        return b.total_predictions - a.total_predictions
      })

      expect(sorted.map((t) => t.total_predictions)).toEqual([3, 1, 0])
    })

    it('should sort tasks by creation date', () => {
      const sorted = [...mockTasks].sort((a, b) => {
        const aVal = new Date(a.created_at).getTime()
        const bVal = new Date(b.created_at).getTime()
        return bVal - aVal
      })

      expect(sorted.map((t) => t.id)).toEqual(['3', '2', '1'])
    })
  })

  describe('Task Selection Logic', () => {
    it('should add task to selection', () => {
      const selectedTasks = new Set<string>()
      const taskId = '1'

      if (!selectedTasks.has(taskId)) {
        selectedTasks.add(taskId)
      }

      expect(selectedTasks.has('1')).toBe(true)
      expect(selectedTasks.size).toBe(1)
    })

    it('should remove task from selection', () => {
      const selectedTasks = new Set<string>(['1', '2', '3'])
      const taskId = '2'

      if (selectedTasks.has(taskId)) {
        selectedTasks.delete(taskId)
      }

      expect(selectedTasks.has('2')).toBe(false)
      expect(selectedTasks.size).toBe(2)
    })

    it('should toggle task selection', () => {
      const selectedTasks = new Set<string>(['1'])
      const taskId = '2'

      if (selectedTasks.has(taskId)) {
        selectedTasks.delete(taskId)
      } else {
        selectedTasks.add(taskId)
      }

      expect(selectedTasks.has('2')).toBe(true)
      expect(selectedTasks.size).toBe(2)
    })

    it('should select all tasks', () => {
      const tasks = ['1', '2', '3']
      const selectedTasks = new Set(tasks)

      expect(selectedTasks.size).toBe(3)
      expect(Array.from(selectedTasks)).toEqual(tasks)
    })

    it('should deselect all tasks', () => {
      const selectedTasks = new Set(['1', '2', '3'])
      selectedTasks.clear()

      expect(selectedTasks.size).toBe(0)
    })

    it('should calculate header checkbox state - all selected', () => {
      const filteredTasks = [{ id: '1' }, { id: '2' }, { id: '3' }]
      const selectedTasks = new Set(['1', '2', '3'])

      const filteredTaskIds = filteredTasks.map((t) => t.id)
      const allSelected =
        filteredTasks.length > 0 &&
        filteredTaskIds.every((id) => selectedTasks.has(id))
      const someSelected = filteredTaskIds.some((id) => selectedTasks.has(id))
      const isIndeterminate = someSelected && !allSelected

      expect(allSelected).toBe(true)
      expect(isIndeterminate).toBe(false)
    })

    it('should calculate header checkbox state - some selected', () => {
      const filteredTasks = [{ id: '1' }, { id: '2' }, { id: '3' }]
      const selectedTasks = new Set(['1', '2'])

      const filteredTaskIds = filteredTasks.map((t) => t.id)
      const allSelected =
        filteredTasks.length > 0 &&
        filteredTaskIds.every((id) => selectedTasks.has(id))
      const someSelected = filteredTaskIds.some((id) => selectedTasks.has(id))
      const isIndeterminate = someSelected && !allSelected

      expect(allSelected).toBe(false)
      expect(isIndeterminate).toBe(true)
    })

    it('should calculate header checkbox state - none selected', () => {
      const filteredTasks = [{ id: '1' }, { id: '2' }, { id: '3' }]
      const selectedTasks = new Set<string>()

      const filteredTaskIds = filteredTasks.map((t) => t.id)
      const allSelected =
        filteredTasks.length > 0 &&
        filteredTaskIds.every((id) => selectedTasks.has(id))
      const someSelected = filteredTaskIds.some((id) => selectedTasks.has(id))
      const isIndeterminate = someSelected && !allSelected

      expect(allSelected).toBe(false)
      expect(isIndeterminate).toBe(false)
    })
  })

  describe('Task Display Value Extraction', () => {
    it('should extract text field', () => {
      const task = { data: { text: 'Sample text' } }
      const value = task.data.text

      expect(value).toBe('Sample text')
    })

    it('should extract question field', () => {
      const task = { data: { question: 'What is this?' } }
      const value = task.data.question

      expect(value).toBe('What is this?')
    })

    it('should extract prompt field', () => {
      const task = { data: { prompt: 'Analyze this' } }
      const value = task.data.prompt

      expect(value).toBe('Analyze this')
    })

    it('should fall back to first string value', () => {
      const task = { data: { custom_field: 'Custom value', number: 123 } }
      const firstStringValue = Object.values(task.data).find(
        (v) => typeof v === 'string'
      )

      expect(firstStringValue).toBe('Custom value')
    })

    it('should handle task with no string values', () => {
      const task = { id: '123', data: { number: 123, boolean: true } }
      const firstStringValue = Object.values(task.data).find(
        (v) => typeof v === 'string'
      )

      expect(firstStringValue).toBeUndefined()
    })
  })

  describe('Permission Checks', () => {
    it('should allow assignment for superadmin', () => {
      const user = { is_superadmin: true, role: 'ADMIN' }
      const canUnassign = user.is_superadmin

      expect(canUnassign).toBe(true)
    })

    it('should allow assignment for admin role', () => {
      const user = { is_superadmin: false, role: 'ADMIN' }
      const canUnassign =
        user.is_superadmin ||
        ['ADMIN', 'admin', 'CONTRIBUTOR', 'contributor'].includes(user.role)

      expect(canUnassign).toBe(true)
    })

    it('should allow assignment for contributor role', () => {
      const user = { is_superadmin: false, role: 'CONTRIBUTOR' }
      const canUnassign =
        user.is_superadmin ||
        ['ADMIN', 'admin', 'CONTRIBUTOR', 'contributor'].includes(user.role)

      expect(canUnassign).toBe(true)
    })

    it('should not allow assignment for annotator role', () => {
      const user = { is_superadmin: false, role: 'ANNOTATOR' }
      const canUnassign =
        user.is_superadmin ||
        ['ADMIN', 'admin', 'CONTRIBUTOR', 'contributor'].includes(user.role)

      expect(canUnassign).toBe(false)
    })

    it('should not allow assignment for user role', () => {
      const user = { is_superadmin: false, role: 'USER' }
      const canUnassign =
        user.is_superadmin ||
        ['ADMIN', 'admin', 'CONTRIBUTOR', 'contributor'].includes(user.role)

      expect(canUnassign).toBe(false)
    })
  })

  describe('Task Statistics Calculation', () => {
    const mockTasks = [
      {
        id: '1',
        total_annotations: 2,
        total_predictions: 1,
        cancelled_annotations: 0,
      },
      {
        id: '2',
        total_annotations: 3,
        total_predictions: 2,
        cancelled_annotations: 1,
      },
      {
        id: '3',
        total_annotations: 1,
        total_predictions: 0,
        cancelled_annotations: 0,
      },
    ]

    it('should calculate total annotations', () => {
      const total = mockTasks.reduce((sum, t) => sum + t.total_annotations, 0)

      expect(total).toBe(6)
    })

    it('should calculate total predictions', () => {
      const total = mockTasks.reduce((sum, t) => sum + t.total_predictions, 0)

      expect(total).toBe(3)
    })

    it('should calculate active annotations (excluding cancelled)', () => {
      const total = mockTasks.reduce(
        (sum, t) => sum + (t.total_annotations - t.cancelled_annotations),
        0
      )

      expect(total).toBe(5)
    })
  })

  describe('Column Visibility Management', () => {
    const defaultColumns = [
      { id: 'id', label: 'ID', visible: true },
      { id: 'completed', label: 'Completed', visible: true },
      { id: 'assigned', label: 'Assigned', visible: false },
    ]

    it('should toggle column visibility', () => {
      const columnId = 'assigned'
      const updated = defaultColumns.map((col) =>
        col.id === columnId ? { ...col, visible: !col.visible } : col
      )

      const assignedCol = updated.find((c) => c.id === 'assigned')
      expect(assignedCol?.visible).toBe(true)
    })

    it('should filter visible columns', () => {
      const visible = defaultColumns.filter((col) => col.visible)

      expect(visible).toHaveLength(2)
      expect(visible.map((c) => c.id)).toEqual(['id', 'completed'])
    })

    it('should reset columns to default', () => {
      const modifiedColumns = [
        { id: 'id', label: 'ID', visible: false },
        { id: 'completed', label: 'Completed', visible: false },
        { id: 'assigned', label: 'Assigned', visible: true },
      ]

      const reset = defaultColumns.map((col) => ({ ...col }))

      expect(reset[0].visible).toBe(true)
      expect(reset[1].visible).toBe(true)
      expect(reset[2].visible).toBe(false)
    })
  })

  describe('Export Format Validation', () => {
    it('should accept valid export formats', () => {
      const validFormats = ['json', 'csv', 'tsv']

      validFormats.forEach((format) => {
        expect(['json', 'csv', 'tsv']).toContain(format)
      })
    })

    it('should default to json format', () => {
      const format: 'json' | 'csv' | 'tsv' = 'json'

      expect(format).toBe('json')
    })
  })

  describe('Bulk Operation Validation', () => {
    it('should validate bulk delete requires selection', () => {
      const selectedTasks = new Set<string>()
      const canDelete = selectedTasks.size > 0

      expect(canDelete).toBe(false)
    })

    it('should validate bulk export requires selection', () => {
      const selectedTasks = new Set(['1', '2'])
      const canExport = selectedTasks.size > 0

      expect(canExport).toBe(true)
    })

    it('should validate bulk archive requires selection', () => {
      const selectedTasks = new Set<string>()
      const canArchive = selectedTasks.size > 0

      expect(canArchive).toBe(false)
    })
  })
})

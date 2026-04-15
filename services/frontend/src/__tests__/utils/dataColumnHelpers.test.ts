/**
 * Unit tests for data column helper utilities
 */

import { Task } from '../../types/labelStudio'
import {
  detectValueType,
  extractDataColumns,
  formatCellValue,
  formatFieldLabel,
  getTaskDisplayValue,
  hasConsistentDataStructure,
} from '../../utils/dataColumnHelpers'

// Mock task data for testing
const mockTasks: Task[] = [
  {
    id: 1,
    project_id: 'project-1',
    data: {
      title: 'Test Document 1',
      question: 'What is the main topic?',
      category: 'research',
      priority: 5,
      active: true,
      created_date: '2024-01-15',
      tags: ['important', 'urgent'],
      metadata: { author: 'John Doe', version: 1 },
    },
    is_labeled: false,
    total_annotations: 0,
    cancelled_annotations: 0,
    total_predictions: 0,
    created_at: '2024-01-15T10:00:00Z',
  },
  {
    id: 2,
    project_id: 'project-1',
    data: {
      title: 'Test Document 2',
      question: 'How does this relate to the previous document?',
      category: 'analysis',
      priority: 3,
      active: false,
      created_date: '2024-01-16',
      tags: ['follow-up'],
      metadata: { author: 'Jane Smith', version: 2 },
    },
    is_labeled: true,
    total_annotations: 2,
    cancelled_annotations: 0,
    total_predictions: 1,
    created_at: '2024-01-16T10:00:00Z',
  },
  {
    id: 3,
    project_id: 'project-1',
    data: {
      title: 'Test Document 3',
      question: 'What are the key findings?',
      category: 'research',
      priority: 4,
      active: true,
      created_date: '2024-01-17',
      // Note: missing tags and metadata to test inconsistent structure
    },
    is_labeled: false,
    total_annotations: 1,
    cancelled_annotations: 1,
    total_predictions: 0,
    created_at: '2024-01-17T10:00:00Z',
  },
]

describe('dataColumnHelpers', () => {
  describe('detectValueType', () => {
    it('should correctly detect value types', () => {
      expect(detectValueType('hello')).toBe('text')
      expect(detectValueType(42)).toBe('number')
      expect(detectValueType(true)).toBe('boolean')
      expect(detectValueType(false)).toBe('boolean')
      expect(detectValueType('2024-01-15')).toBe('date')
      expect(detectValueType(['a', 'b'])).toBe('array')
      expect(detectValueType({ key: 'value' })).toBe('object')
      expect(detectValueType(null)).toBe('text')
      expect(detectValueType(undefined)).toBe('text')
    })

    it('should detect date strings correctly', () => {
      expect(detectValueType('2024-01-15T10:00:00Z')).toBe('date')
      expect(detectValueType('2024-12-31')).toBe('date')
      expect(detectValueType('not-a-date')).toBe('text')
    })
  })

  describe('formatFieldLabel', () => {
    it('should format field names to readable labels', () => {
      expect(formatFieldLabel('created_date')).toBe('Created Date')
      expect(formatFieldLabel('firstName')).toBe('First Name')
      expect(formatFieldLabel('UPPERCASE')).toBe('Uppercase')
      expect(formatFieldLabel('multiple_word_field_name')).toBe(
        'Multiple Word Field Name'
      )
      expect(formatFieldLabel('simpleField')).toBe('Simple Field')
    })

    it('should handle edge cases', () => {
      expect(formatFieldLabel('')).toBe('')
      expect(formatFieldLabel('a')).toBe('A')
      expect(formatFieldLabel('_underscore_start')).toBe(' Underscore Start')
    })
  })

  describe('formatCellValue', () => {
    it('should format text values with truncation', () => {
      const shortText = 'Short text'
      const longText =
        'This is a very long text that should be truncated when displayed in table cells'

      const shortResult = formatCellValue(shortText, 'text', 50)
      expect(shortResult.display).toBe(shortText)
      expect(shortResult.full).toBe(shortText)
      expect(shortResult.truncated).toBe(false)

      const longResult = formatCellValue(longText, 'text', 20)
      expect(longResult.display).toBe('This is a very long ...')
      expect(longResult.full).toBe(longText)
      expect(longResult.truncated).toBe(true)
    })

    it('should format boolean values', () => {
      const trueResult = formatCellValue(true, 'boolean')
      expect(trueResult.display).toBe('✓')
      expect(trueResult.full).toBe('true')
      expect(trueResult.truncated).toBe(false)

      const falseResult = formatCellValue(false, 'boolean')
      expect(falseResult.display).toBe('✗')
      expect(falseResult.full).toBe('false')
      expect(falseResult.truncated).toBe(false)
    })

    it('should format number values', () => {
      const result = formatCellValue(1234.56, 'number')
      // Number formatting depends on locale, just check it's a string with the number
      expect(result.display).toMatch(/1.234[,.]56|1,234[.,]56/)
      expect(result.full).toMatch(/1.234[,.]56|1,234[.,]56/)
      expect(result.truncated).toBe(false)
    })

    it('should format array values', () => {
      const shortArray = ['a', 'b', 'c']
      const longArray = ['item1', 'item2', 'item3', 'item4', 'item5', 'item6']

      const shortResult = formatCellValue(shortArray, 'array', 50)
      expect(shortResult.display).toBe('a, b, c')
      expect(shortResult.full).toBe('a, b, c')
      expect(shortResult.truncated).toBe(false)

      const longResult = formatCellValue(longArray, 'array', 20)
      expect(longResult.display).toBe('item1, item2, item3,...')
      expect(longResult.full).toBe('item1, item2, item3, item4, item5, item6')
      expect(longResult.truncated).toBe(true)
    })

    it('should format null/undefined values', () => {
      const nullResult = formatCellValue(null, 'text')
      expect(nullResult.display).toBe('-')
      expect(nullResult.full).toBe('-')
      expect(nullResult.truncated).toBe(false)

      const undefinedResult = formatCellValue(undefined, 'text')
      expect(undefinedResult.display).toBe('-')
      expect(undefinedResult.full).toBe('-')
      expect(undefinedResult.truncated).toBe(false)
    })
  })

  describe('extractDataColumns', () => {
    it('should extract columns from consistent task data', () => {
      const columns = extractDataColumns(mockTasks, 10)

      expect(columns.length).toBeGreaterThan(0)

      // Should prioritize common fields
      const columnKeys = columns.map((col) => col.key)
      expect(columnKeys).toContain('title')
      expect(columnKeys).toContain('question')

      // Should include proper types
      const titleColumn = columns.find((col) => col.key === 'title')
      expect(titleColumn?.type).toBe('text')
      expect(titleColumn?.label).toBe('Title')

      const priorityColumn = columns.find((col) => col.key === 'priority')
      expect(priorityColumn?.type).toBe('number')
      expect(priorityColumn?.label).toBe('Priority')

      const activeColumn = columns.find((col) => col.key === 'active')
      expect(activeColumn?.type).toBe('boolean')
      expect(activeColumn?.label).toBe('Active')
    })

    it('should respect maxColumns limit', () => {
      const columns = extractDataColumns(mockTasks, 3)
      expect(columns.length).toBeLessThanOrEqual(3)
    })

    it('should handle empty task array', () => {
      const columns = extractDataColumns([], 10)
      expect(columns).toEqual([])
    })

    it('should skip complex nested objects and arrays', () => {
      const columns = extractDataColumns(mockTasks, 10)
      const columnKeys = columns.map((col) => col.key)

      // Should not include complex objects like metadata
      expect(columnKeys).not.toContain('metadata')

      // Should include simple arrays like tags
      expect(columnKeys).toContain('tags')
    })

    it('should prioritize fields correctly', () => {
      const columns = extractDataColumns(mockTasks, 10)

      // Priority fields should appear first
      const firstColumns = columns.slice(0, 3).map((col) => col.key)
      expect(firstColumns).toContain('title')
      expect(firstColumns).toContain('question')
    })
  })

  describe('hasConsistentDataStructure', () => {
    it('should return true for consistent task structures', () => {
      const consistentTasks = mockTasks.slice(0, 2) // First two tasks have similar structure
      expect(hasConsistentDataStructure(consistentTasks)).toBe(true)
    })

    it('should return false for very inconsistent structures', () => {
      const inconsistentTasks = [
        mockTasks[0],
        {
          id: 4,
          project_id: 'project-1',
          data: {
            completely_different_field: 'value',
            another_field: 'another_value',
          },
          is_labeled: false,
          total_annotations: 0,
          cancelled_annotations: 0,
          total_predictions: 0,
          created_at: '2024-01-18T10:00:00Z',
        } as Task,
      ]

      expect(hasConsistentDataStructure(inconsistentTasks)).toBe(false)
    })

    it('should handle edge cases', () => {
      expect(hasConsistentDataStructure([])).toBe(true)
      expect(hasConsistentDataStructure([mockTasks[0]])).toBe(true)
    })
  })

  describe('getTaskDisplayValue', () => {
    it('should return priority field values', () => {
      const task = mockTasks[0]
      expect(getTaskDisplayValue(task)).toBe('Test Document 1') // title is priority field
    })

    it('should fallback to first string value', () => {
      const taskWithoutPriorityFields: Task = {
        id: 5,
        project_id: 'project-1',
        data: {
          some_field: 'fallback value',
          number_field: 42,
        },
        is_labeled: false,
        total_annotations: 0,
        cancelled_annotations: 0,
        total_predictions: 0,
        created_at: '2024-01-18T10:00:00Z',
      }

      expect(getTaskDisplayValue(taskWithoutPriorityFields)).toBe(
        'fallback value'
      )
    })

    it('should fallback to task ID when no string values exist', () => {
      const taskWithoutStrings: Task = {
        id: 6,
        project_id: 'project-1',
        data: {
          number_field: 42,
          boolean_field: true,
        },
        is_labeled: false,
        total_annotations: 0,
        cancelled_annotations: 0,
        total_predictions: 0,
        created_at: '2024-01-18T10:00:00Z',
      }

      expect(getTaskDisplayValue(taskWithoutStrings)).toBe('Task 6')
    })

    it('should handle tasks with no data', () => {
      const taskWithoutData: Task = {
        id: 7,
        project_id: 'project-1',
        data: {},
        is_labeled: false,
        total_annotations: 0,
        cancelled_annotations: 0,
        total_predictions: 0,
        created_at: '2024-01-18T10:00:00Z',
      }

      expect(getTaskDisplayValue(taskWithoutData)).toBe('Task 7')
    })
  })

  describe('integration scenarios', () => {
    it('should handle real-world task variations', () => {
      const realWorldTasks: Task[] = [
        {
          id: 101,
          project_id: 'legal-docs',
          data: {
            fallnummer: 'CASE-2024-001',
            title: 'Contract Review',
            category: 'legal',
            priority: 1,
            status: 'pending',
          },
          is_labeled: false,
          total_annotations: 0,
          cancelled_annotations: 0,
          total_predictions: 0,
          created_at: '2024-01-01T10:00:00Z',
        },
        {
          id: 102,
          project_id: 'legal-docs',
          data: {
            fallnummer: 'CASE-2024-002',
            title: 'Dispute Analysis',
            category: 'legal',
            priority: 2,
            status: 'in_progress',
          },
          is_labeled: true,
          total_annotations: 3,
          cancelled_annotations: 0,
          total_predictions: 1,
          created_at: '2024-01-02T10:00:00Z',
        },
      ]

      const columns = extractDataColumns(realWorldTasks, 8)

      // Should prioritize fallnummer (German legal case number)
      expect(columns.map((col) => col.key)).toContain('fallnummer')
      expect(columns.map((col) => col.key)).toContain('title')
      expect(columns.map((col) => col.key)).toContain('category')

      // Should have proper formatting
      const fallnummerColumn = columns.find((col) => col.key === 'fallnummer')
      expect(fallnummerColumn?.label).toBe('Fallnummer')
    })
  })
})

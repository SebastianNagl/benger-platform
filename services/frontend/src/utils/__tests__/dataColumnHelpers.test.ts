/**
 * Unit tests for data column helper utilities
 * @jest-environment jsdom
 */

import { Task } from '@/lib/api/types'
import {
  detectValueType,
  extractDataColumns,
  extractMetadataColumns,
  formatCellValue,
  formatFieldLabel,
  getTaskDisplayValue,
  hasConsistentDataStructure,
  hasConsistentMetadataStructure,
} from '../dataColumnHelpers'

describe('detectValueType', () => {
  it('should detect null and undefined as text', () => {
    expect(detectValueType(null)).toBe('text')
    expect(detectValueType(undefined)).toBe('text')
  })

  it('should detect boolean type', () => {
    expect(detectValueType(true)).toBe('boolean')
    expect(detectValueType(false)).toBe('boolean')
  })

  it('should detect number type', () => {
    expect(detectValueType(42)).toBe('number')
    expect(detectValueType(0)).toBe('number')
    expect(detectValueType(-100)).toBe('number')
    expect(detectValueType(3.14)).toBe('number')
  })

  it('should detect date strings', () => {
    expect(detectValueType('2025-01-15')).toBe('date')
    expect(detectValueType('2025-01-15T10:30:00Z')).toBe('date')
    expect(detectValueType('2025-12-31')).toBe('date')
  })

  it('should detect regular text strings', () => {
    expect(detectValueType('hello')).toBe('text')
    expect(detectValueType('some text')).toBe('text')
    expect(detectValueType('')).toBe('text')
    expect(detectValueType('123-456')).toBe('text') // Not a date pattern
  })

  it('should detect array type', () => {
    expect(detectValueType([])).toBe('array')
    expect(detectValueType([1, 2, 3])).toBe('array')
    expect(detectValueType(['a', 'b', 'c'])).toBe('array')
  })

  it('should detect object type', () => {
    expect(detectValueType({})).toBe('object')
    expect(detectValueType({ key: 'value' })).toBe('object')
  })

  it('should handle edge case of unknown types', () => {
    // Edge case: Symbol or other exotic types should default to 'text'
    const sym = Symbol('test')
    expect(detectValueType(sym)).toBe('text')
  })
})

describe('formatFieldLabel', () => {
  it('should format snake_case to Title Case', () => {
    expect(formatFieldLabel('first_name')).toBe('First Name')
    expect(formatFieldLabel('user_id')).toBe('User Id')
    expect(formatFieldLabel('case_number')).toBe('Case Number')
  })

  it('should format camelCase to Title Case', () => {
    expect(formatFieldLabel('firstName')).toBe('First Name')
    expect(formatFieldLabel('userId')).toBe('User Id')
    expect(formatFieldLabel('caseNumber')).toBe('Case Number')
  })

  it('should format mixed case correctly', () => {
    expect(formatFieldLabel('user_firstName')).toBe('User First Name')
    expect(formatFieldLabel('API_Key')).toBe('Api Key')
  })

  it('should handle single word', () => {
    expect(formatFieldLabel('name')).toBe('Name')
    expect(formatFieldLabel('id')).toBe('Id')
  })

  it('should handle already formatted strings', () => {
    expect(formatFieldLabel('Name')).toBe('Name')
    expect(formatFieldLabel('TITLE')).toBe('Title')
  })

  it('should handle empty string', () => {
    expect(formatFieldLabel('')).toBe('')
  })
})

describe('formatCellValue', () => {
  it('should format null and undefined', () => {
    expect(formatCellValue(null, 'text')).toEqual({
      display: '-',
      full: '-',
      truncated: false,
    })
    expect(formatCellValue(undefined, 'text')).toEqual({
      display: '-',
      full: '-',
      truncated: false,
    })
  })

  it('should format boolean values', () => {
    expect(formatCellValue(true, 'boolean')).toEqual({
      display: '✓',
      full: 'true',
      truncated: false,
    })
    expect(formatCellValue(false, 'boolean')).toEqual({
      display: '✗',
      full: 'false',
      truncated: false,
    })
  })

  it('should format number values', () => {
    const result1000 = formatCellValue(1000, 'number')
    expect(result1000.truncated).toBe(false)
    expect(result1000.display).toBe(result1000.full)
    expect(result1000.display).toContain('1')
    expect(result1000.display).toContain('000')

    expect(formatCellValue(42, 'number')).toEqual({
      display: '42',
      full: '42',
      truncated: false,
    })
  })

  it('should format number strings as numbers', () => {
    expect(formatCellValue('1000', 'number')).toEqual({
      display: '1000',
      full: '1000',
      truncated: false,
    })
  })

  it('should format date values', () => {
    const date = new Date('2025-01-15T10:30:00Z')
    const result = formatCellValue('2025-01-15T10:30:00Z', 'date')

    expect(result.truncated).toBe(false)
    expect(result.display).toBeTruthy()
    expect(result.full).toBeTruthy()
  })

  it('should fallback to text for invalid dates', () => {
    const result = formatCellValue('not-a-date', 'date', 10)
    // Invalid dates are converted to 'Invalid Date' by Date constructor
    expect(result.display).toContain('Invalid')
    expect(result.truncated).toBe(false)
  })

  it('should handle date parsing without errors', () => {
    // Test with invalid date string - Date constructor returns 'Invalid Date'
    const longInvalidDate = 'x'.repeat(100)
    const result = formatCellValue(longInvalidDate, 'date', 20)
    // Date constructor will return 'Invalid Date' string
    expect(result.display).toContain('Invalid')
    expect(result.truncated).toBe(false)
  })

  it('should format array values', () => {
    expect(formatCellValue(['a', 'b', 'c'], 'array')).toEqual({
      display: 'a, b, c',
      full: 'a, b, c',
      truncated: false,
    })
  })

  it('should truncate long array values', () => {
    const longArray = ['item1', 'item2', 'item3', 'item4', 'item5', 'item6']
    const result = formatCellValue(longArray, 'array', 20)

    expect(result.display).toBe('item1, item2, item3,...')
    expect(result.full).toBe('item1, item2, item3, item4, item5, item6')
    expect(result.truncated).toBe(true)
  })

  it('should format text values', () => {
    expect(formatCellValue('Hello World', 'text')).toEqual({
      display: 'Hello World',
      full: 'Hello World',
      truncated: false,
    })
  })

  it('should truncate long text values', () => {
    const longText = 'This is a very long text that exceeds the maximum length'
    const result = formatCellValue(longText, 'text', 20)

    expect(result.display).toBe('This is a very long ...')
    expect(result.full).toBe(longText)
    expect(result.truncated).toBe(true)
  })

  it('should respect custom maxLength parameter', () => {
    const text = 'Hello World'
    const result = formatCellValue(text, 'text', 5)

    expect(result.display).toBe('Hello...')
    expect(result.truncated).toBe(true)
  })

  it('should handle non-array value with array type', () => {
    expect(formatCellValue('not-an-array', 'array')).toEqual({
      display: 'not-an-array',
      full: 'not-an-array',
      truncated: false,
    })
  })
})

describe('extractDataColumns', () => {
  it('should return empty array for no tasks', () => {
    expect(extractDataColumns([])).toEqual([])
  })

  it('should return empty array for null/undefined', () => {
    expect(extractDataColumns(null as any)).toEqual([])
    expect(extractDataColumns(undefined as any)).toEqual([])
  })

  it('should extract basic columns from tasks', () => {
    const tasks = [
      {
        id: '1',
        name: 'Task 1',
        data: {
          title: 'Test Title',
          description: 'Test Description',
          count: 42,
        },
      },
    ] as Task[]

    const columns = extractDataColumns(tasks)

    expect(columns.length).toBe(3)
    expect(columns.find((c) => c.key === 'title')).toBeTruthy()
    expect(columns.find((c) => c.key === 'description')).toBeTruthy()
    expect(columns.find((c) => c.key === 'count')).toBeTruthy()
  })

  it('should prioritize PRIORITY_FIELDS correctly', () => {
    const tasks = [
      {
        id: '1',
        name: 'Task 1',
        data: {
          random_field: 'value',
          name: 'Priority Name',
          another_field: 'value2',
          id: '123',
        },
      },
    ] as Task[]

    const columns = extractDataColumns(tasks)

    // Priority fields should come first
    expect(columns[0].key).toBe('name')
    expect(columns[1].key).toBe('id')
  })

  it('should filter out complex objects', () => {
    const tasks = [
      {
        id: '1',
        name: 'Task 1',
        data: {
          simple_field: 'text',
          complex_object: { nested: { deep: 'value' } },
          number_field: 42,
        },
      },
    ] as Task[]

    const columns = extractDataColumns(tasks)

    expect(columns.find((c) => c.key === 'simple_field')).toBeTruthy()
    expect(columns.find((c) => c.key === 'number_field')).toBeTruthy()
    expect(columns.find((c) => c.key === 'complex_object')).toBeFalsy()
  })

  it('should include simple arrays of primitives', () => {
    const tasks = [
      {
        id: '1',
        name: 'Task 1',
        data: {
          tags: ['tag1', 'tag2', 'tag3'],
          numbers: [1, 2, 3],
          text: 'simple',
        },
      },
    ] as Task[]

    const columns = extractDataColumns(tasks)

    expect(columns.find((c) => c.key === 'tags')).toBeTruthy()
    expect(columns.find((c) => c.key === 'numbers')).toBeTruthy()
  })

  it('should filter out arrays of objects', () => {
    const tasks = [
      {
        id: '1',
        name: 'Task 1',
        data: {
          simple_array: ['a', 'b'],
          complex_array: [{ id: 1 }, { id: 2 }],
        },
      },
    ] as Task[]

    const columns = extractDataColumns(tasks)

    expect(columns.find((c) => c.key === 'simple_array')).toBeTruthy()
    expect(columns.find((c) => c.key === 'complex_array')).toBeFalsy()
  })

  it('should respect maxColumns parameter', () => {
    const tasks = [
      {
        id: '1',
        name: 'Task 1',
        data: {
          field1: 'a',
          field2: 'b',
          field3: 'c',
          field4: 'd',
          field5: 'e',
        },
      },
    ] as Task[]

    const columns = extractDataColumns(tasks, 3)
    expect(columns.length).toBe(3)
  })

  it('should handle tasks without data property', () => {
    const tasks = [
      { id: '1', name: 'Task 1' },
      { id: '2', name: 'Task 2', data: { title: 'Test' } },
    ] as Task[]

    const columns = extractDataColumns(tasks)
    expect(columns.length).toBe(1)
    expect(columns[0].key).toBe('title')
  })

  it('should handle tasks with non-object data', () => {
    const tasks = [
      { id: '1', name: 'Task 1', data: 'not-an-object' as any },
      { id: '2', name: 'Task 2', data: { title: 'Test' } },
    ] as Task[]

    const columns = extractDataColumns(tasks)
    expect(columns.length).toBe(1)
    expect(columns[0].key).toBe('title')
  })

  it('should detect correct types for columns', () => {
    const tasks = [
      {
        id: '1',
        name: 'Task 1',
        data: {
          text_field: 'hello',
          number_field: 42,
          boolean_field: true,
          date_field: '2025-01-15',
          array_field: ['a', 'b'],
        },
      },
    ] as Task[]

    const columns = extractDataColumns(tasks)

    expect(columns.find((c) => c.key === 'text_field')?.type).toBe('text')
    expect(columns.find((c) => c.key === 'number_field')?.type).toBe('number')
    expect(columns.find((c) => c.key === 'boolean_field')?.type).toBe('boolean')
    expect(columns.find((c) => c.key === 'date_field')?.type).toBe('date')
    expect(columns.find((c) => c.key === 'array_field')?.type).toBe('array')
  })

  it('should sample only first 5 tasks', () => {
    const tasks = Array.from({ length: 10 }, (_, i) => ({
      id: `${i}`,
      name: `Task ${i}`,
      data: {
        common_field: 'value',
        [`unique_field_${i}`]: `value_${i}`,
      },
    })) as Task[]

    const columns = extractDataColumns(tasks)

    // Should only see fields from first 5 tasks
    const uniqueFields = columns.filter((c) =>
      c.key.startsWith('unique_field_')
    )
    expect(uniqueFields.length).toBeLessThanOrEqual(5)
  })

  it('should format column labels correctly', () => {
    const tasks = [
      {
        id: '1',
        name: 'Task 1',
        data: {
          first_name: 'John',
          user_id: '123',
        },
      },
    ] as Task[]

    const columns = extractDataColumns(tasks)

    expect(columns.find((c) => c.key === 'first_name')?.label).toBe(
      'First Name'
    )
    expect(columns.find((c) => c.key === 'user_id')?.label).toBe('User Id')
  })

  it('should sort columns by priority then alphabetically', () => {
    const tasks = [
      {
        id: '1',
        name: 'Task 1',
        data: {
          zebra: 'z',
          apple: 'a',
          name: 'priority',
          banana: 'b',
          id: 'priority2',
        },
      },
    ] as Task[]

    const columns = extractDataColumns(tasks)

    // Priority fields first
    expect(columns[0].key).toBe('name')
    expect(columns[1].key).toBe('id')
    // Then alphabetically
    expect(columns[2].key).toBe('apple')
    expect(columns[3].key).toBe('banana')
    expect(columns[4].key).toBe('zebra')
  })
})

describe('getTaskDisplayValue', () => {
  it('should return priority field value if available', () => {
    const task = {
      id: '1',
      name: 'Task Name',
      data: {
        random_field: 'random',
        title: 'Important Title',
        other_field: 'other',
      },
    } as Task

    expect(getTaskDisplayValue(task)).toBe('Important Title')
  })

  it('should check all priority fields in order', () => {
    const taskWithName = {
      id: '1',
      name: 'Task Name',
      data: {
        name: 'Name Field',
        title: 'Title Field',
      },
    } as Task

    expect(getTaskDisplayValue(taskWithName)).toBe('Name Field')

    const taskWithTitle = {
      id: '2',
      name: 'Task Name',
      data: {
        title: 'Title Field',
        question: 'Question Field',
      },
    } as Task

    expect(getTaskDisplayValue(taskWithTitle)).toBe('Title Field')
  })

  it('should fallback to first string value', () => {
    const task = {
      id: '1',
      name: 'Task Name',
      data: {
        number_field: 42,
        text_field: 'First String',
        another_text: 'Second String',
      },
    } as Task

    expect(getTaskDisplayValue(task)).toBe('First String')
  })

  it('should return task ID when no data', () => {
    const task = {
      id: '123',
      name: 'Task Name',
    } as Task

    expect(getTaskDisplayValue(task)).toBe('Task 123')
  })

  it('should return task ID when data is empty', () => {
    const task = {
      id: '456',
      name: 'Task Name',
      data: {},
    } as Task

    expect(getTaskDisplayValue(task)).toBe('Task 456')
  })

  it('should return task ID when no string values available', () => {
    const task = {
      id: '789',
      name: 'Task Name',
      data: {
        number: 42,
        boolean: true,
        array: [1, 2, 3],
      },
    } as Task

    expect(getTaskDisplayValue(task)).toBe('Task 789')
  })

  it('should ignore non-string priority fields', () => {
    const task = {
      id: '1',
      name: 'Task Name',
      data: {
        name: 123, // Not a string
        title: true, // Not a string
        text: 'Valid String',
      },
    } as Task

    expect(getTaskDisplayValue(task)).toBe('Valid String')
  })
})

describe('hasConsistentDataStructure', () => {
  it('should return true for empty array', () => {
    expect(hasConsistentDataStructure([])).toBe(true)
  })

  it('should return true for single task', () => {
    const tasks = [
      {
        id: '1',
        name: 'Task 1',
        data: { field1: 'value' },
      },
    ] as Task[]

    expect(hasConsistentDataStructure(tasks)).toBe(true)
  })

  it('should return true for consistent structures', () => {
    const tasks = [
      {
        id: '1',
        name: 'Task 1',
        data: { name: 'John', age: 30, city: 'Munich' },
      },
      {
        id: '2',
        name: 'Task 2',
        data: { name: 'Jane', age: 25, city: 'Berlin' },
      },
      {
        id: '3',
        name: 'Task 3',
        data: { name: 'Bob', age: 35, city: 'Hamburg' },
      },
    ] as Task[]

    expect(hasConsistentDataStructure(tasks)).toBe(true)
  })

  it('should return true for mostly consistent structures (70% threshold)', () => {
    const tasks = [
      {
        id: '1',
        name: 'Task 1',
        data: { field1: 'a', field2: 'b', field3: 'c', field4: 'd' },
      },
      {
        id: '2',
        name: 'Task 2',
        data: { field1: 'a', field2: 'b', field3: 'c', field5: 'e' }, // 75% match
      },
    ] as Task[]

    expect(hasConsistentDataStructure(tasks)).toBe(true)
  })

  it('should return false for inconsistent structures', () => {
    const tasks = [
      {
        id: '1',
        name: 'Task 1',
        data: { field1: 'a', field2: 'b', field3: 'c' },
      },
      {
        id: '2',
        name: 'Task 2',
        data: { fieldX: 'x', fieldY: 'y', fieldZ: 'z' }, // 0% match
      },
    ] as Task[]

    expect(hasConsistentDataStructure(tasks)).toBe(false)
  })

  it('should handle tasks without data', () => {
    const tasks = [
      {
        id: '1',
        name: 'Task 1',
        data: { field1: 'value' },
      },
      {
        id: '2',
        name: 'Task 2',
      } as Task,
    ]

    expect(hasConsistentDataStructure(tasks)).toBe(false)
  })

  it('should sample only first 10 tasks', () => {
    const tasks = [
      ...Array.from({ length: 10 }, (_, i) => ({
        id: `${i}`,
        name: `Task ${i}`,
        data: { field1: 'a', field2: 'b' },
      })),
      {
        id: '11',
        name: 'Task 11',
        data: { completely: 'different' },
      },
    ] as Task[]

    // Should return true because the 11th task is not checked
    expect(hasConsistentDataStructure(tasks)).toBe(true)
  })
})

describe('extractMetadataColumns', () => {
  it('should return empty array for no tasks', () => {
    expect(extractMetadataColumns([])).toEqual([])
  })

  it('should return empty array for null/undefined', () => {
    expect(extractMetadataColumns(null as any)).toEqual([])
    expect(extractMetadataColumns(undefined as any)).toEqual([])
  })

  it('should extract metadata columns from tasks', () => {
    const tasks = [
      {
        id: '1',
        name: 'Task 1',
        meta: {
          tags: ['tag1', 'tag2'],
          status: 'active',
          priority: 1,
        },
      },
    ] as any[]

    const columns = extractMetadataColumns(tasks)

    expect(columns.length).toBe(3)
    expect(columns.find((c) => c.key === 'tags')).toBeTruthy()
    expect(columns.find((c) => c.key === 'status')).toBeTruthy()
    expect(columns.find((c) => c.key === 'priority')).toBeTruthy()
  })

  it('should prioritize common metadata fields', () => {
    const tasks = [
      {
        id: '1',
        name: 'Task 1',
        meta: {
          random_field: 'value',
          tags: ['tag1'],
          another_field: 'value2',
          status: 'active',
        },
      },
    ] as any[]

    const columns = extractMetadataColumns(tasks)

    // Priority fields should come first
    expect(columns[0].key).toBe('tags')
    expect(columns[1].key).toBe('status')
  })

  it('should filter out complex objects', () => {
    const tasks = [
      {
        id: '1',
        name: 'Task 1',
        meta: {
          simple_field: 'text',
          complex_object: { nested: { deep: 'value' } },
          tags: ['tag1'],
        },
      },
    ] as any[]

    const columns = extractMetadataColumns(tasks)

    expect(columns.find((c) => c.key === 'simple_field')).toBeTruthy()
    expect(columns.find((c) => c.key === 'tags')).toBeTruthy()
    expect(columns.find((c) => c.key === 'complex_object')).toBeFalsy()
  })

  it('should include arrays (unlike data columns)', () => {
    const tasks = [
      {
        id: '1',
        name: 'Task 1',
        meta: {
          tags: ['tag1', 'tag2'],
          items: [{ id: 1 }, { id: 2 }],
        },
      },
    ] as any[]

    const columns = extractMetadataColumns(tasks)

    expect(columns.find((c) => c.key === 'tags')).toBeTruthy()
    expect(columns.find((c) => c.key === 'items')).toBeTruthy()
  })

  it('should respect maxColumns parameter', () => {
    const tasks = [
      {
        id: '1',
        name: 'Task 1',
        meta: {
          field1: 'a',
          field2: 'b',
          field3: 'c',
          field4: 'd',
          field5: 'e',
        },
      },
    ] as any[]

    const columns = extractMetadataColumns(tasks, 3)
    expect(columns.length).toBe(3)
  })

  it('should handle tasks without meta property', () => {
    const tasks = [
      { id: '1', name: 'Task 1' },
      { id: '2', name: 'Task 2', meta: { tags: ['tag1'] } },
    ] as any[]

    const columns = extractMetadataColumns(tasks)
    expect(columns.length).toBe(1)
    expect(columns[0].key).toBe('tags')
  })

  it('should handle tasks with non-object meta', () => {
    const tasks = [
      { id: '1', name: 'Task 1', meta: 'not-an-object' },
      { id: '2', name: 'Task 2', meta: { tags: ['tag1'] } },
    ] as any[]

    const columns = extractMetadataColumns(tasks)
    expect(columns.length).toBe(1)
    expect(columns[0].key).toBe('tags')
  })

  it('should sample first 10 tasks', () => {
    const tasks = Array.from({ length: 15 }, (_, i) => ({
      id: `${i}`,
      name: `Task ${i}`,
      meta: {
        common_field: 'value',
        [`unique_field_${i}`]: `value_${i}`,
      },
    })) as any[]

    const columns = extractMetadataColumns(tasks)

    // Should only see fields from first 10 tasks
    const uniqueFields = columns.filter((c) =>
      c.key.startsWith('unique_field_')
    )
    expect(uniqueFields.length).toBeLessThanOrEqual(10)
  })
})

describe('hasConsistentMetadataStructure', () => {
  it('should return true for empty array', () => {
    expect(hasConsistentMetadataStructure([])).toBe(true)
  })

  it('should return true for single task', () => {
    const tasks = [
      {
        id: '1',
        name: 'Task 1',
        meta: { field1: 'value' },
      },
    ] as any[]

    expect(hasConsistentMetadataStructure(tasks)).toBe(true)
  })

  it('should return true for consistent structures', () => {
    const tasks = [
      {
        id: '1',
        name: 'Task 1',
        meta: { tags: ['tag1'], status: 'active', priority: 1 },
      },
      {
        id: '2',
        name: 'Task 2',
        meta: { tags: ['tag2'], status: 'inactive', priority: 2 },
      },
    ] as any[]

    expect(hasConsistentMetadataStructure(tasks)).toBe(true)
  })

  it('should return true for mostly consistent structures (60% threshold)', () => {
    const tasks = [
      {
        id: '1',
        name: 'Task 1',
        meta: {
          field1: 'a',
          field2: 'b',
          field3: 'c',
          field4: 'd',
          field5: 'e',
        },
      },
      {
        id: '2',
        name: 'Task 2',
        meta: { field1: 'a', field2: 'b', field3: 'c', field6: 'f' }, // 60% match
      },
    ] as any[]

    expect(hasConsistentMetadataStructure(tasks)).toBe(true)
  })

  it('should return false for inconsistent structures', () => {
    const tasks = [
      {
        id: '1',
        name: 'Task 1',
        meta: { field1: 'a', field2: 'b', field3: 'c' },
      },
      {
        id: '2',
        name: 'Task 2',
        meta: { fieldX: 'x' }, // Low match percentage
      },
    ] as any[]

    expect(hasConsistentMetadataStructure(tasks)).toBe(false)
  })

  it('should handle tasks without meta', () => {
    const tasks = [
      {
        id: '1',
        name: 'Task 1',
        meta: { field1: 'value' },
      },
      {
        id: '2',
        name: 'Task 2',
      },
    ] as any[]

    // Should ignore tasks without meta
    expect(hasConsistentMetadataStructure(tasks)).toBe(true)
  })

  it('should handle tasks with empty meta', () => {
    const tasks = [
      {
        id: '1',
        name: 'Task 1',
        meta: { field1: 'value' },
      },
      {
        id: '2',
        name: 'Task 2',
        meta: {},
      },
    ] as any[]

    // Should ignore tasks with empty meta
    expect(hasConsistentMetadataStructure(tasks)).toBe(true)
  })

  it('should return true when only one task has metadata', () => {
    const tasks = [
      {
        id: '1',
        name: 'Task 1',
        meta: { field1: 'value' },
      },
      {
        id: '2',
        name: 'Task 2',
      },
      {
        id: '3',
        name: 'Task 3',
      },
    ] as any[]

    expect(hasConsistentMetadataStructure(tasks)).toBe(true)
  })

  it('should sample only first 10 tasks with metadata', () => {
    const tasks = [
      ...Array.from({ length: 10 }, (_, i) => ({
        id: `${i}`,
        name: `Task ${i}`,
        meta: { field1: 'a', field2: 'b' },
      })),
      {
        id: '11',
        name: 'Task 11',
        meta: { completely: 'different' },
      },
    ] as any[]

    // Should return true because the 11th task is not checked
    expect(hasConsistentMetadataStructure(tasks)).toBe(true)
  })
})

describe('Edge Cases', () => {
  it('should handle empty strings in data', () => {
    const tasks = [
      {
        id: '1',
        name: 'Task 1',
        data: {
          empty_field: '',
          normal_field: 'value',
        },
      },
    ] as Task[]

    const columns = extractDataColumns(tasks)
    expect(columns.find((c) => c.key === 'empty_field')).toBeTruthy()
    expect(columns.find((c) => c.key === 'empty_field')?.type).toBe('text')
  })

  it('should handle zero values', () => {
    const tasks = [
      {
        id: '1',
        name: 'Task 1',
        data: {
          zero_number: 0,
          zero_string: '0',
        },
      },
    ] as Task[]

    const columns = extractDataColumns(tasks)
    expect(columns.find((c) => c.key === 'zero_number')?.type).toBe('number')
    expect(columns.find((c) => c.key === 'zero_string')?.type).toBe('text')
  })

  it('should handle false boolean values', () => {
    const result = formatCellValue(false, 'boolean')
    expect(result.display).toBe('✗')
    expect(result.full).toBe('false')
  })

  it('should handle mixed array types', () => {
    const tasks = [
      {
        id: '1',
        name: 'Task 1',
        data: {
          mixed_array: ['string', 123, true],
        },
      },
    ] as Task[]

    const columns = extractDataColumns(tasks)
    // Mixed simple arrays should still be included
    expect(columns.find((c) => c.key === 'mixed_array')).toBeTruthy()
  })

  it('should handle very long field names', () => {
    const longFieldName =
      'this_is_a_very_long_field_name_that_should_still_be_processed_correctly'
    const tasks = [
      {
        id: '1',
        name: 'Task 1',
        data: {
          [longFieldName]: 'value',
        },
      },
    ] as Task[]

    const columns = extractDataColumns(tasks)
    expect(columns.find((c) => c.key === longFieldName)).toBeTruthy()
    expect(
      columns.find((c) => c.key === longFieldName)?.label.length
    ).toBeGreaterThan(0)
  })

  it('should handle special characters in field names', () => {
    const fieldName = 'field-with-dashes'
    const tasks = [
      {
        id: '1',
        name: 'Task 1',
        data: {
          [fieldName]: 'value',
        },
      },
    ] as Task[]

    const columns = extractDataColumns(tasks)
    expect(columns.find((c) => c.key === fieldName)).toBeTruthy()
  })

  it('should handle unicode characters', () => {
    const tasks = [
      {
        id: '1',
        name: 'Task 1',
        data: {
          unicode_field: '日本語テキスト',
        },
      },
    ] as Task[]

    const columns = extractDataColumns(tasks)
    const result = formatCellValue('日本語テキスト', 'text')
    expect(result.display).toBe('日本語テキスト')
  })

  it('should handle negative numbers', () => {
    const result = formatCellValue(-42, 'number')
    expect(result.display).toBe('-42')
  })

  it('should handle decimal numbers', () => {
    const result = formatCellValue(3.14159, 'number')
    expect(result.display).toContain('3')
    expect(result.display).toContain('14')
  })

  it('should handle empty arrays', () => {
    const result = formatCellValue([], 'array')
    expect(result.display).toBe('')
    expect(result.full).toBe('')
    expect(result.truncated).toBe(false)
  })

  it('should handle very large numbers', () => {
    const result = formatCellValue(1000000000, 'number')
    expect(result.display).toContain('1')
    expect(result.display).toContain('000')
    expect(result.display.length).toBeGreaterThan(10)
  })
})

/**
 * Unit tests for nested data column helper utilities
 */

import { Task } from '@/lib/api/types'
import {
  detectValueType,
  extractNestedDataColumns,
  formatNestedCellValue,
  formatNestedFieldLabel,
  getTaskDisplayValueNested,
  getTaskNestedValue,
  hasConsistentNestedStructure,
  loadColumnConfig,
  saveColumnConfig,
} from '../nestedDataColumnHelpers'

// Mock localStorage
const localStorageMock = (() => {
  let store: Record<string, string> = {}
  return {
    getItem: (key: string) => store[key] || null,
    setItem: (key: string, value: string) => {
      store[key] = value
    },
    clear: () => {
      store = {}
    },
  }
})()

Object.defineProperty(window, 'localStorage', {
  value: localStorageMock,
})

describe('detectValueType', () => {
  it('should detect boolean type', () => {
    expect(detectValueType(true)).toBe('boolean')
    expect(detectValueType(false)).toBe('boolean')
  })

  it('should detect number type', () => {
    expect(detectValueType(123)).toBe('number')
    expect(detectValueType(3.14)).toBe('number')
    expect(detectValueType(0)).toBe('number')
  })

  it('should detect date strings', () => {
    expect(detectValueType('2024-01-15')).toBe('date')
    expect(detectValueType('2024-01-15T10:30:00')).toBe('date')
  })

  it('should detect text type', () => {
    expect(detectValueType('hello')).toBe('text')
    expect(detectValueType('not a date')).toBe('text')
  })

  it('should detect array type', () => {
    expect(detectValueType([])).toBe('array')
    expect(detectValueType([1, 2, 3])).toBe('array')
  })

  it('should detect object type', () => {
    expect(detectValueType({})).toBe('object')
    expect(detectValueType({ key: 'value' })).toBe('object')
  })

  it('should handle null and undefined', () => {
    expect(detectValueType(null)).toBe('text')
    expect(detectValueType(undefined)).toBe('text')
  })
})

describe('formatNestedFieldLabel', () => {
  it('should format simple field names', () => {
    expect(formatNestedFieldLabel('field_name')).toBe('Field Name')
    expect(formatNestedFieldLabel('camelCase')).toBe('Camel Case')
  })

  it('should format nested fields with separator', () => {
    expect(formatNestedFieldLabel('parent.child')).toBe('Parent › Child')
    expect(formatNestedFieldLabel('level1.level2.level3')).toBe(
      'Level1 › Level2 › Level3'
    )
  })

  it('should handle array indices', () => {
    expect(formatNestedFieldLabel('items[0]')).toBe('Items [0]')
    expect(formatNestedFieldLabel('data.items[2].name')).toBe(
      'Data › Items [2] Name' // No separator after array index
    )
  })

  it('should handle complex field names', () => {
    expect(formatNestedFieldLabel('prompts.prompt_clean')).toBe(
      'Prompts › Prompt Clean'
    )
    expect(formatNestedFieldLabel('number/name')).toBe('Number/name')
  })
})

describe('extractNestedDataColumns', () => {
  const mockTasks: Task[] = [
    {
      id: '1',
      data: {
        area: 'Treu und Glaube',
        'number/name': 'Fall 1',
        prompts: {
          prompt_clean: 'Question 1',
          prompt_enhanced: 'Enhanced question 1',
        },
        binary_solution: 'Ja',
      },
    },
    {
      id: '2',
      data: {
        area: 'Vertragsrecht',
        'number/name': 'Fall 2',
        prompts: {
          prompt_clean: 'Question 2',
          prompt_enhanced: 'Enhanced question 2',
        },
        binary_solution: 'Nein',
      },
    },
  ] as any

  it('should extract nested columns from tasks', () => {
    const columns = extractNestedDataColumns(mockTasks, 20, true)

    // Check that priority fields come first
    const keys = columns.map((c) => c.key)
    expect(keys).toContain('prompts.prompt_clean')
    expect(keys).toContain('area')
    expect(keys).toContain('number/name')
    expect(keys).toContain('binary_solution')

    // Check column properties
    const promptColumn = columns.find((c) => c.key === 'prompts.prompt_clean')
    expect(promptColumn).toBeDefined()
    expect(promptColumn?.isNested).toBe(true)
    expect(promptColumn?.depth).toBe(1)
    expect(promptColumn?.type).toBe('text')
  })

  it('should respect maxColumns parameter', () => {
    const columns = extractNestedDataColumns(mockTasks, 3, true)
    expect(columns.length).toBeLessThanOrEqual(3)
  })

  it('should include all nested fields including long text', () => {
    const tasksWithLongText: Task[] = [
      {
        id: '1',
        data: {
          short: 'short text',
          nested: {
            veryLongText: 'x'.repeat(600), // Over 500 chars
          },
        },
      },
    ] as any

    const columns = extractNestedDataColumns(tasksWithLongText, 20, true)
    const keys = columns.map((c) => c.key)
    expect(keys).toContain('short')
    // Changed: Now we include all nested fields per the implementation
    expect(keys).toContain('nested.veryLongText')
  })

  it('should handle empty tasks array', () => {
    const columns = extractNestedDataColumns([], 20, true)
    expect(columns).toEqual([])
  })

  it('should not include nested fields when includeNested is false', () => {
    const columns = extractNestedDataColumns(mockTasks, 20, false)
    const nestedColumns = columns.filter((c) => c.isNested)
    expect(nestedColumns).toHaveLength(0)
  })

  it('should prioritize fields correctly', () => {
    const columns = extractNestedDataColumns(mockTasks, 20, true)

    // Priority fields should come first
    const promptCleanIndex = columns.findIndex(
      (c) => c.key === 'prompts.prompt_clean'
    )
    const binarySolutionIndex = columns.findIndex(
      (c) => c.key === 'binary_solution'
    )
    const promptEnhancedIndex = columns.findIndex(
      (c) => c.key === 'prompts.prompt_enhanced'
    )

    // prompt_clean should come before prompt_enhanced (due to priority)
    if (promptCleanIndex !== -1 && promptEnhancedIndex !== -1) {
      expect(promptCleanIndex).toBeLessThan(promptEnhancedIndex)
    }
  })
})

describe('getTaskNestedValue', () => {
  const mockTask: Task = {
    id: '1',
    data: {
      simple: 'value',
      nested: {
        field: 'nested value',
        deep: {
          value: 42,
        },
      },
      array: [1, 2, 3],
    },
  } as any

  it('should get simple field value', () => {
    expect(getTaskNestedValue(mockTask, 'simple')).toBe('value')
  })

  it('should get nested field value', () => {
    expect(getTaskNestedValue(mockTask, 'nested.field')).toBe('nested value')
    expect(getTaskNestedValue(mockTask, 'nested.deep.value')).toBe(42)
  })

  it('should get array value', () => {
    expect(getTaskNestedValue(mockTask, 'array')).toEqual([1, 2, 3])
  })

  it('should return undefined for non-existent path', () => {
    expect(getTaskNestedValue(mockTask, 'nonexistent')).toBeUndefined()
    expect(getTaskNestedValue(mockTask, 'nested.nonexistent')).toBeUndefined()
  })

  it('should handle task without data', () => {
    const taskWithoutData = { id: '1' } as any
    expect(getTaskNestedValue(taskWithoutData, 'any.path')).toBeUndefined()
  })
})

describe('formatNestedCellValue', () => {
  it('should format boolean values', () => {
    expect(formatNestedCellValue(true, 'boolean')).toEqual({
      display: '✓',
      full: 'true',
      truncated: false,
    })
    expect(formatNestedCellValue(false, 'boolean')).toEqual({
      display: '✗',
      full: 'false',
      truncated: false,
    })
  })

  it('should format number values', () => {
    const result = formatNestedCellValue(1234, 'number')
    expect(result.truncated).toBe(false)
    // Check that it's formatted (either with comma or dot based on locale)
    expect(result.display).toMatch(/^1[,.]234$/)
    expect(result.full).toMatch(/^1[,.]234$/)
  })

  it('should format date values', () => {
    const result = formatNestedCellValue('2024-01-15', 'date')
    expect(result.truncated).toBe(false)
    expect(result.display).toContain('2024')
  })

  it('should format and truncate long text', () => {
    const longText = 'x'.repeat(150)
    const result = formatNestedCellValue(longText, 'text', 100)
    expect(result.truncated).toBe(true)
    expect(result.display).toHaveLength(103) // 100 + '...'
    expect(result.full).toBe(longText)
  })

  it('should format arrays', () => {
    const result = formatNestedCellValue(['apple', 'banana', 'orange'], 'array')
    expect(result.display).toBe('apple, banana, orange')
    expect(result.truncated).toBe(false)
  })

  it('should format objects as JSON', () => {
    const obj = { key: 'value', nested: { field: 'test' } }
    const result = formatNestedCellValue(obj, 'object')
    expect(result.truncated).toBe(true)
    expect(result.full).toContain('"key"')
    expect(result.full).toContain('"value"')
  })

  it('should handle null and undefined', () => {
    expect(formatNestedCellValue(null, 'text')).toEqual({
      display: '-',
      full: '-',
      truncated: false,
    })
    expect(formatNestedCellValue(undefined, 'text')).toEqual({
      display: '-',
      full: '-',
      truncated: false,
    })
  })
})

describe('getTaskDisplayValueNested', () => {
  it('should prioritize "fall" field', () => {
    const task = {
      id: '1',
      data: {
        fall: 'Case description',
        text: 'Other text',
        prompts: { prompt_clean: 'Prompt text' },
      },
    } as any
    expect(getTaskDisplayValueNested(task)).toBe('Case description')
  })

  it('should use nested prompt_clean as fallback', () => {
    const task = {
      id: '1',
      data: {
        prompts: { prompt_clean: 'Clean prompt text' },
        other: 'value',
      },
    } as any
    expect(getTaskDisplayValueNested(task)).toBe('Clean prompt text')
  })

  it('should truncate long values', () => {
    const longText = 'x'.repeat(200)
    const task = {
      id: '1',
      data: {
        text: longText,
      },
    } as any
    const result = getTaskDisplayValueNested(task)
    expect(result).toHaveLength(153) // 150 + '...'
    expect(result.endsWith('...')).toBe(true)
  })

  it('should fall back to task ID', () => {
    const task = {
      id: '123',
      data: {},
    } as any
    expect(getTaskDisplayValueNested(task)).toBe('Task 123')
  })

  it('should handle task without data', () => {
    const task = { id: '456' } as any
    expect(getTaskDisplayValueNested(task)).toBe('Task 456')
  })
})

describe('hasConsistentNestedStructure', () => {
  it('should return true for consistent structure', () => {
    const tasks = [
      { id: '1', data: { field1: 'a', field2: 'b' } },
      { id: '2', data: { field1: 'c', field2: 'd' } },
      { id: '3', data: { field1: 'e', field2: 'f' } },
    ] as any
    expect(hasConsistentNestedStructure(tasks)).toBe(true)
  })

  it('should return true if 60% of fields match', () => {
    const tasks = [
      { id: '1', data: { field1: 'a', field2: 'b', field3: 'c' } },
      { id: '2', data: { field1: 'd', field2: 'e' } }, // Missing field3
      { id: '3', data: { field1: 'f', field2: 'g', field3: 'h' } },
    ] as any
    expect(hasConsistentNestedStructure(tasks)).toBe(true)
  })

  it('should return false for inconsistent structure', () => {
    const tasks = [
      { id: '1', data: { field1: 'a' } },
      { id: '2', data: { completely: 'different', structure: 'here' } },
      { id: '3', data: { another: 'schema' } },
    ] as any
    expect(hasConsistentNestedStructure(tasks)).toBe(false)
  })

  it('should handle single task', () => {
    const tasks = [{ id: '1', data: { field: 'value' } }] as any
    expect(hasConsistentNestedStructure(tasks)).toBe(true)
  })

  it('should handle empty array', () => {
    expect(hasConsistentNestedStructure([])).toBe(true)
  })
})

describe('Column configuration persistence', () => {
  beforeEach(() => {
    localStorageMock.clear()
  })

  it('should save column configuration', () => {
    const columns = ['col1', 'col2', 'col3']
    saveColumnConfig('project123', columns)

    const stored = localStorageMock.getItem('benger_task_columns_config')
    expect(stored).toBeTruthy()
    const parsed = JSON.parse(stored!)
    expect(parsed['project123']).toEqual(columns)
  })

  it('should load column configuration', () => {
    const columns = ['col1', 'col2', 'col3']
    localStorageMock.setItem(
      'benger_task_columns_config',
      JSON.stringify({ project123: columns })
    )

    const loaded = loadColumnConfig('project123')
    expect(loaded).toEqual(columns)
  })

  it('should return null for non-existent project', () => {
    localStorageMock.setItem(
      'benger_task_columns_config',
      JSON.stringify({ other: ['col1'] })
    )

    const loaded = loadColumnConfig('project123')
    expect(loaded).toBeNull()
  })

  it('should handle localStorage errors gracefully', () => {
    // Simulate localStorage error
    const originalGetItem = localStorageMock.getItem
    localStorageMock.getItem = () => {
      throw new Error('Storage error')
    }

    const loaded = loadColumnConfig('project123')
    expect(loaded).toBeNull()

    localStorageMock.getItem = originalGetItem
  })
})

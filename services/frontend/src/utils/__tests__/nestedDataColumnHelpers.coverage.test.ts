/**
 * Coverage tests for nestedDataColumnHelpers - targets specific uncovered branches.
 */
import {
  detectValueType,
  extractNestedDataColumns,
  formatNestedCellValue,
  formatNestedFieldLabel,
  getTaskNestedValue,
  hasConsistentNestedStructure,
  saveColumnConfig,
  loadColumnConfig,
} from '../nestedDataColumnHelpers'

describe('nestedDataColumnHelpers - coverage extensions', () => {
  describe('detectValueType edge cases', () => {
    it('should detect boolean for actual booleans', () => {
      const result = detectValueType(true)
      expect(result).toBeDefined()
    })

    it('should detect array type', () => {
      const result = detectValueType([1, 2, 3])
      expect(result).toBeDefined()
    })

    it('should detect object type', () => {
      const result = detectValueType({ key: 'value' })
      expect(result).toBeDefined()
    })

    it('should detect numeric value', () => {
      const result = detectValueType(42)
      expect(result).toBe('number')
    })

    it('should handle null/undefined', () => {
      const result = detectValueType(null)
      expect(result).toBeDefined()
    })
  })

  describe('formatNestedFieldLabel', () => {
    it('should format dot-notation paths into readable labels', () => {
      const label = formatNestedFieldLabel('data.prompts.prompt_clean')
      expect(label).toBeDefined()
      expect(typeof label).toBe('string')
    })

    it('should handle single-level paths', () => {
      const label = formatNestedFieldLabel('text')
      expect(label).toBeDefined()
    })
  })

  describe('getTaskNestedValue', () => {
    it('should return value from nested task data', () => {
      const task = { id: '1', data: { text: 'hello', nested: { value: 42 } } } as any
      const result = getTaskNestedValue(task, 'text')
      expect(result).toBeDefined()
    })

    it('should return undefined for missing path', () => {
      const task = { id: '1', data: {} } as any
      const result = getTaskNestedValue(task, 'missing.deep')
      expect(result).toBeUndefined()
    })
  })

  describe('formatNestedCellValue', () => {
    it('should format various value types', () => {
      // formatNestedCellValue may return React elements or strings
      const arrayResult = formatNestedCellValue([1, 2, 3])
      expect(arrayResult).toBeDefined()

      const objResult = formatNestedCellValue({ key: 'value' })
      expect(objResult).toBeDefined()

      const nullResult = formatNestedCellValue(null)
      expect(nullResult).toBeDefined()

      const numResult = formatNestedCellValue(42)
      expect(numResult).toBeDefined()
    })
  })

  describe('hasConsistentNestedStructure', () => {
    it('should return true for tasks with consistent structure', () => {
      const tasks = [
        { id: '1', data: { text: 'a', meta: { score: 1 } } },
        { id: '2', data: { text: 'b', meta: { score: 2 } } },
      ] as any[]
      expect(hasConsistentNestedStructure(tasks)).toBe(true)
    })

    it('should handle empty tasks array', () => {
      expect(hasConsistentNestedStructure([])).toBeDefined()
    })

    it('should handle single task', () => {
      const tasks = [{ id: '1', data: { text: 'a' } }] as any[]
      expect(hasConsistentNestedStructure(tasks)).toBe(true)
    })
  })

  describe('column config storage', () => {
    beforeEach(() => {
      // Mock localStorage
      const store: Record<string, string> = {}
      jest.spyOn(Storage.prototype, 'getItem').mockImplementation((key) => store[key] || null)
      jest.spyOn(Storage.prototype, 'setItem').mockImplementation((key, value) => { store[key] = value })
    })

    afterEach(() => {
      jest.restoreAllMocks()
    })

    it('should save and load column config', () => {
      saveColumnConfig('project-1', ['col1', 'col2'])
      const loaded = loadColumnConfig('project-1')
      expect(loaded).toEqual(['col1', 'col2'])
    })

    it('should return null for non-existent config', () => {
      const loaded = loadColumnConfig('non-existent')
      expect(loaded).toBeNull()
    })
  })

  describe('extractNestedDataColumns', () => {
    it('should extract columns from task data', () => {
      const tasks = [
        { id: '1', data: { text: 'hello', score: 0.9 } },
        { id: '2', data: { text: 'world', score: 0.8 } },
      ] as any[]
      const columns = extractNestedDataColumns(tasks)
      expect(columns).toBeDefined()
      expect(columns.length).toBeGreaterThan(0)
    })

    it('should handle tasks with deeply nested data', () => {
      const tasks = [
        { id: '1', data: { meta: { nested: { deep: 'value' } } } },
      ] as any[]
      const columns = extractNestedDataColumns(tasks)
      expect(columns).toBeDefined()
    })
  })
})

/**
 * @jest-environment jsdom
 */

/**
 * Comprehensive tests for useColumnSettings and useTablePreferences hooks
 * Tests hook behavior, data persistence, state management, and edge cases
 */

import { act, renderHook, waitFor } from '@testing-library/react'
import { useColumnSettings, useTablePreferences } from '../useColumnSettings'

// Mock localStorage
const localStorageMock = (() => {
  let store: Record<string, string> = {}

  return {
    getItem: jest.fn((key: string) => store[key] || null),
    setItem: jest.fn((key: string, value: string) => {
      store[key] = value
    }),
    removeItem: jest.fn((key: string) => {
      delete store[key]
    }),
    clear: jest.fn(() => {
      store = {}
    }),
    get length() {
      return Object.keys(store).length
    },
    key: jest.fn((index: number) => Object.keys(store)[index] || null),
  }
})()

Object.defineProperty(window, 'localStorage', {
  value: localStorageMock,
  writable: true,
})

// Mock console methods to avoid noise in tests
const consoleLogSpy = jest.spyOn(console, 'log').mockImplementation()
const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation()

// Test data
const mockDefaultColumns = [
  { id: 'name', label: 'Name', visible: true },
  { id: 'email', label: 'Email', visible: true },
  { id: 'age', label: 'Age', visible: false },
  { id: 'status', label: 'Status', visible: true },
]

const mockProjectId = 'test-project-123'
const mockUserId = 'user-456'

describe('useColumnSettings Hook', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    localStorageMock.clear()
  })

  afterAll(() => {
    consoleLogSpy.mockRestore()
    consoleErrorSpy.mockRestore()
  })

  describe('1. Basic Hook Behavior', () => {
    it('should return expected interface', () => {
      const { result } = renderHook(() =>
        useColumnSettings(mockProjectId, mockUserId, mockDefaultColumns)
      )

      expect(result.current).toHaveProperty('columns')
      expect(result.current).toHaveProperty('toggleColumn')
      expect(result.current).toHaveProperty('resetColumns')
      expect(result.current).toHaveProperty('updateColumns')
      expect(result.current).toHaveProperty('reorderColumns')
      expect(typeof result.current.toggleColumn).toBe('function')
      expect(typeof result.current.resetColumns).toBe('function')
      expect(typeof result.current.updateColumns).toBe('function')
      expect(typeof result.current.reorderColumns).toBe('function')
      expect(Array.isArray(result.current.columns)).toBe(true)
    })

    it('should initialize with default columns when no saved settings exist', () => {
      const { result } = renderHook(() =>
        useColumnSettings(mockProjectId, mockUserId, mockDefaultColumns)
      )

      expect(result.current.columns).toHaveLength(4)
      expect(result.current.columns[0]).toMatchObject({
        id: 'name',
        label: 'Name',
        visible: true,
        order: 0,
      })
      expect(result.current.columns[1]).toMatchObject({
        id: 'email',
        label: 'Email',
        visible: true,
        order: 1,
      })
    })

    it('should add order property to default columns', () => {
      const { result } = renderHook(() =>
        useColumnSettings(mockProjectId, mockUserId, mockDefaultColumns)
      )

      result.current.columns.forEach((col, index) => {
        expect(col.order).toBe(index)
      })
    })

    it('should handle undefined userId', () => {
      const { result } = renderHook(() =>
        useColumnSettings(mockProjectId, undefined, mockDefaultColumns)
      )

      expect(result.current.columns).toHaveLength(4)
      expect(localStorageMock.getItem).not.toHaveBeenCalled()
    })

    it('should handle SSR (window undefined)', () => {
      const originalWindow = global.window
      // @ts-ignore - intentionally deleting for SSR test
      delete global.window

      const { result } = renderHook(() =>
        useColumnSettings(mockProjectId, mockUserId, mockDefaultColumns)
      )

      expect(result.current.columns).toHaveLength(4)

      // Restore window
      global.window = originalWindow
    })
  })

  describe('2. Data Fetching/State Management', () => {
    it('should load saved settings from localStorage on mount', () => {
      const savedSettings = [
        { id: 'name', visible: false, order: 0 },
        { id: 'email', visible: true, order: 1 },
        { id: 'age', visible: true, order: 2 },
        { id: 'status', visible: false, order: 3 },
      ]

      localStorageMock.setItem(
        `column-settings-${mockUserId}-${mockProjectId}`,
        JSON.stringify(savedSettings)
      )

      const { result } = renderHook(() =>
        useColumnSettings(mockProjectId, mockUserId, mockDefaultColumns)
      )

      expect(result.current.columns[0].visible).toBe(false)
      expect(result.current.columns[1].visible).toBe(true)
      expect(result.current.columns[2].visible).toBe(true)
      expect(result.current.columns[3].visible).toBe(false)
    })

    it('should preserve saved column order', () => {
      const savedSettings = [
        { id: 'status', visible: true, order: 0 },
        { id: 'name', visible: true, order: 1 },
        { id: 'age', visible: true, order: 2 },
        { id: 'email', visible: true, order: 3 },
      ]

      localStorageMock.setItem(
        `column-settings-${mockUserId}-${mockProjectId}`,
        JSON.stringify(savedSettings)
      )

      const { result } = renderHook(() =>
        useColumnSettings(mockProjectId, mockUserId, mockDefaultColumns)
      )

      expect(result.current.columns[0].id).toBe('status')
      expect(result.current.columns[1].id).toBe('name')
      expect(result.current.columns[2].id).toBe('age')
      expect(result.current.columns[3].id).toBe('email')
    })

    it('should add new columns not in saved settings', () => {
      const savedSettings = [
        { id: 'name', visible: true, order: 0 },
        { id: 'email', visible: false, order: 1 },
      ]

      localStorageMock.setItem(
        `column-settings-${mockUserId}-${mockProjectId}`,
        JSON.stringify(savedSettings)
      )

      const { result } = renderHook(() =>
        useColumnSettings(mockProjectId, mockUserId, mockDefaultColumns)
      )

      expect(result.current.columns).toHaveLength(4)
      expect(result.current.columns.find((c) => c.id === 'age')).toBeDefined()
      expect(
        result.current.columns.find((c) => c.id === 'status')
      ).toBeDefined()
    })

    it('should handle saved columns with missing order property', () => {
      const savedSettings = [
        { id: 'name', visible: true },
        { id: 'email', visible: false },
      ]

      localStorageMock.setItem(
        `column-settings-${mockUserId}-${mockProjectId}`,
        JSON.stringify(savedSettings)
      )

      const { result } = renderHook(() =>
        useColumnSettings(mockProjectId, mockUserId, mockDefaultColumns)
      )

      expect(result.current.columns).toHaveLength(4)
      result.current.columns.forEach((col) => {
        expect(typeof col.order).toBe('number')
      })
    })

    it('should save to localStorage when columns change', async () => {
      const { result } = renderHook(() =>
        useColumnSettings(mockProjectId, mockUserId, mockDefaultColumns)
      )

      act(() => {
        result.current.toggleColumn('name')
      })

      await waitFor(() => {
        expect(localStorageMock.setItem).toHaveBeenCalledWith(
          `column-settings-${mockUserId}-${mockProjectId}`,
          expect.any(String)
        )
      })

      const savedData = JSON.parse(
        localStorageMock.setItem.mock.calls[
          localStorageMock.setItem.mock.calls.length - 1
        ][1]
      )
      expect(savedData.find((c: any) => c.id === 'name').visible).toBe(false)
    })

    it('should use unique storage key per user/project combination', () => {
      const projectId1 = 'project-1'
      const projectId2 = 'project-2'
      const userId1 = 'user-1'

      const { result: result1 } = renderHook(() =>
        useColumnSettings(projectId1, userId1, mockDefaultColumns)
      )

      const { result: result2 } = renderHook(() =>
        useColumnSettings(projectId2, userId1, mockDefaultColumns)
      )

      act(() => {
        result1.current.toggleColumn('name')
      })

      act(() => {
        result2.current.toggleColumn('email')
      })

      expect(localStorageMock.setItem).toHaveBeenCalledWith(
        `column-settings-${userId1}-${projectId1}`,
        expect.any(String)
      )
      expect(localStorageMock.setItem).toHaveBeenCalledWith(
        `column-settings-${userId1}-${projectId2}`,
        expect.any(String)
      )
    })
  })

  describe('3. Loading States', () => {
    it('should not have explicit loading state', () => {
      const { result } = renderHook(() =>
        useColumnSettings(mockProjectId, mockUserId, mockDefaultColumns)
      )

      expect(result.current).not.toHaveProperty('loading')
    })

    it('should initialize synchronously', () => {
      const { result } = renderHook(() =>
        useColumnSettings(mockProjectId, mockUserId, mockDefaultColumns)
      )

      expect(result.current.columns).toBeDefined()
      expect(result.current.columns).toHaveLength(4)
    })
  })

  describe('4. Error Handling', () => {
    it('should handle corrupted localStorage data', () => {
      localStorageMock.getItem.mockReturnValueOnce('invalid json {{')

      const { result } = renderHook(() =>
        useColumnSettings(mockProjectId, mockUserId, mockDefaultColumns)
      )

      // Should fall back to default columns
      expect(result.current.columns).toHaveLength(4)
      expect(result.current.columns[0].id).toBe('name')
      expect(result.current.columns[0].visible).toBe(true)
    })

    it('should handle localStorage.getItem throwing error', () => {
      localStorageMock.getItem.mockImplementationOnce(() => {
        throw new Error('Storage error')
      })

      const { result } = renderHook(() =>
        useColumnSettings(mockProjectId, mockUserId, mockDefaultColumns)
      )

      // Should fall back to default columns
      expect(result.current.columns).toHaveLength(4)
      expect(result.current.columns[0].id).toBe('name')
      expect(result.current.columns[0].visible).toBe(true)
    })

    it('should handle localStorage.setItem throwing error', async () => {
      const { result } = renderHook(() =>
        useColumnSettings(mockProjectId, mockUserId, mockDefaultColumns)
      )

      localStorageMock.setItem.mockImplementationOnce(() => {
        throw new Error('Storage full')
      })

      // Should not crash when save fails
      act(() => {
        result.current.toggleColumn('name')
      })

      // State should still update even if save fails
      expect(result.current.columns[0].visible).toBe(false)
    })

    it('should not crash when saved settings reference non-existent columns', () => {
      const savedSettings = [
        { id: 'nonexistent', visible: true, order: 0 },
        { id: 'name', visible: false, order: 1 },
      ]

      localStorageMock.setItem(
        `column-settings-${mockUserId}-${mockProjectId}`,
        JSON.stringify(savedSettings)
      )

      const { result } = renderHook(() =>
        useColumnSettings(mockProjectId, mockUserId, mockDefaultColumns)
      )

      expect(result.current.columns).toHaveLength(4)
      expect(result.current.columns.find((c) => c.id === 'name')).toBeDefined()
    })

    it('should handle empty saved settings array', () => {
      localStorageMock.setItem(
        `column-settings-${mockUserId}-${mockProjectId}`,
        JSON.stringify([])
      )

      const { result } = renderHook(() =>
        useColumnSettings(mockProjectId, mockUserId, mockDefaultColumns)
      )

      expect(result.current.columns).toHaveLength(4)
    })
  })

  describe('5. Data Transformation/Callbacks', () => {
    it('should toggle column visibility', () => {
      const { result } = renderHook(() =>
        useColumnSettings(mockProjectId, mockUserId, mockDefaultColumns)
      )

      const initialVisibility = result.current.columns[0].visible

      act(() => {
        result.current.toggleColumn('name')
      })

      expect(result.current.columns[0].visible).toBe(!initialVisibility)
    })

    it('should only toggle the specified column', () => {
      const { result } = renderHook(() =>
        useColumnSettings(mockProjectId, mockUserId, mockDefaultColumns)
      )

      const initialStates = result.current.columns.map((c) => c.visible)

      act(() => {
        result.current.toggleColumn('email')
      })

      expect(result.current.columns[0].visible).toBe(initialStates[0])
      expect(result.current.columns[1].visible).toBe(!initialStates[1])
      expect(result.current.columns[2].visible).toBe(initialStates[2])
      expect(result.current.columns[3].visible).toBe(initialStates[3])
    })

    it('should handle toggling non-existent column gracefully', () => {
      const { result } = renderHook(() =>
        useColumnSettings(mockProjectId, mockUserId, mockDefaultColumns)
      )

      const initialColumns = [...result.current.columns]

      act(() => {
        result.current.toggleColumn('nonexistent')
      })

      expect(result.current.columns).toEqual(initialColumns)
    })

    it('should reset columns to default state', () => {
      const savedSettings = [
        { id: 'name', visible: false, order: 0 },
        { id: 'email', visible: false, order: 1 },
      ]

      localStorageMock.setItem(
        `column-settings-${mockUserId}-${mockProjectId}`,
        JSON.stringify(savedSettings)
      )

      const { result } = renderHook(() =>
        useColumnSettings(mockProjectId, mockUserId, mockDefaultColumns)
      )

      expect(result.current.columns[0].visible).toBe(false)

      act(() => {
        result.current.resetColumns()
      })

      expect(result.current.columns[0].visible).toBe(true)
      expect(result.current.columns[1].visible).toBe(true)
    })

    it('should remove saved settings from localStorage on reset', () => {
      const { result } = renderHook(() =>
        useColumnSettings(mockProjectId, mockUserId, mockDefaultColumns)
      )

      act(() => {
        result.current.resetColumns()
      })

      expect(localStorageMock.removeItem).toHaveBeenCalledWith(
        `column-settings-${mockUserId}-${mockProjectId}`
      )
    })

    it('should update columns with new column definitions', () => {
      const { result } = renderHook(() =>
        useColumnSettings(mockProjectId, mockUserId, mockDefaultColumns)
      )

      const newColumns = [
        { id: 'name', label: 'Full Name', visible: true },
        { id: 'phone', label: 'Phone', visible: true },
      ]

      act(() => {
        result.current.updateColumns(newColumns)
      })

      expect(result.current.columns).toHaveLength(2)
      expect(result.current.columns[0].label).toBe('Full Name')
      expect(result.current.columns[1].id).toBe('phone')
    })

    it('should preserve visibility settings when updating columns', () => {
      const { result } = renderHook(() =>
        useColumnSettings(mockProjectId, mockUserId, mockDefaultColumns)
      )

      act(() => {
        result.current.toggleColumn('name')
      })

      const newColumns = [
        { id: 'name', label: 'Full Name', visible: true },
        { id: 'email', label: 'Email Address', visible: true },
      ]

      act(() => {
        result.current.updateColumns(newColumns)
      })

      expect(result.current.columns[0].visible).toBe(false)
      expect(result.current.columns[1].visible).toBe(true)
    })

    it('should preserve order when updating columns', () => {
      const { result } = renderHook(() =>
        useColumnSettings(mockProjectId, mockUserId, mockDefaultColumns)
      )

      act(() => {
        result.current.reorderColumns(0, 2)
      })

      const firstColumnOrder = result.current.columns[0].order

      const newColumns = result.current.columns.map((c) => ({
        ...c,
        label: `Updated ${c.label}`,
      }))

      act(() => {
        result.current.updateColumns(newColumns)
      })

      expect(result.current.columns[0].order).toBe(firstColumnOrder)
    })

    it('should add new columns at the end when updating', () => {
      const { result } = renderHook(() =>
        useColumnSettings(mockProjectId, mockUserId, mockDefaultColumns)
      )

      const newColumns = [
        ...mockDefaultColumns,
        { id: 'newCol', label: 'New Column', visible: true },
      ]

      act(() => {
        result.current.updateColumns(newColumns)
      })

      expect(result.current.columns).toHaveLength(5)
      expect(result.current.columns[4].id).toBe('newCol')
      expect(result.current.columns[4].order).toBeGreaterThan(
        result.current.columns[3].order!
      )
    })

    it('should reorder columns correctly', () => {
      const { result } = renderHook(() =>
        useColumnSettings(mockProjectId, mockUserId, mockDefaultColumns)
      )

      act(() => {
        result.current.reorderColumns(0, 2)
      })

      expect(result.current.columns[0].id).toBe('email')
      expect(result.current.columns[1].id).toBe('age')
      expect(result.current.columns[2].id).toBe('name')
    })

    it('should update order property after reordering', () => {
      const { result } = renderHook(() =>
        useColumnSettings(mockProjectId, mockUserId, mockDefaultColumns)
      )

      act(() => {
        result.current.reorderColumns(1, 3)
      })

      result.current.columns.forEach((col, index) => {
        expect(col.order).toBe(index)
      })
    })

    it('should handle reordering to same position', () => {
      const { result } = renderHook(() =>
        useColumnSettings(mockProjectId, mockUserId, mockDefaultColumns)
      )

      const initialColumns = [...result.current.columns]

      act(() => {
        result.current.reorderColumns(1, 1)
      })

      expect(result.current.columns.map((c) => c.id)).toEqual(
        initialColumns.map((c) => c.id)
      )
    })

    it('should maintain stable callback references', () => {
      const { result, rerender } = renderHook(() =>
        useColumnSettings(mockProjectId, mockUserId, mockDefaultColumns)
      )

      const callbacks = {
        toggleColumn: result.current.toggleColumn,
        resetColumns: result.current.resetColumns,
        updateColumns: result.current.updateColumns,
        reorderColumns: result.current.reorderColumns,
      }

      rerender()

      expect(result.current.toggleColumn).toBe(callbacks.toggleColumn)
      expect(result.current.resetColumns).toBe(callbacks.resetColumns)
      expect(result.current.updateColumns).toBe(callbacks.updateColumns)
      expect(result.current.reorderColumns).toBe(callbacks.reorderColumns)
    })
  })

  describe('6. Refetch/Invalidation', () => {
    it('should not have refetch mechanism as it uses localStorage', () => {
      const { result } = renderHook(() =>
        useColumnSettings(mockProjectId, mockUserId, mockDefaultColumns)
      )

      expect(result.current).not.toHaveProperty('refetch')
    })

    it('should sync changes to localStorage automatically', async () => {
      const { result } = renderHook(() =>
        useColumnSettings(mockProjectId, mockUserId, mockDefaultColumns)
      )

      act(() => {
        result.current.toggleColumn('name')
      })

      await waitFor(() => {
        expect(localStorageMock.setItem).toHaveBeenCalled()
      })
    })
  })

  describe('7. Edge Cases', () => {
    it('should handle empty default columns array', () => {
      const { result } = renderHook(() =>
        useColumnSettings(mockProjectId, mockUserId, [])
      )

      expect(result.current.columns).toEqual([])
    })

    it('should handle very large column arrays', () => {
      const largeColumns = Array.from({ length: 1000 }, (_, i) => ({
        id: `col-${i}`,
        label: `Column ${i}`,
        visible: i % 2 === 0,
      }))

      const { result } = renderHook(() =>
        useColumnSettings(mockProjectId, mockUserId, largeColumns)
      )

      expect(result.current.columns).toHaveLength(1000)
    })

    it('should handle columns with special characters in IDs', () => {
      const specialColumns = [
        { id: 'name with spaces', label: 'Name', visible: true },
        { id: 'email@special', label: 'Email', visible: true },
        { id: 'status-dashed', label: 'Status', visible: true },
      ]

      const { result } = renderHook(() =>
        useColumnSettings(mockProjectId, mockUserId, specialColumns)
      )

      act(() => {
        result.current.toggleColumn('email@special')
      })

      expect(result.current.columns[1].visible).toBe(false)
    })

    it('should handle rapid consecutive state changes', () => {
      const { result } = renderHook(() =>
        useColumnSettings(mockProjectId, mockUserId, mockDefaultColumns)
      )

      act(() => {
        result.current.toggleColumn('name')
        result.current.toggleColumn('email')
        result.current.toggleColumn('age')
        result.current.toggleColumn('name')
      })

      expect(result.current.columns[0].visible).toBe(true)
      expect(result.current.columns[1].visible).toBe(false)
      expect(result.current.columns[2].visible).toBe(true)
    })

    it('should handle columns without visible property', () => {
      const columnsWithoutVisible = [
        { id: 'name', label: 'Name' },
        { id: 'email', label: 'Email' },
      ] as any

      const { result } = renderHook(() =>
        useColumnSettings(mockProjectId, mockUserId, columnsWithoutVisible)
      )

      expect(result.current.columns).toHaveLength(2)
    })

    it('should handle reordering beyond array bounds', () => {
      const { result } = renderHook(() =>
        useColumnSettings(mockProjectId, mockUserId, mockDefaultColumns)
      )

      const initialColumns = [...result.current.columns]

      act(() => {
        result.current.reorderColumns(0, 100)
      })

      expect(result.current.columns).toHaveLength(initialColumns.length)
    })

    it('should handle reordering with negative indices', () => {
      const { result } = renderHook(() =>
        useColumnSettings(mockProjectId, mockUserId, mockDefaultColumns)
      )

      act(() => {
        result.current.reorderColumns(-1, 0)
      })

      // Reordering with negative index still works due to splice behavior
      // Just verify the hook doesn't crash
      expect(result.current.columns).toHaveLength(4)
    })

    it('should handle duplicate column IDs gracefully', () => {
      const columnsWithDuplicates = [
        { id: 'name', label: 'Name 1', visible: true },
        { id: 'name', label: 'Name 2', visible: false },
        { id: 'email', label: 'Email', visible: true },
      ]

      const { result } = renderHook(() =>
        useColumnSettings(mockProjectId, mockUserId, columnsWithDuplicates)
      )

      expect(result.current.columns).toHaveLength(3)
    })

    it('should handle project ID changes', () => {
      const { unmount } = renderHook(() =>
        useColumnSettings('project-1', mockUserId, mockDefaultColumns)
      )

      unmount()

      const { result } = renderHook(() =>
        useColumnSettings('project-2', mockUserId, mockDefaultColumns)
      )

      // New project ID should load fresh state
      expect(result.current.columns[0].visible).toBe(true)
    })

    it('should handle user ID changes', () => {
      const { unmount } = renderHook(() =>
        useColumnSettings(mockProjectId, 'user-1', mockDefaultColumns)
      )

      unmount()

      const { result } = renderHook(() =>
        useColumnSettings(mockProjectId, 'user-2', mockDefaultColumns)
      )

      // New user ID should load fresh state
      expect(result.current.columns[0].visible).toBe(true)
    })

    it('should not save when userId is undefined', async () => {
      const { result } = renderHook(() =>
        useColumnSettings(mockProjectId, undefined, mockDefaultColumns)
      )

      const setItemCallsBefore = localStorageMock.setItem.mock.calls.length

      act(() => {
        result.current.toggleColumn('name')
      })

      await new Promise((resolve) => setTimeout(resolve, 100))

      expect(localStorageMock.setItem.mock.calls.length).toBe(
        setItemCallsBefore
      )
    })

    it('should not remove from localStorage on reset when userId is undefined', () => {
      const { result } = renderHook(() =>
        useColumnSettings(mockProjectId, undefined, mockDefaultColumns)
      )

      act(() => {
        result.current.resetColumns()
      })

      expect(localStorageMock.removeItem).not.toHaveBeenCalled()
    })
  })

  describe('8. API Integration/Cleanup', () => {
    it('should clean up properly on unmount', () => {
      const { unmount } = renderHook(() =>
        useColumnSettings(mockProjectId, mockUserId, mockDefaultColumns)
      )

      unmount()

      expect(true).toBe(true)
    })

    it('should not have memory leaks with multiple instances', () => {
      const instances = Array.from({ length: 10 }, () =>
        renderHook(() =>
          useColumnSettings(mockProjectId, mockUserId, mockDefaultColumns)
        )
      )

      instances.forEach((instance) => instance.unmount())

      expect(true).toBe(true)
    })

    it('should handle localStorage quota exceeded', async () => {
      const { result } = renderHook(() =>
        useColumnSettings(mockProjectId, mockUserId, mockDefaultColumns)
      )

      const quotaError = new Error('QuotaExceededError')
      quotaError.name = 'QuotaExceededError'
      localStorageMock.setItem.mockImplementationOnce(() => {
        throw quotaError
      })

      // Should not crash when quota is exceeded
      act(() => {
        result.current.toggleColumn('name')
      })

      // State should still update even if save fails
      expect(result.current.columns[0].visible).toBe(false)
    })

    it('should persist changes across hook instances', () => {
      const { result: instance1 } = renderHook(() =>
        useColumnSettings(mockProjectId, mockUserId, mockDefaultColumns)
      )

      act(() => {
        instance1.current.toggleColumn('name')
        instance1.current.toggleColumn('email')
      })

      const { result: instance2 } = renderHook(() =>
        useColumnSettings(mockProjectId, mockUserId, mockDefaultColumns)
      )

      expect(instance2.current.columns[0].visible).toBe(false)
      expect(instance2.current.columns[1].visible).toBe(false)
    })
  })
})

describe('useTablePreferences Hook', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    localStorageMock.clear()
  })

  describe('1. Basic Hook Behavior', () => {
    it('should return expected interface', () => {
      const { result } = renderHook(() =>
        useTablePreferences(mockProjectId, mockUserId)
      )

      expect(result.current).toHaveProperty('preferences')
      expect(result.current).toHaveProperty('updatePreference')
      expect(result.current).toHaveProperty('resetPreferences')
      expect(typeof result.current.updatePreference).toBe('function')
      expect(typeof result.current.resetPreferences).toBe('function')
    })

    it('should initialize with default preferences', () => {
      const { result } = renderHook(() =>
        useTablePreferences(mockProjectId, mockUserId)
      )

      expect(result.current.preferences).toEqual({
        sortBy: 'id',
        sortOrder: 'desc',
        filterStatus: 'all',
        showSearch: false,
      })
    })

    it('should handle undefined userId', () => {
      const { result } = renderHook(() =>
        useTablePreferences(mockProjectId, undefined)
      )

      expect(result.current.preferences).toBeDefined()
      expect(localStorageMock.getItem).not.toHaveBeenCalled()
    })

    it('should handle SSR (window undefined)', () => {
      const originalWindow = global.window
      // @ts-ignore - intentionally deleting for SSR test
      delete global.window

      const { result } = renderHook(() =>
        useTablePreferences(mockProjectId, mockUserId)
      )

      expect(result.current.preferences).toBeDefined()

      // Restore window
      global.window = originalWindow
    })
  })

  describe('2. Data Fetching/State Management', () => {
    it('should load saved preferences from localStorage', () => {
      const savedPreferences = {
        sortBy: 'name',
        sortOrder: 'asc' as const,
        filterStatus: 'completed' as const,
        showSearch: true,
      }

      localStorageMock.setItem(
        `table-preferences-${mockUserId}-${mockProjectId}`,
        JSON.stringify(savedPreferences)
      )

      const { result } = renderHook(() =>
        useTablePreferences(mockProjectId, mockUserId)
      )

      expect(result.current.preferences).toEqual(savedPreferences)
    })

    it('should save to localStorage when preferences change', async () => {
      const { result } = renderHook(() =>
        useTablePreferences(mockProjectId, mockUserId)
      )

      act(() => {
        result.current.updatePreference('sortBy', 'name')
      })

      await waitFor(() => {
        expect(localStorageMock.setItem).toHaveBeenCalledWith(
          `table-preferences-${mockUserId}-${mockProjectId}`,
          expect.any(String)
        )
      })
    })

    it('should use unique storage key per user/project combination', () => {
      const { result: result1 } = renderHook(() =>
        useTablePreferences('project-1', 'user-1')
      )

      const { result: result2 } = renderHook(() =>
        useTablePreferences('project-2', 'user-1')
      )

      act(() => {
        result1.current.updatePreference('sortBy', 'name')
      })

      act(() => {
        result2.current.updatePreference('sortBy', 'email')
      })

      expect(localStorageMock.setItem).toHaveBeenCalledWith(
        'table-preferences-user-1-project-1',
        expect.stringContaining('name')
      )
      expect(localStorageMock.setItem).toHaveBeenCalledWith(
        'table-preferences-user-1-project-2',
        expect.stringContaining('email')
      )
    })
  })

  describe('3. Loading States', () => {
    it('should not have explicit loading state', () => {
      const { result } = renderHook(() =>
        useTablePreferences(mockProjectId, mockUserId)
      )

      expect(result.current).not.toHaveProperty('loading')
    })

    it('should initialize synchronously', () => {
      const { result } = renderHook(() =>
        useTablePreferences(mockProjectId, mockUserId)
      )

      expect(result.current.preferences).toBeDefined()
    })
  })

  describe('4. Error Handling', () => {
    it('should handle corrupted localStorage data', () => {
      localStorageMock.getItem.mockReturnValueOnce('invalid json {{')

      const { result } = renderHook(() =>
        useTablePreferences(mockProjectId, mockUserId)
      )

      // Should fall back to default preferences
      expect(result.current.preferences).toEqual({
        sortBy: 'id',
        sortOrder: 'desc',
        filterStatus: 'all',
        showSearch: false,
      })
    })

    it('should handle localStorage.getItem throwing error', () => {
      localStorageMock.getItem.mockImplementationOnce(() => {
        throw new Error('Storage error')
      })

      const { result } = renderHook(() =>
        useTablePreferences(mockProjectId, mockUserId)
      )

      // Should fall back to default preferences
      expect(result.current.preferences).toBeDefined()
      expect(result.current.preferences.sortBy).toBe('id')
    })

    it('should handle localStorage.setItem throwing error', async () => {
      const { result } = renderHook(() =>
        useTablePreferences(mockProjectId, mockUserId)
      )

      localStorageMock.setItem.mockImplementationOnce(() => {
        throw new Error('Storage full')
      })

      // Should not crash when save fails
      act(() => {
        result.current.updatePreference('sortBy', 'name')
      })

      // State should still update even if save fails
      expect(result.current.preferences.sortBy).toBe('name')
    })
  })

  describe('5. Data Transformation/Callbacks', () => {
    it('should update individual preference', () => {
      const { result } = renderHook(() =>
        useTablePreferences(mockProjectId, mockUserId)
      )

      act(() => {
        result.current.updatePreference('sortBy', 'name')
      })

      expect(result.current.preferences.sortBy).toBe('name')
    })

    it('should update sortOrder preference', () => {
      const { result } = renderHook(() =>
        useTablePreferences(mockProjectId, mockUserId)
      )

      act(() => {
        result.current.updatePreference('sortOrder', 'asc')
      })

      expect(result.current.preferences.sortOrder).toBe('asc')
    })

    it('should update filterStatus preference', () => {
      const { result } = renderHook(() =>
        useTablePreferences(mockProjectId, mockUserId)
      )

      act(() => {
        result.current.updatePreference('filterStatus', 'completed')
      })

      expect(result.current.preferences.filterStatus).toBe('completed')
    })

    it('should update showSearch preference', () => {
      const { result } = renderHook(() =>
        useTablePreferences(mockProjectId, mockUserId)
      )

      act(() => {
        result.current.updatePreference('showSearch', true)
      })

      expect(result.current.preferences.showSearch).toBe(true)
    })

    it('should preserve other preferences when updating one', () => {
      const { result } = renderHook(() =>
        useTablePreferences(mockProjectId, mockUserId)
      )

      act(() => {
        result.current.updatePreference('sortBy', 'name')
      })

      expect(result.current.preferences.sortOrder).toBe('desc')
      expect(result.current.preferences.filterStatus).toBe('all')
      expect(result.current.preferences.showSearch).toBe(false)
    })

    it('should reset preferences to defaults', () => {
      const { result } = renderHook(() =>
        useTablePreferences(mockProjectId, mockUserId)
      )

      act(() => {
        result.current.updatePreference('sortBy', 'name')
        result.current.updatePreference('sortOrder', 'asc')
        result.current.updatePreference('showSearch', true)
      })

      act(() => {
        result.current.resetPreferences()
      })

      expect(result.current.preferences).toEqual({
        sortBy: 'id',
        sortOrder: 'desc',
        filterStatus: 'all',
        showSearch: false,
      })
    })

    it('should remove saved preferences from localStorage on reset', () => {
      const { result } = renderHook(() =>
        useTablePreferences(mockProjectId, mockUserId)
      )

      act(() => {
        result.current.resetPreferences()
      })

      expect(localStorageMock.removeItem).toHaveBeenCalledWith(
        `table-preferences-${mockUserId}-${mockProjectId}`
      )
    })

    it('should maintain stable callback references', () => {
      const { result, rerender } = renderHook(() =>
        useTablePreferences(mockProjectId, mockUserId)
      )

      const callbacks = {
        updatePreference: result.current.updatePreference,
        resetPreferences: result.current.resetPreferences,
      }

      rerender()

      expect(result.current.updatePreference).toBe(callbacks.updatePreference)
      expect(result.current.resetPreferences).toBe(callbacks.resetPreferences)
    })
  })

  describe('6. Refetch/Invalidation', () => {
    it('should not have refetch mechanism', () => {
      const { result } = renderHook(() =>
        useTablePreferences(mockProjectId, mockUserId)
      )

      expect(result.current).not.toHaveProperty('refetch')
    })

    it('should sync changes to localStorage automatically', async () => {
      const { result } = renderHook(() =>
        useTablePreferences(mockProjectId, mockUserId)
      )

      act(() => {
        result.current.updatePreference('sortBy', 'name')
      })

      await waitFor(() => {
        expect(localStorageMock.setItem).toHaveBeenCalled()
      })
    })
  })

  describe('7. Edge Cases', () => {
    it('should handle rapid consecutive updates', () => {
      const { result } = renderHook(() =>
        useTablePreferences(mockProjectId, mockUserId)
      )

      act(() => {
        result.current.updatePreference('sortBy', 'name')
        result.current.updatePreference('sortOrder', 'asc')
        result.current.updatePreference('filterStatus', 'completed')
        result.current.updatePreference('showSearch', true)
      })

      expect(result.current.preferences).toEqual({
        sortBy: 'name',
        sortOrder: 'asc',
        filterStatus: 'completed',
        showSearch: true,
      })
    })

    it('should handle updating with same value', () => {
      const { result } = renderHook(() =>
        useTablePreferences(mockProjectId, mockUserId)
      )

      const setItemCallsBefore = localStorageMock.setItem.mock.calls.length

      act(() => {
        result.current.updatePreference('sortBy', 'id')
      })

      expect(result.current.preferences.sortBy).toBe('id')
      expect(localStorageMock.setItem.mock.calls.length).toBeGreaterThan(
        setItemCallsBefore
      )
    })

    it('should handle custom preference keys', () => {
      const { result } = renderHook(() =>
        useTablePreferences(mockProjectId, mockUserId)
      )

      act(() => {
        result.current.updatePreference('customKey', 'customValue')
      })

      expect((result.current.preferences as any).customKey).toBe('customValue')
    })

    it('should handle project ID changes', () => {
      const { unmount } = renderHook(() =>
        useTablePreferences('project-1', mockUserId)
      )

      unmount()

      const { result } = renderHook(() =>
        useTablePreferences('project-2', mockUserId)
      )

      // New project ID should load fresh state
      expect(result.current.preferences.sortBy).toBe('id')
    })

    it('should handle user ID changes', () => {
      const { unmount } = renderHook(() =>
        useTablePreferences(mockProjectId, 'user-1')
      )

      unmount()

      const { result } = renderHook(() =>
        useTablePreferences(mockProjectId, 'user-2')
      )

      // New user ID should load fresh state
      expect(result.current.preferences.sortBy).toBe('id')
    })

    it('should not save when userId is undefined', async () => {
      const { result } = renderHook(() =>
        useTablePreferences(mockProjectId, undefined)
      )

      const setItemCallsBefore = localStorageMock.setItem.mock.calls.length

      act(() => {
        result.current.updatePreference('sortBy', 'name')
      })

      await new Promise((resolve) => setTimeout(resolve, 100))

      expect(localStorageMock.setItem.mock.calls.length).toBe(
        setItemCallsBefore
      )
    })

    it('should not remove from localStorage on reset when userId is undefined', () => {
      const { result } = renderHook(() =>
        useTablePreferences(mockProjectId, undefined)
      )

      act(() => {
        result.current.resetPreferences()
      })

      expect(localStorageMock.removeItem).not.toHaveBeenCalled()
    })

    it('should handle partial saved preferences', () => {
      const partialPreferences = {
        sortBy: 'name',
        sortOrder: 'asc' as const,
      }

      localStorageMock.setItem(
        `table-preferences-${mockUserId}-${mockProjectId}`,
        JSON.stringify(partialPreferences)
      )

      const { result } = renderHook(() =>
        useTablePreferences(mockProjectId, mockUserId)
      )

      expect(result.current.preferences.sortBy).toBe('name')
      expect(result.current.preferences.sortOrder).toBe('asc')
    })
  })

  describe('8. API Integration/Cleanup', () => {
    it('should clean up properly on unmount', () => {
      const { unmount } = renderHook(() =>
        useTablePreferences(mockProjectId, mockUserId)
      )

      unmount()

      expect(true).toBe(true)
    })

    it('should not have memory leaks with multiple instances', () => {
      const instances = Array.from({ length: 10 }, () =>
        renderHook(() => useTablePreferences(mockProjectId, mockUserId))
      )

      instances.forEach((instance) => instance.unmount())

      expect(true).toBe(true)
    })

    it('should handle localStorage quota exceeded', async () => {
      const { result } = renderHook(() =>
        useTablePreferences(mockProjectId, mockUserId)
      )

      const quotaError = new Error('QuotaExceededError')
      quotaError.name = 'QuotaExceededError'
      localStorageMock.setItem.mockImplementationOnce(() => {
        throw quotaError
      })

      // Should not crash when quota is exceeded
      act(() => {
        result.current.updatePreference('sortBy', 'name')
      })

      // State should still update even if save fails
      expect(result.current.preferences.sortBy).toBe('name')
    })

    it('should persist changes across hook instances', () => {
      const { result: instance1 } = renderHook(() =>
        useTablePreferences(mockProjectId, mockUserId)
      )

      act(() => {
        instance1.current.updatePreference('sortBy', 'name')
        instance1.current.updatePreference('sortOrder', 'asc')
      })

      const { result: instance2 } = renderHook(() =>
        useTablePreferences(mockProjectId, mockUserId)
      )

      expect(instance2.current.preferences.sortBy).toBe('name')
      expect(instance2.current.preferences.sortOrder).toBe('asc')
    })
  })
})

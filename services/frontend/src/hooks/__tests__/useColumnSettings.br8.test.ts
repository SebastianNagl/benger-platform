/**
 * @jest-environment jsdom
 *
 * Branch coverage: useColumnSettings.ts
 * Targets uncovered branches:
 *   - L87: col.order ?? index fallback in save effect
 *   - L131: existing.order ?? index fallback in updateColumns
 *   - L143: sort comparator order fallbacks
 */

import { renderHook, act } from '@testing-library/react'
import { useColumnSettings, useTablePreferences } from '../useColumnSettings'

jest.mock('@/lib/utils/logger', () => ({
  logger: { debug: jest.fn() },
}))

describe('useColumnSettings br8', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('initializes with defaults when no saved settings', () => {
    const defaults = [
      { id: 'col1', visible: true },
      { id: 'col2', visible: false },
    ]
    const { result } = renderHook(() => useColumnSettings('proj1', 'user1', defaults))
    expect(result.current.columns).toHaveLength(2)
    expect(result.current.columns[0].order).toBe(0)
  })

  it('restores from localStorage and handles missing order (L51 ?? fallback)', () => {
    // Save settings without order property
    const saved = [
      { id: 'col1', visible: false },
      { id: 'col2', visible: true },
    ]
    localStorage.setItem('column-settings-user1-proj1', JSON.stringify(saved))

    const defaults = [
      { id: 'col1', visible: true },
      { id: 'col2', visible: false },
    ]
    const { result } = renderHook(() => useColumnSettings('proj1', 'user1', defaults))
    expect(result.current.columns[0].visible).toBe(false)
  })

  it('adds new columns not in saved settings (L57-63)', () => {
    const saved = [{ id: 'col1', visible: true, order: 0 }]
    localStorage.setItem('column-settings-user1-proj1', JSON.stringify(saved))

    const defaults = [
      { id: 'col1', visible: true },
      { id: 'col2', visible: true },
      { id: 'col3', visible: true },
    ]
    const { result } = renderHook(() => useColumnSettings('proj1', 'user1', defaults))
    expect(result.current.columns).toHaveLength(3)
  })

  it('handles parse error from localStorage (L72-73)', () => {
    localStorage.setItem('column-settings-user1-proj1', 'invalid json')
    jest.spyOn(console, 'error').mockImplementation()

    const defaults = [{ id: 'col1', visible: true }]
    const { result } = renderHook(() => useColumnSettings('proj1', 'user1', defaults))
    expect(result.current.columns).toHaveLength(1)
  })

  it('initializes with defaults when userId is undefined (L26)', () => {
    const defaults = [{ id: 'col1', visible: true }]
    const { result } = renderHook(() => useColumnSettings('proj1', undefined, defaults))
    expect(result.current.columns[0].order).toBe(0)
  })

  it('toggleColumn toggles visibility', () => {
    const defaults = [{ id: 'col1', visible: true }]
    const { result } = renderHook(() => useColumnSettings('proj1', 'user1', defaults))

    act(() => {
      result.current.toggleColumn('col1')
    })

    expect(result.current.columns[0].visible).toBe(false)
  })

  it('resetColumns resets to default state', () => {
    const defaults = [{ id: 'col1', visible: true }]
    const { result } = renderHook(() => useColumnSettings('proj1', 'user1', defaults))

    // First toggle to create a non-default state
    act(() => {
      result.current.toggleColumn('col1')
    })

    act(() => {
      result.current.resetColumns()
    })

    // After reset, columns should be back to defaults
    expect(result.current.columns[0].visible).toBe(true)
    expect(result.current.columns[0].order).toBe(0)
  })

  it('updateColumns preserves existing settings and adds new (L124-143)', () => {
    const defaults = [
      { id: 'col1', visible: true },
      { id: 'col2', visible: false },
    ]
    const { result } = renderHook(() => useColumnSettings('proj1', 'user1', defaults))

    act(() => {
      result.current.updateColumns([
        { id: 'col1', visible: true },
        { id: 'col3', visible: true },
      ])
    })

    // col1 should preserve visibility, col3 is new
    expect(result.current.columns.find((c: any) => c.id === 'col1')).toBeTruthy()
    expect(result.current.columns.find((c: any) => c.id === 'col3')).toBeTruthy()
  })

  it('reorderColumns updates order', () => {
    const defaults = [
      { id: 'col1', visible: true },
      { id: 'col2', visible: true },
      { id: 'col3', visible: true },
    ]
    const { result } = renderHook(() => useColumnSettings('proj1', 'user1', defaults))

    act(() => {
      result.current.reorderColumns(0, 2)
    })

    expect(result.current.columns[0].id).toBe('col2')
    expect(result.current.columns[2].id).toBe('col1')
  })
})

describe('useTablePreferences br8', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('initializes with defaults when no saved prefs', () => {
    const { result } = renderHook(() => useTablePreferences('proj1', 'user1'))
    expect(result.current.preferences.sortBy).toBe('id')
    expect(result.current.preferences.sortOrder).toBe('desc')
  })

  it('loads saved preferences', () => {
    const saved = { sortBy: 'name', sortOrder: 'asc', filterStatus: 'completed', showSearch: true }
    localStorage.setItem('table-preferences-user1-proj1', JSON.stringify(saved))

    const { result } = renderHook(() => useTablePreferences('proj1', 'user1'))
    expect(result.current.preferences.sortBy).toBe('name')
    expect(result.current.preferences.sortOrder).toBe('asc')
  })

  it('handles parse error', () => {
    localStorage.setItem('table-preferences-user1-proj1', 'bad json')
    jest.spyOn(console, 'error').mockImplementation()

    const { result } = renderHook(() => useTablePreferences('proj1', 'user1'))
    expect(result.current.preferences.sortBy).toBe('id')
  })

  it('returns defaults when userId is undefined (L193)', () => {
    const { result } = renderHook(() => useTablePreferences('proj1', undefined))
    expect(result.current.preferences.sortBy).toBe('id')
  })

  it('updatePreference updates a single key', () => {
    const { result } = renderHook(() => useTablePreferences('proj1', 'user1'))

    act(() => {
      result.current.updatePreference('sortBy', 'name')
    })

    expect(result.current.preferences.sortBy).toBe('name')
  })

  it('resetPreferences restores default values', () => {
    const { result } = renderHook(() => useTablePreferences('proj1', 'user1'))

    // Change a preference
    act(() => {
      result.current.updatePreference('sortBy', 'name')
    })

    // Reset
    act(() => {
      result.current.resetPreferences()
    })

    // Should be back to defaults
    expect(result.current.preferences.sortBy).toBe('id')
    expect(result.current.preferences.sortOrder).toBe('desc')
  })
})

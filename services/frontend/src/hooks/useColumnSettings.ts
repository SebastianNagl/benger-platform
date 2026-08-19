/**
 * useColumnSettings - Hook for managing persistent column visibility settings
 *
 * Stores column visibility preferences in localStorage per user and project
 */

import { logger } from '@/lib/utils/logger'
import { useCallback, useEffect, useRef, useState } from 'react'

interface ColumnSetting {
  id: string
  visible: boolean
  order?: number
}

function readSavedSettings(storageKey: string): Map<string, ColumnSetting> {
  if (typeof window === 'undefined') return new Map()
  try {
    const saved = localStorage.getItem(storageKey)
    if (saved) {
      const savedSettings: ColumnSetting[] = JSON.parse(saved)
      return new Map(savedSettings.map((s) => [s.id, s]))
    }
  } catch (error) {
    console.error('Failed to load column settings:', error)
  }
  return new Map()
}

export function useColumnSettings(
  projectId: string,
  userId: string | undefined,
  defaultColumns: any[]
) {
  // Create a unique storage key for this user/project combination
  const storageKey = `column-settings-${userId}-${projectId}`

  // Saved settings snapshot from mount time. Dynamic columns (data_*/meta_*)
  // are injected AFTER mount via updateColumns and don't exist in
  // defaultColumns, so their saved visibility/order can only be restored from
  // this snapshot when they arrive — without it, a hidden data column
  // silently reverted to visible on every reload.
  const savedSettingsRef = useRef<Map<string, ColumnSetting> | null>(null)
  if (savedSettingsRef.current === null) {
    savedSettingsRef.current = userId ? readSavedSettings(storageKey) : new Map()
  }

  // Initialize columns from localStorage or use defaults
  const [columns, setColumns] = useState(() => {
    if (typeof window === 'undefined' || !userId) {
      return defaultColumns.map((col, index) => ({ ...col, order: index }))
    }

    try {
      const saved = localStorage.getItem(storageKey)
      if (saved) {
        const savedSettings: ColumnSetting[] = JSON.parse(saved)
        logger.debug('Loading saved column settings:', savedSettings)

        // Create a map of saved settings for quick lookup
        const savedMap = new Map(savedSettings.map((s) => [s.id, s]))

        // Build the column list respecting saved order
        const orderedColumns: any[] = []

        // First, add all saved columns in their saved order
        savedSettings
          .sort((a, b) => (a.order ?? 0) - (b.order ?? 0))
          .forEach((saved) => {
            const defaultCol = defaultColumns.find((d) => d.id === saved.id)
            if (defaultCol) {
              orderedColumns.push({
                ...defaultCol,
                visible: saved.visible,
                order: saved.order ?? orderedColumns.length,
              })
            }
          })

        // Then add any new columns that weren't in saved settings
        defaultColumns.forEach((col, index) => {
          if (!savedMap.has(col.id)) {
            orderedColumns.push({
              ...col,
              order: orderedColumns.length,
            })
          }
        })

        logger.debug(
          'Restored column order:',
          orderedColumns.map((c) => c.id)
        )
        return orderedColumns
      }
    } catch (error) {
      console.error('Failed to load column settings:', error)
    }

    return defaultColumns.map((col, index) => ({ ...col, order: index }))
  })

  // Save to localStorage whenever columns change
  useEffect(() => {
    if (typeof window === 'undefined' || !userId) return

    try {
      const settings: ColumnSetting[] = columns.map((col, index) => ({
        id: col.id,
        visible: col.visible,
        order: col.order ?? index,
      }))
      localStorage.setItem(storageKey, JSON.stringify(settings))
    } catch (error) {
      console.error('Failed to save column settings:', error)
    }
  }, [columns, storageKey, userId])

  // Toggle column visibility
  const toggleColumn = useCallback((columnId: string) => {
    setColumns((prev) =>
      prev.map((col) =>
        col.id === columnId ? { ...col, visible: !col.visible } : col
      )
    )
  }, [])

  // Reset to default settings
  const resetColumns = useCallback(() => {
    const resetCols = defaultColumns.map((col, index) => ({
      ...col,
      order: index,
    }))
    setColumns(resetCols)
    // Drop the mount-time snapshot too, so dynamic columns re-injected after
    // the reset come back with their defaults instead of the stale settings.
    savedSettingsRef.current = new Map()
    if (typeof window !== 'undefined' && userId) {
      localStorage.removeItem(storageKey)
    }
  }, [defaultColumns, storageKey, userId])

  // Update columns (for dynamic columns)
  const updateColumns = useCallback((newColumns: any[]) => {
    // Preserve visibility settings and order when updating columns
    setColumns((prevColumns) => {
      // Create a map of existing columns for quick lookup
      const existingMap = new Map(prevColumns.map((c) => [c.id, c]))

      // Map new columns preserving existing settings
      const updatedColumns = newColumns.map((col, index) => {
        const existing = existingMap.get(col.id)
        if (existing) {
          // Preserve visibility and order from existing column
          return {
            ...col,
            visible: existing.visible,
            order: existing.order ?? index,
          }
        }
        // A column arriving for the first time this session (dynamic
        // data_*/meta_* columns): restore its persisted visibility/order —
        // the mount-time load couldn't, because dynamic ids aren't in
        // defaultColumns yet.
        const saved = savedSettingsRef.current?.get(col.id)
        if (saved) {
          return {
            ...col,
            visible: saved.visible,
            order: saved.order ?? prevColumns.length + index,
          }
        }
        // Genuinely new column, add at the end
        return {
          ...col,
          order: prevColumns.length + index,
        }
      })

      // Sort by order to maintain consistent ordering
      return updatedColumns.sort((a, b) => (a.order ?? 0) - (b.order ?? 0))
    })
  }, [])

  // Reorder columns
  const reorderColumns = useCallback(
    (sourceIndex: number, destinationIndex: number) => {
      logger.debug('Reordering columns:', { sourceIndex, destinationIndex })
      setColumns((prev) => {
        const newColumns = [...prev]
        const [removed] = newColumns.splice(sourceIndex, 1)
        newColumns.splice(destinationIndex, 0, removed)

        // Update order property
        const reordered = newColumns.map((col, index) => ({
          ...col,
          order: index,
        }))
        logger.debug(
          'New column order:',
          reordered.map((c) => c.id)
        )
        return reordered
      })
    },
    []
  )

  return {
    columns,
    toggleColumn,
    resetColumns,
    updateColumns,
    reorderColumns,
  }
}

/**
 * useTablePreferences - Extended hook for all table preferences
 *
 * Stores sorting, filtering, and other table preferences
 */
export function useTablePreferences(
  projectId: string,
  userId: string | undefined
) {
  const storageKey = `table-preferences-${userId}-${projectId}`

  // Load initial preferences
  const loadPreferences = () => {
    if (typeof window === 'undefined' || !userId) {
      return {
        sortBy: 'id',
        sortOrder: 'desc' as 'asc' | 'desc',
        filterStatus: 'all' as 'all' | 'completed' | 'incomplete',
        showSearch: false,
      }
    }

    try {
      const saved = localStorage.getItem(storageKey)
      if (saved) {
        return JSON.parse(saved)
      }
    } catch (error) {
      console.error('Failed to load table preferences:', error)
    }

    return {
      sortBy: 'id',
      sortOrder: 'desc' as 'asc' | 'desc',
      filterStatus: 'all' as 'all' | 'completed' | 'incomplete',
      showSearch: false,
    }
  }

  const [preferences, setPreferences] = useState(loadPreferences)

  // Save preferences whenever they change
  useEffect(() => {
    if (typeof window === 'undefined' || !userId) return

    try {
      localStorage.setItem(storageKey, JSON.stringify(preferences))
    } catch (error) {
      console.error('Failed to save table preferences:', error)
    }
  }, [preferences, storageKey, userId])

  // Update individual preference
  const updatePreference = useCallback((key: string, value: any) => {
    setPreferences((prev: typeof preferences) => ({ ...prev, [key]: value }))
  }, [])

  // Reset all preferences
  const resetPreferences = useCallback(() => {
    const defaults = {
      sortBy: 'id',
      sortOrder: 'desc' as 'asc' | 'desc',
      filterStatus: 'all' as 'all' | 'completed' | 'incomplete',
      showSearch: false,
    }
    setPreferences(defaults)
    if (typeof window !== 'undefined' && userId) {
      localStorage.removeItem(storageKey)
    }
  }, [storageKey, userId])

  return {
    preferences,
    updatePreference,
    resetPreferences,
  }
}

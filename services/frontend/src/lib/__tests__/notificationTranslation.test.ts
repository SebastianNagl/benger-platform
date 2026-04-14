/**
 * Tests for notification translation utilities
 */

import { getTranslatedNotification } from '../notificationTranslation'

const mockT = (key: string, defaultValue?: string, vars?: Record<string, any>) => {
  if (vars && defaultValue) {
    // Simulate i18next behavior: replace variables in the default string
    let result = defaultValue
    for (const [k, v] of Object.entries(vars)) {
      result = result.replace(`{${k}}`, String(v))
    }
    return result
  }
  return defaultValue || key
}

const createNotification = (overrides: any = {}) => ({
  id: 'n1',
  type: 'test',
  title: 'Test Title',
  message: 'Test Message',
  data: {},
  is_read: false,
  created_at: '2025-01-01T00:00:00Z',
  ...overrides,
})

describe('getTranslatedNotification', () => {
  it('should return translated title and message', () => {
    const notification = createNotification()
    const result = getTranslatedNotification(mockT, notification)

    expect(result.title).toBe('Test Title')
    expect(result.message).toBe('Test Message')
  })

  it('should fall back to raw title when translation has unresolved variables', () => {
    const t = () => '{unresolved_var} in translation'
    const notification = createNotification({ title: 'Raw Title' })

    const result = getTranslatedNotification(t, notification)
    expect(result.title).toBe('Raw Title')
  })

  it('should fall back to raw message when translation has unresolved variables', () => {
    const t = () => '{unresolved_var} in message'
    const notification = createNotification({ message: 'Raw Message' })

    const result = getTranslatedNotification(t, notification)
    expect(result.message).toBe('Raw Message')
  })

  it('should use translated string when no unresolved variables', () => {
    const t = () => 'Fully resolved translation'
    const notification = createNotification()

    const result = getTranslatedNotification(t, notification)
    expect(result.title).toBe('Fully resolved translation')
    expect(result.message).toBe('Fully resolved translation')
  })

  it('should fall back when t returns non-string', () => {
    const t = () => undefined
    const notification = createNotification({
      title: 'Fallback Title',
      message: 'Fallback Message',
    })

    const result = getTranslatedNotification(t as any, notification)
    expect(result.title).toBe('Fallback Title')
    expect(result.message).toBe('Fallback Message')
  })

  it('should normalize project_deleted data', () => {
    const t = mockT
    const notification = createNotification({
      type: 'project_deleted',
      data: { deleted_by: 'admin' },
      title: 'Project deleted by {deleted_by_username}',
      message: 'Done',
    })

    const result = getTranslatedNotification(t, notification)
    expect(result.title).toBe('Project deleted by admin')
  })

  it('should normalize project_archived data', () => {
    const t = mockT
    const notification = createNotification({
      type: 'project_archived',
      data: { archived_by: 'user1' },
      title: 'Archived by {archived_by_username}',
      message: 'Done',
    })

    const result = getTranslatedNotification(t, notification)
    expect(result.title).toBe('Archived by user1')
  })

  it('should normalize data_import_success data', () => {
    const t = mockT
    const notification = createNotification({
      type: 'data_import_success',
      data: { task_count: 50, imported_by: 'admin' },
      title: 'Imported {imported_items_count} items by {imported_by_username}',
      message: 'Success',
    })

    const result = getTranslatedNotification(t, notification)
    expect(result.title).toBe('Imported 50 items by admin')
  })

  it('should normalize labeling_config_updated data', () => {
    const t = mockT
    const notification = createNotification({
      type: 'labeling_config_updated',
      data: { updated_by: 'editor' },
      title: 'Updated by {updated_by_username}',
      message: 'Config changed',
    })

    const result = getTranslatedNotification(t, notification)
    expect(result.title).toBe('Updated by editor')
  })

  it('should not override existing normalized fields', () => {
    const t = mockT
    const notification = createNotification({
      type: 'project_deleted',
      data: {
        deleted_by: 'admin',
        deleted_by_username: 'Admin User',
      },
      title: 'Deleted by {deleted_by_username}',
      message: 'Done',
    })

    const result = getTranslatedNotification(t, notification)
    expect(result.title).toBe('Deleted by Admin User')
  })

  it('should handle null data', () => {
    const notification = createNotification({ data: null })
    const result = getTranslatedNotification(mockT, notification)

    expect(result.title).toBeDefined()
    expect(result.message).toBeDefined()
  })
})

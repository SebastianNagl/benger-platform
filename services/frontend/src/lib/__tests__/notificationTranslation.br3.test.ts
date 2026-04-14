/**
 * @jest-environment jsdom
 *
 * Branch coverage: notificationTranslation.ts
 * Targets: normalizeData branches for project_archived, data_import_success, labeling_config_updated
 */

import { getTranslatedNotification } from '../notificationTranslation'

describe('notificationTranslation branch coverage', () => {
  const t = (key: string, defaultVal?: string, _vars?: Record<string, any>) =>
    defaultVal ?? key

  const base = {
    id: '1',
    type: 'general',
    title: 'Title',
    message: 'Msg',
    read: false,
    created_at: '',
  }

  it('normalizes project_archived data', () => {
    const result = getTranslatedNotification(t, {
      ...base,
      type: 'project_archived',
      data: { archived_by: 'admin' },
    })
    expect(result.title).toBe('Title')
  })

  it('normalizes data_import_success with task_count and imported_by', () => {
    const result = getTranslatedNotification(t, {
      ...base,
      type: 'data_import_success',
      data: { task_count: 10, imported_by: 'user1' },
    })
    expect(result.title).toBe('Title')
  })

  it('normalizes labeling_config_updated data', () => {
    const result = getTranslatedNotification(t, {
      ...base,
      type: 'labeling_config_updated',
      data: { updated_by: 'editor' },
    })
    expect(result.title).toBe('Title')
  })

  it('falls back to raw title when translated has unresolved placeholders', () => {
    const tWithPlaceholder = (key: string, defaultVal?: string) => '{task_name}'
    const result = getTranslatedNotification(tWithPlaceholder, base)
    expect(result.title).toBe('Title')
    expect(result.message).toBe('Msg')
  })
})

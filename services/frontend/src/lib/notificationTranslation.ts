import type { Notification } from '@/components/layout/NotificationDropdown'

type TFunction = (
  key: string,
  defaultValueOrVariables?: string | Record<string, any>,
  variables?: Record<string, any>
) => any

/**
 * Given a notification and the i18n t() function, return the translated
 * title and message. Falls back to the raw DB strings for unknown types.
 */
export function getTranslatedNotification(
  t: TFunction,
  notification: Notification
): { title: string; message: string } {
  const { type, data, title: rawTitle, message: rawMessage } = notification
  const d = normalizeData(type, data || {})

  const translatedTitle = t(`notifications.content.${type}.title`, rawTitle, d)
  const translatedMessage = t(
    `notifications.content.${type}.message`,
    rawMessage,
    d
  )

  // If any {variable} placeholders remain unresolved, fall back to the raw
  // DB text which is always meaningful (avoids showing literal "{task_name}").
  const hasUnresolved = (s: string) => /\{\w+\}/.test(s)

  return {
    title:
      typeof translatedTitle === 'string' && !hasUnresolved(translatedTitle)
        ? translatedTitle
        : rawTitle,
    message:
      typeof translatedMessage === 'string' &&
      !hasUnresolved(translatedMessage)
        ? translatedMessage
        : rawMessage,
  }
}

/**
 * Normalize notification data to match the variable names used in
 * translation templates. The backend uses different key names
 * depending on which code path created the notification.
 */
function normalizeData(
  type: string,
  data: Record<string, any>
): Record<string, any> {
  const d = { ...data }

  if (type === 'project_deleted') {
    if (!d.deleted_by_username && d.deleted_by) {
      d.deleted_by_username = d.deleted_by
    }
  }

  if (type === 'project_archived') {
    if (!d.archived_by_username && d.archived_by) {
      d.archived_by_username = d.archived_by
    }
  }

  if (type === 'data_import_success') {
    if (!d.imported_items_count && d.task_count) {
      d.imported_items_count = d.task_count
    }
    if (!d.imported_by_username && d.imported_by) {
      d.imported_by_username = d.imported_by
    }
  }

  if (type === 'labeling_config_updated') {
    if (!d.updated_by_username && d.updated_by) {
      d.updated_by_username = d.updated_by
    }
  }

  return d
}

import type { Notification } from '@/components/layout/NotificationDropdown'

type TFunction = (key: string, variables?: Record<string, any>) => any

/**
 * Given a notification and the i18n t() function, return the translated
 * title and message. Falls back to the raw DB strings for unknown types.
 */
export function getTranslatedNotification(
  t: TFunction,
  notification: Notification,
): { title: string; message: string } {
  const { type, data, title: rawTitle, message: rawMessage } = notification
  const d = normalizeData(type, data || {})

  const titleKey = `notifications.content.${type}.title`
  const messageKey = `notifications.content.${type}.message`
  const translatedTitle = t(titleKey, d)
  const translatedMessage = t(messageKey, d)

  // An unknown type (the key comes back as-is) or unresolved {variable}
  // placeholders fall back to the raw DB text, which is always meaningful
  // (avoids showing a raw key or a literal "{task_name}").
  const hasUnresolved = (s: string) =>
    /\{\w+\}/.test(s) || s === titleKey || s === messageKey

  return {
    title:
      typeof translatedTitle === 'string' && !hasUnresolved(translatedTitle)
        ? translatedTitle
        : rawTitle,
    message:
      typeof translatedMessage === 'string' && !hasUnresolved(translatedMessage)
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
  data: Record<string, any>,
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

/**
 * Non-React translation utility for use in Zustand stores and utility files.
 *
 * Reads the same catalog as I18nContext and determines the current locale
 * from localStorage (same key as I18nProvider).
 */

import { translateKey, type TranslationVars } from '@/lib/i18n/catalog'
import { readStoredLocale } from '@/lib/i18n/locales'

/**
 * Translate a key outside of React context.
 * Supports variable interpolation: translate('key', { count: 5 })
 */
export function translate(key: string, vars?: TranslationVars): string {
  const value = translateKey(readStoredLocale(), key, vars)
  return typeof value === 'string' ? value : key
}

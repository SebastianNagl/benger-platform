/**
 * Non-React translation utility for use in Zustand stores and utility files.
 *
 * Reads from the same locale JSON files as I18nContext and determines
 * the current locale from localStorage (same key as I18nProvider).
 */

let deTranslations: Record<string, any> = {}
let enTranslations: Record<string, any> = {}

try {
  deTranslations = require('@/locales/de/common.json')
  enTranslations = require('@/locales/en/common.json')
} catch {
  // Translations not available
}

const translations: Record<string, Record<string, any>> = {
  de: deTranslations,
  en: enTranslations,
}

function getLocale(): 'de' | 'en' {
  if (typeof window === 'undefined') return 'de'
  try {
    const stored = localStorage.getItem('preferred-locale')
    if (stored === 'en' || stored === 'de') return stored
  } catch {
    // localStorage not available
  }
  return 'de'
}

/**
 * Translate a key outside of React context.
 * Supports variable interpolation: translate('key', { count: 5 })
 */
export function translate(
  key: string,
  vars?: Record<string, any>
): string {
  try {
    const locale = getLocale()
    const keys = key.split('.')
    let value: any = translations[locale]

    for (const k of keys) {
      value = value?.[k]
    }

    if (value === undefined) return key

    if (vars && typeof value === 'string') {
      return value.replace(/\{(\w+)\}/g, (match, variableName) => {
        return vars[variableName] !== undefined
          ? String(vars[variableName])
          : match
      })
    }

    return typeof value === 'string' ? value : key
  } catch {
    return key
  }
}

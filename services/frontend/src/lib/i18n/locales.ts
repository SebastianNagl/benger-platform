/**
 * The UI languages BenGER ships, in switcher order.
 *
 * Everything locale-dependent (catalog lookup, Intl formatting, date-fns,
 * the language menu) reads from here, so adding a language means adding it
 * to LOCALES, LOCALE_META and a catalog folder under src/locales/.
 */

import type { Locale as DateFnsLocale } from 'date-fns'
import {
  de as dateFnsDe,
  enGB as dateFnsEn,
  fr as dateFnsFr,
} from 'date-fns/locale'

export const LOCALES = ['de', 'en', 'fr'] as const

export type Locale = (typeof LOCALES)[number]

export const DEFAULT_LOCALE: Locale = 'de'

/** localStorage key of the user's language choice. */
export const LOCALE_STORAGE_KEY = 'preferred-locale'

export const LOCALE_META: Record<
  Locale,
  { name: string; flag: string; intlTag: string; dateFns: DateFnsLocale }
> = {
  de: { name: 'Deutsch', flag: '🇩🇪', intlTag: 'de-DE', dateFns: dateFnsDe },
  en: { name: 'English', flag: '🇬🇧', intlTag: 'en-GB', dateFns: dateFnsEn },
  fr: { name: 'Français', flag: '🇫🇷', intlTag: 'fr-FR', dateFns: dateFnsFr },
}

export function isLocale(value: unknown): value is Locale {
  return (
    typeof value === 'string' && (LOCALES as readonly string[]).includes(value)
  )
}

/** The locale itself when supported, otherwise the default. */
export function toLocale(value: unknown): Locale {
  return isLocale(value) ? value : DEFAULT_LOCALE
}

/** BCP-47 tag for Intl APIs (toLocaleString, Intl.NumberFormat, ...). */
export function intlTag(locale: string | null | undefined): string {
  return LOCALE_META[toLocale(locale)].intlTag
}

/** date-fns locale object for format()/formatDistance(). */
export function dateFnsLocale(
  locale: string | null | undefined,
): DateFnsLocale {
  return LOCALE_META[toLocale(locale)].dateFns
}

/** The stored language choice, or the default (SSR-safe). */
export function readStoredLocale(): Locale {
  if (typeof window === 'undefined') return DEFAULT_LOCALE
  try {
    return toLocale(localStorage.getItem(LOCALE_STORAGE_KEY))
  } catch {
    return DEFAULT_LOCALE
  }
}

/**
 * Locale-aware replacement for `value.toFixed(digits)` in user-visible text:
 * always `digits` fraction digits, with the UI language's decimal separator
 * ("9,3" in de/fr, "9.3" in en). Keep `toFixed` for data (exports, payloads).
 */
export function formatDecimal(
  value: number,
  locale: string | null | undefined,
  digits = 0,
): string {
  return value.toLocaleString(intlTag(locale), {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

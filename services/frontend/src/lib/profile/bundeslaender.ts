/**
 * The 16 German states as two-letter codes (users.exam_bundesland).
 *
 * Mirrors the `Bundesland` Literal in services/api/schemas/auth_schemas.py;
 * the API rejects any other value with 422. The display names live in the
 * locale catalog under profile.bundeslaender.<code>.
 */

import { translateKey } from '@/lib/i18n/catalog'
import { toLocale } from '@/lib/i18n/locales'

export const BUNDESLAND_CODES = [
  'BW',
  'BY',
  'BE',
  'BB',
  'HB',
  'HH',
  'HE',
  'MV',
  'NI',
  'NW',
  'RP',
  'SL',
  'SN',
  'ST',
  'SH',
  'TH',
] as const

export type BundeslandCode = (typeof BUNDESLAND_CODES)[number]

export function isBundeslandCode(value: unknown): value is BundeslandCode {
  return (
    typeof value === 'string' &&
    (BUNDESLAND_CODES as readonly string[]).includes(value)
  )
}

/** Display name for a code in the given locale (the default locale without one). */
export function bundeslandName(
  code: BundeslandCode,
  locale?: string | null,
): string {
  return translateKey(toLocale(locale), `profile.bundeslaender.${code}`)
}

/**
 * The 16 German states as two-letter codes (users.exam_bundesland).
 *
 * Mirrors the `Bundesland` Literal in services/api/schemas/auth_schemas.py;
 * the API rejects any other value with 422. Names are proper nouns, so they
 * are kept here in both languages rather than in the locale catalog.
 */

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

export const BUNDESLAENDER: Record<BundeslandCode, { de: string; en: string }> =
  {
    BW: { de: 'Baden-Württemberg', en: 'Baden-Württemberg' },
    BY: { de: 'Bayern', en: 'Bavaria' },
    BE: { de: 'Berlin', en: 'Berlin' },
    BB: { de: 'Brandenburg', en: 'Brandenburg' },
    HB: { de: 'Bremen', en: 'Bremen' },
    HH: { de: 'Hamburg', en: 'Hamburg' },
    HE: { de: 'Hessen', en: 'Hesse' },
    MV: {
      de: 'Mecklenburg-Vorpommern',
      en: 'Mecklenburg-Western Pomerania',
    },
    NI: { de: 'Niedersachsen', en: 'Lower Saxony' },
    NW: { de: 'Nordrhein-Westfalen', en: 'North Rhine-Westphalia' },
    RP: { de: 'Rheinland-Pfalz', en: 'Rhineland-Palatinate' },
    SL: { de: 'Saarland', en: 'Saarland' },
    SN: { de: 'Sachsen', en: 'Saxony' },
    ST: { de: 'Sachsen-Anhalt', en: 'Saxony-Anhalt' },
    SH: { de: 'Schleswig-Holstein', en: 'Schleswig-Holstein' },
    TH: { de: 'Thüringen', en: 'Thuringia' },
  }

export function isBundeslandCode(value: unknown): value is BundeslandCode {
  return (
    typeof value === 'string' &&
    (BUNDESLAND_CODES as readonly string[]).includes(value)
  )
}

/** Display name for a code in the given locale (anything but `en` reads German). */
export function bundeslandName(
  code: BundeslandCode,
  locale?: string | null,
): string {
  const names = BUNDESLAENDER[code]
  return locale === 'en' ? names.en : names.de
}

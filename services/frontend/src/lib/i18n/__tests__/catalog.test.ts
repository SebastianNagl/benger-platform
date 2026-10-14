import {
  getTranslationsVersion,
  hasTranslation,
  interpolate,
  lookup,
  registerTranslations,
  subscribeTranslations,
  translateKey,
} from '../catalog'
import {
  dateFnsLocale,
  formatDecimal,
  intlTag,
  isLocale,
  LOCALES,
  readStoredLocale,
  toLocale,
} from '../locales'

describe('locales', () => {
  it('ships German, English and French', () => {
    expect(LOCALES).toEqual(['de', 'en', 'fr'])
  })

  it('maps locales to Intl tags and date-fns locales', () => {
    expect(intlTag('de')).toBe('de-DE')
    expect(intlTag('en')).toBe('en-GB')
    expect(intlTag('fr')).toBe('fr-FR')
    expect(intlTag(undefined)).toBe('de-DE')
    expect(dateFnsLocale('fr').code).toBe('fr')
    expect(dateFnsLocale('xx').code).toBe('de')
  })

  it('formats fixed decimals with the UI language separator', () => {
    expect(formatDecimal(9.25, 'de', 1)).toBe('9,3')
    expect(formatDecimal(9.25, 'fr', 1)).toBe('9,3')
    expect(formatDecimal(9.25, 'en', 1)).toBe('9.3')
    expect(formatDecimal(0.5, 'en', 3)).toBe('0.500')
    expect(formatDecimal(0.5, undefined, 3)).toBe('0,500')
    expect(formatDecimal(12, 'de')).toBe('12')
  })

  it('validates locale values', () => {
    expect(isLocale('fr')).toBe(true)
    expect(isLocale('it')).toBe(false)
    expect(toLocale('it')).toBe('de')
  })

  it('reads the stored choice', () => {
    localStorage.setItem('preferred-locale', 'fr')
    expect(readStoredLocale()).toBe('fr')
    localStorage.setItem('preferred-locale', 'klingon')
    expect(readStoredLocale()).toBe('de')
    localStorage.clear()
  })
})

describe('catalog', () => {
  afterEach(() => {
    registerTranslations('test', { de: {}, en: {}, fr: {} })
  })

  it('resolves platform keys in every locale', () => {
    for (const locale of LOCALES) {
      expect(hasTranslation(locale, 'common.save')).toBe(true)
    }
    expect(translateKey('fr', 'common.save')).not.toBe('common.save')
  })

  it('falls back fr -> en -> de, then to the key', () => {
    registerTranslations('test', {
      de: { zz: { onlyDe: 'nur de', enDe: 'de' } },
      en: { zz: { enDe: 'en' } },
      fr: {},
    })
    expect(lookup('fr', 'zz.enDe')).toBe('en')
    expect(lookup('fr', 'zz.onlyDe')).toBe('nur de')
    expect(lookup('en', 'zz.onlyDe')).toBe('nur de')
    expect(translateKey('fr', 'zz.missing')).toBe('zz.missing')
  })

  it('never returns a branch node', () => {
    expect(translateKey('de', 'common')).toBe('common')
  })

  it('lets an extension add and override keys, replacing by source', () => {
    const listener = jest.fn()
    const unsubscribe = subscribeTranslations(listener)
    const before = getTranslationsVersion()

    registerTranslations('test', {
      de: { zz: { a: 'A {n}' } },
      en: { zz: { a: 'A-en {n}' } },
      fr: { zz: { a: 'A-fr {n}' } },
    })
    expect(translateKey('fr', 'zz.a', { n: 2 })).toBe('A-fr 2')
    expect(listener).toHaveBeenCalledTimes(1)
    expect(getTranslationsVersion()).toBe(before + 1)

    registerTranslations('test', { de: {}, en: {}, fr: {} })
    expect(translateKey('fr', 'zz.a')).toBe('zz.a')
    unsubscribe()
  })

  it('keeps the platform tree intact when an extension merges into a namespace', () => {
    registerTranslations('test', {
      de: { common: { zzExtra: 'x' } },
      en: { common: { zzExtra: 'x' } },
      fr: { common: { zzExtra: 'x' } },
    })
    expect(hasTranslation('de', 'common.save')).toBe(true)
    expect(translateKey('de', 'common.zzExtra')).toBe('x')
  })

  it('interpolates only the variables it is given', () => {
    expect(interpolate('{a} and {b}', { a: 1 })).toBe('1 and {b}')
    expect(interpolate('plain')).toBe('plain')
  })

  it('returns a non-string key unchanged', () => {
    expect(translateKey('de', null as unknown as string)).toBeNull()
  })
})

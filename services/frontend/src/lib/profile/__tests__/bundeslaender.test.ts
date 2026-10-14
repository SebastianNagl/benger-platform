import {
  BUNDESLAND_CODES,
  bundeslandName,
  isBundeslandCode,
} from '../bundeslaender'

jest.mock('@/lib/i18n/catalog', () => ({
  translateKey: (locale: string, key: string) => `${locale}:${key}`,
}))

describe('bundeslaender codebook', () => {
  it('has exactly the 16 distinct states', () => {
    expect(BUNDESLAND_CODES).toHaveLength(16)
    expect(new Set(BUNDESLAND_CODES).size).toBe(16)
  })

  it('validates codes', () => {
    expect(isBundeslandCode('NW')).toBe(true)
    expect(isBundeslandCode('nw')).toBe(false)
    expect(isBundeslandCode('XX')).toBe(false)
    expect(isBundeslandCode(null)).toBe(false)
  })

  it('names states from the catalog in the given locale', () => {
    expect(bundeslandName('BY', 'de')).toBe('de:profile.bundeslaender.BY')
    expect(bundeslandName('BY', 'en')).toBe('en:profile.bundeslaender.BY')
    expect(bundeslandName('BY', 'fr')).toBe('fr:profile.bundeslaender.BY')
  })

  it('falls back to the default locale without a (known) locale', () => {
    expect(bundeslandName('BY', null)).toBe('de:profile.bundeslaender.BY')
    expect(bundeslandName('BY', 'xx')).toBe('de:profile.bundeslaender.BY')
  })
})

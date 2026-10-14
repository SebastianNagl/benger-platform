/**
 * Test helper: `t` mocks backed by the real translation catalog
 * (`@/lib/i18n/catalog`), so tests assert the copy users actually see. A key
 * no catalog carries comes back as the key itself, like the real t().
 *
 * Inside a jest.mock factory (factories may only reach out via require):
 *
 *   jest.mock('@/contexts/I18nContext', () =>
 *     require('@/test-utils/i18nMock').i18nMock('de'),
 *   )
 *
 * Pass a function to switch the locale per test: `i18nMock(() => mockLocale)`.
 * `t` is created once per call, so its identity is stable across renders
 * (several components keep it in effect deps).
 */

export type TestLocale = 'de' | 'en' | 'fr'

type Vars = Record<string, unknown>

function translate(locale: TestLocale, key: string, vars?: Vars): any {
  return jest
    .requireActual('@/lib/i18n/catalog')
    .translateKey(locale, key, vars)
}

/** A catalog-backed `t` for one locale (default English). */
export function createMockT(locale: TestLocale | (() => TestLocale) = 'en') {
  const current = () => (typeof locale === 'function' ? locale() : locale)
  return (key: string, vars?: Vars): any => translate(current(), key, vars)
}

/** Module mock for `@/contexts/I18nContext` backed by the catalog. */
export function i18nMock(locale: TestLocale | (() => TestLocale) = 'en') {
  const current = () => (typeof locale === 'function' ? locale() : locale)
  const t = createMockT(locale)
  return {
    useI18n: () => ({ t, locale: current() }),
    I18nProvider: ({ children }: { children: unknown }) => children,
  }
}

/** English catalog `t` (kept for existing callers). */
export const mockT = createMockT('en')

/** A `useI18n()` return value backed by the catalog (default English). */
export const mockUseI18n = (locale: TestLocale = 'en') => ({
  t: locale === 'en' ? mockT : createMockT(locale),
  locale,
})

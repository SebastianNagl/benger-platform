/**
 * @jest-environment node
 *
 * SSR branch of translate.ts: getLocale() short-circuits to 'de' when
 * `typeof window === 'undefined'`. Lives in a separate node-env file because
 * JSDOM always defines `window`, so this branch is unreachable under jsdom.
 */

import { translate } from '../translate'

describe('translate (SSR / no window)', () => {
  it('falls back to the German locale without touching localStorage', () => {
    // Under node there is no `window`, so getLocale() returns 'de' directly.
    // A nonexistent key still round-trips back to the key itself, proving the
    // function ran without throwing on the missing localStorage.
    expect(translate('navigation.next')).toBe('Weiter')
  })

  it('returns the key unchanged for an unknown key under SSR', () => {
    expect(translate('definitely.not.a.real.key')).toBe('definitely.not.a.real.key')
  })
})

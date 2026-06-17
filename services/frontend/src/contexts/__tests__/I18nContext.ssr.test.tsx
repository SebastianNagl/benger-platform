/**
 * @jest-environment jsdom
 *
 * Coverage for the I18nContext SSR / pre-hydration branch (lines 117-169 of
 * I18nContext.tsx). That whole block only runs when `mounted === false`, i.e.
 * before client hydration completes. The existing suite tried to force this
 * via a `React.useState` callCount mock, but `mounted` actually comes from
 * `useHydration()` — so the branch was never exercised.
 *
 * Here we mock useHydration to return false for the entire file, which drives
 * the provider down its `defaultT` path. `defaultT` uses German as the default
 * locale, has its own variable-interpolation logic, and (unlike the live `t`)
 * has NO object-leaf guard, so an object namespace is returned as-is.
 */
/* eslint-disable react-hooks/globals -- capturing hook values for assertions */

import { render } from '@testing-library/react'
import React from 'react'

// Test the real I18n implementation, not the global stub from test-utils.
jest.unmock('@/contexts/I18nContext')

// Force the provider into its pre-hydration (SSR) branch for the whole file.
jest.mock('@/contexts/HydrationContext', () => ({
  useHydration: jest.fn(() => false),
  HydrationProvider: ({ children }: { children: React.ReactNode }) => (
    <>{children}</>
  ),
}))

import { I18nProvider, useI18n } from '../I18nContext'

const KEY_PLAIN = 'common.save'
const DE_PLAIN = 'Speichern'
const KEY_ONE_VAR = 'projects.bulkActions.archiveSuccess' // "{count} Projekte erfolgreich archiviert"
const KEY_TWO_VARS = 'projects.creation.wizard.step5.selectedCount' // "{count} von {total} Modellen ausgewählt"
const KEY_OBJECT = 'common'

// Render the provider once and capture the context the consumer receives.
const renderSSR = () => {
  let captured: ReturnType<typeof useI18n> | null = null
  const Probe = () => {
    captured = useI18n()
    return <div>probe</div>
  }
  render(
    <I18nProvider>
      <Probe />
    </I18nProvider>
  )
  return () => captured as ReturnType<typeof useI18n>
}

describe('I18nContext — SSR defaultT branch (mounted === false)', () => {
  afterEach(() => {
    jest.clearAllMocks()
  })

  it('reports isReady=false and locale=de while unhydrated', () => {
    const ctx = renderSSR()
    expect(ctx().isReady).toBe(false)
    expect(ctx().locale).toBe('de')
  })

  it('SSR defaultT resolves a real German plain string', () => {
    const ctx = renderSSR()
    expect(ctx().t(KEY_PLAIN)).toBe(DE_PLAIN)
  })

  it('SSR defaultT interpolates a single real variable', () => {
    const ctx = renderSSR()
    const out = ctx().t(KEY_ONE_VAR, { count: 4 })
    expect(out).toContain('4')
    expect(out).not.toContain('{count}')
  })

  it('SSR defaultT interpolates multiple real variables', () => {
    const ctx = renderSSR()
    const out = ctx().t(KEY_TWO_VARS, { count: 2, total: 5 })
    expect(out).toContain('2')
    expect(out).toContain('5')
    expect(out).not.toContain('{total}')
  })

  it('SSR defaultT preserves an unmatched placeholder', () => {
    const ctx = renderSSR()
    const out = ctx().t(KEY_ONE_VAR, { nope: 1 })
    expect(out).toContain('{count}')
  })

  it('SSR defaultT returns the explicit default for a missing key', () => {
    const ctx = renderSSR()
    expect(ctx().t('no.such.key', 'SSR Default')).toBe('SSR Default')
  })

  it('SSR defaultT returns the key when missing and no default given', () => {
    const ctx = renderSSR()
    expect(ctx().t('no.such.key')).toBe('no.such.key')
  })

  it('SSR defaultT (no object guard) returns an object namespace as-is', () => {
    const ctx = renderSSR()
    const out = ctx().t(KEY_OBJECT)
    expect(typeof out).toBe('object')
    expect(out).not.toBeNull()
  })

  it('SSR defaultT applies the string default argument branch', () => {
    const ctx = renderSSR()
    // String second arg routes through the defaultValue assignment in defaultT.
    expect(ctx().t('missing.key.ssr', 'fallback-ssr')).toBe('fallback-ssr')
  })

  it('SSR changeLocale is a no-op that does not throw', () => {
    const ctx = renderSSR()
    expect(() => ctx().changeLocale('en')).not.toThrow()
    expect(ctx().locale).toBe('de')
  })
})

/**
 * @jest-environment jsdom
 *
 * Supplemental coverage for I18nContext that exercises the *real* translation
 * branches the existing suite never reaches:
 *
 *  - Live `t`: the variable-interpolation path (lines 91-97) using real keys
 *    that actually resolve to a string template containing `{placeholder}`.
 *  - Live `t`: the object/array leaf guard (lines 86-88) — a plain object
 *    namespace falls back to the key, an array leaf is returned as-is.
 *  - Live `t`: the string-default-argument path (lines 64-66) where the
 *    second arg is a default string rather than a variables object.
 *
 * The SSR `defaultT` branch lives in I18nContext.ssr.test.tsx, which mocks
 * useHydration to return false for the whole file.
 *
 * Real keys are read against the bundled de/en translation JSON so the
 * assertions stay in sync with the source of truth.
 */
/* eslint-disable react-hooks/globals -- capturing hook values for assertions */

import { act, renderHook, waitFor } from '@testing-library/react'
import React from 'react'

// Test the real implementation, not the global stub from test-utils.
jest.unmock('@/contexts/I18nContext')

import { I18nProvider, useI18n } from '../I18nContext'

// Real translation values (mirrors services/frontend/src/locales/*/common.json).
// These keys are stable, user-facing strings used in the projects UI.
const KEY_PLAIN = 'common.save'
const DE_PLAIN = 'Speichern'
const EN_PLAIN = 'Save'

const KEY_ONE_VAR = 'projects.bulkActions.archiveSuccess' // "{count} Projekte erfolgreich archiviert"
const KEY_TWO_VARS = 'projects.creation.wizard.step5.selectedCount' // "{count} von {total} Modellen ausgewählt"
const KEY_OBJECT = 'common' // resolves to a namespace object (branch node)
const KEY_ARRAY = 'landing.heroTitle.rotatingWords' // resolves to a string[]

const providerWrapper = ({ children }: { children: React.ReactNode }) => (
  <I18nProvider>{children}</I18nProvider>
)

describe('I18nContext — real-key translation branches (live t)', () => {
  beforeEach(() => {
    localStorage.clear()
  })
  afterEach(() => {
    localStorage.clear()
    jest.clearAllMocks()
  })

  it('interpolates a single real variable into a real template', async () => {
    const { result } = renderHook(() => useI18n(), { wrapper: providerWrapper })
    await waitFor(() => expect(result.current.isReady).toBe(true))

    const out = result.current.t(KEY_ONE_VAR, { count: 7 })
    expect(out).toContain('7')
    expect(out).not.toContain('{count}')
  })

  it('interpolates multiple real variables into a real template', async () => {
    const { result } = renderHook(() => useI18n(), { wrapper: providerWrapper })
    await waitFor(() => expect(result.current.isReady).toBe(true))

    const out = result.current.t(KEY_TWO_VARS, { count: 3, total: 9 })
    expect(out).toContain('3')
    expect(out).toContain('9')
    expect(out).not.toContain('{count}')
    expect(out).not.toContain('{total}')
  })

  it('preserves the placeholder when a real-template variable is missing', async () => {
    const { result } = renderHook(() => useI18n(), { wrapper: providerWrapper })
    await waitFor(() => expect(result.current.isReady).toBe(true))

    // Provide an unrelated var so interpolation runs but {count} is unmatched.
    const out = result.current.t(KEY_ONE_VAR, { unrelated: 'x' })
    expect(out).toContain('{count}')
  })

  it('returns the key (not the object) for a namespace/object leaf', async () => {
    const { result } = renderHook(() => useI18n(), { wrapper: providerWrapper })
    await waitFor(() => expect(result.current.isReady).toBe(true))

    // common resolves to a plain object — the object guard returns key.
    expect(result.current.t(KEY_OBJECT)).toBe(KEY_OBJECT)
  })

  it('honours an explicit default value for an object leaf', async () => {
    const { result } = renderHook(() => useI18n(), { wrapper: providerWrapper })
    await waitFor(() => expect(result.current.isReady).toBe(true))

    // Second arg is a STRING => treated as defaultValue (lines 64-66 + 87).
    expect(result.current.t(KEY_OBJECT, 'fallback')).toBe('fallback')
  })

  it('returns an array leaf as-is (arrays are allowed through the guard)', async () => {
    const { result } = renderHook(() => useI18n(), { wrapper: providerWrapper })
    await waitFor(() => expect(result.current.isReady).toBe(true))

    const out = result.current.t(KEY_ARRAY)
    expect(Array.isArray(out)).toBe(true)
    expect((out as string[]).length).toBeGreaterThan(0)
  })

  it('uses the string default argument when a key is missing', async () => {
    const { result } = renderHook(() => useI18n(), { wrapper: providerWrapper })
    await waitFor(() => expect(result.current.isReady).toBe(true))

    // Missing key + string second arg => returns the default (line 80, 65).
    expect(result.current.t('totally.missing.key', 'Default Text')).toBe(
      'Default Text'
    )
  })

  it('switches the resolved string when locale changes de -> en', async () => {
    const { result } = renderHook(() => useI18n(), { wrapper: providerWrapper })
    await waitFor(() => expect(result.current.isReady).toBe(true))

    expect(result.current.t(KEY_PLAIN)).toBe(DE_PLAIN)

    act(() => {
      result.current.changeLocale('en')
    })

    expect(result.current.locale).toBe('en')
    expect(result.current.t(KEY_PLAIN)).toBe(EN_PLAIN)
  })

  it('does not interpolate a plain string when no variables are passed', async () => {
    const { result } = renderHook(() => useI18n(), { wrapper: providerWrapper })
    await waitFor(() => expect(result.current.isReady).toBe(true))

    // No vars => the interpolation branch is skipped, raw value returned.
    expect(result.current.t(KEY_PLAIN)).toBe(DE_PLAIN)
  })
})

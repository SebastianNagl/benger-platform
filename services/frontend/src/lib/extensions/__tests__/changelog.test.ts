import { act, renderHook } from '@testing-library/react'

import {
  type ChangelogEntry,
  getChangelogEntries,
  registerChangelogEntries,
  useChangelogEntries,
} from '../changelog'

const entry = (date: string, textDe: string): ChangelogEntry => ({
  date,
  audience: 'both',
  text: { de: textDe, en: `${textDe} (en)` },
})

describe('Changelog registry', () => {
  test('register then get returns the entries', () => {
    const entries = [entry('2026-08-24', 'Erster Eintrag')]
    registerChangelogEntries('test-roundtrip', entries)
    expect(getChangelogEntries()).toEqual(expect.arrayContaining(entries))
  })

  test('re-registering a source replaces its entries instead of duplicating', () => {
    registerChangelogEntries('test-idempotent', [entry('2026-08-01', 'v1')])
    registerChangelogEntries('test-idempotent', [entry('2026-08-01', 'v1')])

    const matching = getChangelogEntries().filter(
      (e) => e.text.de === 'v1',
    )
    expect(matching).toHaveLength(1)
  })

  test('flattens entries across multiple sources', () => {
    registerChangelogEntries('test-source-a', [entry('2026-08-02', 'aus A')])
    registerChangelogEntries('test-source-b', [entry('2026-08-03', 'aus B')])

    const texts = getChangelogEntries().map((e) => e.text.de)
    expect(texts).toEqual(expect.arrayContaining(['aus A', 'aus B']))
  })

  test('useChangelogEntries re-renders when entries register late', () => {
    const { result } = renderHook(() => useChangelogEntries())
    expect(
      result.current.some((e) => e.text.de === 'später registriert'),
    ).toBe(false)

    act(() => {
      registerChangelogEntries('test-late', [
        entry('2026-08-24', 'später registriert'),
      ])
    })

    expect(
      result.current.some((e) => e.text.de === 'später registriert'),
    ).toBe(true)
  })
})

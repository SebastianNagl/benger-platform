import type { ChangelogEntry } from '@/lib/extensions/changelog'

import { filterAndGroup } from '../changelog'

const entry = (
  date: string,
  audience: ChangelogEntry['audience'],
  textDe: string,
): ChangelogEntry => ({
  date,
  audience,
  text: { de: textDe, en: `${textDe} (en)` },
})

describe('filterAndGroup', () => {
  test('keeps only entries for the given brand plus "both"', () => {
    const groups = filterAndGroup(
      [
        entry('2026-08-24', 'benger', 'nur benger'),
        entry('2026-08-24', 'vertretbar', 'nur vertretbar'),
        entry('2026-08-24', 'both', 'beide'),
      ],
      'benger',
    )
    expect(groups).toHaveLength(1)
    expect(groups[0].entries.map((e) => e.text.de)).toEqual([
      'nur benger',
      'beide',
    ])
  })

  test('vertretbar brand sees vertretbar and both entries', () => {
    const groups = filterAndGroup(
      [
        entry('2026-08-24', 'benger', 'nur benger'),
        entry('2026-08-24', 'vertretbar', 'nur vertretbar'),
        entry('2026-08-24', 'both', 'beide'),
      ],
      'vertretbar',
    )
    expect(groups[0].entries.map((e) => e.text.de)).toEqual([
      'nur vertretbar',
      'beide',
    ])
  })

  test('groups by date, newest date first, preserving input order within a date', () => {
    const groups = filterAndGroup(
      [
        entry('2026-08-01', 'both', 'alt'),
        entry('2026-08-24', 'both', 'neu erstes'),
        entry('2026-08-24', 'both', 'neu zweites'),
      ],
      'benger',
    )
    expect(groups.map((g) => g.date)).toEqual(['2026-08-24', '2026-08-01'])
    expect(groups[0].entries.map((e) => e.text.de)).toEqual([
      'neu erstes',
      'neu zweites',
    ])
  })

  test('returns an empty list when nothing matches', () => {
    expect(
      filterAndGroup([entry('2026-08-24', 'vertretbar', 'x')], 'benger'),
    ).toEqual([])
  })
})

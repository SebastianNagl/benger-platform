import {
  computeWindowState,
  isoToLocalInput,
  localInputToIso,
  windowBoundLabel,
  windowStateLabel,
} from '../projectWindow'

const NOW = new Date('2026-07-01T12:00:00Z')

describe('computeWindowState', () => {
  it('returns "none" when neither bound is set', () => {
    expect(computeWindowState(null, null, NOW)).toBe('none')
    expect(computeWindowState(undefined, undefined, NOW)).toBe('none')
  })

  it('returns "upcoming" before the start', () => {
    expect(
      computeWindowState('2026-07-01T13:00:00Z', '2026-07-01T15:00:00Z', NOW),
    ).toBe('upcoming')
  })

  it('returns "open" within the window', () => {
    expect(
      computeWindowState('2026-07-01T11:00:00Z', '2026-07-01T13:00:00Z', NOW),
    ).toBe('open')
  })

  it('returns "closed" after the end', () => {
    expect(
      computeWindowState('2026-07-01T09:00:00Z', '2026-07-01T11:00:00Z', NOW),
    ).toBe('closed')
  })

  it('handles one-sided windows', () => {
    expect(computeWindowState('2026-07-01T13:00:00Z', null, NOW)).toBe(
      'upcoming',
    )
    expect(computeWindowState('2026-07-01T11:00:00Z', null, NOW)).toBe('open')
    expect(computeWindowState(null, '2026-07-01T13:00:00Z', NOW)).toBe('open')
    expect(computeWindowState(null, '2026-07-01T11:00:00Z', NOW)).toBe('closed')
  })
})

describe('windowBoundLabel', () => {
  it('labels the relevant bound', () => {
    expect(windowBoundLabel('upcoming', '2026-07-01T13:00:00Z', null)).toBe(
      new Date('2026-07-01T13:00:00Z').toLocaleString('de-DE'),
    )
    expect(windowBoundLabel('closed', null, '2026-07-01T11:00:00Z')).toBe(
      new Date('2026-07-01T11:00:00Z').toLocaleString('de-DE'),
    )
    expect(windowBoundLabel('open', '2026-07-01T13:00:00Z', null)).toBeNull()
    expect(windowBoundLabel('none', null, null)).toBeNull()
  })
})

describe('iso <-> datetime-local round-trip', () => {
  it('empty in, empty out', () => {
    expect(isoToLocalInput(null)).toBe('')
    expect(isoToLocalInput(undefined)).toBe('')
    expect(localInputToIso('')).toBeNull()
  })

  it('round-trips a local input back to the same UTC instant', () => {
    const iso = '2026-07-01T12:34:00.000Z'
    const local = isoToLocalInput(iso) // local wall-clock, no tz
    expect(local).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/)
    const back = localInputToIso(local)
    // Same instant to the minute (seconds are dropped by the input format).
    expect(new Date(back!).getTime()).toBe(new Date(iso).getTime())
  })

  it('ignores an unparseable iso', () => {
    expect(isoToLocalInput('not-a-date')).toBe('')
  })
})

describe('windowStateLabel', () => {
  const t = (key: string, vars?: Record<string, unknown>) =>
    vars ? `${key}:${JSON.stringify(vars)}` : key

  it('labels each state, with the opening date when upcoming', () => {
    expect(windowStateLabel('none', null, t, 'de')).toBeNull()
    expect(windowStateLabel('open', null, t, 'de')).toBe(
      'projects.list.windowOpen',
    )
    expect(windowStateLabel('closed', null, t, 'de')).toBe(
      'projects.list.windowClosed',
    )
    expect(windowStateLabel('upcoming', '2026-07-01T13:00:00Z', t, 'fr')).toBe(
      `projects.list.windowUpcoming:${JSON.stringify({
        date: new Date('2026-07-01T13:00:00Z').toLocaleDateString('fr-FR'),
      })}`,
    )
    expect(windowStateLabel('upcoming', null, t, 'de')).toBe(
      'projects.list.windowUpcoming:{"date":""}',
    )
  })
})

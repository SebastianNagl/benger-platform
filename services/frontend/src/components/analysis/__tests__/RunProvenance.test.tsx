/**
 * The provenance of an analysis run fits any width its container gives it.
 * At phone width (390 px) and in narrow overlay columns the rows used to
 * keep label and value on one line and the lists of libraries, counts and
 * timings could not shrink, so the component was wider than its container.
 * jsdom has no layout, so these tests pin the classes that let it shrink:
 * nothing forces a single line, rows wrap, values and list entries break,
 * and the grid and its lists have no minimum width of their own.
 */

import '@testing-library/jest-dom'
import { render, screen, within } from '@testing-library/react'

import { makeRun } from '@/test-utils/analysisFixtures'
import { RunProvenance } from '../RunProvenance'

jest.mock('@/contexts/I18nContext', () =>
  require('@/test-utils/i18nMock').i18nMock('en'),
)

const longRun = () =>
  makeRun({
    library_versions: {
      numpy: '2.3.4',
      scipy: '1.16.2',
      pandas: '2.3.3',
      statsmodels: '0.14.5',
      pyarrow: '21.0.0',
      linearmodels: '6.1',
    },
    frame_counts: {
      tasks: 1200,
      units: 600,
      generations: 125400,
      excluded_parse_failures: 312,
    },
    timings: { frame_s: 12.3456, fit_s: 48.12, total_s: 60.4869 },
  })

const classesOf = (el: Element) => Array.from(el.classList)

describe('RunProvenance at narrow widths', () => {
  it('lets nothing force a single line', () => {
    render(<RunProvenance run={longRun()} />)
    const root = screen.getByTestId('run-provenance')
    for (const el of [root, ...Array.from(root.querySelectorAll('*'))]) {
      const classes = classesOf(el)
      expect(classes).not.toContain('truncate')
      expect(classes).not.toContain('whitespace-nowrap')
      expect(classes).not.toContain('shrink-0')
    }
  })

  it('shrinks its grid and lists to the container', () => {
    render(<RunProvenance run={longRun()} />)
    const root = screen.getByTestId('run-provenance')
    // grid-cols-1 is minmax(0, 1fr): the track does not grow with content.
    expect(root).toHaveClass('grid', 'min-w-0', 'grid-cols-1')
    const lists = root.querySelectorAll('dl')
    expect(lists).toHaveLength(2)
    lists.forEach((dl) => expect(dl).toHaveClass('min-w-0'))
  })

  it('puts a value under its label when both do not fit, and breaks long values', () => {
    render(<RunProvenance run={longRun()} />)
    const rows = screen.getAllByTestId('run-provenance-row')
    expect(rows).toHaveLength(10)
    for (const row of rows) {
      expect(row).toHaveClass('flex', 'flex-wrap', 'min-w-0')
      const value = row.querySelector('dd')!
      // Beside the label while 8rem are left, under it otherwise.
      expect(value).toHaveClass('min-w-0', 'max-w-full', 'flex-[1_1_8rem]')
      expect(value).toHaveClass('[overflow-wrap:anywhere]')
    }
  })

  it('wraps and breaks every library, count and timing entry', () => {
    render(<RunProvenance run={longRun()} />)
    const entries = screen.getAllByTestId('run-provenance-entry')
    // 6 libraries, 4 counts, 3 timings.
    expect(entries).toHaveLength(13)
    for (const entry of entries) {
      expect(entry).toHaveClass('max-w-full', '[overflow-wrap:anywhere]')
      expect(entry.parentElement).toHaveClass('flex-wrap', 'min-w-0')
    }
    expect(
      within(screen.getByTestId('run-provenance')).getByText(
        /excluded_parse_failures/,
      ),
    ).toBeInTheDocument()
  })
})

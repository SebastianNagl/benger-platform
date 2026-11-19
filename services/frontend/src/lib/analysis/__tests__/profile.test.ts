/**
 * Profiles of estimates (`@/lib/analysis/profile`): the scope columns a
 * contrast varies over, the default columns, the points, lines and panels
 * built from synthetic estimates, ordinal x levels, the fitted slopes that
 * belong to exactly what is plotted and the run spec readers.
 */

import { makeEstimate } from '@/test-utils/analysisFixtures'
import {
  makeGapEstimates,
  makeInteractionEstimates,
  makeInteractionRun,
  makePositionEstimates,
  makePositionRun,
  SYSTEM_A,
  SYSTEM_B,
} from '@/test-utils/variantViewFixtures'
import {
  defaultProfileColumns,
  profileFromEstimates,
  profileSlopes,
  scopeColumns,
  specDesigns,
  specEstimands,
} from '../profile'

const curve = () =>
  makePositionEstimates().filter((e) => e.estimand_id === 'mean_by_position')

describe('scopeColumns and defaultProfileColumns', () => {
  it('lists the varying scope columns, numeric first', () => {
    expect(scopeColumns(curve())).toEqual([
      { name: 'pos', numeric: true, values: 4 },
      { name: 'group', numeric: false, values: 2 },
      { name: 'system', numeric: false, values: 2 },
    ])
  })

  it('takes the numeric column as x and the system as series', () => {
    expect(defaultProfileColumns(curve())).toEqual({
      x: 'pos',
      series: 'system',
      facet: null,
    })
  })

  it('draws no profile when only the system varies', () => {
    const rows = [SYSTEM_A, SYSTEM_B].map((system, i) =>
      makeEstimate({ position: i, scope_values: { system } }),
    )
    expect(defaultProfileColumns(rows)).toBeNull()
    expect(defaultProfileColumns([makeEstimate()])).toBeNull()
  })
})

describe('profileFromEstimates', () => {
  it('builds a slope over a numeric scope with series and facets', () => {
    const data = profileFromEstimates(curve(), {
      x: 'pos',
      series: 'system',
      facet: 'group',
    })
    expect(data.xLevels).toBeNull()
    expect(data.panels.map((p) => p.title)).toEqual([
      'group = g1',
      'group = g2',
    ])
    const [g1] = data.panels
    expect(g1.lines.map((l) => l.key)).toEqual([SYSTEM_A, SYSTEM_B])
    // Model names alone where no other system shares the model.
    expect(g1.lines.map((l) => l.label)).toEqual(['sim-alpha', 'sim-beta'])
    expect(g1.lines[0].title).toBe(`system = ${SYSTEM_A}`)
    expect(g1.lines[0].points.map((p) => [p.x, p.estimate])).toEqual([
      [1, 1.5],
      [2, 2],
      [3, 2.5],
      [4, 3],
    ])
    expect(g1.lines[0].points[0]).toMatchObject({
      lower: 1.3,
      upper: 1.7,
      n: 20,
    })
    expect(data.xMean).toBe(2.5)
  })

  it('keeps lines of other scope columns apart without a facet', () => {
    const data = profileFromEstimates(curve(), {
      x: 'pos',
      series: 'system',
      facet: null,
    })
    expect(data.panels).toHaveLength(2)
    expect(data.panels.every((p) => p.lines.length === 2)).toBe(true)
  })

  it('draws an ordinal x at the index of its levels in natural order', () => {
    const rows = ['level 10', 'level 2', 'level 1'].map((level, i) =>
      makeEstimate({
        position: i,
        scope: 'by level',
        scope_values: { level },
        estimate: i,
      }),
    )
    const data = profileFromEstimates(
      rows,
      { x: 'level', series: null, facet: null },
      { allLabel: 'All' },
    )
    expect(data.xLevels).toEqual(['level 1', 'level 2', 'level 10'])
    const [line] = data.panels[0].lines
    expect(line.label).toBe('All')
    expect(line.points.map((p) => [p.x, p.estimate])).toEqual([
      [0, 2],
      [1, 1],
      [2, 0],
    ])
  })

  it('leaves out estimates without a value of x or an estimate', () => {
    const rows = [
      makeEstimate({ position: 0, scope_values: { pos: 1 }, estimate: 1 }),
      makeEstimate({ position: 1, scope_values: { pos: 2 }, estimate: null }),
      makeEstimate({ position: 2, scope_values: {}, estimate: 3 }),
    ]
    const data = profileFromEstimates(rows, {
      x: 'pos',
      series: null,
      facet: null,
    })
    expect(data.panels[0].lines[0].points).toHaveLength(1)
  })
})

describe('the run spec', () => {
  it('gives a level profile the pooled slope of its x column', () => {
    const run = makePositionRun()
    const all = makePositionEstimates()
    const cols = { x: 'pos', series: 'system', facet: null }
    const slopes = profileSlopes(run, all, curve(), cols)
    expect(slopes.map((s) => [s.line, s.estimate.estimate])).toEqual([
      [null, 0.5],
    ])
    expect(profileSlopes(run, all, curve(), { ...cols, x: 'group' })).toEqual(
      [],
    )
    const other = curve().map((e) => ({ ...e, outcome: 'other' }))
    expect(profileSlopes(run, all, other, cols)).toEqual([])
  })

  it('gives a difference profile no slope of the outcome level', () => {
    // Flat gaps next to a level slope of 0.5: that slope is not the gap's.
    const gaps = makeGapEstimates()
    const all = [...makePositionEstimates(), ...gaps]
    expect(
      profileSlopes(makePositionRun(), all, gaps, {
        x: 'pos',
        series: null,
        facet: null,
      }),
    ).toEqual([])
  })

  it('gives each level its own slope in an interaction model', () => {
    const run = makeInteractionRun()
    const all = makeInteractionEstimates()
    const levels = all.filter((e) => e.estimand_id === 'mean_by_party')
    const slopes = profileSlopes(run, all, levels, {
      x: 'pos',
      series: 'party',
      facet: null,
    })
    expect(slopes.map((s) => [s.line, s.estimate.estimate])).toEqual([
      ['a', 0.2],
      ['b', 0.9],
    ])
    // Without the interacted factor as the series no line has one slope.
    expect(
      profileSlopes(run, all, levels, {
        x: 'pos',
        series: null,
        facet: 'party',
      }),
    ).toEqual([])
  })

  it('reads the estimands and designs of a run', () => {
    const run = makePositionRun()
    expect(specEstimands(run).map((e) => e.id)).toEqual([
      'mean_by_position',
      'position',
    ])
    expect(specDesigns(run)).toEqual(['roster'])
    expect(specEstimands(null)).toEqual([])
    expect(specDesigns({ normalized_spec: {} })).toEqual([])
  })
})

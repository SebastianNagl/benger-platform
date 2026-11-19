/**
 * The profile chart and the profiles of a run: a slope over a numeric scope
 * with series and facets drawn from synthetic estimates, ordinal axes,
 * bands, reference slopes, tooltips and the column pickers.
 */

import '@testing-library/jest-dom'
import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { profileFromEstimates } from '@/lib/analysis/profile'
import { makeEstimate, makeRun } from '@/test-utils/analysisFixtures'
import {
  makeGapEstimates,
  makeInteractionEstimates,
  makeInteractionRun,
  makePositionEstimates,
  makePositionRun,
  SYSTEM_A,
} from '@/test-utils/variantViewFixtures'
import { EstimateProfileChart } from '../EstimateProfileChart'
import { EstimateProfiles, profileGroups } from '../EstimateProfiles'

jest.mock('@/contexts/I18nContext', () =>
  require('@/test-utils/i18nMock').i18nMock('en'),
)

const curve = () =>
  makePositionEstimates().filter((e) => e.estimand_id === 'mean_by_position')

describe('EstimateProfileChart', () => {
  it('draws a slope over a numeric scope with series and facets', () => {
    const data = profileFromEstimates(curve(), {
      x: 'pos',
      series: 'system',
      facet: 'group',
    })
    render(
      <EstimateProfileChart
        data={data}
        xLabel="pos"
        yLabel="risk"
        slopes={[{ slope: 0.5, label: 'position · per position' }]}
      />,
    )
    const panels = screen.getAllByTestId('profile-panel')
    expect(panels).toHaveLength(2)
    expect(within(panels[0]).getByText('group = g1')).toBeInTheDocument()
    expect(within(panels[0]).getAllByTestId('profile-line')).toHaveLength(2)
    expect(within(panels[0]).getAllByRole('img')).toHaveLength(1)
    expect(within(panels[0]).getByTestId('profile-slope')).toBeInTheDocument()
    // Direct labels carry the model; the title names the full system key.
    expect(within(panels[0]).getByText('sim-alpha')).toBeInTheDocument()
    expect(
      screen.getByText('Fitted slope position · per position: 0.5'),
    ).toBeInTheDocument()
    expect(screen.getByText('risk by pos')).toBeInTheDocument()
    // The legend lists each series by its full name (as do the line titles).
    expect(
      screen
        .getAllByText(`system = ${SYSTEM_A}`)
        .some((node) => node.tagName === 'SPAN'),
    ).toBe(true)
  })

  it('shows a tooltip with the estimate, interval and n of a point', () => {
    const data = profileFromEstimates(curve(), {
      x: 'pos',
      series: 'system',
      facet: 'group',
    })
    const { container } = render(
      <EstimateProfileChart data={data} xLabel="pos" yLabel="risk" />,
    )
    const point = container.querySelector('circle') as SVGCircleElement
    fireEvent.mouseMove(point, { clientX: 10, clientY: 10 })
    expect(screen.getByRole('tooltip')).toHaveTextContent(
      '1: 1.5 [1.3, 1.7], n = 20',
    )
    fireEvent.mouseLeave(container.querySelector('svg') as SVGSVGElement)
    expect(screen.queryByRole('tooltip')).toBeNull()
  })

  it('draws ordinal ticks, a band and a reference slope', () => {
    const rows = ['low', 'mid', 'high'].map((level, i) =>
      makeEstimate({
        position: i,
        scope: 'by level',
        scope_values: { level },
        estimate: i,
        ci_lower: null,
        ci_upper: null,
      }),
    )
    const data = profileFromEstimates(rows, {
      x: 'level',
      series: null,
      facet: null,
    })
    data.panels[0].band = [
      { x: 0, low: 0, high: 1 },
      { x: 2, low: 1, high: 2 },
    ]
    render(
      <EstimateProfileChart
        data={data}
        xLabel="level"
        yLabel="share"
        reference={{ slope: 1, label: 'Smallest response that matters' }}
      />,
    )
    for (const level of ['high', 'low', 'mid']) {
      expect(screen.getAllByText(level).length).toBeGreaterThan(0)
    }
    expect(screen.getByTestId('profile-band')).toBeInTheDocument()
    expect(screen.getByTestId('profile-reference')).toBeInTheDocument()
    expect(screen.getByText('Ideal range')).toBeInTheDocument()
    expect(
      screen.getByText('Smallest response that matters'),
    ).toBeInTheDocument()
    expect(screen.queryByTestId('profile-slope')).toBeNull()
  })

  it('says when there is nothing to draw', () => {
    render(
      <EstimateProfileChart
        data={{ panels: [], xLevels: null, xMean: 0, yMean: 0 }}
        xLabel="x"
        yLabel="y"
      />,
    )
    expect(screen.getByText('There is nothing to draw.')).toBeInTheDocument()
  })
})

describe('EstimateProfiles', () => {
  it('profiles the first contrast that varies over an ordered scope', async () => {
    const user = userEvent.setup()
    render(
      <EstimateProfiles
        run={makePositionRun()}
        estimates={makePositionEstimates()}
      />,
    )
    expect(screen.getByTestId('profile-x')).toHaveValue('pos')
    expect(screen.getByTestId('profile-series')).toHaveValue('system')
    expect(screen.getByTestId('profile-facet')).toHaveValue('')
    // Without a facet the groups still get panels of their own.
    expect(screen.getAllByTestId('profile-panel')).toHaveLength(2)
    expect(screen.getAllByTestId('profile-slope')).toHaveLength(2)

    await user.selectOptions(screen.getByTestId('profile-facet'), 'group')
    expect(screen.getByTestId('profile-facet')).toHaveValue('group')
    await user.selectOptions(screen.getByTestId('profile-series'), '')
    expect(screen.getByTestId('profile-series')).toHaveValue('')
    expect(screen.getAllByTestId('profile-panel')).toHaveLength(4)
    // x and series never coincide.
    await user.selectOptions(screen.getByTestId('profile-series'), 'system')
    await user.selectOptions(screen.getByTestId('profile-x'), 'system')
    expect(screen.getByTestId('profile-series')).toHaveValue('')
  })

  it('switches between contrasts and resets the columns', async () => {
    const user = userEvent.setup()
    const other = curve().map((e, i) => ({
      ...e,
      position: 100 + i,
      estimand_id: 'second',
    }))
    render(
      <EstimateProfiles
        run={makePositionRun()}
        estimates={[...curve(), ...other]}
      />,
    )
    const select = screen.getByTestId('profile-contrast')
    expect(within(select).getAllByRole('option')).toHaveLength(2)
    await user.selectOptions(screen.getByTestId('profile-facet'), 'group')
    await user.selectOptions(select, within(select).getAllByRole('option')[1])
    expect(screen.getByTestId('profile-facet')).toHaveValue('')
    expect(screen.getAllByTestId('profile-panel')).toHaveLength(2)
    // These estimates hold no slope estimate on the x column.
    expect(screen.queryByTestId('profile-slope')).toBeNull()
    expect(screen.getByTestId('profile-no-slope')).toHaveTextContent(
      'No slope was estimated for this view.',
    )
  })

  it('draws no fitted slope through a flat gap profile', () => {
    render(
      <EstimateProfiles
        run={makePositionRun()}
        estimates={makeGapEstimates()}
        allEstimates={[...makePositionEstimates(), ...makeGapEstimates()]}
      />,
    )
    expect(screen.getAllByTestId('profile-line')).toHaveLength(1)
    expect(screen.queryByTestId('profile-slope')).toBeNull()
    expect(screen.getByTestId('profile-no-slope')).toBeInTheDocument()
  })

  it('draws one slope per level of an interaction model, with its interval', async () => {
    const user = userEvent.setup()
    const all = makeInteractionEstimates()
    render(
      <EstimateProfiles
        run={makeInteractionRun()}
        estimates={all.filter((e) => e.estimand_id === 'mean_by_party')}
        allEstimates={all}
      />,
    )
    expect(screen.getByTestId('profile-x')).toHaveValue('pos')
    expect(screen.getByTestId('profile-series')).toHaveValue('')
    expect(screen.queryByTestId('profile-slope')).toBeNull()
    await user.selectOptions(screen.getByTestId('profile-series'), 'party')
    expect(screen.getAllByTestId('profile-line')).toHaveLength(2)
    expect(screen.getAllByTestId('profile-slope')).toHaveLength(2)
    expect(
      screen.getAllByTestId('profile-slope-legend').map((n) => n.textContent),
    ).toEqual([
      'Fitted slope party = a · slopes · slope a: 0.2 [0.1, 0.3]',
      'Fitted slope party = b · slopes · slope b: 0.9 [0.8, 1]',
    ])
    expect(screen.queryByTestId('profile-no-slope')).toBeNull()
  })

  it('explains when no contrast has an ordered scope', () => {
    render(<EstimateProfiles run={makeRun()} estimates={[makeEstimate()]} />)
    expect(screen.getByTestId('profile-none')).toBeInTheDocument()
    expect(profileGroups([makeEstimate()])).toEqual([])
  })
})

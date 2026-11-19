/**
 * The generic forest plot and the contrast picker around it: rows, the null
 * line, the optional equivalence band and the TOST intervals drawn with it.
 */

import '@testing-library/jest-dom'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { ContrastForestPlot } from '@/components/analysis/ContrastForestPlot'
import { ForestPlot } from '@/components/analysis/ForestPlot'
import { makeEstimate, makeEstimates } from '@/test-utils/analysisFixtures'

jest.mock('@/contexts/I18nContext', () =>
  require('@/test-utils/i18nMock').i18nMock('en'),
)

const rows = [
  {
    id: 'a',
    label: 'Pooled',
    estimate: -2.5,
    lower: -3.48,
    upper: -1.52,
    emphasis: true,
  },
  { id: 'b', label: 'system = sys_a', estimate: 1, lower: -1, upper: 3 },
  {
    id: 'c',
    label: 'system = sys_b',
    estimate: null,
    lower: null,
    upper: null,
    note: 'not estimable',
  },
]

describe('ForestPlot', () => {
  it('draws one row per estimate with points, null line and values', () => {
    render(<ForestPlot rows={rows} ariaLabel="Forest plot of role" />)
    const svg = screen.getByRole('img', { name: 'Forest plot of role' })
    expect(within(svg).getAllByTestId('forest-plot-row')).toHaveLength(3)
    // Two rows have an estimate; the third shows its note instead.
    expect(within(svg).getAllByTestId('forest-plot-point')).toHaveLength(2)
    expect(within(svg).getByText('not estimable')).toBeInTheDocument()
    expect(within(svg).getByTestId('forest-plot-null')).toBeInTheDocument()
    expect(within(svg).getByText('-2.5 [-3.48, -1.52]')).toBeInTheDocument()
    expect(within(svg).queryByTestId('forest-plot-band')).toBeNull()
  })

  it('shades the band only when one is given and draws inner intervals', () => {
    const { rerender } = render(
      <ForestPlot
        rows={[{ ...rows[0], inner: { lower: -3.3, upper: -1.7 } }]}
        band={{ lower: -3, upper: 3, label: 'Equivalence bounds [-3, 3]' }}
        ariaLabel="plot"
        legend={{ interval: 'CI', inner: 'TOST', band: 'Bounds' }}
      />,
    )
    const band = screen.getByTestId('forest-plot-band')
    expect(band).toBeInTheDocument()
    expect(Number(band.getAttribute('width'))).toBeGreaterThan(0)
    expect(screen.getByTestId('forest-plot-inner')).toBeInTheDocument()
    expect(screen.getByText('Bounds')).toBeInTheDocument()
    expect(screen.getByText('TOST')).toBeInTheDocument()

    rerender(<ForestPlot rows={[rows[0]]} band={null} ariaLabel="plot" />)
    expect(screen.queryByTestId('forest-plot-band')).toBeNull()
    expect(screen.queryByTestId('forest-plot-inner')).toBeNull()
  })

  it('places the band between its bounds on the axis', () => {
    render(
      <ForestPlot
        rows={[{ id: 'x', label: 'x', estimate: 0, lower: -10, upper: 10 }]}
        band={{ lower: -5, upper: 5 }}
        ariaLabel="plot"
      />,
    )
    const svg = screen.getByRole('img')
    const tickX = (value: number) => {
      const label = Array.from(svg.querySelectorAll('text')).find(
        (node) =>
          node.textContent?.replace('\u2212', '-') === String(value) &&
          node.getAttribute('text-anchor') === 'middle',
      )
      if (!label) throw new Error(`no axis tick labelled ${value}`)
      return Number(label.getAttribute('x'))
    }
    const band = screen.getByTestId('forest-plot-band')
    const x = Number(band.getAttribute('x'))
    const w = Number(band.getAttribute('width'))
    expect(x).toBeCloseTo(tickX(-5), 6)
    expect(x + w).toBeCloseTo(tickX(5), 6)
    expect(w).toBeCloseTo((tickX(10) - tickX(-10)) / 2, 6)
  })

  it('shortens long labels and keeps the full one as a tooltip', () => {
    const long = 'system = ' + 'x'.repeat(120)
    render(
      <ForestPlot
        rows={[{ id: 'l', label: long, estimate: 1, lower: 0, upper: 2 }]}
        ariaLabel="plot"
      />,
    )
    const svg = screen.getByRole('img')
    expect(svg.querySelector('text title')?.textContent).toBe(long)
  })
})

describe('ContrastForestPlot', () => {
  it('plots the first contrast with its first bound set as the band', () => {
    render(<ContrastForestPlot estimates={makeEstimates()} />)
    const svg = screen.getByRole('img', { name: 'Forest plot of role' })
    expect(within(svg).getAllByTestId('forest-plot-row')).toHaveLength(3)
    expect(within(svg).getByText('Pooled')).toBeInTheDocument()
    expect(within(svg).getByText('system = sys_a')).toBeInTheDocument()
    expect(screen.getByTestId('forest-plot-band')).toBeInTheDocument()
    // With a band, every row draws its TOST interval as well.
    expect(screen.getAllByTestId('forest-plot-inner')).toHaveLength(3)
    expect(
      screen.getByText('Equivalence bounds [-3, 3]', { selector: 'span' }),
    ).toBeInTheDocument()
    expect(
      screen.getByText('Estimate with 95% confidence interval'),
    ).toBeInTheDocument()
  })

  it('switches the band off and to another bound set', async () => {
    const user = userEvent.setup()
    render(<ContrastForestPlot estimates={makeEstimates()} />)
    const picker = screen.getByTestId('forest-band-select')
    expect(picker).toHaveValue('0')
    await user.selectOptions(picker, 'none')
    expect(screen.queryByTestId('forest-plot-band')).toBeNull()
    expect(screen.queryByTestId('forest-plot-inner')).toBeNull()

    await user.selectOptions(picker, '1')
    expect(screen.getByTestId('forest-plot-band')).toBeInTheDocument()
    expect(
      screen.getByText('Equivalence bounds [-2, 2]', { selector: 'span' }),
    ).toBeInTheDocument()
  })

  it('remembers the band per contrast when the contrast changes', async () => {
    const user = userEvent.setup()
    const estimates = [
      ...makeEstimates(),
      makeEstimate({
        position: 4,
        estimand_id: 'slope',
        contrast_id: 'slope',
        null_value: 1,
        estimate: 0.6,
        ci_lower: 0.5,
        ci_upper: 0.7,
      }),
    ]
    render(<ContrastForestPlot estimates={estimates} />)
    await user.selectOptions(screen.getByTestId('forest-band-select'), 'none')
    const contrast = screen.getByTestId('forest-contrast-select')
    // the error-only contrast is not offered
    expect(
      Array.from((contrast as HTMLSelectElement).options).map((o) => o.text),
    ).toEqual(['role', 'slope'])
    await user.selectOptions(contrast, 'slope\u0000slope')
    expect(
      screen.getByRole('img', { name: 'Forest plot of slope' }),
    ).toBeInTheDocument()
    expect(screen.queryByTestId('forest-band-select')).toBeNull()
    // the null line sits at the contrast's null value 1
    expect(screen.getByTestId('forest-plot-null')).toBeInTheDocument()
    await user.selectOptions(contrast, 'role\u0000role')
    expect(screen.getByTestId('forest-band-select')).toHaveValue('none')
  })

  it('offers no band picker for a contrast without equivalence bounds', () => {
    render(
      <ContrastForestPlot
        estimates={[
          makeEstimate({ estimand_id: 'slope', contrast_id: 'slope' }),
        ]}
      />,
    )
    expect(screen.queryByTestId('forest-band-select')).toBeNull()
    expect(screen.queryByTestId('forest-plot-band')).toBeNull()
  })

  it('leaves out contrasts without any estimate and says so when none is left', () => {
    const errorOnly = makeEstimates().filter((e) => e.status === 'error')
    render(<ContrastForestPlot estimates={errorOnly} />)
    expect(
      screen.getByText('This run has no estimate to plot.'),
    ).toBeInTheDocument()
  })
})

/**
 * Bradley-Terry strengths render as a forest: players against the reference
 * per scope, and the forest view of a run that routes Bradley-Terry
 * estimands there and every other estimate to the contrast forest.
 */

import '@testing-library/jest-dom'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { makeEstimates } from '@/test-utils/analysisFixtures'
import {
  makeStrengthEstimates,
  makeStrengthRun,
  SYSTEM_A,
} from '@/test-utils/variantViewFixtures'
import { EstimatesForest } from '../EstimatesForest'
import { StrengthForestPlot, strengthLevel } from '../StrengthForestPlot'

jest.mock('@/contexts/I18nContext', () =>
  require('@/test-utils/i18nMock').i18nMock('en'),
)

const estimand = {
  id: 'pairs',
  estimator: 'bradley_terry',
  reference: 'a',
  players: ['left', 'right'],
  link: 'logit',
}

describe('StrengthForestPlot', () => {
  it('draws the pooled strengths against the reference first', () => {
    render(
      <StrengthForestPlot
        estimand={estimand}
        estimates={makeStrengthEstimates()}
      />,
    )
    const plot = screen.getByTestId('strength-forest-plot')
    const rows = within(plot).getAllByTestId('forest-plot-row')
    expect(rows).toHaveLength(3)
    expect(within(plot).getByText('a')).toBeInTheDocument()
    expect(within(plot).getByText('b')).toBeInTheDocument()
    expect(within(plot).getByText('c')).toBeInTheDocument()
    expect(screen.getByText('Strength (log odds)')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Pooled' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
  })

  it('switches to a system scope', async () => {
    const user = userEvent.setup()
    render(
      <StrengthForestPlot
        estimand={{ ...estimand, link: 'linear' }}
        estimates={makeStrengthEstimates()}
      />,
    )
    const chip = screen.getByRole('button', {
      name: `system = ${SYSTEM_A}`,
    })
    await user.click(chip)
    expect(chip).toHaveAttribute('aria-pressed', 'true')
    expect(
      screen.getByRole('img', {
        name: `Strengths of pairs, system = ${SYSTEM_A}`,
      }),
    ).toBeInTheDocument()
    expect(
      screen.getByText('Strength (difference in probability)'),
    ).toBeInTheDocument()
  })

  it('shows the engine note of a strength without estimate and no reference row without one', () => {
    const [first] = makeStrengthEstimates()
    render(
      <StrengthForestPlot
        estimand={{ id: 'pairs', estimator: 'bradley_terry' }}
        estimates={[
          { ...first, estimate: null, status: 'separation', message: null },
        ]}
      />,
    )
    expect(screen.getAllByTestId('forest-plot-row')).toHaveLength(1)
    expect(screen.getByText('separation')).toBeInTheDocument()
    expect(screen.queryByRole('group')).toBeNull()
  })

  it('renders nothing without estimates and reads strength levels', () => {
    const { container } = render(
      <StrengthForestPlot estimand={estimand} estimates={[]} />,
    )
    expect(container).toBeEmptyDOMElement()
    expect(strengthLevel('strength[x y]')).toBe('x y')
    expect(strengthLevel('other')).toBeNull()
    expect(strengthLevel(null)).toBeNull()
  })
})

describe('EstimatesForest', () => {
  it('draws Bradley-Terry estimands as strengths', () => {
    render(
      <EstimatesForest
        run={makeStrengthRun()}
        estimates={makeStrengthEstimates()}
      />,
    )
    expect(screen.getByTestId('strengths')).toHaveTextContent(
      'Strengths of pairs',
    )
    expect(
      screen.getByText(
        'Bradley-Terry strength of each level of left, right against the reference level a (fixed at 0), with its confidence interval.',
      ),
    ).toBeInTheDocument()
    expect(screen.queryByText('Contrast')).toBeNull()
  })

  it('keeps every other estimate in the contrast forest', () => {
    render(
      <EstimatesForest
        run={makeStrengthRun()}
        estimates={[...makeEstimates(), ...makeStrengthEstimates()]}
      />,
    )
    expect(screen.getByTestId('strengths')).toBeInTheDocument()
    expect(screen.getAllByTestId('forest-plot').length).toBeGreaterThan(0)
  })
})

/**
 * The analysis blocks of the statistics panel: families with their method
 * and adjusted p-values, equivalence tests, MDEs and joint tests (Inference),
 * the run's warnings and fits (Fit).
 */

import '@testing-library/jest-dom'
import { render, screen, within } from '@testing-library/react'

import {
  makeEstimate,
  makeEstimates,
  makeRun,
  makeTost,
} from '@/test-utils/analysisFixtures'
import { StatisticalResultsPanel } from '../StatisticalResultsPanel'
import {
  AnalysisFitBlock,
  AnalysisInferenceBlock,
} from '../statistics/AnalysisStatistics'

jest.mock('@/contexts/I18nContext', () =>
  require('@/test-utils/i18nMock').i18nMock('en'),
)

describe('AnalysisInferenceBlock', () => {
  it('lists each family with its method, size and adjusted p-values', () => {
    render(<AnalysisInferenceBlock estimates={makeEstimates()} />)
    const families = screen.getAllByTestId('analysis-family')
    expect(families).toHaveLength(2)
    // familiesOf sorts the ids: per_system, primary
    expect(
      within(families[0]).getByText('Family per_system: Holm, 2 tests'),
    ).toBeInTheDocument()
    const members = within(families[0]).getAllByTestId('analysis-family-member')
    expect(members).toHaveLength(2)
    expect(within(members[0]).getByText('system = sys_a')).toBeInTheDocument()
    expect(within(members[0]).getByText('2E-4')).toBeInTheDocument()
    expect(within(members[1]).getAllByText('0.570')).toHaveLength(2)

    expect(
      within(families[1]).getByText('Family primary: Holm, 2 tests'),
    ).toBeInTheDocument()
    expect(within(families[1]).getByText('0.020')).toBeInTheDocument()
    expect(
      within(families[1]).getByText(
        'Minimum detectable effect of the family: 1.6 (power 80%, α 0.05)',
      ),
    ).toBeInTheDocument()
  })

  it('lists every equivalence test with bounds and decision', () => {
    render(<AnalysisInferenceBlock estimates={makeEstimates()} />)
    const rows = screen.getAllByTestId('analysis-tost-row')
    // three estimates with two bound sets each
    expect(rows).toHaveLength(6)
    expect(within(rows[0]).getByText('[-3, 3]')).toBeInTheDocument()
    expect(within(rows[0]).getByText('Not established')).toBeInTheDocument()
    expect(within(rows[4]).getByText('Equivalent')).toBeInTheDocument()
  })

  it('shows MDEs and joint tests when the run has them', () => {
    render(
      <AnalysisInferenceBlock
        estimates={[
          makeEstimate({
            position: 0,
            mde: { power: 0.9, alpha: 0.05, tests: 3, value: 2.25 },
          }),
          makeEstimate({
            position: 1,
            estimand_id: 'joint',
            contrast_id: 'all slots',
            kind: 'wald',
            estimate: null,
            statistic: 12.5,
            df: 3,
            p_value: 0.0058,
            p_adjusted: 0.012,
          }),
          makeEstimate({ position: 2, family: 'f', p_adjusted: 0.3 }),
        ]}
      />,
    )
    const mde = screen.getByTestId('analysis-mde-row')
    expect(within(mde).getByText('2.25')).toBeInTheDocument()
    expect(within(mde).getByText('90%')).toBeInTheDocument()
    const joint = screen.getByTestId('analysis-joint-row')
    expect(within(joint).getByText('joint · all slots')).toBeInTheDocument()
    expect(within(joint).getByText('12.5')).toBeInTheDocument()
    expect(within(joint).getByText('3')).toBeInTheDocument()
    expect(within(joint).getByText('0.006')).toBeInTheDocument()
    expect(within(joint).getByText('0.012')).toBeInTheDocument()
    // A family named only on the estimate (no adjustments) still lists it.
    const family = screen.getByTestId('analysis-family')
    expect(within(family).getByText('Family f: —, 1 tests')).toBeInTheDocument()
    expect(within(family).getByText('0.300')).toBeInTheDocument()
  })

  it('says so when the run declares no inference', () => {
    render(
      <AnalysisInferenceBlock
        estimates={[makeEstimate({ tost: [], adjustments: null })]}
      />,
    )
    expect(
      screen.getByText(
        'This run declares no families, equivalence bounds, power settings or joint tests.',
      ),
    ).toBeInTheDocument()
  })

  it('shows an unknown method and a missing decision as given', () => {
    render(
      <AnalysisInferenceBlock
        estimates={[
          makeEstimate({
            tost: [makeTost({ equivalent: null })],
            family: 'g',
            adjustments: [
              {
                family: 'g',
                method: 'custom',
                group: [],
                size: 4,
                p_adjusted: null,
              },
            ],
          }),
        ]}
      />,
    )
    expect(screen.getByText('Family g: custom, 4 tests')).toBeInTheDocument()
    const tost = screen.getByTestId('analysis-tost-row')
    expect(within(tost).getAllByText('—').length).toBeGreaterThan(0)
  })
})

describe('AnalysisFitBlock', () => {
  it('shows the warnings and the fits', () => {
    render(<AnalysisFitBlock run={makeRun()} />)
    expect(
      screen.getByText('by_system [pooled]: collinear regressors'),
    ).toBeInTheDocument()
    expect(screen.getByTestId('run-fits')).toBeInTheDocument()
  })

  it('says so when no fit is recorded', () => {
    render(<AnalysisFitBlock run={makeRun({ fits: null, warnings: null })} />)
    expect(screen.getByText('No fits recorded.')).toBeInTheDocument()
    expect(screen.queryByTestId('analysis-fit-warnings')).toBeNull()
  })
})

describe('StatisticalResultsPanel for an analysis run', () => {
  it('shows the inference and fit blocks instead of metric statistics', () => {
    render(
      <StatisticalResultsPanel
        data={null}
        analysis={{ run: makeRun(), estimates: makeEstimates() }}
      />,
    )
    expect(screen.getByTestId('analysis-statistics')).toBeInTheDocument()
    expect(screen.getByTestId('analysis-inference-block')).toBeInTheDocument()
    expect(screen.getByTestId('analysis-fit-block')).toBeInTheDocument()
    expect(
      screen.queryByText('Select metrics to compute statistics'),
    ).toBeNull()
  })
})

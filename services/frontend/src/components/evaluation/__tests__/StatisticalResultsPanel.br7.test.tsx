/**
 * @jest-environment jsdom
 *
 * Branch coverage round 7: StatisticalResultsPanel.tsx
 * Targets: formatValue, formatPValue, getSignificanceStars, getEffectSizeColor,
 *          getCorrelationColor, showStat filtering, loading/error/null states,
 *          per-model stats, per-field stats, bonferroni correction, warnings
 */

import React from 'react'
import { render, screen } from '@testing-library/react'
import '@testing-library/jest-dom'

// Mock I18n
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, params?: any) => {
      if (params && typeof params === 'object') return `${key}[${JSON.stringify(params)}]`
      return key
    },
  }),
}))

// Must import after mocks
import { StatisticalResultsPanel } from '../StatisticalResultsPanel'

const baseMetrics = {
  accuracy: { mean: 0.85, std: 0.1, ci_lower: 0.8, ci_upper: 0.9, n: 100 },
}

describe('StatisticalResultsPanel br7 - formatValue', () => {
  it('formats value in 0-1 range as percentage', () => {
    render(
      <StatisticalResultsPanel
        data={{
          aggregation: 'overall',
          metrics: {
            accuracy: { mean: 0.856, std: 0.1, ci_lower: 0.8, ci_upper: 0.9, n: 100 },
          },
        }}
      />
    )
    expect(screen.getByText('85.6%')).toBeInTheDocument()
  })

  it('formats value > 1 with 4 decimal places', () => {
    render(
      <StatisticalResultsPanel
        data={{
          aggregation: 'overall',
          metrics: {
            loss: { mean: 2.3456, std: 0.5, ci_lower: 2.0, ci_upper: 2.7, n: 50 },
          },
        }}
      />
    )
    expect(screen.getByText('2.3456')).toBeInTheDocument()
  })
})

describe('StatisticalResultsPanel br7 - formatPValue and significance stars', () => {
  it('formats p < 0.001 as <0.001 with ***', () => {
    render(
      <StatisticalResultsPanel
        data={{
          aggregation: 'overall',
          metrics: baseMetrics,
          pairwise_comparisons: [
            {
              model_a: 'A',
              model_b: 'B',
              metric: 'accuracy',
              ttest_p: 0.0001,
              significant: true,
            },
          ],
        }}
      />
    )
    expect(screen.getByText('<0.001')).toBeInTheDocument()
    expect(screen.getByText('***')).toBeInTheDocument()
  })

  it('formats 0.001 <= p < 0.01 with **', () => {
    render(
      <StatisticalResultsPanel
        data={{
          aggregation: 'overall',
          metrics: baseMetrics,
          pairwise_comparisons: [
            {
              model_a: 'A',
              model_b: 'B',
              metric: 'accuracy',
              ttest_p: 0.005,
              significant: true,
            },
          ],
        }}
      />
    )
    expect(screen.getByText('**')).toBeInTheDocument()
  })

  it('formats 0.01 <= p < 0.05 with *', () => {
    render(
      <StatisticalResultsPanel
        data={{
          aggregation: 'overall',
          metrics: baseMetrics,
          pairwise_comparisons: [
            {
              model_a: 'A',
              model_b: 'B',
              metric: 'accuracy',
              ttest_p: 0.03,
              significant: true,
            },
          ],
        }}
      />
    )
    expect(screen.getByText('*')).toBeInTheDocument()
  })

  it('formats p >= 0.05 with no stars', () => {
    render(
      <StatisticalResultsPanel
        data={{
          aggregation: 'overall',
          metrics: baseMetrics,
          pairwise_comparisons: [
            {
              model_a: 'A',
              model_b: 'B',
              metric: 'accuracy',
              ttest_p: 0.15,
              significant: false,
            },
          ],
        }}
      />
    )
    expect(screen.getByText('0.15')).toBeInTheDocument()
  })
})

describe('StatisticalResultsPanel br7 - getEffectSizeColor', () => {
  it('shows large effect size', () => {
    render(
      <StatisticalResultsPanel
        data={{
          aggregation: 'overall',
          metrics: baseMetrics,
          pairwise_comparisons: [
            {
              model_a: 'A',
              model_b: 'B',
              metric: 'accuracy',
              ttest_p: 0.01,
              cohens_d: 1.2,
              cohens_d_interpretation: 'large',
              significant: true,
            },
          ],
        }}
      />
    )
    expect(screen.getByText(/large/)).toBeInTheDocument()
  })

  it('shows medium effect size', () => {
    render(
      <StatisticalResultsPanel
        data={{
          aggregation: 'overall',
          metrics: baseMetrics,
          pairwise_comparisons: [
            {
              model_a: 'A',
              model_b: 'B',
              metric: 'accuracy',
              ttest_p: 0.01,
              cohens_d: 0.5,
              cohens_d_interpretation: 'medium',
              significant: true,
            },
          ],
        }}
      />
    )
    expect(screen.getByText(/medium/)).toBeInTheDocument()
  })

  it('shows small effect size', () => {
    render(
      <StatisticalResultsPanel
        data={{
          aggregation: 'overall',
          metrics: baseMetrics,
          pairwise_comparisons: [
            {
              model_a: 'A',
              model_b: 'B',
              metric: 'accuracy',
              ttest_p: 0.03,
              cohens_d: 0.2,
              cohens_d_interpretation: 'small',
              significant: true,
            },
          ],
        }}
      />
    )
    expect(screen.getByText(/small/)).toBeInTheDocument()
  })
})

describe('StatisticalResultsPanel br7 - getCorrelationColor', () => {
  it('renders correlation matrix with strong positive values', () => {
    render(
      <StatisticalResultsPanel
        data={{
          aggregation: 'overall',
          metrics: {
            accuracy: { mean: 0.85, std: 0.1, ci_lower: 0.8, ci_upper: 0.9, n: 100 },
            f1: { mean: 0.82, std: 0.12, ci_lower: 0.75, ci_upper: 0.89, n: 100 },
          },
          correlations: {
            accuracy: { accuracy: 1.0, f1: 0.95 },
            f1: { accuracy: 0.95, f1: 1.0 },
          },
        }}
      />
    )
    // Symmetric matrix: 0.95 appears twice
    expect(screen.getAllByText('0.95').length).toBeGreaterThanOrEqual(2)
  })

  it('renders correlation matrix with strong negative values', () => {
    render(
      <StatisticalResultsPanel
        data={{
          aggregation: 'overall',
          metrics: {
            accuracy: { mean: 0.85, std: 0.1, ci_lower: 0.8, ci_upper: 0.9, n: 100 },
            loss: { mean: 2.0, std: 0.5, ci_lower: 1.5, ci_upper: 2.5, n: 100 },
          },
          correlations: {
            accuracy: { accuracy: 1.0, loss: -0.8 },
            loss: { accuracy: -0.8, loss: 1.0 },
          },
        }}
      />
    )
    expect(screen.getAllByText('-0.80').length).toBeGreaterThanOrEqual(2)
  })

  it('renders correlation with moderate positive', () => {
    render(
      <StatisticalResultsPanel
        data={{
          aggregation: 'overall',
          metrics: {
            a: { mean: 0.5, std: 0.1, ci_lower: 0.4, ci_upper: 0.6, n: 10 },
            b: { mean: 0.5, std: 0.1, ci_lower: 0.4, ci_upper: 0.6, n: 10 },
          },
          correlations: {
            a: { a: 1.0, b: 0.5 },
            b: { a: 0.5, b: 1.0 },
          },
        }}
      />
    )
    expect(screen.getAllByText('0.50').length).toBeGreaterThanOrEqual(2)
  })

  it('renders correlation with weak value', () => {
    render(
      <StatisticalResultsPanel
        data={{
          aggregation: 'overall',
          metrics: {
            a: { mean: 0.5, std: 0.1, ci_lower: 0.4, ci_upper: 0.6, n: 10 },
            b: { mean: 0.5, std: 0.1, ci_lower: 0.4, ci_upper: 0.6, n: 10 },
          },
          correlations: {
            a: { a: 1.0, b: 0.1 },
            b: { a: 0.1, b: 1.0 },
          },
        }}
      />
    )
    expect(screen.getAllByText('0.10').length).toBeGreaterThanOrEqual(2)
  })

  it('renders correlation with null value as dash', () => {
    render(
      <StatisticalResultsPanel
        data={{
          aggregation: 'overall',
          metrics: {
            a: { mean: 0.5, std: 0.1, ci_lower: 0.4, ci_upper: 0.6, n: 10 },
            b: { mean: 0.5, std: 0.1, ci_lower: 0.4, ci_upper: 0.6, n: 10 },
          },
          correlations: {
            a: { a: 1.0, b: null },
            b: { a: null, b: 1.0 },
          },
        }}
      />
    )
    expect(screen.getAllByText('-').length).toBeGreaterThan(0)
  })

  it('renders moderate negative correlation', () => {
    render(
      <StatisticalResultsPanel
        data={{
          aggregation: 'overall',
          metrics: {
            a: { mean: 0.5, std: 0.1, ci_lower: 0.4, ci_upper: 0.6, n: 10 },
            b: { mean: 0.5, std: 0.1, ci_lower: 0.4, ci_upper: 0.6, n: 10 },
          },
          correlations: {
            a: { a: 1.0, b: -0.5 },
            b: { a: -0.5, b: 1.0 },
          },
        }}
      />
    )
    expect(screen.getAllByText('-0.50').length).toBeGreaterThanOrEqual(2)
  })

  it('renders weak negative correlation', () => {
    render(
      <StatisticalResultsPanel
        data={{
          aggregation: 'overall',
          metrics: {
            a: { mean: 0.5, std: 0.1, ci_lower: 0.4, ci_upper: 0.6, n: 10 },
            b: { mean: 0.5, std: 0.1, ci_lower: 0.4, ci_upper: 0.6, n: 10 },
          },
          correlations: {
            a: { a: 1.0, b: -0.25 },
            b: { a: -0.25, b: 1.0 },
          },
        }}
      />
    )
    expect(screen.getAllByText('-0.25').length).toBeGreaterThanOrEqual(2)
  })
})

describe('StatisticalResultsPanel br7 - loading, error, null states', () => {
  it('renders loading state', () => {
    render(<StatisticalResultsPanel data={null} loading={true} />)
    expect(screen.getByText('evaluation.statisticalResults.computingStatistics')).toBeInTheDocument()
  })

  it('renders error state', () => {
    render(<StatisticalResultsPanel data={null} error="Something went wrong" />)
    expect(screen.getByText('Something went wrong')).toBeInTheDocument()
  })

  it('renders null data prompt', () => {
    render(<StatisticalResultsPanel data={null} />)
    expect(screen.getByText('evaluation.statisticalResults.selectMetricsPrompt')).toBeInTheDocument()
  })
})

describe('StatisticalResultsPanel br7 - warnings and bonferroni', () => {
  it('renders warnings when present', () => {
    render(
      <StatisticalResultsPanel
        data={{
          aggregation: 'overall',
          metrics: baseMetrics,
          warnings: ['Sample size is small', 'Data may be skewed'],
        }}
      />
    )
    expect(screen.getByText('Sample size is small')).toBeInTheDocument()
    expect(screen.getByText('Data may be skewed')).toBeInTheDocument()
  })

  it('renders bonferroni correction info when applied', () => {
    render(
      <StatisticalResultsPanel
        data={{
          aggregation: 'overall',
          metrics: baseMetrics,
          pairwise_comparisons: [
            { model_a: 'A', model_b: 'B', metric: 'accuracy', ttest_p: 0.01, significant: true },
          ],
          bonferroni_correction: {
            applied: true,
            num_comparisons: 3,
            original_alpha: 0.05,
            corrected_alpha: 0.0167,
          },
        }}
      />
    )
    expect(screen.getByText('evaluation.statisticalResults.bonferroniCorrected')).toBeInTheDocument()
  })

  it('renders warning when bonferroni not applied', () => {
    render(
      <StatisticalResultsPanel
        data={{
          aggregation: 'overall',
          metrics: baseMetrics,
          pairwise_comparisons: [
            { model_a: 'A', model_b: 'B', metric: 'accuracy', ttest_p: 0.01, significant: true },
          ],
          bonferroni_correction: {
            applied: false,
            num_comparisons: 3,
            original_alpha: 0.05,
            corrected_alpha: 0.0167,
          },
        }}
      />
    )
    expect(screen.getByText('evaluation.statisticalResults.multipleComparisons')).toBeInTheDocument()
  })

  it('renders auto-detect warning when multiple comparisons without bonferroni data', () => {
    render(
      <StatisticalResultsPanel
        data={{
          aggregation: 'overall',
          metrics: baseMetrics,
          pairwise_comparisons: [
            { model_a: 'A', model_b: 'B', metric: 'accuracy', ttest_p: 0.01, significant: true },
            { model_a: 'A', model_b: 'C', metric: 'accuracy', ttest_p: 0.02, significant: true },
          ],
        }}
      />
    )
    expect(screen.getByText(/evaluation\.statisticalResults\.considerBonferroni/)).toBeInTheDocument()
  })
})

describe('StatisticalResultsPanel br7 - selectedStatistics filtering', () => {
  it('hides CI column when ci not in selectedStatistics', () => {
    const { container } = render(
      <StatisticalResultsPanel
        data={{
          aggregation: 'overall',
          metrics: baseMetrics,
        }}
        selectedStatistics={['std']}
      />
    )
    // CI header should not appear
    expect(screen.queryByText('evaluation.statisticalResults.ci95')).not.toBeInTheDocument()
  })

  it('shows SE column when se is in selectedStatistics', () => {
    render(
      <StatisticalResultsPanel
        data={{
          aggregation: 'overall',
          metrics: {
            accuracy: { mean: 0.85, std: 0.1, se: 0.01, ci_lower: 0.8, ci_upper: 0.9, n: 100 },
          },
        }}
        selectedStatistics={['se']}
      />
    )
    expect(screen.getByText('evaluation.statisticalResults.se')).toBeInTheDocument()
  })

  it('hides pairwise comparisons when ttest/bootstrap not selected', () => {
    render(
      <StatisticalResultsPanel
        data={{
          aggregation: 'overall',
          metrics: baseMetrics,
          pairwise_comparisons: [
            { model_a: 'A', model_b: 'B', metric: 'accuracy', ttest_p: 0.01, significant: true },
          ],
        }}
        selectedStatistics={['ci']}
      />
    )
    // Pairwise section should not appear
    expect(screen.queryByText('evaluation.statisticalResults.pairwiseComparisons')).not.toBeInTheDocument()
  })

  it('hides effect size column when cohens_d/cliffs_delta not selected', () => {
    render(
      <StatisticalResultsPanel
        data={{
          aggregation: 'overall',
          metrics: baseMetrics,
          pairwise_comparisons: [
            {
              model_a: 'A',
              model_b: 'B',
              metric: 'accuracy',
              ttest_p: 0.01,
              cohens_d: 0.8,
              cohens_d_interpretation: 'large',
              significant: true,
            },
          ],
        }}
        selectedStatistics={['ttest']}
      />
    )
    // Effect size header should not appear
    expect(screen.queryByText('evaluation.statisticalResults.effectSize')).not.toBeInTheDocument()
  })

  it('hides correlation matrix when correlation not in selectedStatistics', () => {
    render(
      <StatisticalResultsPanel
        data={{
          aggregation: 'overall',
          metrics: baseMetrics,
          correlations: {
            accuracy: { accuracy: 1.0 },
          },
        }}
        selectedStatistics={['ci']}
      />
    )
    expect(screen.queryByText('evaluation.statisticalResults.correlationMatrix')).not.toBeInTheDocument()
  })
})

describe('StatisticalResultsPanel br7 - per-model and per-field breakdowns', () => {
  it('renders per-model statistics table', () => {
    render(
      <StatisticalResultsPanel
        data={{
          aggregation: 'model',
          metrics: baseMetrics,
          by_model: {
            'gpt-4': {
              model_id: 'gpt-4',
              model_name: 'GPT-4',
              metrics: {
                accuracy: { mean: 0.9, std: 0.05, ci_lower: 0.85, ci_upper: 0.95, n: 50, se: 0.007 },
              },
              sample_count: 50,
            },
            'claude': {
              model_id: 'claude',
              metrics: {
                accuracy: { mean: 0.88, std: 0.06, ci_lower: 0.82, ci_upper: 0.94, n: 50 },
              },
              sample_count: 50,
            },
          },
        }}
      />
    )
    expect(screen.getByText('GPT-4')).toBeInTheDocument()
    expect(screen.getByText('claude')).toBeInTheDocument() // Falls back to modelId
    expect(screen.getByText('evaluation.statisticalResults.perModelStatistics')).toBeInTheDocument()
  })

  it('renders per-field statistics table', () => {
    render(
      <StatisticalResultsPanel
        data={{
          aggregation: 'field',
          metrics: baseMetrics,
          by_field: {
            'answer': {
              field_name: 'answer',
              metrics: {
                accuracy: { mean: 0.92, std: 0.04, ci_lower: 0.88, ci_upper: 0.96, n: 30, se: 0.007 },
              },
              sample_count: 30,
            },
          },
        }}
      />
    )
    expect(screen.getByText('answer')).toBeInTheDocument()
    expect(screen.getByText('evaluation.statisticalResults.perFieldStatistics')).toBeInTheDocument()
  })

  it('shows "overall" title when model/field breakdown present', () => {
    render(
      <StatisticalResultsPanel
        data={{
          aggregation: 'model',
          metrics: baseMetrics,
          by_model: {
            'gpt-4': {
              model_id: 'gpt-4',
              model_name: 'GPT-4',
              metrics: baseMetrics,
              sample_count: 50,
            },
          },
        }}
      />
    )
    expect(screen.getByText('evaluation.statisticalResults.overallStatistics')).toBeInTheDocument()
  })

  it('shows dash for missing metric in model breakdown', () => {
    const { container } = render(
      <StatisticalResultsPanel
        data={{
          aggregation: 'model',
          metrics: {
            accuracy: { mean: 0.85, std: 0.1, ci_lower: 0.8, ci_upper: 0.9, n: 100 },
            f1: { mean: 0.82, std: 0.12, ci_lower: 0.75, ci_upper: 0.89, n: 100 },
          },
          by_model: {
            'gpt-4': {
              model_id: 'gpt-4',
              model_name: 'GPT-4',
              metrics: {
                accuracy: { mean: 0.9, std: 0.05, ci_lower: 0.85, ci_upper: 0.95, n: 50 },
                // Missing f1 metric
              },
              sample_count: 50,
            },
          },
        }}
      />
    )
    // Should contain the em-dash for the missing metric cell
    const cells = container.querySelectorAll('td')
    const dashCells = Array.from(cells).filter(cell => cell.textContent?.trim() === '\u2014')
    expect(dashCells.length).toBeGreaterThan(0)
  })
})

describe('StatisticalResultsPanel br7 - SE in model/field rows', () => {
  it('shows SE in per-model stats when se selected and se value present', () => {
    render(
      <StatisticalResultsPanel
        data={{
          aggregation: 'model',
          metrics: baseMetrics,
          by_model: {
            'gpt-4': {
              model_id: 'gpt-4',
              model_name: 'GPT-4',
              metrics: {
                accuracy: { mean: 0.9, std: 0.05, ci_lower: 0.85, ci_upper: 0.95, n: 50, se: 0.007 },
              },
              sample_count: 50,
            },
          },
        }}
        selectedStatistics={['se', 'ci']}
      />
    )
    // SE value should be rendered
    expect(screen.getByText(/0.007/)).toBeInTheDocument()
  })

  it('shows SE in per-field stats when se selected and se value present', () => {
    render(
      <StatisticalResultsPanel
        data={{
          aggregation: 'field',
          metrics: baseMetrics,
          by_field: {
            'answer': {
              field_name: 'answer',
              metrics: {
                accuracy: { mean: 0.92, std: 0.04, ci_lower: 0.88, ci_upper: 0.96, n: 30, se: 0.008 },
              },
              sample_count: 30,
            },
          },
        }}
        selectedStatistics={['se', 'ci']}
      />
    )
    expect(screen.getByText(/0.008/)).toBeInTheDocument()
  })

  it('renders SE dash in overall metrics when se undefined', () => {
    render(
      <StatisticalResultsPanel
        data={{
          aggregation: 'overall',
          metrics: {
            accuracy: { mean: 0.85, std: 0.1, ci_lower: 0.8, ci_upper: 0.9, n: 100 },
          },
        }}
        selectedStatistics={['se']}
      />
    )
    // Should show em-dash for missing SE
    const cells = document.querySelectorAll('td')
    const seCell = Array.from(cells).find(c => c.textContent?.trim() === '\u2014')
    expect(seCell).toBeTruthy()
  })
})

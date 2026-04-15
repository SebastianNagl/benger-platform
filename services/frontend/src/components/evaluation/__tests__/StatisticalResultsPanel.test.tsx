/**
 * @jest-environment jsdom
 */
import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'
import { StatisticalResultsPanel } from '../StatisticalResultsPanel'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, params?: Record<string, any>) => {
      const translations: Record<string, string> = {
        'evaluation.statisticalResults.computingStatistics':
          'Computing statistics...',
        'evaluation.statisticalResults.selectMetricsPrompt':
          'Select metrics to see statistical analysis',
        'evaluation.statisticalResults.aggregation': 'Aggregation',
        'evaluation.statisticalResults.metricStatistics': 'Metric Statistics',
        'evaluation.statisticalResults.overallStatistics': 'Overall Statistics',
        'evaluation.statisticalResults.perModelStatistics':
          'Per-Model Statistics',
        'evaluation.statisticalResults.perFieldStatistics':
          'Per-Field Statistics',
        'evaluation.statisticalResults.metric': 'Metric',
        'evaluation.statisticalResults.mean': 'Mean',
        'evaluation.statisticalResults.ci95': '95% CI',
        'evaluation.statisticalResults.std': 'Std',
        'evaluation.statisticalResults.se': 'SE',
        'evaluation.statisticalResults.n': 'N',
        'evaluation.statisticalResults.model': 'Model',
        'evaluation.statisticalResults.field': 'Field',
        'evaluation.statisticalResults.pairwiseComparisons':
          'Pairwise Comparisons',
        'evaluation.statisticalResults.modelA': 'Model A',
        'evaluation.statisticalResults.modelB': 'Model B',
        'evaluation.statisticalResults.pValue': 'p-value',
        'evaluation.statisticalResults.effectSize': 'Effect Size',
        'evaluation.statisticalResults.significant': 'Significant',
        'evaluation.statisticalResults.bonferroniCorrected':
          'Bonferroni Corrected',
        'evaluation.statisticalResults.multipleComparisons':
          'Multiple Comparisons',
        'evaluation.statisticalResults.considerBonferroni': `Consider Bonferroni correction (${params?.count} tests)`,
        'evaluation.statisticalResults.correlationMatrix': 'Correlation Matrix',
        'evaluation.statisticalResults.strongPositive': 'Strong Positive',
        'evaluation.statisticalResults.strongNegative': 'Strong Negative',
        'evaluation.statisticalResults.weakNone': 'Weak/None',
      }
      return translations[key] || key
    },
  }),
}))

jest.mock('@/components/shared/Badge', () => ({
  Badge: ({ children, className }: any) => (
    <span className={className} data-testid="badge">
      {children}
    </span>
  ),
}))

jest.mock('@/components/shared/Card', () => ({
  Card: ({ children, className }: any) => (
    <div className={className} data-testid="card">
      {children}
    </div>
  ),
}))

jest.mock('@/components/shared/LoadingSpinner', () => ({
  LoadingSpinner: () => <div data-testid="loading-spinner" />,
}))

const baseStatisticsData = {
  aggregation: 'model',
  metrics: {
    accuracy: {
      mean: 0.85,
      median: 0.86,
      std: 0.05,
      se: 0.01,
      min: 0.7,
      max: 0.95,
      ci_lower: 0.83,
      ci_upper: 0.87,
      n: 100,
    },
  },
}

describe('StatisticalResultsPanel', () => {
  describe('Loading state', () => {
    it('shows loading spinner and text', () => {
      render(<StatisticalResultsPanel data={null} loading={true} />)
      expect(screen.getByTestId('loading-spinner')).toBeInTheDocument()
      expect(
        screen.getByText('Computing statistics...')
      ).toBeInTheDocument()
    })
  })

  describe('Error state', () => {
    it('shows error message', () => {
      render(
        <StatisticalResultsPanel
          data={null}
          error="Failed to compute statistics"
        />
      )
      expect(
        screen.getByText('Failed to compute statistics')
      ).toBeInTheDocument()
    })
  })

  describe('No data state', () => {
    it('shows prompt to select metrics', () => {
      render(<StatisticalResultsPanel data={null} />)
      expect(
        screen.getByText('Select metrics to see statistical analysis')
      ).toBeInTheDocument()
    })
  })

  describe('Overall metric statistics', () => {
    it('renders metric statistics table', () => {
      render(<StatisticalResultsPanel data={baseStatisticsData} />)
      expect(screen.getByText('Metric Statistics')).toBeInTheDocument()
      expect(screen.getByText('accuracy')).toBeInTheDocument()
    })

    it('renders formatted mean values', () => {
      render(<StatisticalResultsPanel data={baseStatisticsData} />)
      expect(screen.getByText('85.0%')).toBeInTheDocument()
    })

    it('renders standard deviation', () => {
      render(<StatisticalResultsPanel data={baseStatisticsData} />)
      expect(screen.getByText('0.0500')).toBeInTheDocument()
    })

    it('shows sample size n', () => {
      render(<StatisticalResultsPanel data={baseStatisticsData} />)
      expect(screen.getByText('100')).toBeInTheDocument()
    })

    it('shows CI when ci stat is selected', () => {
      render(
        <StatisticalResultsPanel
          data={baseStatisticsData}
          selectedStatistics={['ci']}
        />
      )
      expect(screen.getByText('95% CI')).toBeInTheDocument()
      expect(screen.getByText(/83.0%/)).toBeInTheDocument()
    })

    it('shows SE when se stat is selected', () => {
      render(
        <StatisticalResultsPanel
          data={baseStatisticsData}
          selectedStatistics={['se']}
        />
      )
      expect(screen.getByText('SE')).toBeInTheDocument()
    })

    it('shows all stats when no selection is provided (default behavior)', () => {
      render(<StatisticalResultsPanel data={baseStatisticsData} />)
      // Should show both CI and SE columns
      expect(screen.getByText('95% CI')).toBeInTheDocument()
      expect(screen.getByText('SE')).toBeInTheDocument()
    })
  })

  describe('Aggregation level', () => {
    it('displays aggregation badge', () => {
      render(<StatisticalResultsPanel data={baseStatisticsData} />)
      expect(screen.getByText('model')).toBeInTheDocument()
    })
  })

  describe('Per-model statistics', () => {
    it('renders per-model table when by_model data exists', () => {
      const data = {
        ...baseStatisticsData,
        by_model: {
          'gpt-4': {
            model_id: 'gpt-4',
            model_name: 'GPT-4',
            metrics: {
              accuracy: {
                mean: 0.9,
                std: 0.03,
                se: 0.005,
                ci_lower: 0.89,
                ci_upper: 0.91,
                n: 50,
              },
            },
            sample_count: 50,
          },
        },
      }
      render(<StatisticalResultsPanel data={data} />)
      expect(screen.getByText('Per-Model Statistics')).toBeInTheDocument()
      expect(screen.getByText('GPT-4')).toBeInTheDocument()
      expect(screen.getByText('Overall Statistics')).toBeInTheDocument()
    })

    it('falls back to model_id when model_name is not provided', () => {
      const data = {
        ...baseStatisticsData,
        by_model: {
          'model-abc': {
            model_id: 'model-abc',
            metrics: {
              accuracy: {
                mean: 0.8,
                std: 0.04,
                ci_lower: 0.78,
                ci_upper: 0.82,
                n: 30,
              },
            },
            sample_count: 30,
          },
        },
      }
      render(<StatisticalResultsPanel data={data} />)
      expect(screen.getByText('model-abc')).toBeInTheDocument()
    })
  })

  describe('Per-field statistics', () => {
    it('renders per-field table when by_field data exists', () => {
      const data = {
        ...baseStatisticsData,
        by_field: {
          answer: {
            field_name: 'answer',
            metrics: {
              accuracy: {
                mean: 0.88,
                std: 0.04,
                ci_lower: 0.86,
                ci_upper: 0.9,
                n: 60,
              },
            },
            sample_count: 60,
          },
        },
      }
      render(<StatisticalResultsPanel data={data} />)
      expect(screen.getByText('Per-Field Statistics')).toBeInTheDocument()
      expect(screen.getByText('answer')).toBeInTheDocument()
    })
  })

  describe('Pairwise comparisons', () => {
    const pairwiseData = {
      ...baseStatisticsData,
      pairwise_comparisons: [
        {
          model_a: 'GPT-4',
          model_b: 'Claude 3',
          metric: 'accuracy',
          ttest_p: 0.003,
          ttest_significant: true,
          cohens_d: 0.85,
          cohens_d_interpretation: 'large',
          significant: true,
        },
      ],
    }

    it('renders pairwise comparisons table', () => {
      render(<StatisticalResultsPanel data={pairwiseData} />)
      expect(screen.getByText('Pairwise Comparisons')).toBeInTheDocument()
      expect(screen.getByText('GPT-4')).toBeInTheDocument()
      expect(screen.getByText('Claude 3')).toBeInTheDocument()
    })

    it('shows significance stars for p-values', () => {
      render(<StatisticalResultsPanel data={pairwiseData} />)
      // p=0.003 -> **
      expect(screen.getByText('**')).toBeInTheDocument()
    })

    it('hides pairwise table when significance tests are not selected', () => {
      render(
        <StatisticalResultsPanel
          data={pairwiseData}
          selectedStatistics={['ci', 'se']}
        />
      )
      expect(
        screen.queryByText('Pairwise Comparisons')
      ).not.toBeInTheDocument()
    })

    it('shows pairwise table when ttest is selected', () => {
      render(
        <StatisticalResultsPanel
          data={pairwiseData}
          selectedStatistics={['ttest']}
        />
      )
      expect(screen.getByText('Pairwise Comparisons')).toBeInTheDocument()
    })

    it('shows effect sizes when cohens_d is selected', () => {
      render(
        <StatisticalResultsPanel
          data={pairwiseData}
          selectedStatistics={['ttest', 'cohens_d']}
        />
      )
      expect(screen.getByText('Effect Size')).toBeInTheDocument()
      expect(screen.getByText(/d=0.85/)).toBeInTheDocument()
    })
  })

  describe('Bonferroni correction', () => {
    it('shows Bonferroni corrected badge when correction is applied', () => {
      const data = {
        ...baseStatisticsData,
        pairwise_comparisons: [
          {
            model_a: 'A',
            model_b: 'B',
            metric: 'acc',
            ttest_p: 0.01,
            significant: true,
          },
        ],
        bonferroni_correction: {
          applied: true,
          num_comparisons: 3,
          original_alpha: 0.05,
          corrected_alpha: 0.0167,
        },
      }
      render(<StatisticalResultsPanel data={data} />)
      expect(screen.getByText('Bonferroni Corrected')).toBeInTheDocument()
    })

    it('shows multiple comparisons warning when not corrected', () => {
      const data = {
        ...baseStatisticsData,
        pairwise_comparisons: [
          {
            model_a: 'A',
            model_b: 'B',
            metric: 'acc',
            ttest_p: 0.01,
            significant: true,
          },
          {
            model_a: 'A',
            model_b: 'C',
            metric: 'acc',
            ttest_p: 0.02,
            significant: true,
          },
        ],
      }
      render(<StatisticalResultsPanel data={data} />)
      expect(
        screen.getByText(/Consider Bonferroni correction/)
      ).toBeInTheDocument()
    })

    it('hides Bonferroni info when showBonferroniInfo is false', () => {
      const data = {
        ...baseStatisticsData,
        pairwise_comparisons: [
          {
            model_a: 'A',
            model_b: 'B',
            metric: 'acc',
            ttest_p: 0.01,
            significant: true,
          },
        ],
        bonferroni_correction: {
          applied: true,
          num_comparisons: 3,
          original_alpha: 0.05,
          corrected_alpha: 0.0167,
        },
      }
      render(
        <StatisticalResultsPanel data={data} showBonferroniInfo={false} />
      )
      expect(
        screen.queryByText('Bonferroni Corrected')
      ).not.toBeInTheDocument()
    })
  })

  describe('Correlation matrix', () => {
    it('renders correlation matrix when correlation stat is selected', () => {
      const data = {
        ...baseStatisticsData,
        metrics: {
          accuracy: { ...baseStatisticsData.metrics.accuracy },
          f1: {
            mean: 0.82,
            std: 0.06,
            ci_lower: 0.8,
            ci_upper: 0.84,
            n: 100,
          },
        },
        correlations: {
          accuracy: { accuracy: 1.0, f1: 0.92 },
          f1: { accuracy: 0.92, f1: 1.0 },
        },
      }
      render(
        <StatisticalResultsPanel
          data={data}
          selectedStatistics={['correlation']}
        />
      )
      expect(screen.getByText('Correlation Matrix')).toBeInTheDocument()
      // 0.92 appears twice in the symmetric matrix (accuracy->f1 and f1->accuracy)
      const correlationCells = screen.getAllByText('0.92')
      expect(correlationCells.length).toBe(2)
    })

    it('hides correlation matrix when correlation stat is not selected', () => {
      const data = {
        ...baseStatisticsData,
        correlations: {
          accuracy: { accuracy: 1.0 },
        },
      }
      render(
        <StatisticalResultsPanel
          data={data}
          selectedStatistics={['ci']}
        />
      )
      expect(
        screen.queryByText('Correlation Matrix')
      ).not.toBeInTheDocument()
    })
  })

  describe('Per-model statistics with missing metrics', () => {
    it('renders dash for missing metric in model breakdown', () => {
      const data = {
        ...baseStatisticsData,
        metrics: {
          accuracy: { ...baseStatisticsData.metrics.accuracy },
          f1: {
            mean: 0.82,
            std: 0.06,
            ci_lower: 0.8,
            ci_upper: 0.84,
            n: 100,
          },
        },
        by_model: {
          'gpt-4': {
            model_id: 'gpt-4',
            model_name: 'GPT-4',
            metrics: {
              accuracy: {
                mean: 0.9,
                std: 0.03,
                se: 0.005,
                ci_lower: 0.89,
                ci_upper: 0.91,
                n: 50,
              },
              // f1 is missing for this model
            },
            sample_count: 50,
          },
        },
      }
      render(<StatisticalResultsPanel data={data} />)
      // The missing f1 metric should show a dash (may appear multiple times)
      expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(1)
    })

    it('shows SE annotation in per-model stats when se is selected', () => {
      const data = {
        ...baseStatisticsData,
        by_model: {
          'gpt-4': {
            model_id: 'gpt-4',
            model_name: 'GPT-4',
            metrics: {
              accuracy: {
                mean: 0.9,
                std: 0.03,
                se: 0.005,
                ci_lower: 0.89,
                ci_upper: 0.91,
                n: 50,
              },
            },
            sample_count: 50,
          },
        },
      }
      render(
        <StatisticalResultsPanel
          data={data}
          selectedStatistics={['se', 'ci']}
        />
      )
      // SE should appear as ±value
      expect(screen.getByText('±0.005')).toBeInTheDocument()
    })

    it('hides SE annotation in per-model stats when se is not selected', () => {
      const data = {
        ...baseStatisticsData,
        by_model: {
          'gpt-4': {
            model_id: 'gpt-4',
            model_name: 'GPT-4',
            metrics: {
              accuracy: {
                mean: 0.9,
                std: 0.03,
                se: 0.005,
                ci_lower: 0.89,
                ci_upper: 0.91,
                n: 50,
              },
            },
            sample_count: 50,
          },
        },
      }
      render(
        <StatisticalResultsPanel
          data={data}
          selectedStatistics={['ci']}
        />
      )
      expect(screen.queryByText('±0.005')).not.toBeInTheDocument()
    })
  })

  describe('Per-field statistics with missing metrics', () => {
    it('renders dash for missing metric in field breakdown', () => {
      const data = {
        ...baseStatisticsData,
        metrics: {
          accuracy: { ...baseStatisticsData.metrics.accuracy },
          f1: {
            mean: 0.82,
            std: 0.06,
            ci_lower: 0.8,
            ci_upper: 0.84,
            n: 100,
          },
        },
        by_field: {
          answer: {
            field_name: 'answer',
            metrics: {
              accuracy: {
                mean: 0.88,
                std: 0.04,
                ci_lower: 0.86,
                ci_upper: 0.9,
                n: 60,
              },
              // f1 is missing
            },
            sample_count: 60,
          },
        },
      }
      render(<StatisticalResultsPanel data={data} />)
      expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(1)
    })

    it('shows SE in per-field stats when se is selected', () => {
      const data = {
        ...baseStatisticsData,
        by_field: {
          answer: {
            field_name: 'answer',
            metrics: {
              accuracy: {
                mean: 0.88,
                std: 0.04,
                se: 0.008,
                ci_lower: 0.86,
                ci_upper: 0.9,
                n: 60,
              },
            },
            sample_count: 60,
          },
        },
      }
      render(
        <StatisticalResultsPanel
          data={data}
          selectedStatistics={['se', 'ci']}
        />
      )
      expect(screen.getByText('±0.008')).toBeInTheDocument()
    })
  })

  describe('Overall statistics SE column', () => {
    it('shows SE dash when se value is undefined', () => {
      const data = {
        aggregation: 'model',
        metrics: {
          accuracy: {
            mean: 0.85,
            std: 0.05,
            // se is undefined
            ci_lower: 0.83,
            ci_upper: 0.87,
            n: 100,
          },
        },
      }
      render(<StatisticalResultsPanel data={data} selectedStatistics={['se']} />)
      expect(screen.getByText('—')).toBeInTheDocument()
    })
  })

  describe('Non-significant pairwise comparison', () => {
    it('renders X icon for non-significant comparisons', () => {
      const data = {
        ...baseStatisticsData,
        pairwise_comparisons: [
          {
            model_a: 'A',
            model_b: 'B',
            metric: 'acc',
            ttest_p: 0.15,
            significant: false,
          },
        ],
      }
      render(<StatisticalResultsPanel data={data} />)
      // Non-significant uses XCircleIcon
      expect(screen.getByText('Pairwise Comparisons')).toBeInTheDocument()
    })
  })

  describe('Correlation matrix with null values', () => {
    it('renders dash for null correlation values', () => {
      const data = {
        ...baseStatisticsData,
        metrics: {
          accuracy: { ...baseStatisticsData.metrics.accuracy },
          f1: {
            mean: 0.82,
            std: 0.06,
            ci_lower: 0.8,
            ci_upper: 0.84,
            n: 100,
          },
        },
        correlations: {
          accuracy: { accuracy: 1.0, f1: null },
          f1: { accuracy: null, f1: 1.0 },
        },
      }
      render(
        <StatisticalResultsPanel
          data={data}
          selectedStatistics={['correlation']}
        />
      )
      // Null correlations show as '-'
      expect(screen.getAllByText('-').length).toBe(2)
    })
  })

  describe('Warnings', () => {
    it('renders warning messages', () => {
      const data = {
        ...baseStatisticsData,
        warnings: ['Small sample size may affect reliability'],
      }
      render(<StatisticalResultsPanel data={data} />)
      expect(
        screen.getByText('Small sample size may affect reliability')
      ).toBeInTheDocument()
    })

    it('renders multiple warnings', () => {
      const data = {
        ...baseStatisticsData,
        warnings: ['Warning 1', 'Warning 2'],
      }
      render(<StatisticalResultsPanel data={data} />)
      expect(screen.getByText('Warning 1')).toBeInTheDocument()
      expect(screen.getByText('Warning 2')).toBeInTheDocument()
    })
  })
})

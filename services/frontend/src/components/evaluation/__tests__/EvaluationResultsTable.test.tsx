/**
 * @jest-environment jsdom
 */
import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { EvaluationResultsTable } from '../EvaluationResultsTable'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, params?: Record<string, any>) => {
      const translations: Record<string, string> = {
        'evaluation.resultsTable.noResults': 'No results available',
        'evaluation.resultsTable.rank': 'Rank',
        'evaluation.resultsTable.model': 'Model',
        'evaluation.resultsTable.scoreHigh': 'High (>70%)',
        'evaluation.resultsTable.scoreMedium': 'Medium (50-70%)',
        'evaluation.resultsTable.scoreLow': 'Low (<50%)',
        'evaluation.resultsTable.baseline': 'Baseline',
        'evaluation.resultsTable.significanceLegend':
          '* p<0.05, ** p<0.01, *** p<0.001',
        'evaluation.resultsTable.baselineNote': `Compared against ${params?.model}`,
      }
      return translations[key] || key
    },
  }),
}))

describe('EvaluationResultsTable', () => {
  const defaultProps = {
    results: [
      {
        modelId: 'gpt-4',
        modelName: 'GPT-4',
        metrics: { accuracy: 0.85, f1: 0.82 },
        rank: 1,
      },
      {
        modelId: 'claude-3',
        modelName: 'Claude 3',
        metrics: { accuracy: 0.78, f1: 0.75 },
        rank: 2,
      },
    ],
  }

  describe('Empty state', () => {
    it('renders no results message when results array is empty', () => {
      render(<EvaluationResultsTable results={[]} />)
      expect(screen.getByText('No results available')).toBeInTheDocument()
    })
  })

  describe('Table rendering', () => {
    it('renders model names in the table', () => {
      render(<EvaluationResultsTable {...defaultProps} />)
      expect(screen.getByText('GPT-4')).toBeInTheDocument()
      expect(screen.getByText('Claude 3')).toBeInTheDocument()
    })

    it('renders metric column headers', () => {
      render(<EvaluationResultsTable {...defaultProps} />)
      expect(screen.getByText('accuracy')).toBeInTheDocument()
      expect(screen.getByText('f1')).toBeInTheDocument()
    })

    it('renders rank badges', () => {
      render(<EvaluationResultsTable {...defaultProps} />)
      expect(screen.getByText('#1')).toBeInTheDocument()
      expect(screen.getByText('#2')).toBeInTheDocument()
    })

    it('renders dash for undefined rank', () => {
      const results = [
        { modelId: 'test', metrics: { accuracy: 0.5 } },
      ]
      render(<EvaluationResultsTable results={results} />)
      expect(screen.getByText('-')).toBeInTheDocument()
    })

    it('renders formatted metric values as percentages for 0-1 range', () => {
      render(<EvaluationResultsTable {...defaultProps} />)
      expect(screen.getByText('85.0%')).toBeInTheDocument()
      expect(screen.getByText('82.0%')).toBeInTheDocument()
      expect(screen.getByText('78.0%')).toBeInTheDocument()
      expect(screen.getByText('75.0%')).toBeInTheDocument()
    })

    it('falls back to modelId when modelName is not provided', () => {
      const results = [
        { modelId: 'test-model-id', metrics: { accuracy: 0.5 } },
      ]
      render(<EvaluationResultsTable results={results} />)
      expect(screen.getByText('test-model-id')).toBeInTheDocument()
    })
  })

  describe('Score color coding', () => {
    it('applies green class for high scores (>=0.7)', () => {
      const results = [
        { modelId: 'high', metrics: { score: 0.85 } },
      ]
      render(<EvaluationResultsTable results={results} />)
      const scoreEl = screen.getByText('85.0%')
      expect(scoreEl).toHaveClass('bg-green-100')
    })

    it('applies yellow class for medium scores (0.5-0.7)', () => {
      const results = [
        { modelId: 'medium', metrics: { score: 0.6 } },
      ]
      render(<EvaluationResultsTable results={results} />)
      const scoreEl = screen.getByText('60.0%')
      expect(scoreEl).toHaveClass('bg-yellow-100')
    })

    it('applies red class for low scores (<0.5)', () => {
      const results = [
        { modelId: 'low', metrics: { score: 0.3 } },
      ]
      render(<EvaluationResultsTable results={results} />)
      const scoreEl = screen.getByText('30.0%')
      expect(scoreEl).toHaveClass('bg-red-100')
    })
  })

  describe('MetricValue objects', () => {
    it('renders confidence intervals when provided', () => {
      const results = [
        {
          modelId: 'test',
          metrics: {
            accuracy: {
              value: 0.85,
              confidenceInterval: { lower: 0.8, upper: 0.9 },
            },
          },
        },
      ]
      render(<EvaluationResultsTable results={results} />)
      expect(screen.getByText('85.0%')).toBeInTheDocument()
      expect(screen.getByText(/80.0%/)).toBeInTheDocument()
      expect(screen.getByText(/90.0%/)).toBeInTheDocument()
    })

    it('renders significance indicators (***)', () => {
      const results = [
        {
          modelId: 'test',
          metrics: {
            accuracy: {
              value: 0.85,
              significance: 0.0005,
            },
          },
        },
      ]
      render(<EvaluationResultsTable results={results} />)
      const sup = document.querySelector('sup')
      expect(sup).toBeInTheDocument()
      expect(sup!.textContent).toBe('***')
    })

    it('renders ** for p < 0.01', () => {
      const results = [
        {
          modelId: 'test',
          metrics: {
            accuracy: { value: 0.85, significance: 0.005 },
          },
        },
      ]
      render(<EvaluationResultsTable results={results} />)
      const sup = document.querySelector('sup')
      expect(sup).toBeInTheDocument()
      expect(sup!.textContent).toBe('**')
    })

    it('renders * for p < 0.05', () => {
      const results = [
        {
          modelId: 'test',
          metrics: {
            accuracy: { value: 0.85, significance: 0.03 },
          },
        },
      ]
      render(<EvaluationResultsTable results={results} />)
      const sup = document.querySelector('sup')
      expect(sup).toBeInTheDocument()
      expect(sup!.textContent).toBe('*')
    })

    it('renders dash for missing metrics', () => {
      const results = [
        { modelId: 'a', metrics: { accuracy: 0.9 }, rank: 1 },
        { modelId: 'b', metrics: { f1: 0.8 }, rank: 2 },
      ]
      render(<EvaluationResultsTable results={results} />)
      // Missing metric cells render <span className="text-gray-400">-</span>
      const dashSpans = document.querySelectorAll('span.text-gray-400')
      const metricDashes = Array.from(dashSpans).filter(
        (span) => span.textContent === '-'
      )
      // Two dashes: model "a" missing "f1", model "b" missing "accuracy"
      expect(metricDashes.length).toBe(2)
    })
  })

  describe('Custom metric display names', () => {
    it('uses metricNames map for column headers', () => {
      const metricNames = { accuracy: 'Accuracy Score', f1: 'F1 Measure' }
      render(
        <EvaluationResultsTable {...defaultProps} metricNames={metricNames} />
      )
      expect(screen.getByText('Accuracy Score')).toBeInTheDocument()
      expect(screen.getByText('F1 Measure')).toBeInTheDocument()
    })

    it('uses metricDescriptions as tooltip titles', () => {
      const metricDescriptions = { accuracy: 'Overall accuracy metric' }
      render(
        <EvaluationResultsTable
          {...defaultProps}
          metricDescriptions={metricDescriptions}
        />
      )
      // The th element should have the title
      const th = screen.getByTitle('Overall accuracy metric')
      expect(th).toBeInTheDocument()
    })
  })

  describe('Baseline model', () => {
    it('shows baseline badge for baseline model', () => {
      render(
        <EvaluationResultsTable {...defaultProps} baselineModel="gpt-4" />
      )
      expect(screen.getByText('Baseline')).toBeInTheDocument()
    })

    it('shows significance legend when baseline is set', () => {
      render(
        <EvaluationResultsTable {...defaultProps} baselineModel="gpt-4" />
      )
      expect(
        screen.getByText('* p<0.05, ** p<0.01, *** p<0.001')
      ).toBeInTheDocument()
    })

    it('shows baseline note footer', () => {
      render(
        <EvaluationResultsTable {...defaultProps} baselineModel="gpt-4" />
      )
      expect(screen.getByText('Compared against gpt-4')).toBeInTheDocument()
    })
  })

  describe('Sorting', () => {
    it('sorts by model when clicking model column', async () => {
      const user = userEvent.setup()
      render(<EvaluationResultsTable {...defaultProps} />)

      const modelHeader = screen.getByText('Model')
      await user.click(modelHeader)

      // After clicking: sort should change direction
      const rows = screen.getAllByRole('row')
      // Header row + 2 data rows
      expect(rows).toHaveLength(3)
    })

    it('cycles through sort directions: desc -> asc -> null', async () => {
      const user = userEvent.setup()
      render(<EvaluationResultsTable {...defaultProps} />)

      const accuracyHeader = screen.getByText('accuracy')

      // First click: desc
      await user.click(accuracyHeader)
      // Second click: asc
      await user.click(accuracyHeader)
      // Third click: null (no sort)
      await user.click(accuracyHeader)

      // Table should still render correctly after all clicks
      expect(screen.getByText('GPT-4')).toBeInTheDocument()
      expect(screen.getByText('Claude 3')).toBeInTheDocument()
    })
  })

  describe('Score legend', () => {
    it('shows color legend for high, medium, and low scores', () => {
      render(<EvaluationResultsTable {...defaultProps} />)
      expect(screen.getByText('High (>70%)')).toBeInTheDocument()
      expect(screen.getByText('Medium (50-70%)')).toBeInTheDocument()
      expect(screen.getByText('Low (<50%)')).toBeInTheDocument()
    })
  })

  describe('Higher is better', () => {
    it('inverts color coding when higherIsBetter is false', () => {
      const results = [
        { modelId: 'test', metrics: { error_rate: 0.2 } },
      ]
      render(
        <EvaluationResultsTable
          results={results}
          higherIsBetter={{ error_rate: false }}
        />
      )
      // 0.2 with higherIsBetter=false means score = 1-0.2 = 0.8, which is green
      const scoreEl = screen.getByText('20.0%')
      expect(scoreEl).toHaveClass('bg-green-100')
    })
  })

  describe('Large values', () => {
    it('formats values > 1 with 3 decimal places (not percentage)', () => {
      const results = [
        { modelId: 'test', metrics: { perplexity: 25.678 } },
      ]
      render(<EvaluationResultsTable results={results} />)
      expect(screen.getByText('25.678')).toBeInTheDocument()
    })
  })
})

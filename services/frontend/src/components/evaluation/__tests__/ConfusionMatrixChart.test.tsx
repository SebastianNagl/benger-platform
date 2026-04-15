/**
 * @jest-environment jsdom
 */
import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'
import { ConfusionMatrixChart } from '../ConfusionMatrixChart'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, params?: Record<string, any>) => {
      const translations: Record<string, string> = {
        'evaluation.confusionMatrix.count': 'Count',
        'evaluation.confusionMatrix.titleWithField': `Confusion Matrix: ${params?.field}`,
        'evaluation.confusionMatrix.predictedLabel': 'Predicted Label',
        'evaluation.confusionMatrix.trueLabel': 'True Label',
        'evaluation.confusionMatrix.classificationMetrics':
          'Classification Metrics',
        'evaluation.confusionMatrix.overallAccuracy': 'Overall Accuracy',
        'evaluation.confusionMatrix.precision': 'Precision',
        'evaluation.confusionMatrix.recall': 'Recall',
        'evaluation.confusionMatrix.f1': 'F1',
      }
      return translations[key] || key
    },
  }),
}))

// Mock next/dynamic to render Plot as a simple div
jest.mock('next/dynamic', () => {
  return function dynamic() {
    const MockPlot = ({ data, layout, config }: any) => (
      <div data-testid="plotly-chart" data-layout={JSON.stringify(layout)}>
        Plotly Chart
      </div>
    )
    MockPlot.displayName = 'MockPlot'
    return MockPlot
  }
})

const sampleData = {
  field_name: 'answer_type',
  labels: ['Yes', 'No', 'Maybe'],
  matrix: [
    [45, 5, 2],
    [3, 40, 7],
    [1, 6, 38],
  ],
  accuracy: 0.836,
  precision_per_class: { Yes: 0.918, No: 0.784, Maybe: 0.808 },
  recall_per_class: { Yes: 0.865, No: 0.8, Maybe: 0.844 },
  f1_per_class: { Yes: 0.891, No: 0.792, Maybe: 0.826 },
}

describe('ConfusionMatrixChart', () => {
  describe('Chart rendering', () => {
    it('renders the Plotly chart', () => {
      render(<ConfusionMatrixChart data={sampleData} />)
      expect(screen.getByTestId('plotly-chart')).toBeInTheDocument()
    })

    it('renders with custom title', () => {
      render(
        <ConfusionMatrixChart data={sampleData} title="Custom Title" />
      )
      expect(screen.getByTestId('plotly-chart')).toBeInTheDocument()
    })
  })

  describe('Classification metrics summary', () => {
    it('renders classification metrics section', () => {
      render(<ConfusionMatrixChart data={sampleData} />)
      expect(
        screen.getByText('Classification Metrics')
      ).toBeInTheDocument()
    })

    it('renders overall accuracy', () => {
      render(<ConfusionMatrixChart data={sampleData} />)
      // Text includes trailing colon and space: "Overall Accuracy: "
      expect(screen.getByText(/Overall Accuracy/)).toBeInTheDocument()
      expect(screen.getByText('83.60%')).toBeInTheDocument()
    })

    it('renders per-class metrics for all labels', () => {
      render(<ConfusionMatrixChart data={sampleData} />)
      expect(screen.getByText('Yes')).toBeInTheDocument()
      expect(screen.getByText('No')).toBeInTheDocument()
      expect(screen.getByText('Maybe')).toBeInTheDocument()
    })

    it('renders precision values for each class', () => {
      render(<ConfusionMatrixChart data={sampleData} />)
      // Yes precision: 91.8%
      expect(screen.getByText('91.8%')).toBeInTheDocument()
      // No precision: 78.4%
      expect(screen.getByText('78.4%')).toBeInTheDocument()
    })

    it('renders recall values for each class', () => {
      render(<ConfusionMatrixChart data={sampleData} />)
      // Yes recall: 86.5%
      expect(screen.getByText('86.5%')).toBeInTheDocument()
    })

    it('renders F1 values for each class', () => {
      render(<ConfusionMatrixChart data={sampleData} />)
      // Yes F1: 89.1%
      expect(screen.getByText('89.1%')).toBeInTheDocument()
    })

    it('renders metric labels', () => {
      render(<ConfusionMatrixChart data={sampleData} />)
      // Each class card shows "Precision:", "Recall:", "F1:" (with colon)
      const precisionLabels = screen.getAllByText(/^Precision:$/)
      expect(precisionLabels.length).toBe(3)
      const recallLabels = screen.getAllByText(/^Recall:$/)
      expect(recallLabels.length).toBe(3)
      const f1Labels = screen.getAllByText(/^F1:$/)
      expect(f1Labels.length).toBe(3)
    })
  })

  describe('Edge cases', () => {
    it('handles missing class metrics gracefully (defaults to 0)', () => {
      const data = {
        ...sampleData,
        precision_per_class: {},
        recall_per_class: {},
        f1_per_class: {},
      }
      render(<ConfusionMatrixChart data={data} />)
      // Should render 0.0% for all missing values
      const zeros = screen.getAllByText('0.0%')
      expect(zeros.length).toBeGreaterThanOrEqual(3) // At least 3 classes * some metrics
    })

    it('handles binary classification (2 classes)', () => {
      const binaryData = {
        field_name: 'sentiment',
        labels: ['Positive', 'Negative'],
        matrix: [
          [80, 20],
          [10, 90],
        ],
        accuracy: 0.85,
        precision_per_class: { Positive: 0.889, Negative: 0.818 },
        recall_per_class: { Positive: 0.8, Negative: 0.9 },
        f1_per_class: { Positive: 0.842, Negative: 0.857 },
      }
      render(<ConfusionMatrixChart data={binaryData} />)
      expect(screen.getByText('Positive')).toBeInTheDocument()
      expect(screen.getByText('Negative')).toBeInTheDocument()
      expect(screen.getByText('85.00%')).toBeInTheDocument()
    })
  })
})

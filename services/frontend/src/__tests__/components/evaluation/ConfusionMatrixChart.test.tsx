/**
 * Unit tests for ConfusionMatrixChart component
 */

/**
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'
import { ConfusionMatrixChart } from '../../../components/evaluation/ConfusionMatrixChart'

// Mock dynamic import for react-plotly.js
jest.mock('next/dynamic', () => ({
  __esModule: true,
  default: (func: any) => {
    const Plot = ({ data, layout, config }: any) => (
      <div
        data-testid="plotly-chart"
        data-chart-data={JSON.stringify(data)}
        data-layout={JSON.stringify(layout)}
        data-config={JSON.stringify(config)}
      />
    )
    Plot.displayName = 'Plot'
    return Plot
  },
}))
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, varsOrDefault?: any) => {
      const translations: Record<string, any> = require('../../../locales/en/common.json')
      const parts = key.split('.')
      let value: any = translations
      for (const part of parts) {
        if (value && typeof value === 'object' && part in value) {
          value = value[part]
        } else {
          return key
        }
      }
      if (typeof value !== 'string') return key
      if (varsOrDefault && typeof varsOrDefault === 'object') {
        for (const [k, v] of Object.entries(varsOrDefault)) {
          value = value.replace(new RegExp(`\\{${k}\\}`, 'g'), String(v))
        }
      }
      return value
    },
    locale: 'en',
  }),
}))


describe('ConfusionMatrixChart', () => {
  const mockData = {
    field_name: 'sentiment',
    labels: ['positive', 'negative', 'neutral'],
    matrix: [
      [45, 3, 2],
      [2, 48, 0],
      [1, 2, 47],
    ],
    accuracy: 0.93,
    precision_per_class: {
      positive: 0.9375,
      negative: 0.9057,
      neutral: 0.9592,
    },
    recall_per_class: {
      positive: 0.9,
      negative: 0.96,
      neutral: 0.94,
    },
    f1_per_class: {
      positive: 0.9184,
      negative: 0.932,
      neutral: 0.9495,
    },
  }

  describe('Chart Rendering', () => {
    it('should render plotly chart', () => {
      render(<ConfusionMatrixChart data={mockData} />)

      expect(screen.getByTestId('plotly-chart')).toBeInTheDocument()
    })

    it('should render with default dimensions', () => {
      render(<ConfusionMatrixChart data={mockData} />)

      const chart = screen.getByTestId('plotly-chart')
      const layout = JSON.parse(chart.getAttribute('data-layout') || '{}')

      expect(layout.width).toBe(700)
      expect(layout.height).toBe(700)
    })

    it('should render with custom dimensions', () => {
      render(<ConfusionMatrixChart data={mockData} width={800} height={600} />)

      const chart = screen.getByTestId('plotly-chart')
      const layout = JSON.parse(chart.getAttribute('data-layout') || '{}')

      expect(layout.width).toBe(800)
      expect(layout.height).toBe(600)
    })

    it('should render with default title', () => {
      render(<ConfusionMatrixChart data={mockData} />)

      const chart = screen.getByTestId('plotly-chart')
      const layout = JSON.parse(chart.getAttribute('data-layout') || '{}')

      expect(layout.title.text).toBe('Confusion Matrix - sentiment')
    })

    it('should render with custom title', () => {
      render(
        <ConfusionMatrixChart data={mockData} title="Custom Matrix Title" />
      )

      const chart = screen.getByTestId('plotly-chart')
      const layout = JSON.parse(chart.getAttribute('data-layout') || '{}')

      expect(layout.title.text).toBe('Custom Matrix Title')
    })

    it('should configure chart as heatmap', () => {
      render(<ConfusionMatrixChart data={mockData} />)

      const chart = screen.getByTestId('plotly-chart')
      const chartData = JSON.parse(
        chart.getAttribute('data-chart-data') || '[]'
      )

      expect(chartData[0].type).toBe('heatmap')
    })

    it('should use viridis colorscale', () => {
      render(<ConfusionMatrixChart data={mockData} />)

      const chart = screen.getByTestId('plotly-chart')
      const chartData = JSON.parse(
        chart.getAttribute('data-chart-data') || '[]'
      )

      expect(chartData[0].colorscale).toBe('Viridis')
    })

    it('should show colorbar with title', () => {
      render(<ConfusionMatrixChart data={mockData} />)

      const chart = screen.getByTestId('plotly-chart')
      const chartData = JSON.parse(
        chart.getAttribute('data-chart-data') || '[]'
      )

      expect(chartData[0].colorbar.title.text).toBe('Count')
    })

    it('should configure axes labels', () => {
      render(<ConfusionMatrixChart data={mockData} />)

      const chart = screen.getByTestId('plotly-chart')
      const layout = JSON.parse(chart.getAttribute('data-layout') || '{}')

      expect(layout.xaxis.title.text).toBe('Predicted Label')
      expect(layout.yaxis.title.text).toBe('True Label')
    })

    it('should reverse y-axis', () => {
      render(<ConfusionMatrixChart data={mockData} />)

      const chart = screen.getByTestId('plotly-chart')
      const layout = JSON.parse(chart.getAttribute('data-layout') || '{}')

      expect(layout.yaxis.autorange).toBe('reversed')
    })

    it('should set proper margins', () => {
      render(<ConfusionMatrixChart data={mockData} />)

      const chart = screen.getByTestId('plotly-chart')
      const layout = JSON.parse(chart.getAttribute('data-layout') || '{}')

      expect(layout.margin).toEqual({ l: 120, r: 80, t: 120, b: 100 })
    })
  })

  describe('Matrix Data', () => {
    it('should pass matrix data correctly', () => {
      render(<ConfusionMatrixChart data={mockData} />)

      const chart = screen.getByTestId('plotly-chart')
      const chartData = JSON.parse(
        chart.getAttribute('data-chart-data') || '[]'
      )

      expect(chartData[0].z).toEqual(mockData.matrix)
    })

    it('should pass labels for x and y axes', () => {
      render(<ConfusionMatrixChart data={mockData} />)

      const chart = screen.getByTestId('plotly-chart')
      const chartData = JSON.parse(
        chart.getAttribute('data-chart-data') || '[]'
      )

      expect(chartData[0].x).toEqual(mockData.labels)
      expect(chartData[0].y).toEqual(mockData.labels)
    })

    it('should generate annotations for each cell', () => {
      render(<ConfusionMatrixChart data={mockData} />)

      const chart = screen.getByTestId('plotly-chart')
      const chartData = JSON.parse(
        chart.getAttribute('data-chart-data') || '[]'
      )

      expect(chartData[0].annotations).toHaveLength(9)
    })

    it('should create annotations with correct values', () => {
      render(<ConfusionMatrixChart data={mockData} />)

      const chart = screen.getByTestId('plotly-chart')
      const chartData = JSON.parse(
        chart.getAttribute('data-chart-data') || '[]'
      )
      const firstAnnotation = chartData[0].annotations[0]

      expect(firstAnnotation.text).toBe('45')
      expect(firstAnnotation.x).toBe('positive')
      expect(firstAnnotation.y).toBe('positive')
    })

    it('should set white text for high values', () => {
      render(<ConfusionMatrixChart data={mockData} />)

      const chart = screen.getByTestId('plotly-chart')
      const chartData = JSON.parse(
        chart.getAttribute('data-chart-data') || '[]'
      )
      const highValueAnnotation = chartData[0].annotations[0]

      expect(highValueAnnotation.font.color).toBe('white')
    })

    it('should set black text for low values', () => {
      render(<ConfusionMatrixChart data={mockData} />)

      const chart = screen.getByTestId('plotly-chart')
      const chartData = JSON.parse(
        chart.getAttribute('data-chart-data') || '[]'
      )
      const lowValueAnnotation = chartData[0].annotations[1]

      expect(lowValueAnnotation.font.color).toBe('black')
    })

    it('should calculate max value correctly', () => {
      render(<ConfusionMatrixChart data={mockData} />)

      const chart = screen.getByTestId('plotly-chart')
      const chartData = JSON.parse(
        chart.getAttribute('data-chart-data') || '[]'
      )
      const annotations = chartData[0].annotations

      const values = mockData.matrix.flat()
      const maxValue = Math.max(...values)
      expect(maxValue).toBe(48)

      const annotation48 = annotations.find((a: any) => a.text === '48')
      expect(annotation48.font.color).toBe('white')
    })
  })

  describe('Metrics Summary', () => {
    it('should render metrics summary section', () => {
      render(<ConfusionMatrixChart data={mockData} />)

      expect(screen.getByText('Classification Metrics')).toBeInTheDocument()
    })

    it('should display overall accuracy', () => {
      render(<ConfusionMatrixChart data={mockData} />)

      expect(screen.getByText('Overall Accuracy:')).toBeInTheDocument()
      expect(screen.getByText('93.00%')).toBeInTheDocument()
    })

    it('should render metric cards for each label', () => {
      render(<ConfusionMatrixChart data={mockData} />)

      expect(screen.getByText('positive')).toBeInTheDocument()
      expect(screen.getByText('negative')).toBeInTheDocument()
      expect(screen.getByText('neutral')).toBeInTheDocument()
    })

    it('should display precision for each class', () => {
      render(<ConfusionMatrixChart data={mockData} />)

      expect(screen.getByText('93.8%')).toBeInTheDocument()
      expect(screen.getByText('90.6%')).toBeInTheDocument()
      expect(screen.getByText('95.9%')).toBeInTheDocument()
    })

    it('should display recall for each class', () => {
      render(<ConfusionMatrixChart data={mockData} />)

      expect(screen.getByText('90.0%')).toBeInTheDocument()
      expect(screen.getByText('96.0%')).toBeInTheDocument()
      expect(screen.getByText('94.0%')).toBeInTheDocument()
    })

    it('should display f1 score for each class', () => {
      render(<ConfusionMatrixChart data={mockData} />)

      expect(screen.getByText('91.8%')).toBeInTheDocument()
      expect(screen.getByText('93.2%')).toBeInTheDocument()
      expect(screen.getByText('95.0%')).toBeInTheDocument()
    })

    it('should render precision label', () => {
      render(<ConfusionMatrixChart data={mockData} />)

      const precisionLabels = screen.getAllByText('Precision:')
      expect(precisionLabels).toHaveLength(3)
    })

    it('should render recall label', () => {
      render(<ConfusionMatrixChart data={mockData} />)

      const recallLabels = screen.getAllByText('Recall:')
      expect(recallLabels).toHaveLength(3)
    })

    it('should render f1 label', () => {
      render(<ConfusionMatrixChart data={mockData} />)

      const f1Labels = screen.getAllByText('F1:')
      expect(f1Labels).toHaveLength(3)
    })

    it('should handle missing precision values', () => {
      const dataWithMissing = {
        ...mockData,
        precision_per_class: {},
      }

      render(<ConfusionMatrixChart data={dataWithMissing} />)

      expect(screen.getAllByText('0.0%').length).toBeGreaterThan(0)
    })

    it('should handle missing recall values', () => {
      const dataWithMissing = {
        ...mockData,
        recall_per_class: {},
      }

      render(<ConfusionMatrixChart data={dataWithMissing} />)

      expect(screen.getAllByText('0.0%').length).toBeGreaterThan(0)
    })

    it('should handle missing f1 values', () => {
      const dataWithMissing = {
        ...mockData,
        f1_per_class: {},
      }

      render(<ConfusionMatrixChart data={dataWithMissing} />)

      expect(screen.getAllByText('0.0%').length).toBeGreaterThan(0)
    })
  })

  describe('Configuration', () => {
    it('should enable responsive mode', () => {
      render(<ConfusionMatrixChart data={mockData} />)

      const chart = screen.getByTestId('plotly-chart')
      const config = JSON.parse(chart.getAttribute('data-config') || '{}')

      expect(config.responsive).toBe(true)
    })

    it('should display mode bar', () => {
      render(<ConfusionMatrixChart data={mockData} />)

      const chart = screen.getByTestId('plotly-chart')
      const config = JSON.parse(chart.getAttribute('data-config') || '{}')

      expect(config.displayModeBar).toBe(true)
    })

    it('should hide plotly logo', () => {
      render(<ConfusionMatrixChart data={mockData} />)

      const chart = screen.getByTestId('plotly-chart')
      const config = JSON.parse(chart.getAttribute('data-config') || '{}')

      expect(config.displaylogo).toBe(false)
    })

    it('should remove specific mode bar buttons', () => {
      render(<ConfusionMatrixChart data={mockData} />)

      const chart = screen.getByTestId('plotly-chart')
      const config = JSON.parse(chart.getAttribute('data-config') || '{}')

      expect(config.modeBarButtonsToRemove).toContain('lasso2d')
      expect(config.modeBarButtonsToRemove).toContain('select2d')
    })
  })

  describe('Edge Cases', () => {
    it('should handle 2x2 matrix', () => {
      const binaryData = {
        field_name: 'binary',
        labels: ['yes', 'no'],
        matrix: [
          [30, 5],
          [3, 32],
        ],
        accuracy: 0.886,
        precision_per_class: { yes: 0.909, no: 0.865 },
        recall_per_class: { yes: 0.857, no: 0.914 },
        f1_per_class: { yes: 0.882, no: 0.889 },
      }

      render(<ConfusionMatrixChart data={binaryData} />)

      const chart = screen.getByTestId('plotly-chart')
      const chartData = JSON.parse(
        chart.getAttribute('data-chart-data') || '[]'
      )

      expect(chartData[0].z).toHaveLength(2)
      expect(chartData[0].annotations).toHaveLength(4)
    })

    it('should handle 4x4 matrix', () => {
      const multiData = {
        field_name: 'multi',
        labels: ['a', 'b', 'c', 'd'],
        matrix: [
          [20, 2, 1, 0],
          [1, 21, 0, 1],
          [0, 1, 22, 0],
          [1, 0, 1, 21],
        ],
        accuracy: 0.92,
        precision_per_class: { a: 0.91, b: 0.88, c: 0.92, d: 0.95 },
        recall_per_class: { a: 0.87, b: 0.91, c: 0.96, d: 0.91 },
        f1_per_class: { a: 0.89, b: 0.895, c: 0.94, d: 0.93 },
      }

      render(<ConfusionMatrixChart data={multiData} />)

      const chart = screen.getByTestId('plotly-chart')
      const chartData = JSON.parse(
        chart.getAttribute('data-chart-data') || '[]'
      )

      expect(chartData[0].z).toHaveLength(4)
      expect(chartData[0].annotations).toHaveLength(16)
    })

    it('should handle zero values in matrix', () => {
      const dataWithZeros = {
        ...mockData,
        matrix: [
          [0, 0, 0],
          [0, 0, 0],
          [0, 0, 0],
        ],
      }

      render(<ConfusionMatrixChart data={dataWithZeros} />)

      const chart = screen.getByTestId('plotly-chart')
      const chartData = JSON.parse(
        chart.getAttribute('data-chart-data') || '[]'
      )

      expect(chartData[0].annotations[0].text).toBe('0')
    })

    it('should handle large values in matrix', () => {
      const dataWithLarge = {
        ...mockData,
        matrix: [
          [1000, 50, 30],
          [40, 1200, 60],
          [20, 70, 1100],
        ],
      }

      render(<ConfusionMatrixChart data={dataWithLarge} />)

      const chart = screen.getByTestId('plotly-chart')
      const chartData = JSON.parse(
        chart.getAttribute('data-chart-data') || '[]'
      )

      expect(chartData[0].annotations[0].text).toBe('1000')
    })

    it('should handle long label names', () => {
      const dataWithLongLabels = {
        ...mockData,
        labels: [
          'very_long_positive_label',
          'extremely_long_negative_label',
          'incredibly_long_neutral_label',
        ],
      }

      render(<ConfusionMatrixChart data={dataWithLongLabels} />)

      expect(screen.getByText('very_long_positive_label')).toBeInTheDocument()
    })

    it('should handle perfect accuracy', () => {
      const perfectData = {
        ...mockData,
        accuracy: 1.0,
      }

      render(<ConfusionMatrixChart data={perfectData} />)

      expect(screen.getByText('100.00%')).toBeInTheDocument()
    })

    it('should handle zero accuracy', () => {
      const zeroData = {
        ...mockData,
        accuracy: 0.0,
      }

      render(<ConfusionMatrixChart data={zeroData} />)

      expect(screen.getByText('0.00%')).toBeInTheDocument()
    })

    it('should handle single label', () => {
      const singleLabelData = {
        field_name: 'single',
        labels: ['only_one'],
        matrix: [[50]],
        accuracy: 1.0,
        precision_per_class: { only_one: 1.0 },
        recall_per_class: { only_one: 1.0 },
        f1_per_class: { only_one: 1.0 },
      }

      render(<ConfusionMatrixChart data={singleLabelData} />)

      const chart = screen.getByTestId('plotly-chart')
      const chartData = JSON.parse(
        chart.getAttribute('data-chart-data') || '[]'
      )

      expect(chartData[0].z).toHaveLength(1)
      expect(chartData[0].annotations).toHaveLength(1)
    })
  })

  describe('Styling', () => {
    it('should apply wrapper styling', () => {
      const { container } = render(<ConfusionMatrixChart data={mockData} />)

      const wrapper = container.querySelector('.space-y-4')
      expect(wrapper).toBeInTheDocument()
    })

    it('should apply metrics summary styling', () => {
      const { container } = render(<ConfusionMatrixChart data={mockData} />)

      const summary = container.querySelector(
        '.rounded-lg.border.bg-gray-50.p-4'
      )
      expect(summary).toBeInTheDocument()
    })

    it('should apply grid styling to metric cards', () => {
      const { container } = render(<ConfusionMatrixChart data={mockData} />)

      const grid = container.querySelector('.grid')
      expect(grid).toHaveClass(
        'grid-cols-1',
        'gap-3',
        'md:grid-cols-2',
        'lg:grid-cols-3'
      )
    })

    it('should apply card styling to each metric card', () => {
      const { container } = render(<ConfusionMatrixChart data={mockData} />)

      const cards = container.querySelectorAll(
        '.rounded.border.bg-white.p-3.shadow-sm'
      )
      expect(cards).toHaveLength(3)
    })

    it('should apply centered styling to chart container', () => {
      const { container } = render(<ConfusionMatrixChart data={mockData} />)

      const chartContainer = container.querySelector(
        '.flex.flex-col.items-center'
      )
      expect(chartContainer).toBeInTheDocument()
    })

    it('should apply blue color to accuracy value', () => {
      const { container } = render(<ConfusionMatrixChart data={mockData} />)

      const accuracy = container.querySelector('.text-blue-600')
      expect(accuracy).toHaveTextContent('93.00%')
    })

    it('should apply correct text sizes', () => {
      const { container } = render(<ConfusionMatrixChart data={mockData} />)

      const smallTexts = container.querySelectorAll('.text-sm')
      expect(smallTexts.length).toBeGreaterThan(0)
    })
  })

  describe('Accessibility', () => {
    it('should have proper heading structure', () => {
      const { container } = render(<ConfusionMatrixChart data={mockData} />)

      const heading = container.querySelector('h4')
      expect(heading).toHaveTextContent('Classification Metrics')
    })

    it('should have semantic metric card structure', () => {
      const { container } = render(<ConfusionMatrixChart data={mockData} />)

      const cards = container.querySelectorAll('.rounded.border.bg-white')
      expect(cards.length).toBe(3)

      cards.forEach((card) => {
        const labelName = card.querySelector('.font-medium.text-gray-700')
        const metrics = card.querySelectorAll('.flex.justify-between')

        expect(labelName).toBeInTheDocument()
        expect(metrics.length).toBe(3)
      })
    })

    it('should have clear metric labels', () => {
      render(<ConfusionMatrixChart data={mockData} />)

      expect(screen.getAllByText('Precision:')).toHaveLength(3)
      expect(screen.getAllByText('Recall:')).toHaveLength(3)
      expect(screen.getAllByText('F1:')).toHaveLength(3)
    })
  })

  describe('useMemo Optimization', () => {
    it('should memoize plot data', () => {
      const { rerender } = render(<ConfusionMatrixChart data={mockData} />)

      const chart1 = screen.getByTestId('plotly-chart')
      const data1 = chart1.getAttribute('data-chart-data')

      rerender(<ConfusionMatrixChart data={mockData} />)

      const chart2 = screen.getByTestId('plotly-chart')
      const data2 = chart2.getAttribute('data-chart-data')

      expect(data1).toBe(data2)
    })

    it('should update plot data when matrix changes', () => {
      const { rerender } = render(<ConfusionMatrixChart data={mockData} />)

      const chart1 = screen.getByTestId('plotly-chart')
      const data1 = chart1.getAttribute('data-chart-data')

      const newData = {
        ...mockData,
        matrix: [
          [40, 5, 5],
          [5, 45, 0],
          [3, 4, 43],
        ],
      }

      rerender(<ConfusionMatrixChart data={newData} />)

      const chart2 = screen.getByTestId('plotly-chart')
      const data2 = chart2.getAttribute('data-chart-data')

      expect(data1).not.toBe(data2)
    })
  })
})

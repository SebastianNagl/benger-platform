/**
 * @jest-environment jsdom
 */
import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MetricSelector } from '../MetricSelector'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, params?: Record<string, any>) => {
      const translations: Record<string, string> = {
        'evaluation.metricSelector.selectMetrics': 'Select Metrics',
        'evaluation.metricSelector.selectedCount': `${params?.selected} of ${params?.total} selected`,
        'evaluation.metricSelector.clearAll': 'Clear All',
        'evaluation.metricSelector.searchPlaceholder': 'Search metrics...',
        'evaluation.metricSelector.quickPresets': 'Quick Presets',
        'evaluation.metricSelector.noResults': 'No metrics found',
      }
      return translations[key] || key
    },
  }),
}))

jest.mock('@/components/shared/Badge', () => ({
  Badge: ({ children, className, variant }: any) => (
    <span className={className} data-variant={variant}>
      {children}
    </span>
  ),
}))

jest.mock('@/components/shared/Button', () => ({
  Button: ({ children, onClick, className, variant }: any) => (
    <button onClick={onClick} className={className} data-variant={variant}>
      {children}
    </button>
  ),
}))

jest.mock('@/components/shared/Card', () => ({
  Card: ({ children, className }: any) => (
    <div className={className}>{children}</div>
  ),
}))

jest.mock('@/components/shared/Checkbox', () => ({
  Checkbox: ({ checked, onChange }: any) => (
    <input type="checkbox" checked={checked} onChange={onChange} />
  ),
}))

describe('MetricSelector', () => {
  const availableMetrics = [
    'accuracy',
    'precision',
    'recall',
    'f1',
    'bleu',
    'rouge',
    'bertscore',
  ]
  const defaultProps = {
    availableMetrics,
    selectedMetrics: [] as string[],
    onSelectionChange: jest.fn(),
  }

  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('Basic rendering', () => {
    it('renders header with Select Metrics title', () => {
      render(<MetricSelector {...defaultProps} />)
      expect(screen.getByText('Select Metrics')).toBeInTheDocument()
    })

    it('shows selected count', () => {
      render(
        <MetricSelector
          {...defaultProps}
          selectedMetrics={['accuracy', 'f1']}
        />
      )
      expect(screen.getByText('2 of 7 selected')).toBeInTheDocument()
    })

    it('shows search input', () => {
      render(<MetricSelector {...defaultProps} />)
      expect(
        screen.getByPlaceholderText('Search metrics...')
      ).toBeInTheDocument()
    })

    it('shows quick presets section', () => {
      render(<MetricSelector {...defaultProps} />)
      expect(screen.getByText('Quick Presets')).toBeInTheDocument()
    })
  })

  describe('Grouped categories', () => {
    it('renders metric categories', () => {
      render(<MetricSelector {...defaultProps} />)
      // Classification metrics category should be visible (has accuracy, precision, recall, f1)
      expect(screen.getByText('Classification Metrics')).toBeInTheDocument()
    })

    it('shows category descriptions', () => {
      render(<MetricSelector {...defaultProps} />)
      expect(
        screen.getByText('For categorical predictions')
      ).toBeInTheDocument()
    })

    it('shows selected count badge per category', () => {
      render(
        <MetricSelector
          {...defaultProps}
          selectedMetrics={['accuracy', 'f1']}
        />
      )
      // Classification has 4 available and 2 selected
      expect(screen.getByText('2/4')).toBeInTheDocument()
    })

    it('expands category on click to show individual metrics', async () => {
      const user = userEvent.setup()
      render(<MetricSelector {...defaultProps} />)

      const categoryHeader = screen.getByText('Classification Metrics')
      await user.click(categoryHeader)

      expect(screen.getByText('accuracy')).toBeInTheDocument()
      expect(screen.getByText('precision')).toBeInTheDocument()
      expect(screen.getByText('recall')).toBeInTheDocument()
      expect(screen.getByText('f1')).toBeInTheDocument()
    })

    it('collapses category on second click', async () => {
      const user = userEvent.setup()
      render(<MetricSelector {...defaultProps} />)

      const categoryHeader = screen.getByText('Classification Metrics')
      await user.click(categoryHeader) // expand
      expect(screen.getByText('accuracy')).toBeInTheDocument()

      await user.click(categoryHeader) // collapse
      // accuracy still appears in category badge or header, but the checkbox label disappears
      const checkboxes = screen.queryAllByRole('checkbox')
      expect(checkboxes).toHaveLength(0)
    })
  })

  describe('Flat list view', () => {
    it('renders metrics in flat list when groupByCategory is false', () => {
      render(<MetricSelector {...defaultProps} groupByCategory={false} />)
      expect(screen.getByText('accuracy')).toBeInTheDocument()
      expect(screen.getByText('f1')).toBeInTheDocument()
    })
  })

  describe('Metric selection', () => {
    it('calls onSelectionChange when toggling a metric', async () => {
      const user = userEvent.setup()
      const onSelectionChange = jest.fn()
      render(
        <MetricSelector
          {...defaultProps}
          groupByCategory={false}
          onSelectionChange={onSelectionChange}
        />
      )

      const checkbox = screen.getAllByRole('checkbox')[0]
      await user.click(checkbox)

      expect(onSelectionChange).toHaveBeenCalled()
    })

    it('deselects a selected metric', async () => {
      const user = userEvent.setup()
      const onSelectionChange = jest.fn()
      render(
        <MetricSelector
          {...defaultProps}
          groupByCategory={false}
          selectedMetrics={['bleu']}
          onSelectionChange={onSelectionChange}
        />
      )

      // Click the label for 'bleu' to deselect it
      const bleuLabel = screen.getByText('bleu').closest('label')
      await user.click(bleuLabel!)

      expect(onSelectionChange).toHaveBeenCalledWith([])
    })
  })

  describe('Search', () => {
    it('filters metrics by search query', async () => {
      const user = userEvent.setup()
      render(
        <MetricSelector {...defaultProps} groupByCategory={false} />
      )

      const searchInput = screen.getByPlaceholderText('Search metrics...')
      await user.type(searchInput, 'acc')

      expect(screen.getByText('accuracy')).toBeInTheDocument()
      // f1 should not be visible
      expect(screen.queryByText('f1')).not.toBeInTheDocument()
    })

    it('shows no results message when search finds nothing', async () => {
      const user = userEvent.setup()
      render(
        <MetricSelector {...defaultProps} groupByCategory={false} />
      )

      const searchInput = screen.getByPlaceholderText('Search metrics...')
      await user.type(searchInput, 'nonexistent')

      expect(screen.getByText('No metrics found')).toBeInTheDocument()
    })
  })

  describe('Presets', () => {
    it('renders preset buttons', () => {
      render(<MetricSelector {...defaultProps} />)
      expect(screen.getByText('Standard NLG Metrics')).toBeInTheDocument()
      expect(screen.getByText('Classification Suite')).toBeInTheDocument()
      expect(screen.getByText('All Available')).toBeInTheDocument()
    })

    it('applies Classification Suite preset', async () => {
      const user = userEvent.setup()
      const onSelectionChange = jest.fn()
      render(
        <MetricSelector
          {...defaultProps}
          onSelectionChange={onSelectionChange}
        />
      )

      await user.click(screen.getByText('Classification Suite'))

      // Should only include metrics that are in availableMetrics
      expect(onSelectionChange).toHaveBeenCalledWith(
        expect.arrayContaining(['accuracy', 'precision', 'recall', 'f1'])
      )
    })

    it('applies All Available preset', async () => {
      const user = userEvent.setup()
      const onSelectionChange = jest.fn()
      render(
        <MetricSelector
          {...defaultProps}
          onSelectionChange={onSelectionChange}
        />
      )

      await user.click(screen.getByText('All Available'))

      expect(onSelectionChange).toHaveBeenCalledWith(availableMetrics)
    })
  })

  describe('Clear All', () => {
    it('clears selection when Clear All is clicked', async () => {
      const user = userEvent.setup()
      const onSelectionChange = jest.fn()
      render(
        <MetricSelector
          {...defaultProps}
          selectedMetrics={['accuracy']}
          onSelectionChange={onSelectionChange}
        />
      )

      await user.click(screen.getByText('Clear All'))

      expect(onSelectionChange).toHaveBeenCalledWith([])
    })
  })

  describe('Only available metrics', () => {
    it('only shows metrics from availableMetrics list in categories', () => {
      render(
        <MetricSelector
          {...defaultProps}
          availableMetrics={['accuracy']}
          groupByCategory={false}
        />
      )
      expect(screen.getByText('accuracy')).toBeInTheDocument()
      expect(screen.queryByText('f1')).not.toBeInTheDocument()
    })

    it('filters out categories with no available metrics', () => {
      render(
        <MetricSelector
          {...defaultProps}
          availableMetrics={['accuracy']}
        />
      )
      // Lexical Metrics category should not appear
      expect(screen.queryByText('Lexical Metrics')).not.toBeInTheDocument()
    })
  })
})

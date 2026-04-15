/**
 * @jest-environment jsdom
 */
import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ChartTypeSelector } from '../ChartTypeSelector'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => {
      const translations: Record<string, string> = {
        'evaluation.chartType.selectView': 'Select View',
        'evaluation.chartType.dataView': 'Data',
        'evaluation.chartType.dataViewDescription': 'Raw data table',
        'evaluation.chartType.dataViewBestFor': 'Export and analysis',
        'evaluation.chartType.barChart': 'Bar Chart',
        'evaluation.chartType.barChartDescription': 'Grouped bar chart',
        'evaluation.chartType.barChartBestFor': 'Comparing models',
        'evaluation.chartType.radarChart': 'Radar Chart',
        'evaluation.chartType.radarChartDescription': 'Spider web chart',
        'evaluation.chartType.radarChartBestFor': 'Multi-metric overview',
        'evaluation.chartType.boxPlot': 'Box Plot',
        'evaluation.chartType.boxPlotDescription': 'Distribution view',
        'evaluation.chartType.boxPlotBestFor': 'Score distributions',
        'evaluation.chartType.heatmap': 'Heatmap',
        'evaluation.chartType.heatmapDescription': 'Color matrix',
        'evaluation.chartType.heatmapBestFor': 'Correlation patterns',
        'evaluation.chartType.tableChart': 'Table',
        'evaluation.chartType.tableChartDescription': 'Tabular results',
        'evaluation.chartType.tableChartBestFor': 'Detailed comparison',
      }
      return translations[key] || key
    },
  }),
}))

jest.mock('@/contexts/HydrationContext', () => ({
  useHydration: () => true,
}))

// Mock localStorage
const localStorageMock = (() => {
  let store: Record<string, string> = {}
  return {
    getItem: jest.fn((key: string) => store[key] || null),
    setItem: jest.fn((key: string, value: string) => {
      store[key] = value
    }),
    removeItem: jest.fn((key: string) => {
      delete store[key]
    }),
    clear: jest.fn(() => {
      store = {}
    }),
  }
})()

Object.defineProperty(window, 'localStorage', { value: localStorageMock })

describe('ChartTypeSelector', () => {
  const defaultProps = {
    selectedType: 'bar' as const,
    onChange: jest.fn(),
  }

  beforeEach(() => {
    jest.clearAllMocks()
    localStorageMock.clear()
  })

  describe('Closed state', () => {
    it('shows selected chart type label', () => {
      render(<ChartTypeSelector {...defaultProps} />)
      expect(screen.getByText('Bar Chart')).toBeInTheDocument()
    })

    it('shows Data label for data type', () => {
      render(<ChartTypeSelector {...defaultProps} selectedType="data" />)
      expect(screen.getByText('Data')).toBeInTheDocument()
    })
  })

  describe('Dropdown', () => {
    it('opens dropdown on click', async () => {
      const user = userEvent.setup()
      render(<ChartTypeSelector {...defaultProps} />)

      await user.click(screen.getByText('Bar Chart'))

      expect(screen.getByText('Radar Chart')).toBeInTheDocument()
      expect(screen.getByText('Box Plot')).toBeInTheDocument()
      expect(screen.getByText('Heatmap')).toBeInTheDocument()
    })

    it('shows descriptions for each chart type', async () => {
      const user = userEvent.setup()
      render(<ChartTypeSelector {...defaultProps} />)

      await user.click(screen.getByText('Bar Chart'))

      expect(screen.getByText('Raw data table')).toBeInTheDocument()
      expect(screen.getByText('Spider web chart')).toBeInTheDocument()
    })

    it('shows checkmark for selected type', async () => {
      const user = userEvent.setup()
      render(<ChartTypeSelector {...defaultProps} selectedType="bar" />)

      await user.click(screen.getByText('Bar Chart'))

      // The selected item should have the emerald styling
      const barButton = screen.getAllByText('Bar Chart')
      const dropdownOption = barButton[barButton.length - 1].closest('button')
      expect(dropdownOption).toHaveClass('bg-emerald-50')
    })
  })

  describe('Selection', () => {
    it('calls onChange when chart type is selected', async () => {
      const user = userEvent.setup()
      const onChange = jest.fn()
      render(
        <ChartTypeSelector selectedType="bar" onChange={onChange} />
      )

      await user.click(screen.getByText('Bar Chart'))
      await user.click(screen.getByText('Radar Chart'))

      expect(onChange).toHaveBeenCalledWith('radar')
    })

    it('closes dropdown after selection', async () => {
      const user = userEvent.setup()
      render(<ChartTypeSelector {...defaultProps} />)

      await user.click(screen.getByText('Bar Chart'))
      await user.click(screen.getByText('Radar Chart'))

      // Dropdown should be closed - descriptions should not be visible
      expect(screen.queryByText('Spider web chart')).not.toBeInTheDocument()
    })

    it('saves preference to localStorage', async () => {
      const user = userEvent.setup()
      render(<ChartTypeSelector {...defaultProps} />)

      await user.click(screen.getByText('Bar Chart'))
      await user.click(screen.getByText('Radar Chart'))

      expect(localStorageMock.setItem).toHaveBeenCalledWith(
        'benger-preferred-chart-type',
        'radar'
      )
    })
  })

  describe('Available types filter', () => {
    it('only shows available chart types', async () => {
      const user = userEvent.setup()
      render(
        <ChartTypeSelector
          {...defaultProps}
          availableTypes={['bar', 'data']}
        />
      )

      await user.click(screen.getByText('Bar Chart'))

      expect(screen.getByText('Data')).toBeInTheDocument()
      expect(screen.queryByText('Radar Chart')).not.toBeInTheDocument()
    })
  })

  describe('Disabled types', () => {
    it('shows disabled types with reduced opacity', async () => {
      const user = userEvent.setup()
      render(
        <ChartTypeSelector
          {...defaultProps}
          disabledTypes={['heatmap']}
          disabledReasons={{ heatmap: 'Requires multiple models' }}
        />
      )

      await user.click(screen.getByText('Bar Chart'))

      const heatmapButton = screen.getByText('Heatmap').closest('button')
      expect(heatmapButton).toHaveAttribute(
        'title',
        'Requires multiple models'
      )
      expect(heatmapButton).toBeDisabled()
    })

    it('does not call onChange for disabled types', async () => {
      const user = userEvent.setup()
      const onChange = jest.fn()
      render(
        <ChartTypeSelector
          selectedType="bar"
          onChange={onChange}
          disabledTypes={['heatmap']}
        />
      )

      await user.click(screen.getByText('Bar Chart'))
      const heatmapButton = screen.getByText('Heatmap').closest('button')
      await user.click(heatmapButton!)

      expect(onChange).not.toHaveBeenCalledWith('heatmap')
    })
  })

  describe('Close behavior', () => {
    it('closes on outside click', async () => {
      const user = userEvent.setup()
      render(
        <div>
          <ChartTypeSelector {...defaultProps} />
          <div data-testid="outside">Outside</div>
        </div>
      )

      await user.click(screen.getByText('Bar Chart'))
      expect(screen.getByText('Radar Chart')).toBeInTheDocument()

      await user.click(screen.getByTestId('outside'))
      expect(screen.queryByText('Radar Chart')).not.toBeInTheDocument()
    })
  })
})

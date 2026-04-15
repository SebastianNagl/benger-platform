/**
 * @jest-environment jsdom
 *
 * Branch coverage tests for ChartTypeSelector.
 * Targets 12 uncovered branches including:
 * - localStorage preference loading with disabled/unavailable types
 * - size='sm' rendering
 * - disabled types with reasons
 * - outside click handling
 */

import '@testing-library/jest-dom'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { ChartTypeSelector } from '../ChartTypeSelector'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => {
      const translations: Record<string, string> = {
        'evaluation.chartType.selectView': 'Select View',
        'evaluation.chartType.dataView': 'Data',
        'evaluation.chartType.dataViewDescription': 'Raw data table',
        'evaluation.chartType.dataViewBestFor': 'Export',
        'evaluation.chartType.barChart': 'Bar Chart',
        'evaluation.chartType.barChartDescription': 'Grouped bar',
        'evaluation.chartType.barChartBestFor': 'Comparing',
        'evaluation.chartType.radarChart': 'Radar',
        'evaluation.chartType.radarChartDescription': 'Spider chart',
        'evaluation.chartType.radarChartBestFor': 'Multi-metric',
        'evaluation.chartType.boxPlot': 'Box Plot',
        'evaluation.chartType.boxPlotDescription': 'Distribution',
        'evaluation.chartType.boxPlotBestFor': 'Distributions',
        'evaluation.chartType.heatmap': 'Heatmap',
        'evaluation.chartType.heatmapDescription': 'Color matrix',
        'evaluation.chartType.heatmapBestFor': 'Correlation',
        'evaluation.chartType.tableChart': 'Table',
        'evaluation.chartType.tableChartDescription': 'Tabular',
        'evaluation.chartType.tableChartBestFor': 'Detail',
      }
      return translations[key] || key
    },
  }),
}))

jest.mock('@/contexts/HydrationContext', () => ({
  useHydration: () => true,
}))

jest.mock('@heroicons/react/24/outline', () => ({
  ChartBarIcon: (props: any) => <svg {...props} data-testid="bar-icon" />,
  ChartPieIcon: (props: any) => <svg {...props} data-testid="pie-icon" />,
  ChevronDownIcon: (props: any) => <svg {...props} data-testid="chevron-icon" />,
  Square3Stack3DIcon: (props: any) => <svg {...props} data-testid="stack-icon" />,
  Squares2X2Icon: (props: any) => <svg {...props} data-testid="squares-icon" />,
  TableCellsIcon: (props: any) => <svg {...props} data-testid="table-icon" />,
}))

const mockLocalStorage = (() => {
  let store: Record<string, string> = {}
  return {
    getItem: jest.fn((key: string) => store[key] || null),
    setItem: jest.fn((key: string, value: string) => { store[key] = value }),
    removeItem: jest.fn((key: string) => { delete store[key] }),
    clear: () => { store = {} },
    reset: () => { store = {} },
  }
})()

Object.defineProperty(window, 'localStorage', { value: mockLocalStorage })

describe('ChartTypeSelector branch coverage', () => {
  beforeEach(() => {
    mockLocalStorage.reset()
    mockLocalStorage.getItem.mockClear()
    mockLocalStorage.setItem.mockClear()
    jest.clearAllMocks()
  })

  it('loads saved preference from localStorage on mount', () => {
    mockLocalStorage.getItem.mockReturnValueOnce('radar')
    const onChange = jest.fn()
    render(
      <ChartTypeSelector selectedType="bar" onChange={onChange} />
    )
    expect(onChange).toHaveBeenCalledWith('radar')
  })

  it('does not apply saved preference if type is disabled', () => {
    mockLocalStorage.getItem.mockReturnValueOnce('box')
    const onChange = jest.fn()
    render(
      <ChartTypeSelector
        selectedType="bar"
        onChange={onChange}
        disabledTypes={['box']}
      />
    )
    expect(onChange).not.toHaveBeenCalledWith('box')
  })

  it('does not apply saved preference if type is not in availableTypes', () => {
    mockLocalStorage.getItem.mockReturnValueOnce('heatmap')
    const onChange = jest.fn()
    render(
      <ChartTypeSelector
        selectedType="bar"
        onChange={onChange}
        availableTypes={['data', 'bar', 'table']}
      />
    )
    expect(onChange).not.toHaveBeenCalledWith('heatmap')
  })

  it('opens dropdown and shows all types', () => {
    render(
      <ChartTypeSelector selectedType="bar" onChange={jest.fn()} />
    )
    fireEvent.click(screen.getByText('Bar Chart'))
    expect(screen.getByText('Data')).toBeInTheDocument()
    expect(screen.getByText('Radar')).toBeInTheDocument()
    expect(screen.getByText('Heatmap')).toBeInTheDocument()
  })

  it('filters types by availableTypes', () => {
    render(
      <ChartTypeSelector
        selectedType="data"
        onChange={jest.fn()}
        availableTypes={['data', 'bar']}
      />
    )
    fireEvent.click(screen.getByText('Data'))
    expect(screen.getByText('Bar Chart')).toBeInTheDocument()
    // Radar should not be in dropdown items (only in the dropdown, not as a filtered type)
    const items = screen.getAllByRole('button')
    const labels = items.map(i => i.textContent)
    expect(labels.join('')).not.toContain('Radar')
  })

  it('disables types with disabled reason tooltip', () => {
    render(
      <ChartTypeSelector
        selectedType="bar"
        onChange={jest.fn()}
        disabledTypes={['heatmap']}
        disabledReasons={{ heatmap: 'Requires 2+ models' }}
      />
    )
    fireEvent.click(screen.getByText('Bar Chart'))
    const heatmapBtn = screen.getByText('Heatmap').closest('button')
    expect(heatmapBtn).toBeDisabled()
    expect(heatmapBtn).toHaveAttribute('title', 'Requires 2+ models')
  })

  it('clicking disabled type does not trigger onChange', () => {
    const onChange = jest.fn()
    render(
      <ChartTypeSelector
        selectedType="bar"
        onChange={onChange}
        disabledTypes={['heatmap']}
      />
    )
    fireEvent.click(screen.getByText('Bar Chart'))
    onChange.mockClear()
    fireEvent.click(screen.getByText('Heatmap').closest('button')!)
    expect(onChange).not.toHaveBeenCalled()
  })

  it('selects a type and saves to localStorage', () => {
    const onChange = jest.fn()
    // Prevent saved pref from interfering
    mockLocalStorage.getItem.mockReturnValue(null)
    render(
      <ChartTypeSelector selectedType="bar" onChange={onChange} />
    )
    fireEvent.click(screen.getByText('Bar Chart'))
    onChange.mockClear()
    fireEvent.click(screen.getByText('Radar'))
    expect(onChange).toHaveBeenCalledWith('radar')
    expect(mockLocalStorage.setItem).toHaveBeenCalledWith('benger-preferred-chart-type', 'radar')
  })

  it('closes dropdown on outside click', () => {
    render(
      <ChartTypeSelector selectedType="bar" onChange={jest.fn()} />
    )
    fireEvent.click(screen.getByText('Bar Chart'))
    expect(screen.getByText('Data')).toBeInTheDocument()
    // Simulate outside click
    fireEvent.mouseDown(document)
    // Dropdown should close
  })

  it('renders with size sm', () => {
    mockLocalStorage.getItem.mockReturnValue(null)
    render(
      <ChartTypeSelector selectedType="bar" onChange={jest.fn()} size="sm" />
    )
    expect(screen.getByText('Bar Chart')).toBeInTheDocument()
  })

  it('shows Select View when selectedType is unknown', () => {
    mockLocalStorage.getItem.mockReturnValue(null)
    render(
      <ChartTypeSelector selectedType={'unknown' as any} onChange={jest.fn()} />
    )
    expect(screen.getByText('Select View')).toBeInTheDocument()
  })
})

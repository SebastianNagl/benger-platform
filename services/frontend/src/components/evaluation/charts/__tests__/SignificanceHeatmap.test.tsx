/**
 * Tests for SignificanceHeatmap component
 * Tests data processing, rendering logic, legend display, and click callbacks
 */

/**
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({ t: (key: string) => key, locale: 'en' }),
}))

// Mock next/dynamic to return a simple component that captures props
const mockPlotProps: any[] = []
jest.mock('next/dynamic', () => {
  return () => {
    const MockPlot = (props: any) => {
      mockPlotProps.push(props)
      return (
        <div data-testid="plotly-chart">
          <span data-testid="plot-data">{JSON.stringify(props.data)}</span>
          <span data-testid="plot-layout">{JSON.stringify(props.layout)}</span>
        </div>
      )
    }
    MockPlot.displayName = 'MockPlot'
    return MockPlot
  }
})

import { SignificanceHeatmap } from '../SignificanceHeatmap'

describe('SignificanceHeatmap', () => {
  const modelIds = ['gpt-4', 'llama-3', 'mistral']

  const significanceData = [
    {
      model_a: 'gpt-4',
      model_b: 'llama-3',
      p_value: 0.001,
      significant: true,
      effect_size: 0.8,
      stars: '***',
    },
    {
      model_a: 'gpt-4',
      model_b: 'mistral',
      p_value: 0.03,
      significant: true,
      effect_size: 0.3,
      stars: '*',
    },
    {
      model_a: 'llama-3',
      model_b: 'mistral',
      p_value: 0.12,
      significant: false,
      effect_size: 0.1,
      stars: '',
    },
  ]

  beforeEach(() => {
    mockPlotProps.length = 0
  })

  it('renders without crashing', () => {
    const { container } = render(
      <SignificanceHeatmap
        modelIds={modelIds}
        metric="F1"
        significanceData={significanceData}
      />
    )
    expect(container).toBeTruthy()
  })

  it('renders the Plotly chart', () => {
    render(
      <SignificanceHeatmap
        modelIds={modelIds}
        metric="F1"
        significanceData={significanceData}
      />
    )
    expect(screen.getByTestId('plotly-chart')).toBeInTheDocument()
  })

  it('passes correct model IDs as axes to the plot', () => {
    render(
      <SignificanceHeatmap
        modelIds={modelIds}
        metric="F1"
        significanceData={significanceData}
      />
    )
    const lastProps = mockPlotProps[mockPlotProps.length - 1]
    expect(lastProps.data[0].x).toEqual(modelIds)
    expect(lastProps.data[0].y).toEqual(modelIds)
  })

  it('builds a lower-triangular heatmap matrix with nulls above diagonal', () => {
    render(
      <SignificanceHeatmap
        modelIds={modelIds}
        metric="F1"
        significanceData={significanceData}
      />
    )
    const lastProps = mockPlotProps[mockPlotProps.length - 1]
    const z = lastProps.data[0].z

    // Diagonal should be 0
    expect(z[0][0]).toBe(0)
    expect(z[1][1]).toBe(0)
    expect(z[2][2]).toBe(0)

    // Upper triangle (i < j) should be null
    expect(z[0][1]).toBeNull()
    expect(z[0][2]).toBeNull()
    expect(z[1][2]).toBeNull()
  })

  it('populates lower-triangle with effect sizes from significance data', () => {
    render(
      <SignificanceHeatmap
        modelIds={modelIds}
        metric="F1"
        significanceData={significanceData}
      />
    )
    const lastProps = mockPlotProps[mockPlotProps.length - 1]
    const z = lastProps.data[0].z

    // z[i][j] where i > j: key is `${modelIds[j]}:${modelIds[i]}`
    // z[1][0]: key = "gpt-4:llama-3" -> effect_size 0.8
    expect(z[1][0]).toBe(0.8)
    // z[2][0]: key = "gpt-4:mistral" -> effect_size 0.3
    expect(z[2][0]).toBe(0.3)
    // z[2][1]: key = "llama-3:mistral" -> effect_size 0.1
    expect(z[2][1]).toBe(0.1)
  })

  it('includes metric name in the layout title', () => {
    render(
      <SignificanceHeatmap
        modelIds={modelIds}
        metric="BLEU"
        significanceData={significanceData}
      />
    )
    const lastProps = mockPlotProps[mockPlotProps.length - 1]
    expect(lastProps.layout.title.text).toContain('BLEU')
  })

  it('uses the provided height for layout dimensions', () => {
    render(
      <SignificanceHeatmap
        modelIds={modelIds}
        metric="F1"
        significanceData={significanceData}
        height={600}
      />
    )
    const lastProps = mockPlotProps[mockPlotProps.length - 1]
    expect(lastProps.layout.height).toBe(600)
    expect(lastProps.layout.width).toBe(600)
  })

  it('defaults height to 400 when not provided', () => {
    render(
      <SignificanceHeatmap
        modelIds={modelIds}
        metric="F1"
        significanceData={significanceData}
      />
    )
    const lastProps = mockPlotProps[mockPlotProps.length - 1]
    expect(lastProps.layout.height).toBe(400)
  })

  it('renders the legend section', () => {
    render(
      <SignificanceHeatmap
        modelIds={modelIds}
        metric="F1"
        significanceData={significanceData}
      />
    )
    expect(screen.getByText('evaluation.charts.significance.legend')).toBeInTheDocument()
    expect(screen.getByText('evaluation.charts.significance.colorScale')).toBeInTheDocument()
    expect(screen.getByText('evaluation.charts.significance.significanceStars')).toBeInTheDocument()
  })

  it('displays significance stars in the legend', () => {
    render(
      <SignificanceHeatmap
        modelIds={modelIds}
        metric="F1"
        significanceData={significanceData}
      />
    )
    expect(screen.getByText('***')).toBeInTheDocument()
    expect(screen.getByText('**')).toBeInTheDocument()
    expect(screen.getByText('*')).toBeInTheDocument()
  })

  it('fires onCellClick callback with model names when a cell is clicked', () => {
    const onCellClick = jest.fn()
    render(
      <SignificanceHeatmap
        modelIds={modelIds}
        metric="F1"
        significanceData={significanceData}
        onCellClick={onCellClick}
      />
    )
    const lastProps = mockPlotProps[mockPlotProps.length - 1]
    // Simulate Plotly click event
    lastProps.onClick({
      points: [{ x: 'gpt-4', y: 'llama-3' }],
    })
    expect(onCellClick).toHaveBeenCalledWith('llama-3', 'gpt-4')
  })

  it('does not fire onCellClick when clicking the diagonal (same model)', () => {
    const onCellClick = jest.fn()
    render(
      <SignificanceHeatmap
        modelIds={modelIds}
        metric="F1"
        significanceData={significanceData}
        onCellClick={onCellClick}
      />
    )
    const lastProps = mockPlotProps[mockPlotProps.length - 1]
    lastProps.onClick({
      points: [{ x: 'gpt-4', y: 'gpt-4' }],
    })
    expect(onCellClick).not.toHaveBeenCalled()
  })

  it('does not crash when clicking with no onCellClick callback', () => {
    render(
      <SignificanceHeatmap
        modelIds={modelIds}
        metric="F1"
        significanceData={significanceData}
      />
    )
    const lastProps = mockPlotProps[mockPlotProps.length - 1]
    expect(() => {
      lastProps.onClick({ points: [{ x: 'gpt-4', y: 'llama-3' }] })
    }).not.toThrow()
  })

  it('does not crash with empty click event', () => {
    const onCellClick = jest.fn()
    render(
      <SignificanceHeatmap
        modelIds={modelIds}
        metric="F1"
        significanceData={significanceData}
        onCellClick={onCellClick}
      />
    )
    const lastProps = mockPlotProps[mockPlotProps.length - 1]
    lastProps.onClick({ points: [] })
    expect(onCellClick).not.toHaveBeenCalled()
  })

  it('handles empty significance data gracefully', () => {
    render(
      <SignificanceHeatmap
        modelIds={modelIds}
        metric="F1"
        significanceData={[]}
      />
    )
    const lastProps = mockPlotProps[mockPlotProps.length - 1]
    const z = lastProps.data[0].z
    // Diagonal should still be 0, rest null
    expect(z[0][0]).toBe(0)
    expect(z[1][0]).toBeNull()
  })

  it('handles a single model (1x1 matrix)', () => {
    render(
      <SignificanceHeatmap
        modelIds={['only-model']}
        metric="F1"
        significanceData={[]}
      />
    )
    const lastProps = mockPlotProps[mockPlotProps.length - 1]
    const z = lastProps.data[0].z
    expect(z.length).toBe(1)
    expect(z[0][0]).toBe(0)
  })

  it('creates annotations with white text for large effect sizes (> 0.5)', () => {
    render(
      <SignificanceHeatmap
        modelIds={modelIds}
        metric="F1"
        significanceData={significanceData}
      />
    )
    const lastProps = mockPlotProps[mockPlotProps.length - 1]
    const annotations = lastProps.layout.annotations

    // Effect size 0.8 (> 0.5) should have white text
    const starAnnotation = annotations.find((a: any) => a.text === '***')
    expect(starAnnotation).toBeDefined()
    expect(starAnnotation.font.color).toBe('white')
  })

  it('creates annotations with black text for small effect sizes (<= 0.5)', () => {
    render(
      <SignificanceHeatmap
        modelIds={modelIds}
        metric="F1"
        significanceData={significanceData}
      />
    )
    const lastProps = mockPlotProps[mockPlotProps.length - 1]
    const annotations = lastProps.layout.annotations

    // Effect size 0.3 (<= 0.5) should have black text
    const singleStarAnnotation = annotations.find((a: any) => a.text === '*')
    expect(singleStarAnnotation).toBeDefined()
    expect(singleStarAnnotation.font.color).toBe('black')
  })

  it('includes note text in the legend', () => {
    render(
      <SignificanceHeatmap
        modelIds={modelIds}
        metric="F1"
        significanceData={significanceData}
      />
    )
    // noteLabel is inside a <strong> tag with a colon appended
    expect(screen.getByText(/evaluation\.charts\.significance\.noteLabel/)).toBeInTheDocument()
  })

  it('builds correct customdata structure for hover tooltips', () => {
    render(
      <SignificanceHeatmap
        modelIds={modelIds}
        metric="F1"
        significanceData={significanceData}
      />
    )
    const lastProps = mockPlotProps[mockPlotProps.length - 1]
    const customdata = lastProps.data[0].customdata

    // customdata[1][0] should have data for llama-3 vs gpt-4
    expect(customdata[1][0].pValue).toBe(0.001)
    expect(customdata[1][0].effectSize).toBe(0.8)
    expect(customdata[1][0].significant).toBe(true)
    expect(customdata[1][0].stars).toBe('***')

    // Diagonal entry should have null values
    expect(customdata[0][0].pValue).toBeNull()
    expect(customdata[0][0].effectSize).toBeNull()
  })
})

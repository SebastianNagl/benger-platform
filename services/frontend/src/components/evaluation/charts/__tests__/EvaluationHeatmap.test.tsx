/**
 * Tests for EvaluationHeatmap component
 * Tests data processing, score range calculation, export functionality, and callbacks
 */

/**
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({ t: (key: string, params?: any) => params ? `${key}:${JSON.stringify(params)}` : key, locale: 'en' }),
}))

// Mock next/dynamic for Plotly
const mockPlotProps: any[] = []
jest.mock('next/dynamic', () => {
  return () => {
    const MockPlot = (props: any) => {
      mockPlotProps.push(props)
      return <div data-testid="plotly-chart" />
    }
    MockPlot.displayName = 'MockPlot'
    return MockPlot
  }
})

// Mock heroicons
jest.mock('@heroicons/react/24/outline', () => ({
  ArrowDownTrayIcon: ({ className }: any) => <svg data-testid="download-icon" className={className} />,
  ClipboardDocumentIcon: ({ className }: any) => <svg data-testid="clipboard-icon" className={className} />,
}))

import { EvaluationHeatmap } from '../EvaluationHeatmap'

describe('EvaluationHeatmap', () => {
  const predictionFields = ['pred_field_a', 'pred_field_b']
  const referenceFields = ['ref_field_x', 'ref_field_y', 'ref_field_z']
  const scores: Record<string, Record<string, number>> = {
    pred_field_a: { ref_field_x: 0.85, ref_field_y: 0.72, ref_field_z: 0.91 },
    pred_field_b: { ref_field_x: 0.60, ref_field_y: 0.45, ref_field_z: 0.78 },
  }

  beforeEach(() => {
    mockPlotProps.length = 0
    jest.clearAllMocks()
  })

  it('renders without crashing', () => {
    const { container } = render(
      <EvaluationHeatmap
        predictionFields={predictionFields}
        referenceFields={referenceFields}
        scores={scores}
        metric="BLEU"
      />
    )
    expect(container).toBeTruthy()
  })

  it('renders the Plotly chart', () => {
    render(
      <EvaluationHeatmap
        predictionFields={predictionFields}
        referenceFields={referenceFields}
        scores={scores}
        metric="BLEU"
      />
    )
    expect(screen.getByTestId('plotly-chart')).toBeInTheDocument()
  })

  it('passes correct axes to the plot', () => {
    render(
      <EvaluationHeatmap
        predictionFields={predictionFields}
        referenceFields={referenceFields}
        scores={scores}
        metric="BLEU"
      />
    )
    const lastProps = mockPlotProps[mockPlotProps.length - 1]
    expect(lastProps.data[0].x).toEqual(referenceFields)
    expect(lastProps.data[0].y).toEqual(predictionFields)
  })

  it('builds z-matrix with correct score values', () => {
    render(
      <EvaluationHeatmap
        predictionFields={predictionFields}
        referenceFields={referenceFields}
        scores={scores}
        metric="BLEU"
      />
    )
    const lastProps = mockPlotProps[mockPlotProps.length - 1]
    const z = lastProps.data[0].z

    expect(z[0][0]).toBe(0.85) // pred_field_a x ref_field_x
    expect(z[0][1]).toBe(0.72) // pred_field_a x ref_field_y
    expect(z[0][2]).toBe(0.91) // pred_field_a x ref_field_z
    expect(z[1][0]).toBe(0.60) // pred_field_b x ref_field_x
    expect(z[1][1]).toBe(0.45) // pred_field_b x ref_field_y
    expect(z[1][2]).toBe(0.78) // pred_field_b x ref_field_z
  })

  it('includes metric name in layout title', () => {
    render(
      <EvaluationHeatmap
        predictionFields={predictionFields}
        referenceFields={referenceFields}
        scores={scores}
        metric="ROUGE-L"
      />
    )
    const lastProps = mockPlotProps[mockPlotProps.length - 1]
    expect(lastProps.layout.title.text).toContain('ROUGE-L')
  })

  it('calculates dynamic layout size based on field counts', () => {
    render(
      <EvaluationHeatmap
        predictionFields={predictionFields}
        referenceFields={referenceFields}
        scores={scores}
        metric="BLEU"
      />
    )
    const lastProps = mockPlotProps[mockPlotProps.length - 1]
    // width = Math.max(600, 3 * 120) = 600
    expect(lastProps.layout.width).toBe(600)
    // height = Math.max(400, 2 * 80) = 400
    expect(lastProps.layout.height).toBe(400)
  })

  it('renders export CSV and LaTeX buttons', () => {
    render(
      <EvaluationHeatmap
        predictionFields={predictionFields}
        referenceFields={referenceFields}
        scores={scores}
        metric="BLEU"
      />
    )
    expect(screen.getByText('evaluation.charts.heatmap.exportCsv')).toBeInTheDocument()
    expect(screen.getByText('evaluation.charts.heatmap.exportLatex')).toBeInTheDocument()
  })

  it('renders the legend section with color scale', () => {
    render(
      <EvaluationHeatmap
        predictionFields={predictionFields}
        referenceFields={referenceFields}
        scores={scores}
        metric="BLEU"
      />
    )
    expect(screen.getByText('evaluation.charts.heatmap.legend')).toBeInTheDocument()
    expect(screen.getByText('evaluation.charts.heatmap.colorScale')).toBeInTheDocument()
    expect(screen.getByText('evaluation.charts.heatmap.highScore')).toBeInTheDocument()
    expect(screen.getByText('evaluation.charts.heatmap.mediumScore')).toBeInTheDocument()
    expect(screen.getByText('evaluation.charts.heatmap.lowScore')).toBeInTheDocument()
  })

  it('displays min and max score values in the legend', () => {
    render(
      <EvaluationHeatmap
        predictionFields={predictionFields}
        referenceFields={referenceFields}
        scores={scores}
        metric="BLEU"
      />
    )
    // minScore = 0.45, maxScore = 0.91
    expect(screen.getByText('0.4500')).toBeInTheDocument()
    expect(screen.getByText('0.9100')).toBeInTheDocument()
  })

  it('fires onCellClick with prediction and reference field names', () => {
    const onCellClick = jest.fn()
    render(
      <EvaluationHeatmap
        predictionFields={predictionFields}
        referenceFields={referenceFields}
        scores={scores}
        metric="BLEU"
        onCellClick={onCellClick}
      />
    )
    const lastProps = mockPlotProps[mockPlotProps.length - 1]
    lastProps.onClick({
      points: [{ x: 'ref_field_y', y: 'pred_field_a' }],
    })
    expect(onCellClick).toHaveBeenCalledWith('pred_field_a', 'ref_field_y')
  })

  it('does not crash when clicking without onCellClick callback', () => {
    render(
      <EvaluationHeatmap
        predictionFields={predictionFields}
        referenceFields={referenceFields}
        scores={scores}
        metric="BLEU"
      />
    )
    const lastProps = mockPlotProps[mockPlotProps.length - 1]
    expect(() => {
      lastProps.onClick({ points: [{ x: 'ref_field_y', y: 'pred_field_a' }] })
    }).not.toThrow()
  })

  it('handles missing scores with null values in the matrix', () => {
    const sparseScores: Record<string, Record<string, number>> = {
      pred_field_a: { ref_field_x: 0.5 },
      // pred_field_b has no entries
    }
    render(
      <EvaluationHeatmap
        predictionFields={predictionFields}
        referenceFields={referenceFields}
        scores={sparseScores}
        metric="BLEU"
      />
    )
    const lastProps = mockPlotProps[mockPlotProps.length - 1]
    const z = lastProps.data[0].z
    expect(z[0][0]).toBe(0.5)
    expect(z[0][1]).toBeNull()
    expect(z[1][0]).toBeNull()
  })

  it('triggers CSV download when CSV button is clicked', () => {
    const mockCreateObjectURL = jest.fn(() => 'blob:test-url')
    global.URL.createObjectURL = mockCreateObjectURL

    render(
      <EvaluationHeatmap
        predictionFields={predictionFields}
        referenceFields={referenceFields}
        scores={scores}
        metric="BLEU"
      />
    )

    fireEvent.click(screen.getByText('evaluation.charts.heatmap.exportCsv'))

    // createObjectURL should have been called with a Blob
    expect(mockCreateObjectURL).toHaveBeenCalled()
    const blob = mockCreateObjectURL.mock.calls[0][0]
    expect(blob).toBeInstanceOf(Blob)
    expect(blob.type).toBe('text/csv;charset=utf-8;')
  })

  it('copies LaTeX to clipboard when LaTeX button is clicked', async () => {
    const mockWriteText = jest.fn().mockResolvedValue(undefined)
    Object.assign(navigator, {
      clipboard: { writeText: mockWriteText },
    })

    render(
      <EvaluationHeatmap
        predictionFields={predictionFields}
        referenceFields={referenceFields}
        scores={scores}
        metric="BLEU"
      />
    )

    await act(async () => {
      fireEvent.click(screen.getByText('evaluation.charts.heatmap.exportLatex'))
    })

    expect(mockWriteText).toHaveBeenCalled()
    const latexContent = mockWriteText.mock.calls[0][0]
    expect(latexContent).toContain('\\begin{table}')
    expect(latexContent).toContain('\\end{table}')
    expect(latexContent).toContain('\\begin{tabular}')
    expect(latexContent).toContain('BLEU')
    expect(latexContent).toContain('\\textbf{pred_field_a}')
  })

  it('creates text annotations with white color for scores > 0.5', () => {
    render(
      <EvaluationHeatmap
        predictionFields={predictionFields}
        referenceFields={referenceFields}
        scores={scores}
        metric="BLEU"
      />
    )
    const lastProps = mockPlotProps[mockPlotProps.length - 1]
    const annotations = lastProps.layout.annotations

    // score 0.85 > 0.5 -> white text
    const highScoreAnnotation = annotations.find((a: any) => a.text === '0.850')
    expect(highScoreAnnotation).toBeDefined()
    expect(highScoreAnnotation.font.color).toBe('white')
  })

  it('creates text annotations with black color for scores <= 0.5', () => {
    render(
      <EvaluationHeatmap
        predictionFields={predictionFields}
        referenceFields={referenceFields}
        scores={scores}
        metric="BLEU"
      />
    )
    const lastProps = mockPlotProps[mockPlotProps.length - 1]
    const annotations = lastProps.layout.annotations

    // score 0.45 <= 0.5 -> black text
    const lowScoreAnnotation = annotations.find((a: any) => a.text === '0.450')
    expect(lowScoreAnnotation).toBeDefined()
    expect(lowScoreAnnotation.font.color).toBe('black')
  })

  it('shows default min/max when all scores are missing', () => {
    const { container } = render(
      <EvaluationHeatmap
        predictionFields={['a']}
        referenceFields={['b']}
        scores={{}}
        metric="BLEU"
      />
    )
    // minScore defaults to 0, maxScore defaults to 1
    expect(container.textContent).toContain('0.0000')
    expect(container.textContent).toContain('1.0000')
  })
})

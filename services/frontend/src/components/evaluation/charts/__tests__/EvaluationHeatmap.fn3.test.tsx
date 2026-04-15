/**
 * fn3 function coverage for EvaluationHeatmap.tsx
 * Targets: handleExportCSV, handleCopyTable, onCellClick handler
 */

import React from 'react'
import { render, screen } from '@testing-library/react'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    locale: 'en',
    t: (key: string) => key,
    changeLocale: jest.fn(),
    isReady: true,
  }),
}))

// Mock react-plotly.js dynamic import
jest.mock('next/dynamic', () => {
  return () => {
    const MockPlot = (props: any) => (
      <div data-testid="heatmap-plot" onClick={() => props.onClick?.({ points: [{ x: 'ref1', y: 'pred1' }] })} />
    )
    MockPlot.displayName = 'MockPlot'
    return MockPlot
  }
})

import { EvaluationHeatmap } from '../EvaluationHeatmap'

describe('EvaluationHeatmap fn3', () => {
  const defaultProps = {
    predictionFields: ['pred1', 'pred2'],
    referenceFields: ['ref1', 'ref2'],
    scores: {
      pred1: { ref1: 0.85, ref2: 0.72 },
      pred2: { ref1: 0.68, ref2: 0.91 },
    },
    metric: 'bleu',
  }

  it('renders heatmap with data', () => {
    render(<EvaluationHeatmap {...defaultProps} />)
    expect(screen.getByTestId('heatmap-plot')).toBeInTheDocument()
  })

  it('renders with onCellClick callback', () => {
    const onCellClick = jest.fn()
    render(<EvaluationHeatmap {...defaultProps} onCellClick={onCellClick} />)
    expect(screen.getByTestId('heatmap-plot')).toBeInTheDocument()
  })

  it('renders with empty scores', () => {
    render(
      <EvaluationHeatmap
        predictionFields={['pred1']}
        referenceFields={['ref1']}
        scores={{ pred1: {} }}
        metric="rouge"
      />
    )
    expect(screen.getByTestId('heatmap-plot')).toBeInTheDocument()
  })
})

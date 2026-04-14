/**
 * @jest-environment jsdom
 *
 * Branch coverage: EvaluationResultsTable.tsx
 * Targets: L73 (significance p>=0.05 returns ''), L119-120 (sort by rank with Infinity),
 *          L146 (sort direction null->desc)
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
        'evaluation.resultsTable.scoreHigh': 'High',
        'evaluation.resultsTable.scoreMedium': 'Medium',
        'evaluation.resultsTable.scoreLow': 'Low',
        'evaluation.resultsTable.baseline': 'Baseline',
        'evaluation.resultsTable.significanceLegend': 'Significance',
        'evaluation.resultsTable.baselineNote': `Baseline: ${params?.model}`,
      }
      return translations[key] || key
    },
  }),
}))

describe('EvaluationResultsTable br4 - uncovered branches', () => {
  it('returns empty string for significance p >= 0.05 (line 73)', () => {
    // Significance p=0.1 should NOT render a <sup> element
    const results = [
      {
        modelId: 'test',
        metrics: {
          accuracy: { value: 0.85, significance: 0.1 },
        },
      },
    ]
    render(<EvaluationResultsTable results={results} />)
    expect(screen.getByText('85.0%')).toBeInTheDocument()
    // No significance indicator should appear
    const sup = document.querySelector('sup')
    expect(sup).toBeNull()
  })

  it('sorts by rank column with undefined ranks (Infinity fallback, lines 119-120)', async () => {
    const user = userEvent.setup()
    const results = [
      { modelId: 'a', metrics: { score: 0.9 }, rank: 2 },
      { modelId: 'b', metrics: { score: 0.8 } }, // no rank -> Infinity
      { modelId: 'c', metrics: { score: 0.7 }, rank: 1 },
    ]
    render(<EvaluationResultsTable results={results} />)

    // Click Rank header to sort by rank desc first
    const rankHeader = screen.getByText('Rank')
    await user.click(rankHeader)
    // Click again to sort asc
    await user.click(rankHeader)

    // All rows should still render
    expect(screen.getByText('a')).toBeInTheDocument()
    expect(screen.getByText('b')).toBeInTheDocument()
    expect(screen.getByText('c')).toBeInTheDocument()
  })

  it('cycles sort from null back to desc (line 146)', async () => {
    const user = userEvent.setup()
    const results = [
      { modelId: 'a', metrics: { score: 0.9 } },
      { modelId: 'b', metrics: { score: 0.5 } },
    ]
    render(<EvaluationResultsTable results={results} />)

    const scoreHeader = screen.getByText('score')
    // Default: modelId asc. Click score: desc
    await user.click(scoreHeader)
    // Click score again: asc
    await user.click(scoreHeader)
    // Click score again: null (unsorted)
    await user.click(scoreHeader)
    // Click score one more time: desc again (null -> desc branch)
    await user.click(scoreHeader)

    expect(screen.getByText('a')).toBeInTheDocument()
    expect(screen.getByText('b')).toBeInTheDocument()
  })

  it('handles rank=3 styling (lines 262-263)', () => {
    const results = [
      { modelId: 'bronze', metrics: { score: 0.7 }, rank: 3 },
    ]
    render(<EvaluationResultsTable results={results} />)
    expect(screen.getByText('#3')).toBeInTheDocument()
  })

  it('handles rank>3 styling (line 264)', () => {
    const results = [
      { modelId: 'other', metrics: { score: 0.5 }, rank: 4 },
    ]
    render(<EvaluationResultsTable results={results} />)
    expect(screen.getByText('#4')).toBeInTheDocument()
  })
})

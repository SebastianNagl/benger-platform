/**
 * @jest-environment jsdom
 *
 * Branch coverage tests for FieldPairSelector.
 * Targets 5 uncovered branches:
 * - empty fieldPairs returns null
 * - deselect when only 1 selected (blocked)
 * - display text for 1 selected pair with missing label
 * - ungrouped pairs (neither model nor human)
 * - resultCount display and hasResults=false indicator
 */

import '@testing-library/jest-dom'
import { render, screen, fireEvent } from '@testing-library/react'
import { FieldPairSelector, extractFieldPairsFromConfig, FieldPair } from '../FieldPairSelector'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, vars?: Record<string, any>) => {
      const t: Record<string, string> = {
        'evaluation.fieldPair.label': 'Field Pairs',
        'evaluation.fieldPair.selectPlaceholder': 'Select pairs...',
        'evaluation.fieldPair.allPairs': 'All Pairs',
        'evaluation.fieldPair.nSelected': `${vars?.n || 0} selected`,
        'evaluation.fieldPair.selectAll': 'Select All',
        'evaluation.fieldPair.clear': 'Clear',
        'evaluation.fieldPair.modelResponses': 'Model Responses',
        'evaluation.fieldPair.humanAnnotations': 'Human Annotations',
        'evaluation.fieldPair.selectedCount': `${vars?.selected || 0}/${vars?.total || 0}`,
        'evaluation.fieldPair.resultCount': `${vars?.count || 0} results`,
        'evaluation.fieldPair.noResults': 'No results',
      }
      return t[key] || key
    },
  }),
}))

jest.mock('@heroicons/react/24/outline', () => ({
  ArrowRightIcon: (props: any) => <svg {...props} data-testid="arrow-right" />,
  CheckIcon: (props: any) => <svg {...props} data-testid="check-icon" />,
  ChevronDownIcon: (props: any) => <svg {...props} data-testid="chevron-icon" />,
}))

const modelPairs: FieldPair[] = [
  { id: 'gen_a->ref', predictionField: 'generation_a', referenceField: 'reference', displayLabel: 'gen_a -> ref', source: 'model', resultCount: 10 },
  { id: 'gen_b->ref', predictionField: 'generation_b', referenceField: 'reference', displayLabel: 'gen_b -> ref', source: 'model', hasResults: false },
]

const humanPairs: FieldPair[] = [
  { id: 'ann->ref', predictionField: 'annotation', referenceField: 'reference', displayLabel: 'ann -> ref', source: 'human' },
]

describe('FieldPairSelector', () => {
  it('returns null when fieldPairs is empty', () => {
    const { container } = render(
      <FieldPairSelector fieldPairs={[]} selectedPairs={[]} onChange={jest.fn()} />
    )
    expect(container.innerHTML).toBe('')
  })

  it('shows "All Pairs" when all are selected', () => {
    render(
      <FieldPairSelector
        fieldPairs={modelPairs}
        selectedPairs={['gen_a->ref', 'gen_b->ref']}
        onChange={jest.fn()}
      />
    )
    expect(screen.getByText('All Pairs')).toBeInTheDocument()
  })

  it('shows display label when only 1 pair selected', () => {
    render(
      <FieldPairSelector
        fieldPairs={modelPairs}
        selectedPairs={['gen_a->ref']}
        onChange={jest.fn()}
      />
    )
    expect(screen.getByText('gen_a -> ref')).toBeInTheDocument()
  })

  it('shows count when multiple (but not all) selected', () => {
    const allPairs = [...modelPairs, ...humanPairs]
    render(
      <FieldPairSelector
        fieldPairs={allPairs}
        selectedPairs={['gen_a->ref', 'ann->ref']}
        onChange={jest.fn()}
      />
    )
    expect(screen.getByText('2 selected')).toBeInTheDocument()
  })

  it('opens dropdown and shows grouped pairs', () => {
    const allPairs = [...modelPairs, ...humanPairs]
    render(
      <FieldPairSelector
        fieldPairs={allPairs}
        selectedPairs={['gen_a->ref']}
        onChange={jest.fn()}
      />
    )
    fireEvent.click(screen.getByText('gen_a -> ref'))
    expect(screen.getByText('Model Responses')).toBeInTheDocument()
    expect(screen.getByText('Human Annotations')).toBeInTheDocument()
  })

  it('toggles pair selection', () => {
    const onChange = jest.fn()
    render(
      <FieldPairSelector
        fieldPairs={modelPairs}
        selectedPairs={['gen_a->ref']}
        onChange={onChange}
      />
    )
    fireEvent.click(screen.getByText('gen_a -> ref'))
    // Select gen_b
    fireEvent.click(screen.getByText('generation_b'))
    expect(onChange).toHaveBeenCalledWith(['gen_a->ref', 'gen_b->ref'])
  })

  it('prevents deselecting the last selected pair', () => {
    const onChange = jest.fn()
    render(
      <FieldPairSelector
        fieldPairs={modelPairs}
        selectedPairs={['gen_a->ref']}
        onChange={onChange}
      />
    )
    fireEvent.click(screen.getByText('gen_a -> ref'))
    // Try to deselect the only selected pair
    fireEvent.click(screen.getByText('generation_a'))
    expect(onChange).not.toHaveBeenCalled()
  })

  it('select all button selects all pairs', () => {
    const onChange = jest.fn()
    render(
      <FieldPairSelector
        fieldPairs={modelPairs}
        selectedPairs={['gen_a->ref']}
        onChange={onChange}
      />
    )
    fireEvent.click(screen.getByText('gen_a -> ref'))
    fireEvent.click(screen.getByText('Select All'))
    expect(onChange).toHaveBeenCalledWith(['gen_a->ref', 'gen_b->ref'])
  })

  it('clear button keeps first pair selected', () => {
    const onChange = jest.fn()
    render(
      <FieldPairSelector
        fieldPairs={modelPairs}
        selectedPairs={['gen_a->ref', 'gen_b->ref']}
        onChange={onChange}
      />
    )
    fireEvent.click(screen.getByText('All Pairs'))
    fireEvent.click(screen.getByText('Clear'))
    expect(onChange).toHaveBeenCalledWith(['gen_a->ref'])
  })

  it('shows "No results" for pair with hasResults=false', () => {
    render(
      <FieldPairSelector
        fieldPairs={modelPairs}
        selectedPairs={['gen_a->ref']}
        onChange={jest.fn()}
      />
    )
    fireEvent.click(screen.getByText('gen_a -> ref'))
    expect(screen.getByText('No results')).toBeInTheDocument()
  })

  it('shows result count when provided', () => {
    render(
      <FieldPairSelector
        fieldPairs={modelPairs}
        selectedPairs={['gen_a->ref']}
        onChange={jest.fn()}
      />
    )
    fireEvent.click(screen.getByText('gen_a -> ref'))
    expect(screen.getByText('10 results')).toBeInTheDocument()
  })

  it('disabled prop prevents opening dropdown', () => {
    render(
      <FieldPairSelector
        fieldPairs={modelPairs}
        selectedPairs={['gen_a->ref']}
        onChange={jest.fn()}
        disabled={true}
      />
    )
    fireEvent.click(screen.getByText('gen_a -> ref'))
    expect(screen.queryByText('Select All')).not.toBeInTheDocument()
  })
})

describe('extractFieldPairsFromConfig', () => {
  it('extracts pairs from evaluation configs', () => {
    const configs = [
      { id: '1', prediction_fields: ['generation_a'], reference_fields: ['reference'] },
    ]
    const pairs = extractFieldPairsFromConfig(configs)
    expect(pairs).toHaveLength(1)
    expect(pairs[0].source).toBe('model')
  })

  it('deduplicates pairs', () => {
    const configs = [
      { id: '1', prediction_fields: ['annotation'], reference_fields: ['reference'] },
      { id: '2', prediction_fields: ['annotation'], reference_fields: ['reference'] },
    ]
    const pairs = extractFieldPairsFromConfig(configs)
    expect(pairs).toHaveLength(1)
  })

  it('includes results info when provided', () => {
    const configs = [
      { id: '1', prediction_fields: ['gen'], reference_fields: ['ref'] },
    ]
    const resultsMap = { 'gen→ref': { hasResults: true, resultCount: 42 } }
    const pairs = extractFieldPairsFromConfig(configs, resultsMap)
    expect(pairs[0].resultCount).toBe(42)
  })
})

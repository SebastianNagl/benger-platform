/**
 * @jest-environment jsdom
 */
import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import {
  FieldPairSelector,
  extractFieldPairsFromConfig,
} from '../FieldPairSelector'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, params?: Record<string, any>) => {
      const translations: Record<string, string> = {
        'evaluation.fieldPair.label': 'Field Pairs',
        'evaluation.fieldPair.selectPlaceholder': 'Select field pairs...',
        'evaluation.fieldPair.allPairs': 'All Pairs',
        'evaluation.fieldPair.nSelected': `${params?.n} pairs selected`,
        'evaluation.fieldPair.selectAll': 'Select All',
        'evaluation.fieldPair.clear': 'Clear',
        'evaluation.fieldPair.modelResponses': 'Model Responses',
        'evaluation.fieldPair.humanAnnotations': 'Human Annotations',
        'evaluation.fieldPair.selectedCount': `${params?.selected} of ${params?.total} selected`,
        'evaluation.fieldPair.resultCount': `${params?.count} results`,
        'evaluation.fieldPair.noResults': 'No results',
      }
      return translations[key] || key
    },
  }),
}))

const sampleFieldPairs = [
  {
    id: 'generation_answer->answer',
    predictionField: 'generation_answer',
    referenceField: 'answer',
    displayLabel: 'generation_answer -> answer',
    source: 'model' as const,
    hasResults: true,
    resultCount: 50,
  },
  {
    id: 'human_answer->answer',
    predictionField: 'human_answer',
    referenceField: 'answer',
    displayLabel: 'human_answer -> answer',
    source: 'human' as const,
    hasResults: true,
    resultCount: 30,
  },
]

describe('FieldPairSelector', () => {
  const defaultProps = {
    fieldPairs: sampleFieldPairs,
    selectedPairs: ['generation_answer->answer'],
    onChange: jest.fn(),
  }

  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('Empty state', () => {
    it('returns null when no field pairs provided', () => {
      const { container } = render(
        <FieldPairSelector
          fieldPairs={[]}
          selectedPairs={[]}
          onChange={jest.fn()}
        />
      )
      expect(container.firstChild).toBeNull()
    })
  })

  describe('Closed state', () => {
    it('shows the label', () => {
      render(<FieldPairSelector {...defaultProps} />)
      expect(screen.getByText('Field Pairs')).toBeInTheDocument()
    })

    it('shows single pair display label when one pair selected', () => {
      render(<FieldPairSelector {...defaultProps} />)
      expect(
        screen.getByText('generation_answer -> answer')
      ).toBeInTheDocument()
    })

    it('shows All Pairs when all are selected', () => {
      render(
        <FieldPairSelector
          {...defaultProps}
          selectedPairs={[
            'generation_answer->answer',
            'human_answer->answer',
          ]}
        />
      )
      expect(screen.getByText('All Pairs')).toBeInTheDocument()
    })

    it('shows count when multiple pairs selected', () => {
      render(
        <FieldPairSelector
          {...defaultProps}
          fieldPairs={[
            ...sampleFieldPairs,
            {
              id: 'extra->ref',
              predictionField: 'extra',
              referenceField: 'ref',
              displayLabel: 'extra -> ref',
              source: 'model' as const,
            },
          ]}
          selectedPairs={['generation_answer->answer', 'human_answer->answer']}
        />
      )
      expect(screen.getByText('2 pairs selected')).toBeInTheDocument()
    })

    it('shows placeholder when no pairs selected', () => {
      render(
        <FieldPairSelector {...defaultProps} selectedPairs={[]} />
      )
      expect(screen.getByText('Select field pairs...')).toBeInTheDocument()
    })
  })

  describe('Dropdown open', () => {
    it('shows grouped sections: model and human', async () => {
      const user = userEvent.setup()
      render(<FieldPairSelector {...defaultProps} />)

      await user.click(
        screen.getByText('generation_answer -> answer')
      )

      expect(screen.getByText('Model Responses')).toBeInTheDocument()
      expect(screen.getByText('Human Annotations')).toBeInTheDocument()
    })

    it('shows field pair options with arrows', async () => {
      const user = userEvent.setup()
      render(<FieldPairSelector {...defaultProps} />)

      await user.click(
        screen.getByText('generation_answer -> answer')
      )

      expect(screen.getByText('generation_answer')).toBeInTheDocument()
      expect(screen.getByText('human_answer')).toBeInTheDocument()
    })

    it('shows result count for pairs', async () => {
      const user = userEvent.setup()
      render(<FieldPairSelector {...defaultProps} />)

      await user.click(
        screen.getByText('generation_answer -> answer')
      )

      expect(screen.getByText('50 results')).toBeInTheDocument()
      expect(screen.getByText('30 results')).toBeInTheDocument()
    })

    it('shows selected count footer', async () => {
      const user = userEvent.setup()
      render(<FieldPairSelector {...defaultProps} />)

      await user.click(
        screen.getByText('generation_answer -> answer')
      )

      expect(screen.getByText('1 of 2 selected')).toBeInTheDocument()
    })
  })

  describe('Toggling pairs', () => {
    it('adds a pair when selected', async () => {
      const user = userEvent.setup()
      const onChange = jest.fn()
      render(
        <FieldPairSelector
          {...defaultProps}
          onChange={onChange}
        />
      )

      await user.click(
        screen.getByText('generation_answer -> answer')
      )
      await user.click(screen.getByText('human_answer'))

      expect(onChange).toHaveBeenCalledWith([
        'generation_answer->answer',
        'human_answer->answer',
      ])
    })

    it('removes a pair when deselected (if more than one)', async () => {
      const user = userEvent.setup()
      const onChange = jest.fn()
      render(
        <FieldPairSelector
          {...defaultProps}
          selectedPairs={[
            'generation_answer->answer',
            'human_answer->answer',
          ]}
          onChange={onChange}
        />
      )

      await user.click(screen.getByText('All Pairs'))
      await user.click(screen.getByText('generation_answer'))

      expect(onChange).toHaveBeenCalledWith(['human_answer->answer'])
    })

    it('does not allow deselecting the last pair', async () => {
      const user = userEvent.setup()
      const onChange = jest.fn()
      render(
        <FieldPairSelector
          {...defaultProps}
          selectedPairs={['generation_answer->answer']}
          onChange={onChange}
        />
      )

      await user.click(
        screen.getByText('generation_answer -> answer')
      )
      await user.click(screen.getByText('generation_answer'))

      // onChange should not be called since it's the last selected pair
      expect(onChange).not.toHaveBeenCalled()
    })
  })

  describe('Bulk actions', () => {
    it('selects all pairs', async () => {
      const user = userEvent.setup()
      const onChange = jest.fn()
      render(
        <FieldPairSelector {...defaultProps} onChange={onChange} />
      )

      await user.click(
        screen.getByText('generation_answer -> answer')
      )
      await user.click(screen.getByText('Select All'))

      expect(onChange).toHaveBeenCalledWith([
        'generation_answer->answer',
        'human_answer->answer',
      ])
    })

    it('clears to first pair only', async () => {
      const user = userEvent.setup()
      const onChange = jest.fn()
      render(
        <FieldPairSelector
          {...defaultProps}
          selectedPairs={[
            'generation_answer->answer',
            'human_answer->answer',
          ]}
          onChange={onChange}
        />
      )

      await user.click(screen.getByText('All Pairs'))
      await user.click(screen.getByText('Clear'))

      expect(onChange).toHaveBeenCalledWith(['generation_answer->answer'])
    })
  })

  describe('Disabled state', () => {
    it('does not open dropdown when disabled', async () => {
      const user = userEvent.setup()
      render(<FieldPairSelector {...defaultProps} disabled />)

      await user.click(
        screen.getByText('generation_answer -> answer')
      )

      expect(screen.queryByText('Model Responses')).not.toBeInTheDocument()
    })
  })

  describe('No results indicator', () => {
    it('shows no results label for pairs without results', async () => {
      const user = userEvent.setup()
      const pairsWithNoResults = [
        {
          ...sampleFieldPairs[0],
          hasResults: false,
        },
      ]
      render(
        <FieldPairSelector
          fieldPairs={pairsWithNoResults}
          selectedPairs={[pairsWithNoResults[0].id]}
          onChange={jest.fn()}
        />
      )

      // Click the dropdown trigger button (the button element containing the display text)
      const trigger = screen.getByRole('button')
      await user.click(trigger)

      expect(screen.getByText('No results')).toBeInTheDocument()
    })
  })
})

describe('extractFieldPairsFromConfig', () => {
  it('extracts field pairs from evaluation configs', () => {
    const configs = [
      {
        id: 'config-1',
        prediction_fields: ['generation_answer'],
        reference_fields: ['answer'],
      },
    ]
    const pairs = extractFieldPairsFromConfig(configs)

    expect(pairs).toHaveLength(1)
    expect(pairs[0].predictionField).toBe('generation_answer')
    expect(pairs[0].referenceField).toBe('answer')
    expect(pairs[0].source).toBe('model')
  })

  it('creates N x M pairs from multiple fields', () => {
    const configs = [
      {
        id: 'config-1',
        prediction_fields: ['gen_a', 'gen_b'],
        reference_fields: ['ref_a', 'ref_b'],
      },
    ]
    const pairs = extractFieldPairsFromConfig(configs)
    expect(pairs).toHaveLength(4)
  })

  it('deduplicates pairs across configs', () => {
    const configs = [
      {
        id: 'config-1',
        prediction_fields: ['gen'],
        reference_fields: ['ref'],
      },
      {
        id: 'config-2',
        prediction_fields: ['gen'],
        reference_fields: ['ref'],
      },
    ]
    const pairs = extractFieldPairsFromConfig(configs)
    expect(pairs).toHaveLength(1)
  })

  it('detects model source from generation_ prefix', () => {
    const configs = [
      {
        id: 'config-1',
        prediction_fields: ['generation_answer'],
        reference_fields: ['answer'],
      },
    ]
    const pairs = extractFieldPairsFromConfig(configs)
    expect(pairs[0].source).toBe('model')
  })

  it('detects human source for non-model fields', () => {
    const configs = [
      {
        id: 'config-1',
        prediction_fields: ['human:answer'],
        reference_fields: ['answer'],
      },
    ]
    const pairs = extractFieldPairsFromConfig(configs)
    expect(pairs[0].source).toBe('human')
  })

  it('replaces __all_model__ with display name', () => {
    const configs = [
      {
        id: 'config-1',
        prediction_fields: ['__all_model__'],
        reference_fields: ['answer'],
      },
    ]
    const pairs = extractFieldPairsFromConfig(configs)
    expect(pairs[0].predictionField).toBe('All Models')
  })

  it('includes result count from resultsMap', () => {
    const configs = [
      {
        id: 'config-1',
        prediction_fields: ['gen'],
        reference_fields: ['ref'],
      },
    ]
    const resultsMap = {
      'gen\u2192ref': { hasResults: true, resultCount: 42 },
    }
    const pairs = extractFieldPairsFromConfig(configs, resultsMap)
    expect(pairs[0].resultCount).toBe(42)
  })
})

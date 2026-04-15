/**
 * @jest-environment jsdom
 */
import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AggregationSelector } from '../AggregationSelector'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, params?: Record<string, any>) => {
      const translations: Record<string, string> = {
        'evaluation.aggregation.perSample': 'Per Sample',
        'evaluation.aggregation.perSampleDescription':
          'Individual prediction vs ground truth',
        'evaluation.aggregation.perModel': 'Per Model',
        'evaluation.aggregation.perModelDescription':
          'Aggregate scores per model',
        'evaluation.aggregation.perField': 'Per Field',
        'evaluation.aggregation.perFieldDescription':
          'Breakdown by evaluated field',
        'evaluation.aggregation.overall': 'Overall',
        'evaluation.aggregation.overallDescription':
          'Single aggregate across everything',
        'evaluation.aggregation.selectPlaceholder': 'Select aggregation...',
        'evaluation.aggregation.allSelected': 'All Levels',
        'evaluation.aggregation.selectAll': 'Select All',
        'evaluation.aggregation.reset': 'Reset',
        'evaluation.aggregation.selectedCount': `${params?.selected} of ${params?.total} selected`,
      }
      return translations[key] || key
    },
  }),
}))

jest.mock('@/components/shared/Button', () => ({
  Button: ({ children, onClick, className }: any) => (
    <button onClick={onClick} className={className}>
      {children}
    </button>
  ),
}))

describe('AggregationSelector', () => {
  const defaultProps = {
    levels: ['model'] as ('sample' | 'model' | 'field' | 'overall')[],
    onChange: jest.fn(),
  }

  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('Closed state', () => {
    it('shows selected level label', () => {
      render(<AggregationSelector {...defaultProps} />)
      expect(screen.getByText('Per Model')).toBeInTheDocument()
    })

    it('shows All Levels when all selected', () => {
      render(
        <AggregationSelector
          {...defaultProps}
          levels={['sample', 'model', 'field', 'overall']}
        />
      )
      expect(screen.getByText('All Levels')).toBeInTheDocument()
    })

    it('shows multiple labels comma-separated', () => {
      render(
        <AggregationSelector
          {...defaultProps}
          levels={['model', 'field']}
        />
      )
      expect(screen.getByText('Per Model, Per Field')).toBeInTheDocument()
    })

    it('shows placeholder when levels is empty', () => {
      render(
        <AggregationSelector {...defaultProps} levels={[]} />
      )
      expect(screen.getByText('Select aggregation...')).toBeInTheDocument()
    })
  })

  describe('Dropdown open', () => {
    it('shows all aggregation options', async () => {
      const user = userEvent.setup()
      render(<AggregationSelector {...defaultProps} />)

      await user.click(screen.getByText('Per Model'))

      expect(screen.getByText('Per Sample')).toBeInTheDocument()
      expect(screen.getByText('Per Field')).toBeInTheDocument()
      expect(screen.getByText('Overall')).toBeInTheDocument()
    })

    it('shows descriptions for each option', async () => {
      const user = userEvent.setup()
      render(<AggregationSelector {...defaultProps} />)

      await user.click(screen.getByText('Per Model'))

      expect(
        screen.getByText('Aggregate scores per model')
      ).toBeInTheDocument()
      expect(
        screen.getByText('Individual prediction vs ground truth')
      ).toBeInTheDocument()
    })

    it('shows selected count footer', async () => {
      const user = userEvent.setup()
      render(<AggregationSelector {...defaultProps} />)

      await user.click(screen.getByText('Per Model'))

      expect(screen.getByText('1 of 4 selected')).toBeInTheDocument()
    })
  })

  describe('Level toggling', () => {
    it('adds a level when toggled', async () => {
      const user = userEvent.setup()
      const onChange = jest.fn()
      render(
        <AggregationSelector levels={['model']} onChange={onChange} />
      )

      await user.click(screen.getByText('Per Model'))
      // Click "Per Sample" option in dropdown
      await user.click(screen.getByText('Per Sample'))

      expect(onChange).toHaveBeenCalledWith(['model', 'sample'])
    })

    it('removes a level when already selected (if more than one)', async () => {
      const user = userEvent.setup()
      const onChange = jest.fn()
      render(
        <AggregationSelector
          levels={['model', 'field']}
          onChange={onChange}
        />
      )

      await user.click(screen.getByText('Per Model, Per Field'))
      // Click "Per Model" to deselect it (there are two items labeled "Per Model" - the trigger and the option)
      const options = screen.getAllByText('Per Model')
      const dropdownOption = options[options.length - 1]
      await user.click(dropdownOption)

      expect(onChange).toHaveBeenCalledWith(['field'])
    })

    it('does not allow deselecting the last level', async () => {
      const user = userEvent.setup()
      const onChange = jest.fn()
      render(
        <AggregationSelector levels={['model']} onChange={onChange} />
      )

      await user.click(screen.getByText('Per Model'))
      // Try to deselect the only selected level
      const options = screen.getAllByText('Per Model')
      await user.click(options[options.length - 1])

      // onChange should NOT be called because we can't deselect the last one
      expect(onChange).not.toHaveBeenCalled()
    })
  })

  describe('Bulk actions', () => {
    it('selects all levels', async () => {
      const user = userEvent.setup()
      const onChange = jest.fn()
      render(
        <AggregationSelector levels={['model']} onChange={onChange} />
      )

      await user.click(screen.getByText('Per Model'))
      await user.click(screen.getByText('Select All'))

      expect(onChange).toHaveBeenCalledWith([
        'sample',
        'model',
        'field',
        'overall',
      ])
    })

    it('resets to model only', async () => {
      const user = userEvent.setup()
      const onChange = jest.fn()
      render(
        <AggregationSelector
          levels={['sample', 'model', 'field']}
          onChange={onChange}
        />
      )

      await user.click(screen.getByText(/Per Sample/))
      await user.click(screen.getByText('Reset'))

      expect(onChange).toHaveBeenCalledWith(['model'])
    })
  })

  describe('Available levels filter', () => {
    it('only shows available levels', async () => {
      const user = userEvent.setup()
      render(
        <AggregationSelector
          {...defaultProps}
          availableLevels={['model', 'overall']}
        />
      )

      await user.click(screen.getByText('Per Model'))

      expect(screen.getByText('Overall')).toBeInTheDocument()
      expect(screen.queryByText('Per Sample')).not.toBeInTheDocument()
      expect(screen.queryByText('Per Field')).not.toBeInTheDocument()
    })
  })

  describe('Close behavior', () => {
    it('closes dropdown on outside click', async () => {
      const user = userEvent.setup()
      render(
        <div>
          <AggregationSelector {...defaultProps} />
          <div data-testid="outside">Outside</div>
        </div>
      )

      await user.click(screen.getByText('Per Model'))
      expect(screen.getByText('Per Sample')).toBeInTheDocument()

      await user.click(screen.getByTestId('outside'))
      expect(screen.queryByText('Per Sample')).not.toBeInTheDocument()
    })
  })
})

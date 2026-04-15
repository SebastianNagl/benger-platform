/**
 * @jest-environment jsdom
 */
import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { StatisticsSelector } from '../StatisticsSelector'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, params?: Record<string, any>) => {
      const translations: Record<string, string> = {
        'evaluation.statistics.ci': 'Confidence Intervals (95% CI)',
        'evaluation.statistics.ciShort': 'CI',
        'evaluation.statistics.se': 'Standard Error',
        'evaluation.statistics.seShort': 'SE',
        'evaluation.statistics.std': 'Standard Deviation',
        'evaluation.statistics.stdShort': 'Std',
        'evaluation.statistics.ttest': 'T-test',
        'evaluation.statistics.ttestShort': 't-test',
        'evaluation.statistics.bootstrap': 'Bootstrap Significance',
        'evaluation.statistics.bootstrapShort': 'Bootstrap',
        'evaluation.statistics.cohensD': "Cohen's d",
        'evaluation.statistics.cohensDShort': "d",
        'evaluation.statistics.cliffsDelta': "Cliff's delta",
        'evaluation.statistics.cliffsDeltaShort': "delta",
        'evaluation.statistics.correlation': 'Correlation',
        'evaluation.statistics.correlationShort': 'Corr',
        'evaluation.statistics.selectPlaceholder': 'Select statistics...',
        'evaluation.statistics.allMethods': 'All Methods',
        'evaluation.statistics.nSelected': `${params?.n} selected`,
        'evaluation.statistics.selectAll': 'Select All',
        'evaluation.statistics.clearAll': 'Clear All',
        'evaluation.statistics.selectedCount': `${params?.selected} of ${params?.total} selected`,
        'evaluation.statistics.categoryBasic': 'Basic',
        'evaluation.statistics.categorySignificance': 'Significance',
        'evaluation.statistics.categoryEffectSize': 'Effect Size',
        'evaluation.statistics.categoryRelationship': 'Relationship',
      }
      return translations[key] || key
    },
  }),
}))

jest.mock('@/components/shared/Button', () => ({
  Button: ({ children, onClick, className, variant }: any) => (
    <button onClick={onClick} className={className} data-variant={variant}>
      {children}
    </button>
  ),
}))

describe('StatisticsSelector', () => {
  const defaultProps = {
    selectedMethods: [] as string[],
    onChange: jest.fn(),
  }

  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('Closed state', () => {
    it('shows placeholder when no methods selected', () => {
      render(<StatisticsSelector {...defaultProps} />)
      expect(screen.getByText('Select statistics...')).toBeInTheDocument()
    })

    it('shows All Methods when all are selected', () => {
      render(
        <StatisticsSelector
          {...defaultProps}
          selectedMethods={[
            'ci',
            'se',
            'std',
            'ttest',
            'bootstrap',
            'cohens_d',
            'cliffs_delta',
            'correlation',
          ]}
        />
      )
      expect(screen.getByText('All Methods')).toBeInTheDocument()
    })

    it('shows individual labels when 1-2 methods selected', () => {
      render(
        <StatisticsSelector
          {...defaultProps}
          selectedMethods={['ci', 'se']}
        />
      )
      expect(screen.getByText('CI, SE')).toBeInTheDocument()
    })

    it('shows count when 3+ methods selected', () => {
      render(
        <StatisticsSelector
          {...defaultProps}
          selectedMethods={['ci', 'se', 'std']}
        />
      )
      expect(screen.getByText('3 selected')).toBeInTheDocument()
    })
  })

  describe('Dropdown open', () => {
    it('shows dropdown on click', async () => {
      const user = userEvent.setup()
      render(<StatisticsSelector {...defaultProps} />)

      await user.click(screen.getByText('Select statistics...'))

      expect(screen.getByText('Basic')).toBeInTheDocument()
      expect(screen.getByText('Significance')).toBeInTheDocument()
      expect(screen.getByText('Effect Size')).toBeInTheDocument()
      expect(screen.getByText('Relationship')).toBeInTheDocument()
    })

    it('shows all statistical methods', async () => {
      const user = userEvent.setup()
      render(<StatisticsSelector {...defaultProps} />)

      await user.click(screen.getByText('Select statistics...'))

      expect(
        screen.getByText('Confidence Intervals (95% CI)')
      ).toBeInTheDocument()
      expect(screen.getByText('Standard Error')).toBeInTheDocument()
      expect(screen.getByText('T-test')).toBeInTheDocument()
      expect(screen.getByText("Cohen's d")).toBeInTheDocument()
      expect(screen.getByText('Correlation')).toBeInTheDocument()
    })

    it('shows selected count in footer', async () => {
      const user = userEvent.setup()
      render(
        <StatisticsSelector
          {...defaultProps}
          selectedMethods={['ci', 'se']}
        />
      )

      await user.click(screen.getByText('CI, SE'))

      expect(screen.getByText('2 of 8 selected')).toBeInTheDocument()
    })
  })

  describe('Method toggling', () => {
    it('calls onChange to add a method when clicked', async () => {
      const user = userEvent.setup()
      const onChange = jest.fn()
      render(
        <StatisticsSelector
          selectedMethods={[]}
          onChange={onChange}
        />
      )

      await user.click(screen.getByText('Select statistics...'))
      await user.click(screen.getByText('Confidence Intervals (95% CI)'))

      expect(onChange).toHaveBeenCalledWith(['ci'])
    })

    it('calls onChange to remove a method when already selected', async () => {
      const user = userEvent.setup()
      const onChange = jest.fn()
      render(
        <StatisticsSelector
          selectedMethods={['ci', 'se']}
          onChange={onChange}
        />
      )

      await user.click(screen.getByText('CI, SE'))
      await user.click(screen.getByText('Confidence Intervals (95% CI)'))

      expect(onChange).toHaveBeenCalledWith(['se'])
    })
  })

  describe('Bulk actions', () => {
    it('selects all methods', async () => {
      const user = userEvent.setup()
      const onChange = jest.fn()
      render(
        <StatisticsSelector selectedMethods={[]} onChange={onChange} />
      )

      await user.click(screen.getByText('Select statistics...'))
      await user.click(screen.getByText('Select All'))

      expect(onChange).toHaveBeenCalledWith([
        'ci',
        'se',
        'std',
        'ttest',
        'bootstrap',
        'cohens_d',
        'cliffs_delta',
        'correlation',
      ])
    })

    it('clears all methods', async () => {
      const user = userEvent.setup()
      const onChange = jest.fn()
      render(
        <StatisticsSelector
          selectedMethods={['ci', 'se']}
          onChange={onChange}
        />
      )

      await user.click(screen.getByText('CI, SE'))
      await user.click(screen.getByText('Clear All'))

      expect(onChange).toHaveBeenCalledWith([])
    })
  })

  describe('Close behavior', () => {
    it('closes dropdown when clicking outside', async () => {
      const user = userEvent.setup()
      render(
        <div>
          <StatisticsSelector {...defaultProps} />
          <div data-testid="outside">Outside</div>
        </div>
      )

      await user.click(screen.getByText('Select statistics...'))
      expect(screen.getByText('Basic')).toBeInTheDocument()

      await user.click(screen.getByTestId('outside'))
      expect(screen.queryByText('Basic')).not.toBeInTheDocument()
    })
  })
})

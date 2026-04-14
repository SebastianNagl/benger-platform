/**
 * @jest-environment jsdom
 */
import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ScoreCard, formatAcademicScore } from '../ScoreCard'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, params?: Record<string, any>) => {
      const translations: Record<string, string> = {
        'evaluation.scoreCard.infoAbout': `Info about ${params?.metric}`,
        'evaluation.scoreCard.sampleSize': `n = ${params?.n}`,
        'evaluation.scoreCard.clusters': `${params?.count} clusters`,
        'evaluation.scoreCard.ciLabel': `${params?.level}% CI`,
        'evaluation.scoreCard.ciShort': 'CI',
      }
      return translations[key] || key
    },
  }),
}))

describe('ScoreCard', () => {
  const defaultProps = {
    metric: 'Accuracy',
    value: 0.85,
  }

  describe('Basic rendering', () => {
    it('renders metric name', () => {
      render(<ScoreCard {...defaultProps} />)
      expect(screen.getByText('Accuracy')).toBeInTheDocument()
    })

    it('renders value in decimal format by default (3 decimal places)', () => {
      render(<ScoreCard {...defaultProps} />)
      expect(screen.getByText('0.850')).toBeInTheDocument()
    })

    it('renders value as percentage when formatAs=percentage', () => {
      render(<ScoreCard {...defaultProps} formatAs="percentage" />)
      expect(screen.getByText('85.0%')).toBeInTheDocument()
    })

    it('renders value as raw when formatAs=raw', () => {
      render(<ScoreCard {...defaultProps} formatAs="raw" />)
      expect(screen.getByText('0.85')).toBeInTheDocument()
    })
  })

  describe('Color coding', () => {
    it('applies green color for high score (>=0.7)', () => {
      const { container } = render(<ScoreCard metric="test" value={0.85} />)
      const card = container.firstChild as HTMLElement
      expect(card).toHaveClass('bg-green-50')
      expect(card).toHaveClass('border-green-200')
    })

    it('applies yellow color for medium score (0.5-0.7)', () => {
      const { container } = render(<ScoreCard metric="test" value={0.6} />)
      const card = container.firstChild as HTMLElement
      expect(card).toHaveClass('bg-yellow-50')
      expect(card).toHaveClass('border-yellow-200')
    })

    it('applies red color for low score (<0.5)', () => {
      const { container } = render(<ScoreCard metric="test" value={0.3} />)
      const card = container.firstChild as HTMLElement
      expect(card).toHaveClass('bg-red-50')
      expect(card).toHaveClass('border-red-200')
    })

    it('inverts colors when higherIsBetter is false', () => {
      // Value 0.2 with higherIsBetter=false -> inverted score = 0.8 -> green
      const { container } = render(
        <ScoreCard metric="error" value={0.2} higherIsBetter={false} />
      )
      const card = container.firstChild as HTMLElement
      expect(card).toHaveClass('bg-green-50')
    })

    it('normalizes to custom value range', () => {
      // value=80, range 0-100, normalized to 0.8 -> green
      const { container } = render(
        <ScoreCard
          metric="test"
          value={80}
          valueRange={{ min: 0, max: 100 }}
          formatAs="raw"
        />
      )
      const card = container.firstChild as HTMLElement
      expect(card).toHaveClass('bg-green-50')
    })
  })

  describe('Sample size display', () => {
    it('shows sample size when provided', () => {
      render(<ScoreCard {...defaultProps} sampleSize={1500} />)
      // toLocaleString formatting may vary by environment
      expect(screen.getByText(/n = 1.?500/)).toBeInTheDocument()
    })

    it('does not show sample size when not provided', () => {
      render(<ScoreCard {...defaultProps} />)
      expect(screen.queryByText(/n =/)).not.toBeInTheDocument()
    })

    it('shows cluster count when provided', () => {
      render(
        <ScoreCard {...defaultProps} sampleSize={100} clusterCount={50} />
      )
      expect(screen.getByText(/50 clusters/)).toBeInTheDocument()
    })
  })

  describe('Confidence interval', () => {
    it('shows confidence interval text when provided', () => {
      render(
        <ScoreCard
          {...defaultProps}
          confidenceInterval={{ lower: 0.8, upper: 0.9, level: 95 }}
        />
      )
      expect(screen.getByText(/95% CI/)).toBeInTheDocument()
      expect(screen.getByText(/0.800/)).toBeInTheDocument()
      expect(screen.getByText(/0.900/)).toBeInTheDocument()
    })

    it('shows compact CI display when compact=true', () => {
      render(
        <ScoreCard
          {...defaultProps}
          compact
          confidenceInterval={{ lower: 0.8, upper: 0.9 }}
        />
      )
      expect(screen.getByText(/CI/)).toBeInTheDocument()
    })

    it('does not show CI visualization bar when compact=true', () => {
      const { container } = render(
        <ScoreCard
          {...defaultProps}
          compact
          confidenceInterval={{ lower: 0.8, upper: 0.9 }}
        />
      )
      // In compact mode, no relative-positioned CI bar container
      const ciBarContainer = container.querySelector('.relative.h-2')
      expect(ciBarContainer).not.toBeInTheDocument()
    })

    it('defaults to 95% CI level when level is not specified', () => {
      render(
        <ScoreCard
          {...defaultProps}
          confidenceInterval={{ lower: 0.8, upper: 0.9 }}
        />
      )
      expect(screen.getByText(/95% CI/)).toBeInTheDocument()
    })
  })

  describe('Tooltip', () => {
    it('shows info icon when description is provided', () => {
      render(
        <ScoreCard {...defaultProps} description="A test metric description" />
      )
      expect(
        screen.getByLabelText('Info about Accuracy')
      ).toBeInTheDocument()
    })

    it('does not show info icon when no description', () => {
      render(<ScoreCard {...defaultProps} />)
      expect(
        screen.queryByLabelText(/Info about/)
      ).not.toBeInTheDocument()
    })

    it('shows tooltip on hover', async () => {
      const user = userEvent.setup()
      render(
        <ScoreCard {...defaultProps} description="Detailed metric info" />
      )

      const infoButton = screen.getByLabelText('Info about Accuracy')
      await user.hover(infoButton)

      expect(screen.getByText('Detailed metric info')).toBeInTheDocument()
    })
  })

  describe('Compact mode', () => {
    it('uses smaller text in compact mode', () => {
      const { container } = render(
        <ScoreCard {...defaultProps} compact />
      )
      const valueEl = container.querySelector('.text-2xl')
      expect(valueEl).toBeInTheDocument()
    })

    it('uses larger text in normal mode', () => {
      const { container } = render(
        <ScoreCard {...defaultProps} />
      )
      const valueEl = container.querySelector('.text-3xl')
      expect(valueEl).toBeInTheDocument()
    })
  })

  describe('Custom className', () => {
    it('applies custom className to root element', () => {
      const { container } = render(
        <ScoreCard {...defaultProps} className="my-custom-class" />
      )
      expect(container.firstChild).toHaveClass('my-custom-class')
    })
  })
})

describe('formatAcademicScore', () => {
  it('formats decimal with 3 decimal places by default', () => {
    expect(formatAcademicScore(0.856)).toBe('0.856')
  })

  it('formats as percentage when requested', () => {
    expect(formatAcademicScore(0.856, { asPercentage: true })).toBe('85.6%')
  })

  it('uses custom decimal places', () => {
    expect(formatAcademicScore(0.85678, { decimals: 4 })).toBe('0.8568')
  })

  it('handles zero correctly', () => {
    expect(formatAcademicScore(0)).toBe('0.000')
  })

  it('handles one correctly', () => {
    expect(formatAcademicScore(1)).toBe('1.000')
  })
})

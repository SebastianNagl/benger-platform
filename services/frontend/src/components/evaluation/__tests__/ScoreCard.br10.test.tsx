/**
 * @jest-environment jsdom
 *
 * Branch coverage tests for ScoreCard and helpers.
 * Targets 5 uncovered branches:
 * - default-arg for higherIsBetter, min, max (lines 55-57)
 * - default-arg for format (line 92)
 * - switch case 'raw' (line 94)
 */

import '@testing-library/jest-dom'
import { render, screen, fireEvent } from '@testing-library/react'
import { ScoreCard, formatAcademicScore } from '../ScoreCard'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, vars?: Record<string, any>) => {
      const translations: Record<string, string> = {
        'evaluation.scoreCard.infoAbout': `Info about ${vars?.metric || ''}`,
        'evaluation.scoreCard.sampleSize': `n = ${vars?.n || ''}`,
        'evaluation.scoreCard.clusters': `${vars?.count || ''} clusters`,
        'evaluation.scoreCard.ciLabel': `${vars?.level || 95}% CI`,
        'evaluation.scoreCard.ciShort': 'CI',
      }
      return translations[key] || key
    },
  }),
}))

jest.mock('@heroicons/react/24/outline', () => ({
  InformationCircleIcon: (props: any) => <svg {...props} data-testid="info-icon" />,
}))

describe('ScoreCard', () => {
  it('renders with default props (higherIsBetter=true, range 0-1, format decimal)', () => {
    render(<ScoreCard metric="F1" value={0.85} />)
    expect(screen.getByText('F1')).toBeInTheDocument()
    expect(screen.getByText('0.850')).toBeInTheDocument()
  })

  it('renders with low score (red color, <0.5)', () => {
    render(<ScoreCard metric="F1" value={0.2} />)
    expect(screen.getByText('0.200')).toBeInTheDocument()
  })

  it('renders with mid score (yellow, 0.5-0.7)', () => {
    render(<ScoreCard metric="F1" value={0.6} />)
    expect(screen.getByText('0.600')).toBeInTheDocument()
  })

  it('renders with formatAs="percentage"', () => {
    render(<ScoreCard metric="F1" value={0.85} formatAs="percentage" />)
    expect(screen.getByText('85.0%')).toBeInTheDocument()
  })

  it('renders with formatAs="raw"', () => {
    render(<ScoreCard metric="BLEU" value={42.5} formatAs="raw" valueRange={{ min: 0, max: 100 }} />)
    expect(screen.getByText('42.50')).toBeInTheDocument()
  })

  it('renders with higherIsBetter=false', () => {
    render(
      <ScoreCard metric="Loss" value={0.3} higherIsBetter={false} />
    )
    expect(screen.getByText('0.300')).toBeInTheDocument()
  })

  it('renders with custom valueRange', () => {
    render(
      <ScoreCard metric="BLEU" value={25} valueRange={{ min: 0, max: 100 }} formatAs="raw" />
    )
    expect(screen.getByText('25.00')).toBeInTheDocument()
  })

  it('renders confidence interval in non-compact mode', () => {
    render(
      <ScoreCard
        metric="F1"
        value={0.85}
        confidenceInterval={{ lower: 0.80, upper: 0.90, level: 95 }}
      />
    )
    expect(screen.getByText(/95% CI/)).toBeInTheDocument()
  })

  it('renders confidence interval in compact mode', () => {
    render(
      <ScoreCard
        metric="F1"
        value={0.85}
        confidenceInterval={{ lower: 0.80, upper: 0.90 }}
        compact
      />
    )
    expect(screen.getByText(/CI/)).toBeInTheDocument()
  })

  it('shows description tooltip on hover', () => {
    render(
      <ScoreCard metric="F1" value={0.85} description="Harmonic mean of P and R" />
    )
    const button = screen.getByLabelText(/Info about F1/)
    fireEvent.mouseEnter(button)
    expect(screen.getByText('Harmonic mean of P and R')).toBeInTheDocument()
    fireEvent.mouseLeave(button)
  })

  it('renders sample size and cluster count', () => {
    render(
      <ScoreCard metric="F1" value={0.85} sampleSize={1000} clusterCount={5} />
    )
    expect(screen.getByText(/n = /)).toBeInTheDocument()
    expect(screen.getByText(/clusters/)).toBeInTheDocument()
  })
})

describe('formatAcademicScore', () => {
  it('formats as decimal with default 3 decimals', () => {
    expect(formatAcademicScore(0.8567)).toBe('0.857')
  })

  it('formats as percentage', () => {
    expect(formatAcademicScore(0.85, { asPercentage: true })).toBe('85.0%')
  })

  it('formats with custom decimal places', () => {
    expect(formatAcademicScore(0.85, { decimals: 2 })).toBe('0.85')
  })

  it('uses default decimals when not specified', () => {
    expect(formatAcademicScore(0.1234, {})).toBe('0.123')
  })
})

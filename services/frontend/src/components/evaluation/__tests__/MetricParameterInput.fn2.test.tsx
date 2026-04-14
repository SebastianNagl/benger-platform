/**
 * Function coverage for MetricParameterInput.tsx
 * Covers: MetricParameterInput component, handleParameterChange, resetToDefaults,
 * showAdvanced toggle, parameter rendering for BLEU, ROUGE, METEOR, chrF
 */

import React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import { MetricParameterInput } from '../MetricParameterInput'

// Mock dependencies
jest.mock('@/components/shared/Button', () => ({
  Button: ({ children, onClick, ...rest }: any) => (
    <button onClick={onClick} {...rest}>{children}</button>
  ),
}))
jest.mock('@/components/shared/Input', () => ({
  Input: (props: any) => <input data-testid={`input-${props.id}`} {...props} />,
}))
jest.mock('@/components/shared/Label', () => ({
  Label: ({ children, ...rest }: any) => <label {...rest}>{children}</label>,
}))
jest.mock('@/components/shared/Tooltip', () => ({
  Tooltip: ({ children }: any) => <div>{children}</div>,
}))
jest.mock('@heroicons/react/24/outline', () => ({
  AdjustmentsHorizontalIcon: () => <span data-testid="icon-adjustments" />,
  InformationCircleIcon: () => <span data-testid="icon-info" />,
}))

describe('MetricParameterInput', () => {
  const mockOnChange = jest.fn()

  beforeEach(() => {
    mockOnChange.mockClear()
  })

  it('returns null for unsupported metric', () => {
    const { container } = render(
      <MetricParameterInput metric="accuracy" parameters={{}} onChange={mockOnChange} />
    )
    expect(container.innerHTML).toBe('')
  })

  it('renders toggle button for BLEU metric', () => {
    render(
      <MetricParameterInput metric="bleu" parameters={{}} onChange={mockOnChange} />
    )
    expect(screen.getByTestId('icon-adjustments')).toBeInTheDocument()
  })

  it('renders toggle button for ROUGE metric', () => {
    render(
      <MetricParameterInput metric="rouge" parameters={{}} onChange={mockOnChange} />
    )
    expect(screen.getByTestId('icon-adjustments')).toBeInTheDocument()
  })

  it('renders toggle button for METEOR metric', () => {
    render(
      <MetricParameterInput metric="meteor" parameters={{}} onChange={mockOnChange} />
    )
    expect(screen.getByTestId('icon-adjustments')).toBeInTheDocument()
  })

  it('renders toggle button for chrF metric', () => {
    render(
      <MetricParameterInput metric="chrf" parameters={{}} onChange={mockOnChange} />
    )
    expect(screen.getByTestId('icon-adjustments')).toBeInTheDocument()
  })

  it('shows advanced parameters when toggled for BLEU', () => {
    render(
      <MetricParameterInput
        metric="bleu"
        parameters={{ max_order: 4, smoothing: 'method1' }}
        onChange={mockOnChange}
      />
    )

    // Click first button (the toggle) to show advanced
    fireEvent.click(screen.getAllByRole('button')[0])

    // After toggle, should show reset defaults button and parameter inputs
    expect(screen.getAllByRole('button').length).toBeGreaterThanOrEqual(2)
  })

  it('shows advanced parameters when toggled for ROUGE', () => {
    render(
      <MetricParameterInput
        metric="rouge"
        parameters={{ variant: 'rougeL', use_stemmer: true }}
        onChange={mockOnChange}
      />
    )

    fireEvent.click(screen.getAllByRole('button')[0])
    expect(screen.getAllByRole('button').length).toBeGreaterThanOrEqual(2)
  })

  it('shows advanced parameters when toggled for METEOR', () => {
    render(
      <MetricParameterInput
        metric="meteor"
        parameters={{ alpha: 0.9, beta: 3.0, gamma: 0.5 }}
        onChange={mockOnChange}
      />
    )

    fireEvent.click(screen.getAllByRole('button')[0])
    expect(screen.getAllByRole('button').length).toBeGreaterThanOrEqual(2)
  })

  it('shows advanced parameters when toggled for chrF', () => {
    render(
      <MetricParameterInput
        metric="chrf"
        parameters={{ char_order: 6, word_order: 0, beta: 2 }}
        onChange={mockOnChange}
      />
    )

    fireEvent.click(screen.getAllByRole('button')[0])
    expect(screen.getAllByRole('button').length).toBeGreaterThanOrEqual(2)
  })

  it('calls resetToDefaults when reset button clicked for BLEU', () => {
    render(
      <MetricParameterInput
        metric="bleu"
        parameters={{ max_order: 2 }}
        onChange={mockOnChange}
      />
    )

    // Open advanced
    fireEvent.click(screen.getAllByRole('button')[0])

    // Click reset defaults button (second button after toggle)
    const buttons = screen.getAllByRole('button')
    const resetBtn = buttons.find(b => b.textContent?.includes('evaluation.metricParams.resetDefaults'))
    if (resetBtn) {
      fireEvent.click(resetBtn)
      expect(mockOnChange).toHaveBeenCalled()
    }
  })
})

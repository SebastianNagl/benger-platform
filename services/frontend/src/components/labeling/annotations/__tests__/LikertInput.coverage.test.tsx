/**
 * Coverage-focused tests for LikertInput
 *
 * Targets uncovered branches:
 * - No toName (annotation not created)
 * - With toName (annotation created)
 * - hint text rendering
 * - config.name fallback
 * - Custom min/max
 * - required flag
 * - External value initialization
 */

/**
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'
import { fireEvent, render, screen } from '@testing-library/react'
import LikertInput from '../LikertInput'

jest.mock('@/lib/labelConfig/dataBinding', () => ({
  buildAnnotationResult: jest.fn((name, type, value, toName) => ({
    id: `${name}-result`,
    from_name: name,
    to_name: toName,
    type: type.toLowerCase(),
    value: { likert: value },
  })),
}))

// Mock LikertScale to expose the onChange callback
jest.mock('@/components/shared/LikertScale', () => ({
  LikertScale: ({ name, label, value, onChange, required, min, max }: any) => (
    <div data-testid="likert-scale">
      <span data-testid="likert-label">{label}</span>
      <span data-testid="likert-value">{value ?? 'none'}</span>
      <span data-testid="likert-range">{min}-{max}</span>
      {required && <span data-testid="likert-required">required</span>}
      <button data-testid="likert-select-3" onClick={() => onChange(3)}>
        Select 3
      </button>
      <button data-testid="likert-select-5" onClick={() => onChange(5)}>
        Select 5
      </button>
    </div>
  ),
}))

const baseConfig = {
  name: 'likert',
  type: 'Likert',
  props: {
    name: 'myLikert',
    toName: 'text',
    min: '1',
    max: '7',
    required: 'false',
    label: 'Quality',
  },
  children: [],
}

describe('LikertInput - branch coverage', () => {
  const mockOnChange = jest.fn()
  const mockOnAnnotation = jest.fn()

  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('renders with label and range', () => {
    render(
      <LikertInput
        config={baseConfig}
        taskData={{}}
        value={undefined}
        onChange={mockOnChange}
        onAnnotation={mockOnAnnotation}
      />
    )

    expect(screen.getByTestId('likert-label')).toHaveTextContent('Quality')
    expect(screen.getByTestId('likert-range')).toHaveTextContent('1-7')
  })

  it('creates annotation when toName is set', () => {
    render(
      <LikertInput
        config={baseConfig}
        taskData={{}}
        value={undefined}
        onChange={mockOnChange}
        onAnnotation={mockOnAnnotation}
      />
    )

    fireEvent.click(screen.getByTestId('likert-select-3'))

    expect(mockOnChange).toHaveBeenCalledWith(3)
    expect(mockOnAnnotation).toHaveBeenCalled()
  })

  it('does not create annotation when toName is missing', () => {
    const config = {
      ...baseConfig,
      props: { ...baseConfig.props, toName: undefined },
    }

    render(
      <LikertInput
        config={config}
        taskData={{}}
        value={undefined}
        onChange={mockOnChange}
        onAnnotation={mockOnAnnotation}
      />
    )

    fireEvent.click(screen.getByTestId('likert-select-5'))

    expect(mockOnChange).toHaveBeenCalledWith(5)
    expect(mockOnAnnotation).not.toHaveBeenCalled()
  })

  it('shows hint text', () => {
    const config = {
      ...baseConfig,
      props: { ...baseConfig.props, hint: 'Select your agreement level' },
    }

    render(
      <LikertInput
        config={config}
        taskData={{}}
        value={undefined}
        onChange={mockOnChange}
        onAnnotation={mockOnAnnotation}
      />
    )

    expect(screen.getByText('Select your agreement level')).toBeInTheDocument()
  })

  it('does not show hint when not provided', () => {
    render(
      <LikertInput
        config={baseConfig}
        taskData={{}}
        value={undefined}
        onChange={mockOnChange}
        onAnnotation={mockOnAnnotation}
      />
    )

    expect(screen.queryByText('Select your agreement level')).not.toBeInTheDocument()
  })

  it('uses config.name as fallback label', () => {
    const config = {
      ...baseConfig,
      props: { ...baseConfig.props, name: undefined, label: undefined },
    }

    render(
      <LikertInput
        config={config}
        taskData={{}}
        value={undefined}
        onChange={mockOnChange}
        onAnnotation={mockOnAnnotation}
      />
    )

    expect(screen.getByTestId('likert-label')).toHaveTextContent('likert')
  })

  it('passes required flag to LikertScale', () => {
    const config = {
      ...baseConfig,
      props: { ...baseConfig.props, required: 'true' },
    }

    render(
      <LikertInput
        config={config}
        taskData={{}}
        value={undefined}
        onChange={mockOnChange}
        onAnnotation={mockOnAnnotation}
      />
    )

    expect(screen.getByTestId('likert-required')).toBeInTheDocument()
  })

  it('initializes with external value', () => {
    render(
      <LikertInput
        config={baseConfig}
        taskData={{}}
        value={4}
        onChange={mockOnChange}
        onAnnotation={mockOnAnnotation}
      />
    )

    expect(screen.getByTestId('likert-value')).toHaveTextContent('4')
  })

  it('uses custom min/max from config', () => {
    const config = {
      ...baseConfig,
      props: { ...baseConfig.props, min: '0', max: '10' },
    }

    render(
      <LikertInput
        config={config}
        taskData={{}}
        value={undefined}
        onChange={mockOnChange}
        onAnnotation={mockOnAnnotation}
      />
    )

    expect(screen.getByTestId('likert-range')).toHaveTextContent('0-10')
  })
})

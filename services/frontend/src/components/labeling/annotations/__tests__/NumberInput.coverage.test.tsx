/**
 * Coverage-focused tests for NumberInput
 *
 * Targets uncovered branches:
 * - NaN value (non-numeric input - onChange/onAnnotation not called)
 * - No toName (annotation not created)
 * - With toName (annotation created)
 * - hint text rendering
 * - required asterisk
 * - config.name fallback
 * - default name fallback
 * - min/max/step props
 */

/**
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'
import { fireEvent, render, screen } from '@testing-library/react'
import NumberInput from '../NumberInput'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({ t: (key: string) => key }),
}))

jest.mock('@/lib/labelConfig/dataBinding', () => ({
  buildAnnotationResult: jest.fn((name, type, value, toName) => ({
    id: `${name}-result`,
    from_name: name,
    to_name: toName,
    type: type.toLowerCase(),
    value: { number: value },
  })),
}))

const baseConfig = {
  name: 'number',
  type: 'Number',
  props: {
    name: 'myNumber',
    toName: 'text',
    min: '0',
    max: '100',
    step: '1',
    required: 'false',
    placeholder: 'Enter number',
  },
  children: [],
}

describe('NumberInput - branch coverage', () => {
  const mockOnChange = jest.fn()
  const mockOnAnnotation = jest.fn()

  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('calls onChange and onAnnotation with valid numeric input', () => {
    render(
      <NumberInput
        config={baseConfig}
        taskData={{}}
        value=""
        onChange={mockOnChange}
        onAnnotation={mockOnAnnotation}
      />
    )

    const input = screen.getByRole('spinbutton')
    fireEvent.change(input, { target: { value: '42' } })

    expect(mockOnChange).toHaveBeenCalledWith(42)
    expect(mockOnAnnotation).toHaveBeenCalled()
  })

  it('does not call onChange when input is NaN', () => {
    render(
      <NumberInput
        config={baseConfig}
        taskData={{}}
        value=""
        onChange={mockOnChange}
        onAnnotation={mockOnAnnotation}
      />
    )

    const input = screen.getByRole('spinbutton')
    fireEvent.change(input, { target: { value: '' } })

    expect(mockOnChange).not.toHaveBeenCalled()
    expect(mockOnAnnotation).not.toHaveBeenCalled()
  })

  it('does not create annotation when toName is missing', () => {
    const config = {
      ...baseConfig,
      props: { ...baseConfig.props, toName: undefined },
    }

    render(
      <NumberInput
        config={config}
        taskData={{}}
        value=""
        onChange={mockOnChange}
        onAnnotation={mockOnAnnotation}
      />
    )

    const input = screen.getByRole('spinbutton')
    fireEvent.change(input, { target: { value: '5' } })

    expect(mockOnChange).toHaveBeenCalledWith(5)
    expect(mockOnAnnotation).not.toHaveBeenCalled()
  })

  it('shows required asterisk', () => {
    const config = {
      ...baseConfig,
      props: { ...baseConfig.props, required: 'true' },
    }

    render(
      <NumberInput
        config={config}
        taskData={{}}
        value=""
        onChange={mockOnChange}
        onAnnotation={mockOnAnnotation}
      />
    )

    expect(screen.getByText('*')).toBeInTheDocument()
  })

  it('shows hint text', () => {
    const config = {
      ...baseConfig,
      props: { ...baseConfig.props, hint: 'Enter between 0 and 100' },
    }

    render(
      <NumberInput
        config={config}
        taskData={{}}
        value=""
        onChange={mockOnChange}
        onAnnotation={mockOnAnnotation}
      />
    )

    expect(screen.getByText('Enter between 0 and 100')).toBeInTheDocument()
  })

  it('uses label from config.props.label', () => {
    const config = {
      ...baseConfig,
      props: { ...baseConfig.props, label: 'Custom Label' },
    }

    render(
      <NumberInput
        config={config}
        taskData={{}}
        value=""
        onChange={mockOnChange}
        onAnnotation={mockOnAnnotation}
      />
    )

    expect(screen.getByText('Custom Label')).toBeInTheDocument()
  })

  it('uses config.name as fallback label', () => {
    const config = {
      ...baseConfig,
      props: { ...baseConfig.props, name: undefined },
    }

    render(
      <NumberInput
        config={config}
        taskData={{}}
        value=""
        onChange={mockOnChange}
        onAnnotation={mockOnAnnotation}
      />
    )

    expect(screen.getByLabelText('number')).toBeInTheDocument()
  })

  it('uses default "number" name when all names are missing', () => {
    const config = {
      name: undefined as any,
      type: 'Number',
      props: { toName: 'text' },
      children: [],
    }

    render(
      <NumberInput
        config={config}
        taskData={{}}
        value=""
        onChange={mockOnChange}
        onAnnotation={mockOnAnnotation}
      />
    )

    expect(screen.getByLabelText('number')).toBeInTheDocument()
  })

  it('initializes with external value', () => {
    render(
      <NumberInput
        config={baseConfig}
        taskData={{}}
        value={7}
        onChange={mockOnChange}
        onAnnotation={mockOnAnnotation}
      />
    )

    const input = screen.getByRole('spinbutton') as HTMLInputElement
    expect(input.value).toBe('7')
  })

  it('uses default placeholder from i18n when not provided', () => {
    const config = {
      ...baseConfig,
      props: { ...baseConfig.props, placeholder: undefined },
    }

    render(
      <NumberInput
        config={config}
        taskData={{}}
        value=""
        onChange={mockOnChange}
        onAnnotation={mockOnAnnotation}
      />
    )

    // Placeholder is the i18n key
    expect(screen.getByPlaceholderText('annotation.numberPlaceholder')).toBeInTheDocument()
  })
})

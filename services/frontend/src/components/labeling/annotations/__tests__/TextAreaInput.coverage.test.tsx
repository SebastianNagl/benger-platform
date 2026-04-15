/**
 * Coverage-focused tests for TextAreaInput
 *
 * Targets uncovered branches:
 * - hideSubmitButton=true hides submit button
 * - showSubmitButton='false' config hides submit button
 * - handleSubmit with empty value and required=true (early return)
 * - handleSubmit without toName (no annotation created)
 * - handleBlur without toName (no annotation)
 * - handleBlur without value (no annotation)
 * - Auto-annotation debounce effect
 * - hint text rendering
 * - required asterisk display
 * - External value sync
 */

/**
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import TextAreaInput from '../TextAreaInput'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({ t: (key: string) => key }),
}))

jest.mock('@/lib/labelConfig/dataBinding', () => ({
  buildAnnotationResult: jest.fn((name, type, value, toName) => ({
    id: `${name}-result`,
    from_name: name,
    to_name: toName,
    type: type.toLowerCase(),
    value: { text: [value] },
  })),
}))

jest.mock('@/lib/utils/logger', () => ({
  logger: { debug: jest.fn(), warn: jest.fn(), error: jest.fn() },
}))

const baseConfig = {
  name: 'textarea',
  type: 'TextArea',
  props: {
    name: 'myTextArea',
    toName: 'text',
    placeholder: 'Write here...',
    rows: '3',
    required: 'false',
    showSubmitButton: 'true',
  },
  children: [],
}

describe('TextAreaInput - branch coverage', () => {
  const mockOnChange = jest.fn()
  const mockOnAnnotation = jest.fn()

  beforeEach(() => {
    jest.clearAllMocks()
    jest.useFakeTimers()
  })

  afterEach(() => {
    jest.useRealTimers()
  })

  it('renders with label and placeholder', () => {
    render(
      <TextAreaInput
        config={baseConfig}
        taskData={{}}
        value=""
        onChange={mockOnChange}
        onAnnotation={mockOnAnnotation}
      />
    )

    expect(screen.getByLabelText('myTextArea')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('Write here...')).toBeInTheDocument()
  })

  it('shows required asterisk when required is true', () => {
    const config = {
      ...baseConfig,
      props: { ...baseConfig.props, required: 'true' },
    }

    render(
      <TextAreaInput
        config={config}
        taskData={{}}
        value=""
        onChange={mockOnChange}
        onAnnotation={mockOnAnnotation}
      />
    )

    expect(screen.getByText('*')).toBeInTheDocument()
  })

  it('shows hint text when provided', () => {
    const config = {
      ...baseConfig,
      props: { ...baseConfig.props, hint: 'Enter at least 100 words' },
    }

    render(
      <TextAreaInput
        config={config}
        taskData={{}}
        value=""
        onChange={mockOnChange}
        onAnnotation={mockOnAnnotation}
      />
    )

    expect(screen.getByText('Enter at least 100 words')).toBeInTheDocument()
  })

  it('hides submit button when hideSubmitButton is true', () => {
    render(
      <TextAreaInput
        config={baseConfig}
        taskData={{}}
        value=""
        onChange={mockOnChange}
        onAnnotation={mockOnAnnotation}
        hideSubmitButton={true}
      />
    )

    expect(screen.queryByText('Submit')).not.toBeInTheDocument()
  })

  it('hides submit button when config showSubmitButton is false', () => {
    const config = {
      ...baseConfig,
      props: { ...baseConfig.props, showSubmitButton: 'false' },
    }

    render(
      <TextAreaInput
        config={config}
        taskData={{}}
        value=""
        onChange={mockOnChange}
        onAnnotation={mockOnAnnotation}
      />
    )

    expect(screen.queryByText('Submit')).not.toBeInTheDocument()
  })

  it('shows submit button by default', () => {
    render(
      <TextAreaInput
        config={baseConfig}
        taskData={{}}
        value=""
        onChange={mockOnChange}
        onAnnotation={mockOnAnnotation}
      />
    )

    expect(screen.getByText('Submit')).toBeInTheDocument()
  })

  it('handleSubmit does nothing when value is empty and required', () => {
    const config = {
      ...baseConfig,
      props: { ...baseConfig.props, required: 'true' },
    }

    render(
      <TextAreaInput
        config={config}
        taskData={{}}
        value=""
        onChange={mockOnChange}
        onAnnotation={mockOnAnnotation}
      />
    )

    const submitButton = screen.getByText('Submit')
    fireEvent.click(submitButton)

    expect(mockOnAnnotation).not.toHaveBeenCalled()
  })

  it('handleSubmit creates annotation when toName is set', () => {
    render(
      <TextAreaInput
        config={baseConfig}
        taskData={{}}
        value="Hello"
        onChange={mockOnChange}
        onAnnotation={mockOnAnnotation}
      />
    )

    const submitButton = screen.getByText('Submit')
    fireEvent.click(submitButton)

    expect(mockOnAnnotation).toHaveBeenCalled()
  })

  it('handleSubmit does nothing when toName is missing', () => {
    const config = {
      ...baseConfig,
      props: { ...baseConfig.props, toName: undefined },
    }

    render(
      <TextAreaInput
        config={config}
        taskData={{}}
        value="Hello"
        onChange={mockOnChange}
        onAnnotation={mockOnAnnotation}
      />
    )

    const submitButton = screen.getByText('Submit')
    fireEvent.click(submitButton)

    expect(mockOnAnnotation).not.toHaveBeenCalled()
  })

  it('handleBlur creates annotation when toName and value are set', () => {
    render(
      <TextAreaInput
        config={baseConfig}
        taskData={{}}
        value="Some text"
        onChange={mockOnChange}
        onAnnotation={mockOnAnnotation}
      />
    )

    const textarea = screen.getByPlaceholderText('Write here...')
    fireEvent.blur(textarea)

    expect(mockOnAnnotation).toHaveBeenCalled()
  })

  it('handleBlur does not create annotation when toName is missing', () => {
    const config = {
      ...baseConfig,
      props: { ...baseConfig.props, toName: undefined },
    }

    render(
      <TextAreaInput
        config={config}
        taskData={{}}
        value="Some text"
        onChange={mockOnChange}
        onAnnotation={mockOnAnnotation}
      />
    )

    const textarea = screen.getByPlaceholderText('Write here...')
    fireEvent.blur(textarea)

    expect(mockOnAnnotation).not.toHaveBeenCalled()
  })

  it('debounced auto-annotation fires after 500ms', async () => {
    render(
      <TextAreaInput
        config={baseConfig}
        taskData={{}}
        value=""
        onChange={mockOnChange}
        onAnnotation={mockOnAnnotation}
      />
    )

    const textarea = screen.getByPlaceholderText('Write here...')
    fireEvent.change(textarea, { target: { value: 'Hello world' } })

    // Before debounce
    expect(mockOnAnnotation).not.toHaveBeenCalled()

    // After debounce
    jest.advanceTimersByTime(600)

    await waitFor(() => {
      expect(mockOnAnnotation).toHaveBeenCalled()
    })
  })

  it('syncs with external value changes', () => {
    const { rerender } = render(
      <TextAreaInput
        config={baseConfig}
        taskData={{}}
        value="initial"
        onChange={mockOnChange}
        onAnnotation={mockOnAnnotation}
      />
    )

    const textarea = screen.getByPlaceholderText('Write here...') as HTMLTextAreaElement
    expect(textarea.value).toBe('initial')

    rerender(
      <TextAreaInput
        config={baseConfig}
        taskData={{}}
        value="updated"
        onChange={mockOnChange}
        onAnnotation={mockOnAnnotation}
      />
    )

    expect(textarea.value).toBe('updated')
  })

  it('clears field when external value becomes undefined', () => {
    const { rerender } = render(
      <TextAreaInput
        config={baseConfig}
        taskData={{}}
        value="some text"
        onChange={mockOnChange}
        onAnnotation={mockOnAnnotation}
      />
    )

    rerender(
      <TextAreaInput
        config={baseConfig}
        taskData={{}}
        value={undefined as any}
        onChange={mockOnChange}
        onAnnotation={mockOnAnnotation}
      />
    )

    const textarea = screen.getByPlaceholderText('Write here...') as HTMLTextAreaElement
    expect(textarea.value).toBe('')
  })

  it('uses config.name fallback when props.name is missing', () => {
    const config = {
      ...baseConfig,
      props: { ...baseConfig.props, name: undefined, label: undefined },
    }

    render(
      <TextAreaInput
        config={config}
        taskData={{}}
        value=""
        onChange={mockOnChange}
        onAnnotation={mockOnAnnotation}
      />
    )

    expect(screen.getByLabelText('textarea')).toBeInTheDocument()
  })

  it('uses default name when both config.name and props.name are missing', () => {
    const config = {
      name: undefined as any,
      type: 'TextArea',
      props: { toName: 'text' },
      children: [],
    }

    render(
      <TextAreaInput
        config={config}
        taskData={{}}
        value=""
        onChange={mockOnChange}
        onAnnotation={mockOnAnnotation}
      />
    )

    expect(screen.getByLabelText('textarea')).toBeInTheDocument()
  })
})

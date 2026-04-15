/**
 * Comprehensive tests for TextAreaInput component
 * Tests the hideSubmitButton functionality, value management, and annotation creation
 */

/**
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

// Mock Label component
jest.mock('@/components/shared/Label', () => ({
  Label: ({ children, htmlFor }: any) => (
    <label data-testid="label" htmlFor={htmlFor}>
      {children}
    </label>
  ),
}))

// Mock Textarea component
jest.mock('@/components/shared/Textarea', () => {
  const React = require('react')
  const Textarea = React.forwardRef(function Textarea(props: any, ref: any) {
    return <textarea ref={ref} {...props} data-testid="textarea" />
  })
  Textarea.displayName = 'Textarea'
  return { Textarea }
})

// Mock data binding utilities
jest.mock('@/lib/labelConfig/dataBinding', () => ({
  buildAnnotationResult: (
    name: string,
    type: string,
    value: any,
    toName: string
  ) => ({
    from_name: name,
    to_name: toName,
    type,
    value: typeof value === 'string' ? { text: [value] } : value,
  }),
}))

// Import the actual component after mocks
import TextAreaInput from '../TextAreaInput'

describe('TextAreaInput', () => {
  const defaultProps = {
    config: {
      type: 'TextArea',
      name: 'test-textarea',
      props: {
        name: 'test-textarea',
        toName: 'context',
        placeholder: 'Enter your answer...',
        rows: '3',
        required: 'false',
        showSubmitButton: 'true',
      },
      children: [],
    },
    taskData: { context: 'Test context' },
    value: '',
    onChange: jest.fn(),
    onAnnotation: jest.fn(),
  }

  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('Submit Button Visibility', () => {
    it('should show submit button by default when showSubmitButton is true', async () => {
      render(<TextAreaInput {...defaultProps} />)

      const submitButton = screen.getByRole('button', { name: /submit/i })
      expect(submitButton).toBeInTheDocument()
    })

    it('should hide submit button when hideSubmitButton is true', async () => {
      render(<TextAreaInput {...defaultProps} hideSubmitButton={true} />)

      const submitButton = screen.queryByRole('button', { name: /submit/i })
      expect(submitButton).not.toBeInTheDocument()
    })

    it('should show submit button when hideSubmitButton is false', async () => {
      render(<TextAreaInput {...defaultProps} hideSubmitButton={false} />)

      const submitButton = screen.getByRole('button', { name: /submit/i })
      expect(submitButton).toBeInTheDocument()
    })

    it('should hide submit button when showSubmitButton config is false, regardless of hideSubmitButton', async () => {
      const propsWithNoSubmitButton = {
        ...defaultProps,
        config: {
          ...defaultProps.config,
          props: {
            ...defaultProps.config.props,
            showSubmitButton: 'false',
          },
        },
      }

      render(
        <TextAreaInput {...propsWithNoSubmitButton} hideSubmitButton={false} />
      )

      const submitButton = screen.queryByRole('button', { name: /submit/i })
      expect(submitButton).not.toBeInTheDocument()
    })

    it('should hide submit button when both showSubmitButton is true but hideSubmitButton is true', async () => {
      const propsWithSubmitButton = {
        ...defaultProps,
        config: {
          ...defaultProps.config,
          props: {
            ...defaultProps.config.props,
            showSubmitButton: 'true',
          },
        },
      }

      render(
        <TextAreaInput {...propsWithSubmitButton} hideSubmitButton={true} />
      )

      const submitButton = screen.queryByRole('button', { name: /submit/i })
      expect(submitButton).not.toBeInTheDocument()
    })
  })

  describe('Submit Button Functionality', () => {
    it('should call onAnnotation when submit button is clicked', async () => {
      const mockOnAnnotation = jest.fn()
      const props = {
        ...defaultProps,
        onAnnotation: mockOnAnnotation,
      }

      render(<TextAreaInput {...props} />)

      const textarea = screen.getByTestId('textarea')
      const submitButton = screen.getByRole('button', { name: /submit/i })

      // Type some text
      fireEvent.change(textarea, { target: { value: 'Test answer' } })

      // Click submit
      fireEvent.click(submitButton)

      await waitFor(() => {
        expect(mockOnAnnotation).toHaveBeenCalledWith({
          from_name: 'test-textarea',
          to_name: 'context',
          type: 'TextArea',
          value: { text: ['Test answer'] },
        })
      })
    })

    it('should disable submit button when required field is empty', () => {
      const propsWithRequired = {
        ...defaultProps,
        config: {
          ...defaultProps.config,
          props: {
            ...defaultProps.config.props,
            required: 'true',
          },
        },
      }

      render(<TextAreaInput {...propsWithRequired} />)

      const submitButton = screen.getByRole('button', { name: /submit/i })
      expect(submitButton).toBeDisabled()
    })

    it('should enable submit button when required field has content', () => {
      const propsWithRequired = {
        ...defaultProps,
        config: {
          ...defaultProps.config,
          props: {
            ...defaultProps.config.props,
            required: 'true',
          },
        },
      }

      render(<TextAreaInput {...propsWithRequired} />)

      const textarea = screen.getByTestId('textarea')
      const submitButton = screen.getByRole('button', { name: /submit/i })

      // Initially disabled
      expect(submitButton).toBeDisabled()

      // Add content
      fireEvent.change(textarea, { target: { value: 'Some content' } })

      // Should be enabled now
      expect(submitButton).toBeEnabled()
    })
  })

  describe('Text Input Functionality', () => {
    it('should call onChange when text is entered', () => {
      const mockOnChange = jest.fn()
      const mockOnAnnotation = jest.fn()

      const props = {
        ...defaultProps,
        onChange: mockOnChange,
        onAnnotation: mockOnAnnotation,
      }

      render(<TextAreaInput {...props} />)

      const textarea = screen.getByTestId('textarea')

      fireEvent.change(textarea, { target: { value: 'Test input' } })

      // onChange is called immediately on change
      expect(mockOnChange).toHaveBeenCalledWith('Test input')
    })

    it('should call onAnnotation on blur', () => {
      const mockOnChange = jest.fn()
      const mockOnAnnotation = jest.fn()

      const props = {
        ...defaultProps,
        onChange: mockOnChange,
        onAnnotation: mockOnAnnotation,
      }

      render(<TextAreaInput {...props} />)

      const textarea = screen.getByTestId('textarea')

      fireEvent.change(textarea, { target: { value: 'Test input' } })
      fireEvent.blur(textarea)

      expect(mockOnAnnotation).toHaveBeenCalledWith({
        from_name: 'test-textarea',
        to_name: 'context',
        type: 'TextArea',
        value: { text: ['Test input'] },
      })
    })

    it('should display external value when provided', () => {
      const props = {
        ...defaultProps,
        value: 'Existing value',
      }

      render(<TextAreaInput {...props} />)

      const textarea = screen.getByTestId('textarea')
      expect(textarea).toHaveValue('Existing value')
    })
  })

  describe('Backward Compatibility', () => {
    it('should maintain current behavior when hideSubmitButton is not provided', () => {
      // This test ensures that existing usage is not broken
      render(<TextAreaInput {...defaultProps} />)

      const submitButton = screen.getByRole('button', { name: /submit/i })
      expect(submitButton).toBeInTheDocument()

      const textarea = screen.getByTestId('textarea')
      expect(textarea).toBeInTheDocument()
    })

    it('should work correctly with all configuration options', () => {
      const complexProps = {
        ...defaultProps,
        config: {
          ...defaultProps.config,
          props: {
            ...defaultProps.config.props,
            label: 'Custom Label',
            placeholder: 'Custom placeholder',
            rows: '5',
            required: 'true',
            hint: 'This is a hint message',
          },
        },
      }

      render(<TextAreaInput {...complexProps} />)

      expect(screen.getByText('Custom Label')).toBeInTheDocument()
      expect(screen.getByText('*')).toBeInTheDocument() // Required indicator
      expect(screen.getByText('This is a hint message')).toBeInTheDocument()

      const textarea = screen.getByTestId('textarea')
      expect(textarea).toHaveAttribute('placeholder', 'Custom placeholder')
      expect(textarea).toHaveAttribute('rows', '5')
      expect(textarea).toBeRequired()
    })
  })

  describe('Value Synchronization', () => {
    it('should sync with external value changes', () => {
      const { rerender } = render(<TextAreaInput {...defaultProps} value="" />)

      const textarea = screen.getByTestId('textarea')
      expect(textarea).toHaveValue('')

      rerender(<TextAreaInput {...defaultProps} value="New external value" />)
      expect(textarea).toHaveValue('New external value')
    })

    it('should clear value when external value becomes undefined', () => {
      const { rerender } = render(
        <TextAreaInput {...defaultProps} value="Initial" />
      )

      const textarea = screen.getByTestId('textarea')
      expect(textarea).toHaveValue('Initial')

      rerender(<TextAreaInput {...defaultProps} value={undefined} />)
      expect(textarea).toHaveValue('')
    })

    it('should handle external value changes while user is typing', () => {
      const { rerender } = render(
        <TextAreaInput {...defaultProps} value="Initial" />
      )

      const textarea = screen.getByTestId('textarea')
      fireEvent.change(textarea, { target: { value: 'User typing' } })

      rerender(<TextAreaInput {...defaultProps} value="External update" />)
      expect(textarea).toHaveValue('External update')
    })
  })

  describe('Blur Event Handling', () => {
    it('should create annotation on blur', () => {
      const mockOnAnnotation = jest.fn()

      render(
        <TextAreaInput {...defaultProps} onAnnotation={mockOnAnnotation} />
      )

      const textarea = screen.getByTestId('textarea')
      fireEvent.change(textarea, { target: { value: 'Blur test' } })
      fireEvent.blur(textarea)

      expect(mockOnAnnotation).toHaveBeenCalled()
    })

    it('should not create annotation on blur if no toName', () => {
      const mockOnAnnotation = jest.fn()
      const propsWithoutToName = {
        ...defaultProps,
        config: {
          ...defaultProps.config,
          props: {
            ...defaultProps.config.props,
            toName: undefined,
          },
        },
        onAnnotation: mockOnAnnotation,
      }

      render(<TextAreaInput {...propsWithoutToName} />)

      const textarea = screen.getByTestId('textarea')
      fireEvent.change(textarea, { target: { value: 'Test' } })
      fireEvent.blur(textarea)

      expect(mockOnAnnotation).not.toHaveBeenCalled()
    })

    it('should not create annotation on blur if value is empty', () => {
      const mockOnAnnotation = jest.fn()

      render(
        <TextAreaInput {...defaultProps} onAnnotation={mockOnAnnotation} />
      )

      const textarea = screen.getByTestId('textarea')
      fireEvent.blur(textarea)

      expect(mockOnAnnotation).not.toHaveBeenCalled()
    })
  })

  describe('Debounced Annotation Creation', () => {
    beforeEach(() => {
      jest.useFakeTimers()
    })

    afterEach(() => {
      jest.runOnlyPendingTimers()
      jest.useRealTimers()
    })

    it('should create annotation after delay when typing stops', () => {
      const mockOnAnnotation = jest.fn()

      render(
        <TextAreaInput {...defaultProps} onAnnotation={mockOnAnnotation} />
      )

      const textarea = screen.getByTestId('textarea')
      fireEvent.change(textarea, { target: { value: 'Test input' } })

      expect(mockOnAnnotation).not.toHaveBeenCalled()

      jest.advanceTimersByTime(500)

      expect(mockOnAnnotation).toHaveBeenCalled()
    })

    it('should cancel previous timer when typing continues', () => {
      const mockOnAnnotation = jest.fn()

      render(
        <TextAreaInput {...defaultProps} onAnnotation={mockOnAnnotation} />
      )

      const textarea = screen.getByTestId('textarea')

      fireEvent.change(textarea, { target: { value: 'Test' } })
      jest.advanceTimersByTime(300)

      fireEvent.change(textarea, { target: { value: 'Test input' } })
      jest.advanceTimersByTime(300)

      expect(mockOnAnnotation).not.toHaveBeenCalled()

      jest.advanceTimersByTime(200)

      expect(mockOnAnnotation).toHaveBeenCalledTimes(1)
    })
  })

  describe('Configuration Props', () => {
    it('should use custom placeholder', () => {
      const customProps = {
        ...defaultProps,
        config: {
          ...defaultProps.config,
          props: {
            ...defaultProps.config.props,
            placeholder: 'Custom placeholder text',
          },
        },
      }

      render(<TextAreaInput {...customProps} />)

      const textarea = screen.getByTestId('textarea')
      expect(textarea).toHaveAttribute('placeholder', 'Custom placeholder text')
    })

    it('should use custom rows', () => {
      const customProps = {
        ...defaultProps,
        config: {
          ...defaultProps.config,
          props: {
            ...defaultProps.config.props,
            rows: '10',
          },
        },
      }

      render(<TextAreaInput {...customProps} />)

      const textarea = screen.getByTestId('textarea')
      expect(textarea).toHaveAttribute('rows', '10')
    })

    it('should display custom label', () => {
      const customProps = {
        ...defaultProps,
        config: {
          ...defaultProps.config,
          props: {
            ...defaultProps.config.props,
            label: 'Custom Label Text',
          },
        },
      }

      render(<TextAreaInput {...customProps} />)

      expect(screen.getByText('Custom Label Text')).toBeInTheDocument()
    })

    it('should use name as label fallback', () => {
      const propsWithoutLabel = {
        ...defaultProps,
        config: {
          ...defaultProps.config,
          props: {
            ...defaultProps.config.props,
            label: undefined,
          },
        },
      }

      render(<TextAreaInput {...propsWithoutLabel} />)

      expect(screen.getByText('test-textarea')).toBeInTheDocument()
    })

    it('should display hint text', () => {
      const propsWithHint = {
        ...defaultProps,
        config: {
          ...defaultProps.config,
          props: {
            ...defaultProps.config.props,
            hint: 'This is helpful hint text',
          },
        },
      }

      render(<TextAreaInput {...propsWithHint} />)

      expect(screen.getByText('This is helpful hint text')).toBeInTheDocument()
    })
  })

  describe('Multiple Instances', () => {
    it('should handle multiple TextAreaInput components independently', () => {
      const mockOnChange1 = jest.fn()
      const mockOnChange2 = jest.fn()

      const props1 = {
        ...defaultProps,
        config: {
          ...defaultProps.config,
          props: { ...defaultProps.config.props, name: 'textarea1' },
        },
        onChange: mockOnChange1,
      }

      const props2 = {
        ...defaultProps,
        config: {
          ...defaultProps.config,
          props: { ...defaultProps.config.props, name: 'textarea2' },
        },
        onChange: mockOnChange2,
      }

      const { container } = render(
        <div>
          <TextAreaInput {...props1} />
          <TextAreaInput {...props2} />
        </div>
      )

      const textareas = container.querySelectorAll('textarea')
      expect(textareas).toHaveLength(2)

      fireEvent.change(textareas[0], { target: { value: 'First' } })
      fireEvent.change(textareas[1], { target: { value: 'Second' } })

      expect(mockOnChange1).toHaveBeenCalledWith('First')
      expect(mockOnChange2).toHaveBeenCalledWith('Second')
    })
  })

  describe('Edge Cases', () => {
    it('should handle missing toName gracefully', () => {
      const propsWithoutToName = {
        ...defaultProps,
        config: {
          ...defaultProps.config,
          props: {
            ...defaultProps.config.props,
            toName: undefined,
          },
        },
      }

      render(<TextAreaInput {...propsWithoutToName} />)

      const textarea = screen.getByTestId('textarea')
      const submitButton = screen.getByRole('button', { name: /submit/i })

      // Should render without errors
      expect(textarea).toBeInTheDocument()
      expect(submitButton).toBeInTheDocument()

      // Clicking submit should not cause errors
      fireEvent.change(textarea, { target: { value: 'Test' } })
      fireEvent.click(submitButton)

      // onAnnotation should not be called without toName
      expect(defaultProps.onAnnotation).not.toHaveBeenCalled()
    })

    it('should handle empty or whitespace-only values when required', () => {
      const propsWithRequired = {
        ...defaultProps,
        config: {
          ...defaultProps.config,
          props: {
            ...defaultProps.config.props,
            required: 'true',
          },
        },
      }

      render(<TextAreaInput {...propsWithRequired} />)

      const textarea = screen.getByTestId('textarea')
      const submitButton = screen.getByRole('button', { name: /submit/i })

      // Test with whitespace only
      fireEvent.change(textarea, { target: { value: '   ' } })
      expect(submitButton).toBeDisabled()

      // Test with actual content
      fireEvent.change(textarea, { target: { value: 'Real content' } })
      expect(submitButton).toBeEnabled()
    })

    it('should handle null and undefined values correctly', () => {
      const propsWithNullValue = {
        ...defaultProps,
        value: null,
      }

      render(<TextAreaInput {...propsWithNullValue} />)

      const textarea = screen.getByTestId('textarea')
      expect(textarea).toHaveValue('')

      // Test with undefined
      const propsWithUndefinedValue = {
        ...defaultProps,
        value: undefined,
      }

      render(<TextAreaInput {...propsWithUndefinedValue} />)

      const textareaUndefined = screen.getAllByTestId('textarea')[1] // Second render
      expect(textareaUndefined).toHaveValue('')
    })
  })
})

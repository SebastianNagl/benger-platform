/**
 * Test suite for Textarea component
 * Issue #364: Comprehensive component testing for shared components
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import React from 'react'
import { Textarea } from '../Textarea'

describe('Textarea Component', () => {
  const defaultProps = {
    id: 'test-textarea',
    name: 'testTextarea',
  }

  describe('1. Basic Rendering', () => {
    it('renders correctly with default props', () => {
      render(<Textarea {...defaultProps} />)

      const textarea = screen.getByRole('textbox')
      expect(textarea).toBeInTheDocument()
      expect(textarea).toHaveAttribute('id', 'test-textarea')
      expect(textarea).toHaveAttribute('name', 'testTextarea')
    })

    it('displays placeholder text', () => {
      render(<Textarea {...defaultProps} placeholder="Enter your comments" />)

      const textarea = screen.getByPlaceholderText('Enter your comments')
      expect(textarea).toBeInTheDocument()
    })

    it('renders as a textarea element', () => {
      render(<Textarea {...defaultProps} />)

      const textarea = screen.getByRole('textbox')
      expect(textarea.tagName).toBe('TEXTAREA')
    })

    it('has correct display name', () => {
      expect(Textarea.displayName).toBe('Textarea')
    })
  })

  describe('2. Value Handling', () => {
    it('displays initial value', () => {
      render(<Textarea {...defaultProps} defaultValue="Initial content" />)

      const textarea = screen.getByRole('textbox')
      expect(textarea).toHaveValue('Initial content')
    })

    it('supports controlled textarea with value prop', () => {
      const { rerender } = render(
        <Textarea {...defaultProps} value="initial" onChange={() => {}} />
      )

      let textarea = screen.getByRole('textbox')
      expect(textarea).toHaveValue('initial')

      rerender(
        <Textarea {...defaultProps} value="updated" onChange={() => {}} />
      )
      textarea = screen.getByRole('textbox')
      expect(textarea).toHaveValue('updated')
    })

    it('handles multiline text correctly', () => {
      const multilineText = 'Line 1\nLine 2\nLine 3'
      render(<Textarea {...defaultProps} defaultValue={multilineText} />)

      const textarea = screen.getByRole('textbox')
      expect(textarea).toHaveValue(multilineText)
    })

    it('handles empty value', () => {
      render(<Textarea {...defaultProps} value="" onChange={() => {}} />)

      const textarea = screen.getByRole('textbox')
      expect(textarea).toHaveValue('')
    })
  })

  describe('3. OnChange Handler', () => {
    it('calls onChange handler when text is entered', async () => {
      const user = userEvent.setup()
      const mockChange = jest.fn()

      render(<Textarea {...defaultProps} onChange={mockChange} />)

      const textarea = screen.getByRole('textbox')
      await user.type(textarea, 'test')

      expect(mockChange).toHaveBeenCalled()
      expect(textarea).toHaveValue('test')
    })

    it('calls onChange with correct event data', async () => {
      const user = userEvent.setup()
      const mockChange = jest.fn()

      render(<Textarea {...defaultProps} onChange={mockChange} />)

      const textarea = screen.getByRole('textbox')
      await user.type(textarea, 'a')

      expect(mockChange).toHaveBeenCalledWith(
        expect.objectContaining({
          target: expect.objectContaining({
            value: 'a',
          }),
        })
      )
    })

    it('handles multiple changes', async () => {
      const user = userEvent.setup()
      const mockChange = jest.fn()

      render(<Textarea {...defaultProps} onChange={mockChange} />)

      const textarea = screen.getByRole('textbox')
      await user.type(textarea, 'hello')

      expect(mockChange).toHaveBeenCalledTimes(5) // One for each character
    })

    it('handles multiline input', async () => {
      const user = userEvent.setup()
      const mockChange = jest.fn()

      render(<Textarea {...defaultProps} onChange={mockChange} />)

      const textarea = screen.getByRole('textbox')
      await user.type(textarea, 'Line 1{Enter}Line 2')

      expect(mockChange).toHaveBeenCalled()
      expect(textarea).toHaveValue('Line 1\nLine 2')
    })
  })

  describe('4. Disabled State', () => {
    it('applies disabled state correctly', () => {
      render(<Textarea {...defaultProps} disabled={true} />)

      const textarea = screen.getByRole('textbox')
      expect(textarea).toBeDisabled()
    })

    it('applies disabled styling classes', () => {
      render(<Textarea {...defaultProps} disabled={true} />)

      const textarea = screen.getByRole('textbox')
      expect(textarea).toHaveClass('disabled:cursor-not-allowed')
      expect(textarea).toHaveClass('disabled:bg-zinc-50')
      expect(textarea).toHaveClass('disabled:text-zinc-500')
    })

    it('prevents input when disabled', async () => {
      const user = userEvent.setup()
      const mockChange = jest.fn()

      render(
        <Textarea {...defaultProps} disabled={true} onChange={mockChange} />
      )

      const textarea = screen.getByRole('textbox')
      await user.type(textarea, 'test')

      expect(mockChange).not.toHaveBeenCalled()
      expect(textarea).toHaveValue('')
    })

    it('does not prevent input when not disabled', async () => {
      const user = userEvent.setup()
      const mockChange = jest.fn()

      render(
        <Textarea {...defaultProps} disabled={false} onChange={mockChange} />
      )

      const textarea = screen.getByRole('textbox')
      await user.type(textarea, 'test')

      expect(mockChange).toHaveBeenCalled()
    })
  })

  describe('5. Styling', () => {
    it('applies default styling classes', () => {
      render(<Textarea {...defaultProps} />)

      const textarea = screen.getByRole('textbox')
      expect(textarea).toHaveClass('block')
      expect(textarea).toHaveClass('w-full')
      expect(textarea).toHaveClass('rounded-md')
      expect(textarea).toHaveClass('border-zinc-300')
      expect(textarea).toHaveClass('bg-white')
      expect(textarea).toHaveClass('text-zinc-900')
    })

    it('applies focus styling classes', () => {
      render(<Textarea {...defaultProps} />)

      const textarea = screen.getByRole('textbox')
      expect(textarea).toHaveClass('focus:border-emerald-500')
      expect(textarea).toHaveClass('focus:ring-emerald-500')
    })

    it('applies dark mode styling classes', () => {
      render(<Textarea {...defaultProps} />)

      const textarea = screen.getByRole('textbox')
      expect(textarea).toHaveClass('dark:border-zinc-700')
      expect(textarea).toHaveClass('dark:bg-zinc-800')
      expect(textarea).toHaveClass('dark:text-white')
    })

    it('applies dark mode disabled styling classes', () => {
      render(<Textarea {...defaultProps} />)

      const textarea = screen.getByRole('textbox')
      expect(textarea).toHaveClass('dark:disabled:bg-zinc-900')
    })

    it('applies resize-vertical class', () => {
      render(<Textarea {...defaultProps} />)

      const textarea = screen.getByRole('textbox')
      expect(textarea).toHaveClass('resize-vertical')
    })

    it('applies custom className', () => {
      render(<Textarea {...defaultProps} className="custom-textarea" />)

      const textarea = screen.getByRole('textbox')
      expect(textarea).toHaveClass('custom-textarea')
    })

    it('combines custom className with default classes', () => {
      render(<Textarea {...defaultProps} className="custom-textarea" />)

      const textarea = screen.getByRole('textbox')
      expect(textarea).toHaveClass('custom-textarea')
      expect(textarea).toHaveClass('block')
      expect(textarea).toHaveClass('w-full')
    })

    it('applies padding classes', () => {
      render(<Textarea {...defaultProps} />)

      const textarea = screen.getByRole('textbox')
      expect(textarea).toHaveClass('px-3')
      expect(textarea).toHaveClass('py-2')
    })
  })

  describe('6. Accessibility', () => {
    it('has textbox role', () => {
      render(<Textarea {...defaultProps} />)

      const textarea = screen.getByRole('textbox')
      expect(textarea).toBeInTheDocument()
    })

    it('supports aria-label attribute', () => {
      render(<Textarea {...defaultProps} aria-label="Description field" />)

      const textarea = screen.getByLabelText('Description field')
      expect(textarea).toBeInTheDocument()
    })

    it('supports aria-describedby attribute', () => {
      render(
        <>
          <Textarea {...defaultProps} aria-describedby="description-help" />
          <div id="description-help">Help text</div>
        </>
      )

      const textarea = screen.getByRole('textbox')
      expect(textarea).toHaveAttribute('aria-describedby', 'description-help')
    })

    it('shows required attribute when required', () => {
      render(<Textarea {...defaultProps} required={true} />)

      const textarea = screen.getByRole('textbox')
      expect(textarea).toHaveAttribute('required')
      expect(textarea).toBeRequired()
    })

    it('supports aria-invalid attribute', () => {
      render(<Textarea {...defaultProps} aria-invalid={true} />)

      const textarea = screen.getByRole('textbox')
      expect(textarea).toHaveAttribute('aria-invalid', 'true')
    })

    it('handles focus and blur events', async () => {
      const user = userEvent.setup()
      const mockFocus = jest.fn()
      const mockBlur = jest.fn()

      render(
        <Textarea {...defaultProps} onFocus={mockFocus} onBlur={mockBlur} />
      )

      const textarea = screen.getByRole('textbox')
      await user.click(textarea)
      expect(mockFocus).toHaveBeenCalledTimes(1)

      await user.tab()
      expect(mockBlur).toHaveBeenCalledTimes(1)
    })
  })

  describe('7. Edge Cases', () => {
    it('handles very long text content', async () => {
      const longText = 'a'.repeat(1000)
      render(<Textarea {...defaultProps} defaultValue={longText} />)

      const textarea = screen.getByRole('textbox')
      expect(textarea).toHaveValue(longText)
    })

    it('supports maxLength attribute', () => {
      render(<Textarea {...defaultProps} maxLength={100} />)

      const textarea = screen.getByRole('textbox')
      expect(textarea).toHaveAttribute('maxLength', '100')
    })

    it('enforces maxLength constraint', async () => {
      const user = userEvent.setup()
      render(<Textarea {...defaultProps} maxLength={5} />)

      const textarea = screen.getByRole('textbox')
      await user.type(textarea, 'abcdefghij')

      expect(textarea).toHaveValue('abcde')
    })

    it('supports readOnly attribute', () => {
      render(<Textarea {...defaultProps} readOnly={true} />)

      const textarea = screen.getByRole('textbox')
      expect(textarea).toHaveAttribute('readOnly')
    })

    it('prevents editing when readOnly', async () => {
      const user = userEvent.setup()
      const mockChange = jest.fn()

      render(
        <Textarea
          {...defaultProps}
          readOnly={true}
          defaultValue="initial"
          onChange={mockChange}
        />
      )

      const textarea = screen.getByRole('textbox')
      await user.type(textarea, 'test')

      expect(mockChange).not.toHaveBeenCalled()
      expect(textarea).toHaveValue('initial')
    })

    it('handles special characters', async () => {
      const specialText = '!@#$%^&*()_+-=[]{}|;:\'",.<>?/~`'
      render(<Textarea {...defaultProps} defaultValue={specialText} />)

      const textarea = screen.getByRole('textbox')
      expect(textarea).toHaveValue(specialText)
    })

    it('handles unicode characters', async () => {
      const unicodeText = '你好世界 🎉 émojis'
      render(<Textarea {...defaultProps} defaultValue={unicodeText} />)

      const textarea = screen.getByRole('textbox')
      expect(textarea).toHaveValue(unicodeText)
    })

    it('handles rows attribute', () => {
      render(<Textarea {...defaultProps} rows={5} />)

      const textarea = screen.getByRole('textbox')
      expect(textarea).toHaveAttribute('rows', '5')
    })

    it('handles cols attribute', () => {
      render(<Textarea {...defaultProps} cols={80} />)

      const textarea = screen.getByRole('textbox')
      expect(textarea).toHaveAttribute('cols', '80')
    })
  })

  describe('8. Props Passthrough', () => {
    it('forwards ref correctly', () => {
      const ref = React.createRef<HTMLTextAreaElement>()
      render(<Textarea {...defaultProps} ref={ref} />)

      expect(ref.current).toBeInstanceOf(HTMLTextAreaElement)
      expect(ref.current?.tagName).toBe('TEXTAREA')
    })

    it('supports all standard textarea attributes', () => {
      render(
        <Textarea
          {...defaultProps}
          placeholder="test placeholder"
          autoComplete="off"
          readOnly={true}
          required={true}
          rows={10}
          cols={50}
        />
      )

      const textarea = screen.getByRole('textbox')
      expect(textarea).toHaveAttribute('placeholder', 'test placeholder')
      expect(textarea).toHaveAttribute('autoComplete', 'off')
      expect(textarea).toHaveAttribute('readOnly')
      expect(textarea).toHaveAttribute('required')
      expect(textarea).toHaveAttribute('rows', '10')
      expect(textarea).toHaveAttribute('cols', '50')
    })

    it('passes through data attributes', () => {
      render(<Textarea {...defaultProps} data-testid="custom-test" />)

      const textarea = screen.getByTestId('custom-test')
      expect(textarea).toBeInTheDocument()
    })

    it('passes through aria attributes', () => {
      render(
        <Textarea
          {...defaultProps}
          aria-label="Custom label"
          aria-required={true}
          aria-invalid={false}
        />
      )

      const textarea = screen.getByRole('textbox')
      expect(textarea).toHaveAttribute('aria-label', 'Custom label')
      expect(textarea).toHaveAttribute('aria-required', 'true')
      expect(textarea).toHaveAttribute('aria-invalid', 'false')
    })

    it('passes through event handlers', async () => {
      const user = userEvent.setup()
      const mockKeyDown = jest.fn()
      const mockKeyUp = jest.fn()
      const mockKeyPress = jest.fn()

      render(
        <Textarea
          {...defaultProps}
          onKeyDown={mockKeyDown}
          onKeyUp={mockKeyUp}
          onKeyPress={mockKeyPress}
        />
      )

      const textarea = screen.getByRole('textbox')
      await user.type(textarea, 'a')

      expect(mockKeyDown).toHaveBeenCalled()
      expect(mockKeyUp).toHaveBeenCalled()
    })

    it('passes through form attributes', () => {
      render(
        <Textarea
          {...defaultProps}
          form="test-form"
          autoFocus={true}
          spellCheck={false}
        />
      )

      const textarea = screen.getByRole('textbox')
      expect(textarea).toHaveAttribute('form', 'test-form')
      expect(textarea).toHaveAttribute('spellCheck', 'false')
    })

    it('supports wrap attribute', () => {
      render(<Textarea {...defaultProps} wrap="soft" />)

      const textarea = screen.getByRole('textbox')
      expect(textarea).toHaveAttribute('wrap', 'soft')
    })

    it('passes through all HTMLTextareaElement attributes', () => {
      render(
        <Textarea
          {...defaultProps}
          dir="rtl"
          lang="en"
          title="Textarea title"
          tabIndex={2}
        />
      )

      const textarea = screen.getByRole('textbox')
      expect(textarea).toHaveAttribute('dir', 'rtl')
      expect(textarea).toHaveAttribute('lang', 'en')
      expect(textarea).toHaveAttribute('title', 'Textarea title')
      expect(textarea).toHaveAttribute('tabIndex', '2')
    })
  })
})

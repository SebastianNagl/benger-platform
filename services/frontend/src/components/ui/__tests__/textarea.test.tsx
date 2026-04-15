import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import React from 'react'
import { Textarea } from '../textarea'

describe('Textarea', () => {
  describe('Basic rendering', () => {
    it('renders correctly as textarea element', () => {
      render(<Textarea data-testid="textarea" />)

      const textarea = screen.getByTestId('textarea')
      expect(textarea).toBeInTheDocument()
      expect(textarea.tagName).toBe('TEXTAREA')
    })

    it('applies default textarea styles', () => {
      render(<Textarea data-testid="textarea" />)

      const textarea = screen.getByTestId('textarea')
      expect(textarea).toHaveClass(
        'flex',
        'min-h-[80px]',
        'w-full',
        'rounded-md',
        'border',
        'border-zinc-300',
        'bg-white',
        'px-3',
        'py-2',
        'text-sm'
      )
    })

    it('includes focus styles', () => {
      render(<Textarea data-testid="textarea" />)

      const textarea = screen.getByTestId('textarea')
      expect(textarea).toHaveClass(
        'focus-visible:outline-none',
        'focus-visible:ring-2',
        'focus-visible:ring-emerald-500',
        'focus-visible:ring-offset-2'
      )
    })

    it('includes disabled styles', () => {
      render(<Textarea data-testid="textarea" />)

      const textarea = screen.getByTestId('textarea')
      expect(textarea).toHaveClass(
        'disabled:cursor-not-allowed',
        'disabled:opacity-50'
      )
    })

    it('includes dark mode styles', () => {
      render(<Textarea data-testid="textarea" />)

      const textarea = screen.getByTestId('textarea')
      expect(textarea).toHaveClass(
        'dark:border-zinc-600',
        'dark:bg-zinc-800',
        'dark:ring-offset-zinc-950',
        'dark:placeholder:text-zinc-400',
        'dark:focus-visible:ring-emerald-400'
      )
    })
  })

  describe('Value and onChange', () => {
    it('displays initial value', () => {
      render(
        <Textarea
          value="initial content"
          onChange={() => {}}
          data-testid="textarea"
        />
      )

      const textarea = screen.getByTestId('textarea') as HTMLTextAreaElement
      expect(textarea.value).toBe('initial content')
    })

    it('handles value changes', async () => {
      const handleChange = jest.fn()
      const user = userEvent.setup()

      render(<Textarea onChange={handleChange} data-testid="textarea" />)

      const textarea = screen.getByTestId('textarea')
      await user.type(textarea, 'test')

      expect(handleChange).toHaveBeenCalledTimes(4) // Once for each character
    })

    it('handles controlled textarea', async () => {
      const ControlledTextarea = () => {
        const [value, setValue] = React.useState('')

        return (
          <Textarea
            value={value}
            onChange={(e) => setValue(e.target.value)}
            data-testid="controlled-textarea"
          />
        )
      }

      const user = userEvent.setup()
      render(<ControlledTextarea />)

      const textarea = screen.getByTestId(
        'controlled-textarea'
      ) as HTMLTextAreaElement
      await user.type(textarea, 'controlled')

      expect(textarea.value).toBe('controlled')
    })

    it('handles multiline content', async () => {
      const user = userEvent.setup()
      render(<Textarea data-testid="textarea" />)

      const textarea = screen.getByTestId('textarea') as HTMLTextAreaElement
      await user.type(textarea, 'Line 1{Enter}Line 2{Enter}Line 3')

      expect(textarea.value).toBe('Line 1\nLine 2\nLine 3')
    })
  })

  describe('Placeholder', () => {
    it('displays placeholder text', () => {
      render(
        <Textarea placeholder="Enter your text here" data-testid="textarea" />
      )

      const textarea = screen.getByTestId('textarea')
      expect(textarea).toHaveAttribute('placeholder', 'Enter your text here')
    })

    it('applies placeholder styles', () => {
      render(<Textarea placeholder="Placeholder" data-testid="textarea" />)

      const textarea = screen.getByTestId('textarea')
      expect(textarea).toHaveClass('placeholder:text-zinc-500')
    })
  })

  describe('Disabled state', () => {
    it('is enabled by default', () => {
      render(<Textarea data-testid="textarea" />)

      const textarea = screen.getByTestId('textarea')
      expect(textarea).not.toBeDisabled()
    })

    it('can be disabled', () => {
      render(<Textarea disabled data-testid="textarea" />)

      const textarea = screen.getByTestId('textarea')
      expect(textarea).toBeDisabled()
    })

    it('does not accept input when disabled', async () => {
      const user = userEvent.setup()
      render(<Textarea disabled data-testid="textarea" />)

      const textarea = screen.getByTestId('textarea') as HTMLTextAreaElement
      await user.type(textarea, 'should not work')

      expect(textarea.value).toBe('')
    })
  })

  describe('Required and validation', () => {
    it('can be marked as required', () => {
      render(<Textarea required data-testid="textarea" />)

      const textarea = screen.getByTestId('textarea')
      expect(textarea).toBeRequired()
    })

    it('supports maxLength attribute', () => {
      render(<Textarea maxLength={100} data-testid="textarea" />)

      const textarea = screen.getByTestId('textarea')
      expect(textarea).toHaveAttribute('maxLength', '100')
    })

    it('supports minLength attribute', () => {
      render(<Textarea minLength={10} data-testid="textarea" />)

      const textarea = screen.getByTestId('textarea')
      expect(textarea).toHaveAttribute('minLength', '10')
    })

    it('supports rows and cols attributes', () => {
      render(<Textarea rows={5} cols={40} data-testid="textarea" />)

      const textarea = screen.getByTestId('textarea')
      expect(textarea).toHaveAttribute('rows', '5')
      expect(textarea).toHaveAttribute('cols', '40')
    })
  })

  describe('Event handling', () => {
    it('handles focus events', () => {
      const handleFocus = jest.fn()
      render(<Textarea onFocus={handleFocus} data-testid="textarea" />)

      const textarea = screen.getByTestId('textarea')
      fireEvent.focus(textarea)

      expect(handleFocus).toHaveBeenCalledTimes(1)
    })

    it('handles blur events', () => {
      const handleBlur = jest.fn()
      render(<Textarea onBlur={handleBlur} data-testid="textarea" />)

      const textarea = screen.getByTestId('textarea')
      fireEvent.focus(textarea)
      fireEvent.blur(textarea)

      expect(handleBlur).toHaveBeenCalledTimes(1)
    })

    it('handles keydown events', () => {
      const handleKeyDown = jest.fn()
      render(<Textarea onKeyDown={handleKeyDown} data-testid="textarea" />)

      const textarea = screen.getByTestId('textarea')
      fireEvent.keyDown(textarea, { key: 'Enter' })

      expect(handleKeyDown).toHaveBeenCalledTimes(1)
    })

    it('handles paste events', () => {
      const handlePaste = jest.fn()
      render(<Textarea onPaste={handlePaste} data-testid="textarea" />)

      const textarea = screen.getByTestId('textarea')
      fireEvent.paste(textarea)

      expect(handlePaste).toHaveBeenCalledTimes(1)
    })

    it('handles input events', () => {
      const handleInput = jest.fn()
      render(<Textarea onInput={handleInput} data-testid="textarea" />)

      const textarea = screen.getByTestId('textarea')
      fireEvent.input(textarea, { target: { value: 'test' } })

      expect(handleInput).toHaveBeenCalledTimes(1)
    })
  })

  describe('Custom props and styling', () => {
    it('applies custom className', () => {
      render(<Textarea className="custom-class" data-testid="textarea" />)

      const textarea = screen.getByTestId('textarea')
      expect(textarea).toHaveClass('custom-class')
      expect(textarea).toHaveClass('flex') // Default styles still applied
    })

    it('forwards HTML textarea attributes', () => {
      render(
        <Textarea
          id="test-textarea"
          name="test-name"
          autoComplete="off"
          aria-label="Test textarea"
          data-testid="textarea"
          readOnly
        />
      )

      const textarea = screen.getByTestId('textarea')
      expect(textarea).toHaveAttribute('id', 'test-textarea')
      expect(textarea).toHaveAttribute('name', 'test-name')
      expect(textarea).toHaveAttribute('autoComplete', 'off')
      expect(textarea).toHaveAttribute('aria-label', 'Test textarea')
      expect(textarea).toHaveAttribute('readOnly')
    })

    it('supports wrap attribute', () => {
      render(<Textarea wrap="hard" data-testid="textarea" />)

      const textarea = screen.getByTestId('textarea')
      expect(textarea).toHaveAttribute('wrap', 'hard')
    })

    it('supports form attribute', () => {
      render(<Textarea form="test-form" data-testid="textarea" />)

      const textarea = screen.getByTestId('textarea')
      expect(textarea).toHaveAttribute('form', 'test-form')
    })
  })

  describe('Ref forwarding', () => {
    it('forwards ref correctly', () => {
      const ref = React.createRef<HTMLTextAreaElement>()

      render(<Textarea ref={ref} data-testid="textarea" />)

      expect(ref.current).toBeInstanceOf(HTMLTextAreaElement)
      expect(ref.current).toBe(screen.getByTestId('textarea'))
    })

    it('allows ref access to textarea methods', () => {
      const ref = React.createRef<HTMLTextAreaElement>()

      render(<Textarea ref={ref} data-testid="textarea" />)

      expect(ref.current?.focus).toBeDefined()
      expect(ref.current?.blur).toBeDefined()
      expect(ref.current?.select).toBeDefined()
    })

    it('can set cursor position via ref', () => {
      const ref = React.createRef<HTMLTextAreaElement>()

      render(<Textarea ref={ref} value="test content" onChange={() => {}} />)

      if (ref.current) {
        ref.current.setSelectionRange(5, 5)
        expect(ref.current.selectionStart).toBe(5)
        expect(ref.current.selectionEnd).toBe(5)
      }
    })
  })

  describe('Focus management', () => {
    it('can be focused programmatically', () => {
      render(<Textarea data-testid="textarea" />)

      const textarea = screen.getByTestId('textarea')
      textarea.focus()

      expect(textarea).toHaveFocus()
    })

    it('can be blurred programmatically', () => {
      render(<Textarea data-testid="textarea" />)

      const textarea = screen.getByTestId('textarea')
      textarea.focus()
      textarea.blur()

      expect(textarea).not.toHaveFocus()
    })

    it('maintains focus during typing', async () => {
      const user = userEvent.setup()
      render(<Textarea data-testid="textarea" />)

      const textarea = screen.getByTestId('textarea')
      await user.click(textarea)
      await user.type(textarea, 'typing')

      expect(textarea).toHaveFocus()
    })
  })

  describe('Accessibility', () => {
    it('is accessible by default', () => {
      render(<Textarea data-testid="textarea" />)

      const textarea = screen.getByTestId('textarea')
      expect(textarea).toBeInTheDocument()
      expect(textarea.tagName).toBe('TEXTAREA')
    })

    it('supports aria attributes', () => {
      render(
        <Textarea
          aria-describedby="help-text"
          aria-invalid="true"
          aria-required="true"
          data-testid="textarea"
        />
      )

      const textarea = screen.getByTestId('textarea')
      expect(textarea).toHaveAttribute('aria-describedby', 'help-text')
      expect(textarea).toHaveAttribute('aria-invalid', 'true')
      expect(textarea).toHaveAttribute('aria-required', 'true')
    })

    it('works with labels', () => {
      render(
        <div>
          <label htmlFor="test-textarea">Test Label</label>
          <Textarea id="test-textarea" data-testid="textarea" />
        </div>
      )

      const textarea = screen.getByLabelText('Test Label')
      expect(textarea).toBe(screen.getByTestId('textarea'))
    })

    it('supports aria-labelledby', () => {
      render(
        <div>
          <h3 id="textarea-label">Description</h3>
          <Textarea aria-labelledby="textarea-label" data-testid="textarea" />
        </div>
      )

      const textarea = screen.getByTestId('textarea')
      expect(textarea).toHaveAttribute('aria-labelledby', 'textarea-label')
    })
  })

  describe('Edge cases', () => {
    it('handles empty value', () => {
      render(<Textarea value="" onChange={() => {}} data-testid="textarea" />)

      const textarea = screen.getByTestId('textarea') as HTMLTextAreaElement
      expect(textarea.value).toBe('')
    })

    it('handles undefined value', () => {
      render(
        <Textarea
          value={undefined}
          onChange={() => {}}
          data-testid="textarea"
        />
      )

      const textarea = screen.getByTestId('textarea')
      expect(textarea).toBeInTheDocument() // Should not crash
    })

    it('handles very long content', () => {
      const longValue = 'a'.repeat(10000)
      render(
        <Textarea
          value={longValue}
          onChange={() => {}}
          data-testid="textarea"
        />
      )

      const textarea = screen.getByTestId('textarea') as HTMLTextAreaElement
      expect(textarea.value).toBe(longValue)
    })

    it('handles special characters and symbols', async () => {
      const user = userEvent.setup()
      const specialText = 'Special chars: !@#$%^&*()_+-='

      render(<Textarea data-testid="textarea" />)

      const textarea = screen.getByTestId('textarea') as HTMLTextAreaElement
      await user.type(textarea, specialText)

      expect(textarea.value).toBe(specialText)
    })

    it('handles unicode characters', async () => {
      const user = userEvent.setup()
      const unicodeText = 'Unicode: 你好 🌟 ñáéíóú'

      render(<Textarea data-testid="textarea" />)

      const textarea = screen.getByTestId('textarea') as HTMLTextAreaElement
      await user.type(textarea, unicodeText)

      expect(textarea.value).toBe(unicodeText)
    })

    it('handles whitespace preservation', async () => {
      const user = userEvent.setup()

      render(<Textarea data-testid="textarea" />)

      const textarea = screen.getByTestId('textarea') as HTMLTextAreaElement
      await user.type(textarea, '   spaced   content   ')

      expect(textarea.value).toBe('   spaced   content   ')
    })
  })

  describe('Resize behavior', () => {
    it('has default min height', () => {
      render(<Textarea data-testid="textarea" />)

      const textarea = screen.getByTestId('textarea')
      expect(textarea).toHaveClass('min-h-[80px]')
    })

    it('allows custom height via className', () => {
      render(<Textarea className="min-h-[120px]" data-testid="textarea" />)

      const textarea = screen.getByTestId('textarea')
      expect(textarea).toHaveClass('min-h-[120px]')
    })

    it('supports resize attribute', () => {
      render(<Textarea style={{ resize: 'vertical' }} data-testid="textarea" />)

      const textarea = screen.getByTestId('textarea')
      expect(textarea).toHaveStyle('resize: vertical')
    })
  })

  describe('Display name', () => {
    it('has correct display name for debugging', () => {
      expect(Textarea.displayName).toBe('Textarea')
    })
  })

  describe('Performance considerations', () => {
    it('does not cause excessive re-renders', () => {
      const renderSpy = jest.fn()

      const TestComponent = () => {
        renderSpy()
        const [value, setValue] = React.useState('')

        return (
          <Textarea
            value={value}
            onChange={(e) => setValue(e.target.value)}
            data-testid="textarea"
          />
        )
      }

      render(<TestComponent />)

      // Initial render
      expect(renderSpy).toHaveBeenCalledTimes(1)
    })

    it('handles rapid typing without issues', async () => {
      const user = userEvent.setup()
      const handleChange = jest.fn()

      render(<Textarea onChange={handleChange} data-testid="textarea" />)

      const textarea = screen.getByTestId('textarea')
      await user.type(textarea, 'rapid typing test', { delay: 1 })

      expect(handleChange).toHaveBeenCalledTimes(17) // Once per character
    })
  })
})

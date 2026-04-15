import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import React from 'react'
import { Input } from '../input'

describe('Input', () => {
  describe('Basic rendering', () => {
    it('renders correctly as input element', () => {
      render(<Input data-testid="input" />)

      const input = screen.getByTestId('input')
      expect(input).toBeInTheDocument()
      expect(input.tagName).toBe('INPUT')
    })

    it('applies default input styles', () => {
      render(<Input data-testid="input" />)

      const input = screen.getByTestId('input')
      expect(input).toHaveClass(
        'flex',
        'h-10',
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
      render(<Input data-testid="input" />)

      const input = screen.getByTestId('input')
      expect(input).toHaveClass(
        'focus-visible:outline-none',
        'focus-visible:ring-2',
        'focus-visible:ring-emerald-500',
        'focus-visible:ring-offset-2'
      )
    })

    it('includes disabled styles', () => {
      render(<Input data-testid="input" />)

      const input = screen.getByTestId('input')
      expect(input).toHaveClass(
        'disabled:cursor-not-allowed',
        'disabled:opacity-50'
      )
    })

    it('includes dark mode styles', () => {
      render(<Input data-testid="input" />)

      const input = screen.getByTestId('input')
      expect(input).toHaveClass(
        'dark:border-zinc-600',
        'dark:bg-zinc-800',
        'dark:ring-offset-zinc-950',
        'dark:placeholder:text-zinc-400',
        'dark:focus-visible:ring-emerald-400'
      )
    })
  })

  describe('Input types', () => {
    it('renders text input by default', () => {
      render(<Input data-testid="input" />)

      const input = screen.getByTestId('input')
      expect(input.tagName).toBe('INPUT')
    })

    it('renders with custom type', () => {
      render(<Input type="email" data-testid="input" />)

      const input = screen.getByTestId('input')
      expect(input).toHaveAttribute('type', 'email')
    })

    it('renders password input', () => {
      render(<Input type="password" data-testid="input" />)

      const input = screen.getByTestId('input')
      expect(input).toHaveAttribute('type', 'password')
    })

    it('renders number input', () => {
      render(<Input type="number" data-testid="input" />)

      const input = screen.getByTestId('input')
      expect(input).toHaveAttribute('type', 'number')
    })

    it('renders file input with file-specific styles', () => {
      render(<Input type="file" data-testid="input" />)

      const input = screen.getByTestId('input')
      expect(input).toHaveAttribute('type', 'file')
      expect(input).toHaveClass(
        'file:border-0',
        'file:bg-transparent',
        'file:text-sm',
        'file:font-medium'
      )
    })
  })

  describe('Value and onChange', () => {
    it('displays initial value', () => {
      render(
        <Input value="initial value" onChange={() => {}} data-testid="input" />
      )

      const input = screen.getByTestId('input') as HTMLInputElement
      expect(input.value).toBe('initial value')
    })

    it('handles value changes', async () => {
      const handleChange = jest.fn()
      const user = userEvent.setup()

      render(<Input onChange={handleChange} data-testid="input" />)

      const input = screen.getByTestId('input')
      await user.type(input, 'test')

      expect(handleChange).toHaveBeenCalledTimes(4) // Once for each character
    })

    it('handles controlled input', async () => {
      const ControlledInput = () => {
        const [value, setValue] = React.useState('')

        return (
          <Input
            value={value}
            onChange={(e) => setValue(e.target.value)}
            data-testid="controlled-input"
          />
        )
      }

      const user = userEvent.setup()
      render(<ControlledInput />)

      const input = screen.getByTestId('controlled-input') as HTMLInputElement
      await user.type(input, 'controlled')

      expect(input.value).toBe('controlled')
    })
  })

  describe('Placeholder', () => {
    it('displays placeholder text', () => {
      render(<Input placeholder="Enter text here" data-testid="input" />)

      const input = screen.getByTestId('input')
      expect(input).toHaveAttribute('placeholder', 'Enter text here')
    })

    it('applies placeholder styles', () => {
      render(<Input placeholder="Placeholder" data-testid="input" />)

      const input = screen.getByTestId('input')
      expect(input).toHaveClass('placeholder:text-zinc-500')
    })
  })

  describe('Disabled state', () => {
    it('is enabled by default', () => {
      render(<Input data-testid="input" />)

      const input = screen.getByTestId('input')
      expect(input).not.toBeDisabled()
    })

    it('can be disabled', () => {
      render(<Input disabled data-testid="input" />)

      const input = screen.getByTestId('input')
      expect(input).toBeDisabled()
    })

    it('does not accept input when disabled', async () => {
      const user = userEvent.setup()
      render(<Input disabled data-testid="input" />)

      const input = screen.getByTestId('input') as HTMLInputElement
      await user.type(input, 'should not work')

      expect(input.value).toBe('')
    })
  })

  describe('Required and validation', () => {
    it('can be marked as required', () => {
      render(<Input required data-testid="input" />)

      const input = screen.getByTestId('input')
      expect(input).toBeRequired()
    })

    it('supports validation patterns', () => {
      render(<Input pattern="[0-9]+" data-testid="input" />)

      const input = screen.getByTestId('input')
      expect(input).toHaveAttribute('pattern', '[0-9]+')
    })

    it('supports min and max for number inputs', () => {
      render(<Input type="number" min="0" max="100" data-testid="input" />)

      const input = screen.getByTestId('input')
      expect(input).toHaveAttribute('min', '0')
      expect(input).toHaveAttribute('max', '100')
    })
  })

  describe('Event handling', () => {
    it('handles focus events', () => {
      const handleFocus = jest.fn()
      render(<Input onFocus={handleFocus} data-testid="input" />)

      const input = screen.getByTestId('input')
      fireEvent.focus(input)

      expect(handleFocus).toHaveBeenCalledTimes(1)
    })

    it('handles blur events', () => {
      const handleBlur = jest.fn()
      render(<Input onBlur={handleBlur} data-testid="input" />)

      const input = screen.getByTestId('input')
      fireEvent.focus(input)
      fireEvent.blur(input)

      expect(handleBlur).toHaveBeenCalledTimes(1)
    })

    it('handles keydown events', () => {
      const handleKeyDown = jest.fn()
      render(<Input onKeyDown={handleKeyDown} data-testid="input" />)

      const input = screen.getByTestId('input')
      fireEvent.keyDown(input, { key: 'Enter' })

      expect(handleKeyDown).toHaveBeenCalledTimes(1)
    })

    it('handles paste events', () => {
      const handlePaste = jest.fn()
      render(<Input onPaste={handlePaste} data-testid="input" />)

      const input = screen.getByTestId('input')
      fireEvent.paste(input)

      expect(handlePaste).toHaveBeenCalledTimes(1)
    })
  })

  describe('Custom props and styling', () => {
    it('applies custom className', () => {
      render(<Input className="custom-class" data-testid="input" />)

      const input = screen.getByTestId('input')
      expect(input).toHaveClass('custom-class')
      expect(input).toHaveClass('flex') // Default styles still applied
    })

    it('forwards HTML input attributes', () => {
      render(
        <Input
          id="test-input"
          name="test-name"
          autoComplete="email"
          aria-label="Test input"
          data-testid="input"
        />
      )

      const input = screen.getByTestId('input')
      expect(input).toHaveAttribute('id', 'test-input')
      expect(input).toHaveAttribute('name', 'test-name')
      expect(input).toHaveAttribute('autoComplete', 'email')
      expect(input).toHaveAttribute('aria-label', 'Test input')
    })

    it('supports maxLength attribute', () => {
      render(<Input maxLength={10} data-testid="input" />)

      const input = screen.getByTestId('input')
      expect(input).toHaveAttribute('maxLength', '10')
    })
  })

  describe('Ref forwarding', () => {
    it('forwards ref correctly', () => {
      const ref = React.createRef<HTMLInputElement>()

      render(<Input ref={ref} data-testid="input" />)

      expect(ref.current).toBeInstanceOf(HTMLInputElement)
      expect(ref.current).toBe(screen.getByTestId('input'))
    })

    it('allows ref access to input methods', () => {
      const ref = React.createRef<HTMLInputElement>()

      render(<Input ref={ref} data-testid="input" />)

      expect(ref.current?.focus).toBeDefined()
      expect(ref.current?.blur).toBeDefined()
      expect(ref.current?.select).toBeDefined()
    })
  })

  describe('Focus management', () => {
    it('can be focused programmatically', () => {
      render(<Input data-testid="input" />)

      const input = screen.getByTestId('input')
      input.focus()

      expect(input).toHaveFocus()
    })

    it('can be blurred programmatically', () => {
      render(<Input data-testid="input" />)

      const input = screen.getByTestId('input')
      input.focus()
      input.blur()

      expect(input).not.toHaveFocus()
    })
  })

  describe('Accessibility', () => {
    it('is accessible by default', () => {
      render(<Input data-testid="input" />)

      const input = screen.getByTestId('input')
      expect(input).toBeInTheDocument()
      expect(input.tagName).toBe('INPUT')
    })

    it('supports aria attributes', () => {
      render(
        <Input
          aria-describedby="help-text"
          aria-invalid="true"
          aria-required="true"
          data-testid="input"
        />
      )

      const input = screen.getByTestId('input')
      expect(input).toHaveAttribute('aria-describedby', 'help-text')
      expect(input).toHaveAttribute('aria-invalid', 'true')
      expect(input).toHaveAttribute('aria-required', 'true')
    })

    it('works with labels', () => {
      render(
        <div>
          <label htmlFor="test-input">Test Label</label>
          <Input id="test-input" data-testid="input" />
        </div>
      )

      const input = screen.getByLabelText('Test Label')
      expect(input).toBe(screen.getByTestId('input'))
    })
  })

  describe('Edge cases', () => {
    it('handles empty value', () => {
      render(<Input value="" onChange={() => {}} data-testid="input" />)

      const input = screen.getByTestId('input') as HTMLInputElement
      expect(input.value).toBe('')
    })

    it('handles undefined value', () => {
      render(
        <Input value={undefined} onChange={() => {}} data-testid="input" />
      )

      const input = screen.getByTestId('input')
      expect(input).toBeInTheDocument() // Should not crash
    })

    it('handles very long values', () => {
      const longValue = 'a'.repeat(1000)
      render(
        <Input value={longValue} onChange={() => {}} data-testid="input" />
      )

      const input = screen.getByTestId('input') as HTMLInputElement
      expect(input.value).toBe(longValue)
    })

    it('handles special characters', async () => {
      const user = userEvent.setup()
      const specialChars = '!@#$%^&*()_+-='

      render(<Input data-testid="input" />)

      const input = screen.getByTestId('input') as HTMLInputElement
      await user.type(input, specialChars)

      expect(input.value).toBe(specialChars)
    })
  })

  describe('Display name', () => {
    it('has correct display name for debugging', () => {
      expect(Input.displayName).toBe('Input')
    })
  })
})

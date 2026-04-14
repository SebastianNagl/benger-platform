import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Button } from '../button'

describe('Button', () => {
  describe('Basic rendering', () => {
    it('renders correctly with default props', () => {
      render(<Button>Click me</Button>)

      const button = screen.getByRole('button', { name: 'Click me' })
      expect(button).toBeInTheDocument()
      expect(button).toHaveTextContent('Click me')
    })

    it('renders as a button element by default', () => {
      render(<Button>Default button</Button>)

      const element = screen.getByRole('button')
      expect(element.tagName).toBe('BUTTON')
    })

    it('renders as span when as="span" is provided', () => {
      render(<Button as="span">Span button</Button>)

      const element = screen.getByText('Span button')
      expect(element.tagName).toBe('SPAN')
    })
  })

  describe('Variants', () => {
    it('applies default variant styles', () => {
      render(<Button>Default</Button>)

      const button = screen.getByRole('button')
      expect(button).toHaveClass(
        'bg-emerald-600',
        'text-white',
        'hover:bg-emerald-700',
        'focus:ring-emerald-500'
      )
    })

    it('applies outline variant styles', () => {
      render(<Button variant="outline">Outline</Button>)

      const button = screen.getByRole('button')
      expect(button).toHaveClass(
        'border',
        'border-zinc-300',
        'bg-transparent',
        'hover:bg-zinc-100'
      )
    })

    it('applies ghost variant styles', () => {
      render(<Button variant="ghost">Ghost</Button>)

      const button = screen.getByRole('button')
      expect(button).toHaveClass('hover:bg-zinc-100')
    })

    it('applies destructive variant styles', () => {
      render(<Button variant="destructive">Destructive</Button>)

      const button = screen.getByRole('button')
      expect(button).toHaveClass(
        'bg-red-600',
        'text-white',
        'hover:bg-red-700',
        'focus:ring-red-500'
      )
    })
  })

  describe('Sizes', () => {
    it('applies default size styles', () => {
      render(<Button>Default size</Button>)

      const button = screen.getByRole('button')
      expect(button).toHaveClass('px-4', 'py-2', 'text-sm')
    })

    it('applies small size styles', () => {
      render(<Button size="sm">Small</Button>)

      const button = screen.getByRole('button')
      expect(button).toHaveClass('px-3', 'py-1.5', 'text-xs')
    })

    it('applies large size styles', () => {
      render(<Button size="lg">Large</Button>)

      const button = screen.getByRole('button')
      expect(button).toHaveClass('px-6', 'py-3', 'text-base')
    })
  })

  describe('Loading state', () => {
    it('shows loading spinner when loading=true', () => {
      render(<Button loading>Loading button</Button>)

      const button = screen.getByRole('button')
      expect(button).toHaveClass('cursor-wait')
      expect(button).toBeDisabled()

      const spinner = button.querySelector('svg')
      expect(spinner).toBeInTheDocument()
      expect(spinner).toHaveClass('animate-spin')
    })

    it('still displays children when loading', () => {
      render(<Button loading>Save changes</Button>)

      const button = screen.getByRole('button')
      expect(button).toHaveTextContent('Save changes')
    })

    it('does not show spinner when loading=false', () => {
      render(<Button loading={false}>Not loading</Button>)

      const button = screen.getByRole('button')
      expect(button).not.toHaveClass('cursor-wait')
      expect(button).not.toBeDisabled()

      const spinner = button.querySelector('svg')
      expect(spinner).not.toBeInTheDocument()
    })
  })

  describe('Disabled state', () => {
    it('is disabled when disabled=true', () => {
      render(<Button disabled>Disabled button</Button>)

      const button = screen.getByRole('button')
      expect(button).toBeDisabled()
      expect(button).toHaveClass(
        'disabled:opacity-50',
        'disabled:pointer-events-none'
      )
    })

    it('is disabled when loading=true', () => {
      render(<Button loading>Loading button</Button>)

      const button = screen.getByRole('button')
      expect(button).toBeDisabled()
    })

    it('is not disabled by default', () => {
      render(<Button>Enabled button</Button>)

      const button = screen.getByRole('button')
      expect(button).not.toBeDisabled()
    })
  })

  describe('Event handling', () => {
    it('handles click events', async () => {
      const handleClick = jest.fn()
      const user = userEvent.setup()

      render(<Button onClick={handleClick}>Click me</Button>)

      await user.click(screen.getByRole('button'))
      expect(handleClick).toHaveBeenCalledTimes(1)
    })

    it('does not handle click when disabled', async () => {
      const handleClick = jest.fn()
      const user = userEvent.setup()

      render(
        <Button onClick={handleClick} disabled>
          Disabled
        </Button>
      )

      await user.click(screen.getByRole('button'))
      expect(handleClick).not.toHaveBeenCalled()
    })

    it('does not handle click when loading', async () => {
      const handleClick = jest.fn()
      const user = userEvent.setup()

      render(
        <Button onClick={handleClick} loading>
          Loading
        </Button>
      )

      await user.click(screen.getByRole('button'))
      expect(handleClick).not.toHaveBeenCalled()
    })

    it('handles keyboard events', () => {
      const handleKeyDown = jest.fn()

      render(<Button onKeyDown={handleKeyDown}>Button</Button>)

      const button = screen.getByRole('button')
      fireEvent.keyDown(button, { key: 'Enter' })

      expect(handleKeyDown).toHaveBeenCalledTimes(1)
    })
  })

  describe('Custom props', () => {
    it('applies custom className alongside default styles', () => {
      render(<Button className="custom-class">Custom</Button>)

      const button = screen.getByRole('button')
      expect(button).toHaveClass('custom-class')
      expect(button).toHaveClass('bg-emerald-600') // Default styles still applied
    })

    it('forwards HTML button attributes', () => {
      render(
        <Button
          type="submit"
          form="test-form"
          data-testid="custom-button"
          aria-label="Custom aria label"
        >
          Submit
        </Button>
      )

      const button = screen.getByRole('button')
      expect(button).toHaveAttribute('type', 'submit')
      expect(button).toHaveAttribute('form', 'test-form')
      expect(button).toHaveAttribute('data-testid', 'custom-button')
      expect(button).toHaveAttribute('aria-label', 'Custom aria label')
    })

    it('sets correct tabIndex for focusability', () => {
      render(<Button tabIndex={0}>Focusable</Button>)

      const button = screen.getByRole('button')
      expect(button).toHaveAttribute('tabIndex', '0')
    })
  })

  describe('Focus and accessibility', () => {
    it('is focusable by default', () => {
      render(<Button>Focusable button</Button>)

      const button = screen.getByRole('button')
      button.focus()
      expect(button).toHaveFocus()
    })

    it('applies focus ring styles', () => {
      render(<Button>Focus ring</Button>)

      const button = screen.getByRole('button')
      expect(button).toHaveClass(
        'focus:outline-none',
        'focus:ring-2',
        'focus:ring-offset-2'
      )
    })

    it('has proper accessibility attributes', () => {
      render(<Button>Accessible button</Button>)

      const button = screen.getByRole('button')
      expect(button).toBeInTheDocument()
      expect(button.tagName).toBe('BUTTON') // Should be a button element
    })
  })

  describe('Combination scenarios', () => {
    it('combines variant and size correctly', () => {
      render(
        <Button variant="outline" size="lg">
          Large outline
        </Button>
      )

      const button = screen.getByRole('button')
      expect(button).toHaveClass('border', 'border-zinc-300') // Outline variant
      expect(button).toHaveClass('px-6', 'py-3', 'text-base') // Large size
    })

    it('handles loading state with custom variant', () => {
      render(
        <Button variant="destructive" loading>
          Loading destructive
        </Button>
      )

      const button = screen.getByRole('button')
      expect(button).toHaveClass('bg-red-600') // Destructive variant
      expect(button).toHaveClass('cursor-wait') // Loading state
      expect(button).toBeDisabled()
    })

    it('handles all props together', () => {
      const handleClick = jest.fn()

      render(
        <Button
          variant="outline"
          size="sm"
          loading={false}
          disabled={false}
          onClick={handleClick}
          className="custom-class"
          data-testid="complex-button"
        >
          Complex button
        </Button>
      )

      const button = screen.getByRole('button')
      expect(button).toHaveClass('border', 'border-zinc-300') // Outline
      expect(button).toHaveClass('px-3', 'py-1.5', 'text-xs') // Small
      expect(button).toHaveClass('custom-class')
      expect(button).not.toBeDisabled()
      expect(button).toHaveAttribute('data-testid', 'complex-button')
    })
  })

  describe('Base styles', () => {
    it('always includes base styles', () => {
      render(<Button>Base styles</Button>)

      const button = screen.getByRole('button')
      expect(button).toHaveClass(
        'inline-flex',
        'items-center',
        'justify-center',
        'font-medium',
        'rounded-md',
        'transition-colors'
      )
    })
  })

  describe('Edge cases', () => {
    it('handles empty children', () => {
      render(<Button></Button>)

      const button = screen.getByRole('button')
      expect(button).toBeInTheDocument()
      expect(button).toHaveTextContent('')
    })

    it('handles complex children', () => {
      render(
        <Button>
          <span>Icon</span>
          <span>Text</span>
        </Button>
      )

      const button = screen.getByRole('button')
      expect(button).toHaveTextContent('IconText')
      expect(button.querySelector('span')).toBeInTheDocument()
    })

    it('maintains consistent styling with cn utility', () => {
      render(<Button className="bg-purple-500">Override styles</Button>)

      const button = screen.getByRole('button')
      // The cn utility should handle class conflicts properly
      expect(button).toHaveClass('bg-purple-500')
    })
  })
})

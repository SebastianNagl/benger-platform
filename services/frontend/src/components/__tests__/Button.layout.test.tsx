/**
 * @jest-environment jsdom
 */

import { ArrowLeftIcon } from '@heroicons/react/24/outline'
import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'
import { Button } from '../shared/Button'

describe('Button Layout Fix - Issue #107', () => {
  it('should render icon and text inline without wrapping', () => {
    render(
      <Button variant="outline" className="flex items-center gap-2">
        <ArrowLeftIcon className="h-4 w-4" />
        Back to Dashboard
      </Button>
    )

    const button = screen.getByRole('button')

    // Check that button has flex layout
    expect(button).toHaveClass('inline-flex', 'items-center')

    // Check that children are not wrapped in additional elements
    const icon = button.querySelector('svg')
    expect(icon).toBeInTheDocument()

    // Check that text is a direct child, not wrapped in span
    expect(button).toHaveTextContent('Back to Dashboard')

    // Ensure no text-center span wrapper exists
    const spans = button.querySelectorAll('span.text-center')
    expect(spans).toHaveLength(0)
  })

  it('should maintain consistent gap spacing', () => {
    render(
      <Button>
        <ArrowLeftIcon className="h-4 w-4" />
        Click Me
      </Button>
    )

    const button = screen.getByRole('button')

    // Default gap should be gap-2
    expect(button).toHaveClass('gap-2')
  })

  it('should work with arrow prop buttons', () => {
    render(<Button arrow="left">Navigate Back</Button>)

    const button = screen.getByRole('button')

    // Should have arrow icon and text inline
    const svg = button.querySelector('svg')
    expect(svg).toBeInTheDocument()
    expect(button).toHaveTextContent('Navigate Back')

    // No wrapper spans
    const spans = button.querySelectorAll('span.text-center')
    expect(spans).toHaveLength(0)
  })

  it('should work with all button variants', () => {
    const variants = [
      'primary',
      'secondary',
      'filled',
      'outline',
      'text',
    ] as const

    variants.forEach((variant) => {
      const { container } = render(
        <Button variant={variant} data-testid={`button-${variant}`}>
          <ArrowLeftIcon className="h-4 w-4" />
          {variant} Button
        </Button>
      )

      const button = screen.getByTestId(`button-${variant}`)

      // All variants should have inline-flex
      expect(button).toHaveClass('inline-flex')

      // No text-center wrapper
      const spans = button.querySelectorAll('span.text-center')
      expect(spans).toHaveLength(0)

      container.remove()
    })
  })

  it('should handle buttons without icons correctly', () => {
    render(<Button>Plain Text Button</Button>)

    const button = screen.getByRole('button')

    // Should still work without icons
    expect(button).toHaveTextContent('Plain Text Button')
    expect(button).toHaveClass('inline-flex')
  })

  it('should allow custom className to override gap', () => {
    render(
      <Button className="gap-4">
        <ArrowLeftIcon className="h-4 w-4" />
        Custom Gap
      </Button>
    )

    const button = screen.getByRole('button')

    // Custom gap should override default
    expect(button).toHaveClass('gap-4')
    expect(button).not.toHaveClass('gap-2')
  })
})

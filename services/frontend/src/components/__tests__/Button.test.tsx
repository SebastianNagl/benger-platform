/**
 * @jest-environment jsdom
 */

import { ArrowLeftIcon } from '@heroicons/react/24/outline'
import { render, screen } from '@testing-library/react'
import { Button } from '../shared/Button'

describe('Button Component', () => {
  it('renders text-only button correctly', () => {
    render(<Button>Click me</Button>)
    expect(screen.getByRole('button')).toBeInTheDocument()
    expect(screen.getByText('Click me')).toBeInTheDocument()
  })

  it('renders button with icon and text inline', () => {
    render(
      <Button variant="outline" className="flex items-center gap-2">
        <ArrowLeftIcon className="h-4 w-4" />
        Back to Dashboard
      </Button>
    )

    const button = screen.getByRole('button')
    expect(button).toBeInTheDocument()
    expect(screen.getByText('Back to Dashboard')).toBeInTheDocument()

    // Check that button has correct flex layout classes
    expect(button).toHaveClass('inline-flex', 'items-center', 'gap-2')
  })

  it('renders button with left arrow correctly', () => {
    render(<Button arrow="left">Back to Dashboard</Button>)

    const button = screen.getByRole('button')
    expect(button).toBeInTheDocument()
    expect(screen.getByText('Back to Dashboard')).toBeInTheDocument()

    // Check for arrow icon with left styling
    const svgElement = button.querySelector('svg')
    expect(svgElement).toBeInTheDocument()
    expect(svgElement).toHaveClass('rotate-180')
  })

  it('renders button with right arrow correctly', () => {
    render(<Button arrow="right">Continue</Button>)

    const button = screen.getByRole('button')
    expect(button).toBeInTheDocument()
    expect(screen.getByText('Continue')).toBeInTheDocument()

    // Check for arrow icon without rotation
    const svgElement = button.querySelector('svg')
    expect(svgElement).toBeInTheDocument()
    expect(svgElement).not.toHaveClass('rotate-180')
  })

  it('renders link button correctly', () => {
    render(<Button href="/dashboard">Go to Dashboard</Button>)

    const link = screen.getByRole('link')
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute('href', '/dashboard')
    expect(screen.getByText('Go to Dashboard')).toBeInTheDocument()
  })

  it('maintains consistent spacing between icon and text', () => {
    render(
      <Button variant="outline">
        <ArrowLeftIcon className="h-4 w-4" />
        Back to Dashboard
      </Button>
    )

    const button = screen.getByRole('button')
    // Check that default gap-2 is applied for consistent spacing
    expect(button).toHaveClass('gap-2')
  })

  it('handles all button variants correctly', () => {
    const variants = [
      'primary',
      'secondary',
      'filled',
      'outline',
      'text',
    ] as const

    variants.forEach((variant) => {
      const { unmount } = render(
        <Button variant={variant}>
          <ArrowLeftIcon className="h-4 w-4" />
          Test Button
        </Button>
      )

      const button = screen.getByRole('button')
      expect(button).toBeInTheDocument()
      expect(screen.getByText('Test Button')).toBeInTheDocument()

      unmount()
    })
  })

  it('does not have text-center span wrapper that causes line breaks', () => {
    render(
      <Button>
        <ArrowLeftIcon className="h-4 w-4" />
        Back to Dashboard
      </Button>
    )

    const button = screen.getByRole('button')
    const textCenterSpan = button.querySelector('span.text-center')

    // The problematic span wrapper should not exist
    expect(textCenterSpan).not.toBeInTheDocument()
  })

  it('allows icon and text to be direct children of flex container', () => {
    render(
      <Button>
        <ArrowLeftIcon className="h-4 w-4" data-testid="icon" />
        <span data-testid="text">Back to Dashboard</span>
      </Button>
    )

    const button = screen.getByRole('button')
    const icon = screen.getByTestId('icon')
    const text = screen.getByTestId('text')

    // Both icon and text should be direct children of the button
    expect(icon.parentElement).toBe(button)
    expect(text.parentElement).toBe(button)
  })
})

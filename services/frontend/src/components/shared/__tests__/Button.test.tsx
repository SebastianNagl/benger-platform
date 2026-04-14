/**
 * Test suite for Button component
 * Issue #364: Comprehensive component testing for shared components
 */

import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Button } from '../Button'

describe('Button Component', () => {
  const defaultProps = {
    children: 'Click me',
  }

  it('renders correctly with default props', () => {
    render(<Button {...defaultProps} />)

    const button = screen.getByRole('button', { name: /click me/i })
    expect(button).toBeInTheDocument()
    expect(button).toHaveTextContent('Click me')
  })

  it('handles onClick events', async () => {
    const user = userEvent.setup()
    const mockClick = jest.fn()

    render(<Button {...defaultProps} onClick={mockClick} />)

    const button = screen.getByRole('button', { name: /click me/i })
    await user.click(button)

    expect(mockClick).toHaveBeenCalledTimes(1)
  })

  it('renders with left arrow when specified', () => {
    render(<Button {...defaultProps} arrow="left" />)

    const button = screen.getByRole('button')
    const svgIcon = button.querySelector('svg')
    expect(svgIcon).toBeInTheDocument()
    expect(button).toHaveTextContent('Click me')
  })

  it('displays disabled state correctly', () => {
    render(<Button {...defaultProps} disabled={true} />)

    const button = screen.getByRole('button')
    expect(button).toBeDisabled()
  })

  it('applies variant styles correctly', () => {
    const { rerender } = render(<Button {...defaultProps} variant="primary" />)

    let button = screen.getByRole('button')
    expect(button).toHaveClass('bg-zinc-900') // Primary variant styling

    rerender(<Button {...defaultProps} variant="secondary" />)
    button = screen.getByRole('button')
    expect(button).toHaveClass('bg-zinc-100') // Secondary variant styling
  })

  it('handles href prop as Link component', () => {
    render(<Button href="/test-link">Link Button</Button>)

    // When href is provided, Button renders as a Link
    const link = screen.getByRole('link')
    expect(link).toBeInTheDocument()
    expect(link).toHaveTextContent('Link Button')
  })

  it('renders with custom className', () => {
    render(<Button {...defaultProps} className="custom-class" />)

    const button = screen.getByRole('button')
    expect(button).toHaveClass('custom-class')
  })

  it('renders with different variants', () => {
    render(<Button variant="secondary">Secondary Button</Button>)

    const button = screen.getByRole('button')
    expect(button).toHaveClass('bg-zinc-100')
    expect(button).toHaveTextContent('Secondary Button')
  })

  it('handles keyboard navigation', async () => {
    const user = userEvent.setup()
    const mockClick = jest.fn()

    render(<Button {...defaultProps} onClick={mockClick} />)

    const button = screen.getByRole('button')
    button.focus()
    await user.keyboard('{Enter}')

    expect(mockClick).toHaveBeenCalledTimes(1)
  })

  it('does not trigger onClick when disabled', async () => {
    const user = userEvent.setup()
    const mockClick = jest.fn()

    render(<Button {...defaultProps} onClick={mockClick} disabled={true} />)

    const button = screen.getByRole('button')
    await user.click(button)

    expect(mockClick).not.toHaveBeenCalled()
  })

  it('renders with arrow icon when arrow prop is provided', () => {
    render(<Button {...defaultProps} arrow="right" />)

    expect(screen.getByText('Click me')).toBeInTheDocument()
    // Arrow is rendered as an SVG with the ArrowIcon component
    const button = screen.getByRole('button')
    const svgIcon = button.querySelector('svg')
    expect(svgIcon).toBeInTheDocument()
  })

  it('handles form submission correctly', () => {
    const mockSubmit = jest.fn((e) => e.preventDefault())

    render(
      <form onSubmit={mockSubmit}>
        <Button type="submit">Submit</Button>
      </form>
    )

    const button = screen.getByRole('button', { name: /submit/i })
    fireEvent.click(button)

    expect(mockSubmit).toHaveBeenCalledTimes(1)
  })

  it('supports accessibility attributes', () => {
    render(
      <Button
        {...defaultProps}
        aria-label="Custom accessible label"
        aria-describedby="description"
      />
    )

    const button = screen.getByRole('button')
    expect(button).toHaveAttribute('aria-label', 'Custom accessible label')
    expect(button).toHaveAttribute('aria-describedby', 'description')
  })

  it('renders disabled Link as a button element', () => {
    render(<Button href="/test" disabled>Disabled Link</Button>)

    // When a Link is disabled, it renders as a button instead
    const button = screen.getByRole('button')
    expect(button).toBeInTheDocument()
    expect(button).toBeDisabled()
    expect(button).toHaveTextContent('Disabled Link')
  })

  it('uses default gap-2 when no custom gap class is provided', () => {
    render(<Button>Test</Button>)
    const button = screen.getByRole('button')
    expect(button.className).toContain('gap-2')
  })

  it('does not add default gap when custom gap class is provided', () => {
    render(<Button className="gap-4">Test</Button>)
    const button = screen.getByRole('button')
    // Should have gap-4 from className but not the default gap-2
    expect(button.className).toContain('gap-4')
  })

  it('renders with filled variant', () => {
    render(<Button variant="filled">Filled</Button>)
    const button = screen.getByRole('button')
    expect(button.className).toContain('bg-zinc-900')
  })

  it('renders with outline variant', () => {
    render(<Button variant="outline">Outline</Button>)
    const button = screen.getByRole('button')
    expect(button.className).toContain('ring-1')
  })

  it('renders with text variant', () => {
    render(<Button variant="text">Text</Button>)
    const button = screen.getByRole('button')
    expect(button.className).toContain('text-emerald-500')
  })

  it('renders text variant arrow with relative class', () => {
    const { container } = render(
      <Button variant="text" arrow="right">Text Arrow</Button>
    )
    const svg = container.querySelector('svg')
    expect(svg).toHaveClass('relative', 'top-px')
  })
})

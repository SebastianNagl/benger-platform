import { render, screen } from '@testing-library/react'
import { Badge } from '../badge'

describe('Badge', () => {
  it('renders children correctly', () => {
    render(<Badge>Badge Text</Badge>)
    expect(screen.getByText('Badge Text')).toBeInTheDocument()
  })

  it('renders with default variant', () => {
    const { container } = render(<Badge>Default</Badge>)
    const badge = container.firstChild as HTMLElement
    expect(badge).toHaveClass('bg-emerald-100')
    expect(badge).toHaveClass('text-emerald-800')
  })

  it('renders with secondary variant', () => {
    const { container } = render(<Badge variant="secondary">Secondary</Badge>)
    const badge = container.firstChild as HTMLElement
    expect(badge).toHaveClass('bg-zinc-100')
    expect(badge).toHaveClass('text-zinc-800')
  })

  it('renders with outline variant', () => {
    const { container } = render(<Badge variant="outline">Outline</Badge>)
    const badge = container.firstChild as HTMLElement
    expect(badge).toHaveClass('border')
    expect(badge).toHaveClass('border-zinc-200')
    expect(badge).toHaveClass('text-zinc-700')
  })

  it('renders with destructive variant', () => {
    const { container } = render(
      <Badge variant="destructive">Destructive</Badge>
    )
    const badge = container.firstChild as HTMLElement
    expect(badge).toHaveClass('bg-red-100')
    expect(badge).toHaveClass('text-red-800')
  })

  it('applies custom className', () => {
    const { container } = render(<Badge className="custom-badge">Custom</Badge>)
    const badge = container.firstChild as HTMLElement
    expect(badge).toHaveClass('custom-badge')
    // Should still have base classes
    expect(badge).toHaveClass('inline-flex')
    expect(badge).toHaveClass('rounded-full')
  })

  it('applies base styling classes', () => {
    const { container } = render(<Badge>Base Styles</Badge>)
    const badge = container.firstChild as HTMLElement
    expect(badge).toHaveClass('inline-flex')
    expect(badge).toHaveClass('items-center')
    expect(badge).toHaveClass('px-2.5')
    expect(badge).toHaveClass('py-0.5')
    expect(badge).toHaveClass('rounded-full')
    expect(badge).toHaveClass('text-xs')
    expect(badge).toHaveClass('font-medium')
  })

  it('renders as div element', () => {
    const { container } = render(<Badge>Div Badge</Badge>)
    const badge = container.firstChild as HTMLElement
    expect(badge.tagName).toBe('DIV')
  })

  it('passes through additional props', () => {
    const { container } = render(
      <Badge data-testid="test-badge" id="badge-id">
        Props Badge
      </Badge>
    )
    const badge = container.firstChild as HTMLElement
    expect(badge).toHaveAttribute('data-testid', 'test-badge')
    expect(badge).toHaveAttribute('id', 'badge-id')
  })

  it('handles onClick prop', () => {
    const handleClick = jest.fn()
    render(<Badge onClick={handleClick}>Clickable Badge</Badge>)

    const badge = screen.getByText('Clickable Badge')
    badge.click()
    expect(handleClick).toHaveBeenCalledTimes(1)
  })

  it('renders multiple badges independently', () => {
    render(
      <>
        <Badge variant="default">Badge 1</Badge>
        <Badge variant="secondary">Badge 2</Badge>
        <Badge variant="outline">Badge 3</Badge>
      </>
    )

    expect(screen.getByText('Badge 1')).toBeInTheDocument()
    expect(screen.getByText('Badge 2')).toBeInTheDocument()
    expect(screen.getByText('Badge 3')).toBeInTheDocument()
  })

  it('handles complex children content', () => {
    render(
      <Badge>
        <span>Complex</span>
        <span> Content</span>
      </Badge>
    )

    expect(screen.getByText('Complex')).toBeInTheDocument()
    expect(screen.getByText('Content')).toBeInTheDocument()
  })
})

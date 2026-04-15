import { fireEvent, render, screen } from '@testing-library/react'
import { Card } from '../Card'

describe('Card', () => {
  it('renders children correctly', () => {
    render(
      <Card>
        <p>Card content</p>
      </Card>
    )
    expect(screen.getByText('Card content')).toBeInTheDocument()
  })

  it('applies default styles', () => {
    const { container } = render(<Card>Content</Card>)
    const cardElement = container.firstChild as HTMLElement
    expect(cardElement).toHaveClass('bg-white')
    expect(cardElement).toHaveClass('rounded-lg')
    expect(cardElement).toHaveClass('border')
    expect(cardElement).toHaveClass('shadow-sm')
  })

  it('applies custom className', () => {
    const customClass = 'custom-card-class'
    const { container } = render(<Card className={customClass}>Content</Card>)
    const cardElement = container.firstChild as HTMLElement
    expect(cardElement).toHaveClass(customClass)
    // Should still have default classes
    expect(cardElement).toHaveClass('bg-white')
  })

  it('handles onClick event', () => {
    const handleClick = jest.fn()
    const { container } = render(
      <Card onClick={handleClick}>Clickable card</Card>
    )

    const card = container.firstChild as HTMLElement
    fireEvent.click(card)
    expect(handleClick).toHaveBeenCalledTimes(1)
  })

  it('renders without onClick handler', () => {
    const { container } = render(<Card>Non-clickable card</Card>)
    const cardElement = container.firstChild as HTMLElement
    expect(cardElement).toBeInTheDocument()
    // Should not throw when clicked without handler
    fireEvent.click(cardElement)
  })

  it('renders complex children', () => {
    render(
      <Card>
        <h2>Card Title</h2>
        <p>Card description</p>
        <button>Action</button>
      </Card>
    )
    expect(screen.getByText('Card Title')).toBeInTheDocument()
    expect(screen.getByText('Card description')).toBeInTheDocument()
    expect(screen.getByText('Action')).toBeInTheDocument()
  })

  it('renders multiple cards independently', () => {
    const handleClick1 = jest.fn()
    const handleClick2 = jest.fn()

    const { container } = render(
      <>
        <Card onClick={handleClick1}>Card 1</Card>
        <Card onClick={handleClick2}>Card 2</Card>
      </>
    )

    const cards = container.querySelectorAll('.rounded-lg')
    fireEvent.click(cards[0])
    expect(handleClick1).toHaveBeenCalledTimes(1)
    expect(handleClick2).not.toHaveBeenCalled()

    fireEvent.click(cards[1])
    expect(handleClick1).toHaveBeenCalledTimes(1)
    expect(handleClick2).toHaveBeenCalledTimes(1)
  })

  it('maintains proper DOM structure', () => {
    const { container } = render(
      <Card className="test-card">
        <span data-testid="child-element">Test</span>
      </Card>
    )

    const cardElement = container.firstChild as HTMLElement
    expect(cardElement.tagName).toBe('DIV')
    expect(
      cardElement.querySelector('[data-testid="child-element"]')
    ).toBeInTheDocument()
  })
})

import { render, screen } from '@testing-library/react'
import { Tag } from '../Tag'

describe('Tag', () => {
  it('renders children text correctly', () => {
    render(<Tag>TEST</Tag>)
    expect(screen.getByText('TEST')).toBeInTheDocument()
  })

  it('applies default medium variant styles', () => {
    const { container } = render(<Tag>TEST</Tag>)
    const tagElement = container.firstChild as HTMLElement
    expect(tagElement).toHaveClass('rounded-lg')
    expect(tagElement).toHaveClass('px-1.5')
    expect(tagElement).toHaveClass('ring-1')
    expect(tagElement).toHaveClass('ring-inset')
  })

  it('applies small variant styles', () => {
    const { container } = render(<Tag variant="small">TEST</Tag>)
    const tagElement = container.firstChild as HTMLElement
    expect(tagElement).not.toHaveClass('rounded-lg')
    expect(tagElement).not.toHaveClass('px-1.5')
  })

  it('applies color based on value mapping for GET', () => {
    const { container } = render(<Tag>GET</Tag>)
    const tagElement = container.firstChild as HTMLElement
    expect(tagElement).toHaveClass('text-emerald-500')
  })

  it('applies color based on value mapping for POST', () => {
    const { container } = render(<Tag>POST</Tag>)
    const tagElement = container.firstChild as HTMLElement
    expect(tagElement).toHaveClass('text-sky-500')
  })

  it('applies color based on value mapping for PUT', () => {
    const { container } = render(<Tag>PUT</Tag>)
    const tagElement = container.firstChild as HTMLElement
    expect(tagElement).toHaveClass('text-amber-500')
  })

  it('applies color based on value mapping for DELETE', () => {
    const { container } = render(<Tag>DELETE</Tag>)
    const tagElement = container.firstChild as HTMLElement
    expect(tagElement).toHaveClass('text-red-500')
  })

  it('applies custom color override', () => {
    const { container } = render(<Tag color="sky">TEST</Tag>)
    const tagElement = container.firstChild as HTMLElement
    expect(tagElement).toHaveClass('text-sky-500')
  })

  it('applies default emerald color for unmapped values', () => {
    const { container } = render(<Tag>CUSTOM</Tag>)
    const tagElement = container.firstChild as HTMLElement
    expect(tagElement).toHaveClass('text-emerald-500')
  })

  it('applies different color styles for different variants', () => {
    const { container: mediumContainer } = render(
      <Tag variant="medium" color="rose">
        TEST
      </Tag>
    )
    const mediumTag = mediumContainer.firstChild as HTMLElement
    expect(mediumTag).toHaveClass('ring-rose-200')
    expect(mediumTag).toHaveClass('bg-rose-50')

    const { container: smallContainer } = render(
      <Tag variant="small" color="rose">
        TEST
      </Tag>
    )
    const smallTag = smallContainer.firstChild as HTMLElement
    expect(smallTag).toHaveClass('text-red-500')
    expect(smallTag).not.toHaveClass('ring-rose-200')
  })

  it('applies common font styles', () => {
    const { container } = render(<Tag>TEST</Tag>)
    const tagElement = container.firstChild as HTMLElement
    expect(tagElement).toHaveClass('font-mono')
    expect(tagElement).toHaveClass('font-semibold')
    expect(tagElement).toHaveClass('text-[0.625rem]/6')
  })

  it('renders as span element', () => {
    const { container } = render(<Tag>TEST</Tag>)
    const tagElement = container.firstChild as HTMLElement
    expect(tagElement.tagName).toBe('SPAN')
  })

  it('handles all color options', () => {
    const colors = ['emerald', 'sky', 'amber', 'rose', 'zinc'] as const
    colors.forEach((color) => {
      const { container } = render(
        <Tag color={color}>{color.toUpperCase()}</Tag>
      )
      const tagElement = container.firstChild as HTMLElement
      expect(tagElement).toBeInTheDocument()
    })
  })
})

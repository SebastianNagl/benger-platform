import { render, screen } from '@testing-library/react'
import React from 'react'
import { Label } from '../label'

describe('Label', () => {
  it('renders children correctly', () => {
    render(<Label>Label Text</Label>)
    expect(screen.getByText('Label Text')).toBeInTheDocument()
  })

  it('renders as label element', () => {
    const { container } = render(<Label>Test Label</Label>)
    const label = container.firstChild as HTMLElement
    expect(label.tagName).toBe('LABEL')
  })

  it('applies default styling classes', () => {
    const { container } = render(<Label>Styled Label</Label>)
    const label = container.firstChild as HTMLElement
    expect(label).toHaveClass('text-sm')
    expect(label).toHaveClass('font-medium')
    expect(label).toHaveClass('leading-none')
    expect(label).toHaveClass('peer-disabled:cursor-not-allowed')
    expect(label).toHaveClass('peer-disabled:opacity-70')
  })

  it('applies custom className', () => {
    const { container } = render(
      <Label className="custom-label-class">Custom Label</Label>
    )
    const label = container.firstChild as HTMLElement
    expect(label).toHaveClass('custom-label-class')
    // Should still have default classes
    expect(label).toHaveClass('text-sm')
    expect(label).toHaveClass('font-medium')
  })

  it('forwards ref correctly', () => {
    const ref = React.createRef<HTMLLabelElement>()
    render(<Label ref={ref}>Ref Label</Label>)
    expect(ref.current).toBeInstanceOf(HTMLLabelElement)
    expect(ref.current?.textContent).toBe('Ref Label')
  })

  it('passes through htmlFor attribute', () => {
    const { container } = render(
      <Label htmlFor="input-id">Label for Input</Label>
    )
    const label = container.firstChild as HTMLElement
    expect(label).toHaveAttribute('for', 'input-id')
  })

  it('handles onClick event', () => {
    const handleClick = jest.fn()
    render(<Label onClick={handleClick}>Clickable Label</Label>)

    const label = screen.getByText('Clickable Label')
    label.click()
    expect(handleClick).toHaveBeenCalledTimes(1)
  })

  it('passes through additional props', () => {
    const { container } = render(
      <Label data-testid="test-label" id="label-id" title="Label Title">
        Props Label
      </Label>
    )
    const label = container.firstChild as HTMLElement
    expect(label).toHaveAttribute('data-testid', 'test-label')
    expect(label).toHaveAttribute('id', 'label-id')
    expect(label).toHaveAttribute('title', 'Label Title')
  })

  it('works with form inputs', () => {
    render(
      <div>
        <Label htmlFor="test-input">Input Label</Label>
        <input id="test-input" type="text" />
      </div>
    )

    const label = screen.getByText('Input Label')
    const input = screen.getByRole('textbox')

    // Check that label is associated with input
    expect(label).toHaveAttribute('for', 'test-input')
    expect(input).toHaveAttribute('id', 'test-input')
  })

  it('renders multiple labels independently', () => {
    render(
      <>
        <Label htmlFor="input1">Label 1</Label>
        <Label htmlFor="input2">Label 2</Label>
        <Label htmlFor="input3">Label 3</Label>
      </>
    )

    expect(screen.getByText('Label 1')).toBeInTheDocument()
    expect(screen.getByText('Label 2')).toBeInTheDocument()
    expect(screen.getByText('Label 3')).toBeInTheDocument()
  })

  it('handles complex children content', () => {
    render(
      <Label>
        <span>Required Field</span>
        <span className="text-red-500"> *</span>
      </Label>
    )

    expect(screen.getByText('Required Field')).toBeInTheDocument()
    expect(screen.getByText('*')).toBeInTheDocument()
    expect(screen.getByText('*')).toHaveClass('text-red-500')
  })

  it('has correct display name for debugging', () => {
    expect(Label.displayName).toBe('Label')
  })
})

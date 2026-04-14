/**
 * Test suite for Input component
 * Issue #364: Comprehensive component testing for shared components
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import React from 'react'
import { Input } from '../Input'

describe('Input Component', () => {
  const defaultProps = {
    id: 'test-input',
    name: 'testInput',
  }

  it('renders correctly with default props', () => {
    render(<Input {...defaultProps} />)

    const input = screen.getByRole('textbox')
    expect(input).toBeInTheDocument()
    expect(input).toHaveAttribute('id', 'test-input')
    expect(input).toHaveAttribute('name', 'testInput')
  })

  it('displays placeholder text', () => {
    render(<Input {...defaultProps} placeholder="Enter your email" />)

    const input = screen.getByPlaceholderText('Enter your email')
    expect(input).toBeInTheDocument()
  })

  it('handles value changes', async () => {
    const user = userEvent.setup()
    const mockChange = jest.fn()

    render(<Input {...defaultProps} onChange={mockChange} />)

    const input = screen.getByRole('textbox')
    await user.type(input, 'test@example.com')

    expect(mockChange).toHaveBeenCalled()
    expect(input).toHaveValue('test@example.com')
  })

  it('applies disabled state correctly', () => {
    render(<Input {...defaultProps} disabled={true} />)

    const input = screen.getByRole('textbox')
    expect(input).toBeDisabled()
    expect(input).toHaveClass('disabled:cursor-not-allowed')
    expect(input).toHaveClass('disabled:bg-zinc-50')
  })

  it('supports different input types', () => {
    const { rerender } = render(<Input {...defaultProps} type="email" />)

    let input = screen.getByRole('textbox')
    expect(input).toHaveAttribute('type', 'email')

    rerender(<Input {...defaultProps} type="password" />)
    // Password inputs don't have textbox role, use the id attribute
    const passwordInput = document.getElementById('test-input')
    expect(passwordInput).toHaveAttribute('type', 'password')
  })

  it('shows required attribute when required', () => {
    render(<Input {...defaultProps} required={true} />)

    const input = screen.getByRole('textbox')
    expect(input).toHaveAttribute('required')
  })

  it('handles focus and blur events', async () => {
    const user = userEvent.setup()
    const mockFocus = jest.fn()
    const mockBlur = jest.fn()

    render(<Input {...defaultProps} onFocus={mockFocus} onBlur={mockBlur} />)

    const input = screen.getByRole('textbox')
    await user.click(input)
    expect(mockFocus).toHaveBeenCalledTimes(1)

    await user.tab()
    expect(mockBlur).toHaveBeenCalledTimes(1)
  })

  it('supports controlled input with value prop', () => {
    const { rerender } = render(<Input {...defaultProps} value="initial" />)

    let input = screen.getByRole('textbox')
    expect(input).toHaveValue('initial')

    rerender(<Input {...defaultProps} value="updated" />)
    input = screen.getByRole('textbox')
    expect(input).toHaveValue('updated')
  })

  it('forwards ref correctly', () => {
    const ref = React.createRef<HTMLInputElement>()
    render(<Input {...defaultProps} ref={ref} />)

    expect(ref.current).toBeInstanceOf(HTMLInputElement)
  })

  it('supports maxLength attribute', () => {
    render(<Input {...defaultProps} maxLength={10} />)

    const input = screen.getByRole('textbox')
    expect(input).toHaveAttribute('maxLength', '10')
  })

  it('applies custom className', () => {
    render(<Input {...defaultProps} className="custom-input" />)

    const input = screen.getByRole('textbox')
    expect(input).toHaveClass('custom-input')
  })

  it('applies default styling classes', () => {
    render(<Input {...defaultProps} />)

    const input = screen.getByRole('textbox')
    expect(input).toHaveClass('block')
    expect(input).toHaveClass('w-full')
    expect(input).toHaveClass('rounded-md')
    expect(input).toHaveClass('border-zinc-300')
  })

  it('supports all standard input props', () => {
    render(
      <Input
        {...defaultProps}
        type="email"
        placeholder="test"
        autoComplete="email"
        readOnly={true}
      />
    )

    const input = screen.getByRole('textbox')
    expect(input).toHaveAttribute('type', 'email')
    expect(input).toHaveAttribute('placeholder', 'test')
    expect(input).toHaveAttribute('autoComplete', 'email')
    expect(input).toHaveAttribute('readOnly')
  })
})

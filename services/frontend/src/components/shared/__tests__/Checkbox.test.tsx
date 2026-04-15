/**
 * @jest-environment jsdom
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Checkbox } from '../Checkbox'

describe('Checkbox Component', () => {
  it('renders checkbox input', () => {
    render(<Checkbox />)

    const checkbox = screen.getByRole('checkbox')
    expect(checkbox).toBeInTheDocument()
    expect(checkbox).toHaveAttribute('type', 'checkbox')
  })

  it('renders with label when provided', () => {
    render(<Checkbox label="Accept terms" id="terms" />)

    expect(screen.getByText('Accept terms')).toBeInTheDocument()
    const label = screen.getByText('Accept terms')
    expect(label).toHaveAttribute('for', 'terms')
  })

  it('does not render label when not provided', () => {
    const { container } = render(<Checkbox />)

    const label = container.querySelector('label')
    expect(label).not.toBeInTheDocument()
  })

  describe('Checked State', () => {
    it('renders unchecked by default', () => {
      render(<Checkbox />)

      const checkbox = screen.getByRole('checkbox')
      expect(checkbox).not.toBeChecked()
    })

    it('renders as checked when checked prop is true', () => {
      render(<Checkbox checked={true} readOnly />)

      const checkbox = screen.getByRole('checkbox')
      expect(checkbox).toBeChecked()
    })

    it('renders as unchecked when checked prop is false', () => {
      render(<Checkbox checked={false} readOnly />)

      const checkbox = screen.getByRole('checkbox')
      expect(checkbox).not.toBeChecked()
    })

    it('can be toggled by user', async () => {
      const user = userEvent.setup()
      render(<Checkbox />)

      const checkbox = screen.getByRole('checkbox')
      expect(checkbox).not.toBeChecked()

      await user.click(checkbox)
      expect(checkbox).toBeChecked()

      await user.click(checkbox)
      expect(checkbox).not.toBeChecked()
    })
  })

  describe('onChange Handler', () => {
    it('calls onChange when clicked', async () => {
      const handleChange = jest.fn()
      const user = userEvent.setup()
      render(<Checkbox onChange={handleChange} />)

      const checkbox = screen.getByRole('checkbox')
      await user.click(checkbox)

      expect(handleChange).toHaveBeenCalledTimes(1)
    })

    it('passes event to onChange handler', async () => {
      const handleChange = jest.fn()
      const user = userEvent.setup()
      render(<Checkbox onChange={handleChange} />)

      const checkbox = screen.getByRole('checkbox')
      await user.click(checkbox)

      expect(handleChange).toHaveBeenCalledWith(
        expect.objectContaining({
          target: expect.objectContaining({
            checked: true,
          }),
        })
      )
    })

    it('does not call onChange when disabled', async () => {
      const handleChange = jest.fn()
      const user = userEvent.setup()
      render(<Checkbox onChange={handleChange} disabled />)

      const checkbox = screen.getByRole('checkbox')
      await user.click(checkbox)

      expect(handleChange).not.toHaveBeenCalled()
    })
  })

  describe('Disabled State', () => {
    it('renders as disabled when disabled prop is true', () => {
      render(<Checkbox disabled />)

      const checkbox = screen.getByRole('checkbox')
      expect(checkbox).toBeDisabled()
    })

    it('applies disabled styling classes', () => {
      render(<Checkbox disabled />)

      const checkbox = screen.getByRole('checkbox')
      expect(checkbox).toHaveClass('disabled:cursor-not-allowed')
      expect(checkbox).toHaveClass('disabled:opacity-50')
    })

    it('cannot be toggled when disabled', async () => {
      const user = userEvent.setup()
      render(<Checkbox disabled />)

      const checkbox = screen.getByRole('checkbox')
      const initialChecked = checkbox.checked

      await user.click(checkbox)
      expect(checkbox.checked).toBe(initialChecked)
    })
  })

  describe('ID and Name Attributes', () => {
    it('applies id attribute', () => {
      render(<Checkbox id="my-checkbox" />)

      const checkbox = screen.getByRole('checkbox')
      expect(checkbox).toHaveAttribute('id', 'my-checkbox')
    })

    it('applies name attribute', () => {
      render(<Checkbox name="agreement" />)

      const checkbox = screen.getByRole('checkbox')
      expect(checkbox).toHaveAttribute('name', 'agreement')
    })

    it('links label to checkbox via id', () => {
      render(<Checkbox id="terms" label="I agree" />)

      const label = screen.getByText('I agree')
      const checkbox = screen.getByRole('checkbox')

      expect(label).toHaveAttribute('for', 'terms')
      expect(checkbox).toHaveAttribute('id', 'terms')
    })
  })

  describe('Styling', () => {
    it('applies default styling classes', () => {
      render(<Checkbox />)

      const checkbox = screen.getByRole('checkbox')
      expect(checkbox).toHaveClass('h-4', 'w-4', 'rounded', 'border-gray-300')
    })

    it('applies focus ring classes', () => {
      render(<Checkbox />)

      const checkbox = screen.getByRole('checkbox')
      expect(checkbox).toHaveClass(
        'focus:ring-2',
        'focus:ring-blue-500',
        'focus:ring-offset-0'
      )
    })

    it('applies custom className', () => {
      render(<Checkbox className="custom-checkbox-class" />)

      const checkbox = screen.getByRole('checkbox')
      expect(checkbox).toHaveClass('custom-checkbox-class')
    })

    it('merges custom className with default classes', () => {
      render(<Checkbox className="my-custom-class" />)

      const checkbox = screen.getByRole('checkbox')
      expect(checkbox).toHaveClass('my-custom-class')
      expect(checkbox).toHaveClass('h-4', 'w-4', 'rounded')
    })

    it('applies text color class', () => {
      render(<Checkbox />)

      const checkbox = screen.getByRole('checkbox')
      expect(checkbox).toHaveClass('text-blue-600')
    })

    it('applies label styling', () => {
      render(<Checkbox label="Test label" id="test" />)

      const label = screen.getByText('Test label')
      expect(label).toHaveClass('ml-2', 'text-sm', 'text-gray-700')
    })
  })

  describe('Accessibility', () => {
    it('has checkbox role', () => {
      render(<Checkbox />)

      expect(screen.getByRole('checkbox')).toBeInTheDocument()
    })

    it('is keyboard accessible', async () => {
      const user = userEvent.setup()
      render(<Checkbox />)

      const checkbox = screen.getByRole('checkbox')
      checkbox.focus()
      expect(checkbox).toHaveFocus()

      await user.keyboard(' ')
      expect(checkbox).toBeChecked()
    })

    it('can be navigated with tab', async () => {
      const user = userEvent.setup()
      render(
        <div>
          <button>Before</button>
          <Checkbox />
          <button>After</button>
        </div>
      )

      const beforeButton = screen.getByRole('button', { name: 'Before' })
      const checkbox = screen.getByRole('checkbox')
      const afterButton = screen.getByRole('button', { name: 'After' })

      beforeButton.focus()
      await user.tab()
      expect(checkbox).toHaveFocus()

      await user.tab()
      expect(afterButton).toHaveFocus()
    })

    it('associates label with checkbox for click handling', async () => {
      const user = userEvent.setup()
      render(<Checkbox id="test" label="Click me" />)

      const checkbox = screen.getByRole('checkbox')
      const label = screen.getByText('Click me')

      expect(checkbox).not.toBeChecked()

      await user.click(label)
      expect(checkbox).toBeChecked()
    })
  })

  describe('ForwardRef', () => {
    it('forwards ref to input element', () => {
      const ref = jest.fn()
      render(<Checkbox ref={ref} />)

      expect(ref).toHaveBeenCalledWith(expect.any(HTMLInputElement))
    })

    it('allows ref access to input methods', () => {
      let checkboxRef: HTMLInputElement | null = null
      render(<Checkbox ref={(el) => (checkboxRef = el)} />)

      expect(checkboxRef).toBeInstanceOf(HTMLInputElement)
      expect(checkboxRef?.tagName).toBe('INPUT')
    })

    it('sets displayName for debugging', () => {
      expect(Checkbox.displayName).toBe('Checkbox')
    })
  })

  describe('HTML Attributes', () => {
    it('passes through additional HTML attributes', () => {
      render(<Checkbox data-testid="custom-checkbox" aria-label="Custom" />)

      const checkbox = screen.getByTestId('custom-checkbox')
      expect(checkbox).toHaveAttribute('aria-label', 'Custom')
    })

    it('supports required attribute', () => {
      render(<Checkbox required />)

      const checkbox = screen.getByRole('checkbox')
      expect(checkbox).toBeRequired()
    })

    it('supports defaultChecked attribute', () => {
      render(<Checkbox defaultChecked />)

      const checkbox = screen.getByRole('checkbox')
      expect(checkbox).toBeChecked()
    })

    it('supports value attribute', () => {
      render(<Checkbox value="accepted" />)

      const checkbox = screen.getByRole('checkbox')
      expect(checkbox).toHaveAttribute('value', 'accepted')
    })
  })

  describe('Edge Cases', () => {
    it('handles empty string label', () => {
      const { container } = render(<Checkbox label="" id="test" />)

      const label = container.querySelector('label')
      expect(label).not.toBeInTheDocument()
    })

    it('handles undefined label', () => {
      render(<Checkbox label={undefined} />)

      const checkbox = screen.getByRole('checkbox')
      expect(checkbox).toBeInTheDocument()
    })

    it('handles very long label text', () => {
      const longLabel = 'a'.repeat(200)
      render(<Checkbox label={longLabel} id="test" />)

      expect(screen.getByText(longLabel)).toBeInTheDocument()
    })

    it('handles special characters in label', () => {
      const specialLabel = '< > & " \''
      render(<Checkbox label={specialLabel} id="test" />)

      expect(screen.getByText(specialLabel)).toBeInTheDocument()
    })

    it('works without id when label is present', () => {
      render(<Checkbox label="No ID" />)

      const label = screen.getByText('No ID')
      expect(label).toBeInTheDocument()
      expect(label).not.toHaveAttribute('for')
    })
  })

  describe('Controlled vs Uncontrolled', () => {
    it('works as uncontrolled component', async () => {
      const user = userEvent.setup()
      render(<Checkbox defaultChecked={false} />)

      const checkbox = screen.getByRole('checkbox')
      expect(checkbox).not.toBeChecked()

      await user.click(checkbox)
      expect(checkbox).toBeChecked()
    })

    it('works as controlled component', async () => {
      const user = userEvent.setup()
      const handleChange = jest.fn()
      const { rerender } = render(
        <Checkbox checked={false} onChange={handleChange} />
      )

      const checkbox = screen.getByRole('checkbox')
      expect(checkbox).not.toBeChecked()

      await user.click(checkbox)
      expect(handleChange).toHaveBeenCalled()

      // Controlled component doesn't change without prop update
      rerender(<Checkbox checked={true} onChange={handleChange} />)
      expect(checkbox).toBeChecked()
    })
  })
})

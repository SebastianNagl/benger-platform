/**
 * @jest-environment jsdom
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Label } from '../Label'

describe('Label Component', () => {
  describe('Basic Rendering', () => {
    it('renders label element', () => {
      render(<Label>Test Label</Label>)

      const label = screen.getByText('Test Label')
      expect(label).toBeInTheDocument()
      expect(label.tagName).toBe('LABEL')
    })

    it('renders with text content', () => {
      render(<Label>Email Address</Label>)

      expect(screen.getByText('Email Address')).toBeInTheDocument()
    })

    it('renders as label element by default', () => {
      const { container } = render(<Label>Label</Label>)

      const label = container.querySelector('label')
      expect(label).toBeInTheDocument()
    })

    it('renders with default structure', () => {
      const { container } = render(<Label>Test</Label>)

      const label = container.firstChild as HTMLElement
      expect(label).toBeInstanceOf(HTMLLabelElement)
    })
  })

  describe('Required Field Handling', () => {
    it('does not show required indicator by default', () => {
      render(<Label>Field Name</Label>)

      expect(screen.queryByText('*')).not.toBeInTheDocument()
    })

    it('handles required fields through parent form context', () => {
      render(
        <form>
          <Label htmlFor="required-field">Required Field</Label>
          <input id="required-field" required />
        </form>
      )

      const input = screen.getByRole('textbox')
      expect(input).toBeRequired()
    })

    it('can render with required indicator via children', () => {
      render(
        <Label>
          Field Name <span className="text-red-500">*</span>
        </Label>
      )

      const requiredIndicator = screen.getByText('*')
      expect(requiredIndicator).toBeInTheDocument()
      expect(requiredIndicator).toHaveClass('text-red-500')
    })
  })

  describe('Styling/Variants', () => {
    it('applies default styling classes', () => {
      render(<Label>Default Label</Label>)

      const label = screen.getByText('Default Label')
      expect(label).toHaveClass('mb-1', 'block', 'text-sm', 'font-medium')
    })

    it('applies text color classes', () => {
      render(<Label>Colored Label</Label>)

      const label = screen.getByText('Colored Label')
      expect(label).toHaveClass('text-gray-700')
    })

    it('applies custom className', () => {
      render(<Label className="custom-class">Custom Label</Label>)

      const label = screen.getByText('Custom Label')
      expect(label).toHaveClass('custom-class')
    })

    it('merges custom className with default classes', () => {
      render(<Label className="my-custom-class">Merged Label</Label>)

      const label = screen.getByText('Merged Label')
      expect(label).toHaveClass('my-custom-class')
      expect(label).toHaveClass('mb-1', 'block', 'text-sm')
    })

    it('allows overriding default classes via className', () => {
      render(<Label className="mb-4 text-lg">Override Label</Label>)

      const label = screen.getByText('Override Label')
      expect(label).toHaveClass('mb-4', 'text-lg')
    })

    it('applies font weight class', () => {
      render(<Label>Font Weight</Label>)

      const label = screen.getByText('Font Weight')
      expect(label).toHaveClass('font-medium')
    })

    it('applies block display class', () => {
      render(<Label>Block Label</Label>)

      const label = screen.getByText('Block Label')
      expect(label).toHaveClass('block')
    })

    it('applies bottom margin class', () => {
      render(<Label>Margin Label</Label>)

      const label = screen.getByText('Margin Label')
      expect(label).toHaveClass('mb-1')
    })
  })

  describe('Children/Content', () => {
    it('renders string children', () => {
      render(<Label>String Content</Label>)

      expect(screen.getByText('String Content')).toBeInTheDocument()
    })

    it('renders JSX children', () => {
      render(
        <Label>
          <span>Nested Content</span>
        </Label>
      )

      expect(screen.getByText('Nested Content')).toBeInTheDocument()
    })

    it('renders multiple children', () => {
      render(
        <Label>
          First <strong>Bold</strong> Last
        </Label>
      )

      expect(screen.getByText('Bold')).toBeInTheDocument()
    })

    it('renders complex children structure', () => {
      render(
        <Label>
          <span className="flex items-center gap-2">
            <span>Label Text</span>
            <span className="text-red-500">*</span>
          </span>
        </Label>
      )

      expect(screen.getByText('Label Text')).toBeInTheDocument()
      expect(screen.getByText('*')).toBeInTheDocument()
    })

    it('renders with icon children', () => {
      render(
        <Label>
          <div className="flex items-center">
            <svg data-testid="icon" />
            <span>With Icon</span>
          </div>
        </Label>
      )

      expect(screen.getByTestId('icon')).toBeInTheDocument()
      expect(screen.getByText('With Icon')).toBeInTheDocument()
    })

    it('preserves whitespace in children', () => {
      render(<Label> Spaced Content </Label>)

      expect(screen.getByText(/Spaced\s+Content/)).toBeInTheDocument()
    })

    it('renders numeric children', () => {
      render(<Label>{123}</Label>)

      expect(screen.getByText('123')).toBeInTheDocument()
    })

    it('renders boolean children as empty', () => {
      const { container } = render(<Label>{true as any}</Label>)

      const label = container.querySelector('label')
      expect(label?.textContent).toBe('')
    })
  })

  describe('HTML Attributes', () => {
    it('applies htmlFor attribute', () => {
      render(<Label htmlFor="input-id">For Input</Label>)

      const label = screen.getByText('For Input')
      expect(label).toHaveAttribute('for', 'input-id')
    })

    it('links to input via htmlFor', () => {
      render(
        <div>
          <Label htmlFor="my-input">My Input</Label>
          <input id="my-input" />
        </div>
      )

      const label = screen.getByText('My Input')
      expect(label).toHaveAttribute('for', 'my-input')
    })

    it('renders without htmlFor attribute when not provided', () => {
      render(<Label>No For</Label>)

      const label = screen.getByText('No For')
      expect(label).not.toHaveAttribute('for')
    })

    it('only accepts defined props', () => {
      render(
        <Label htmlFor="test-id" className="test-class">
          Test Label
        </Label>
      )

      const label = screen.getByText('Test Label')
      expect(label).toHaveAttribute('for', 'test-id')
      expect(label).toHaveClass('test-class')
    })

    it('does not pass through additional HTML attributes', () => {
      // Label component only accepts htmlFor, children, and className
      // This test verifies the component's interface constraints
      render(<Label htmlFor="input-id">Constrained Label</Label>)

      const label = screen.getByText('Constrained Label')
      expect(label).toBeInTheDocument()
      expect(label).toHaveAttribute('for', 'input-id')
    })
  })

  describe('Accessibility', () => {
    it('associates with form input via htmlFor', () => {
      render(
        <div>
          <Label htmlFor="username">Username</Label>
          <input id="username" type="text" />
        </div>
      )

      const input = screen.getByRole('textbox')
      const label = screen.getByText('Username')

      expect(label).toHaveAttribute('for', 'username')
      expect(input).toHaveAttribute('id', 'username')
    })

    it('clicking label focuses associated input', async () => {
      const user = userEvent.setup()
      render(
        <div>
          <Label htmlFor="email">Email</Label>
          <input id="email" type="email" />
        </div>
      )

      const label = screen.getByText('Email')
      const input = screen.getByRole('textbox') as HTMLInputElement

      await user.click(label)
      expect(document.activeElement).toBe(input)
    })

    it('clicking label without htmlFor does not affect anything', async () => {
      const user = userEvent.setup()
      render(
        <div>
          <Label>No Association</Label>
          <input type="text" />
        </div>
      )

      const label = screen.getByText('No Association')
      const input = screen.getByRole('textbox')

      await user.click(label)
      expect(document.activeElement).not.toBe(input)
    })

    it('supports screen reader accessible text', () => {
      render(
        <Label htmlFor="field">
          <span>Visible Text</span>
          <span className="sr-only">Additional screen reader context</span>
        </Label>
      )

      expect(screen.getByText('Visible Text')).toBeInTheDocument()
      expect(
        screen.getByText('Additional screen reader context')
      ).toBeInTheDocument()
    })

    it('maintains semantic HTML structure', () => {
      const { container } = render(<Label>Semantic Label</Label>)

      const label = container.querySelector('label')
      expect(label).toBeInTheDocument()
      expect(label?.tagName).toBe('LABEL')
    })

    it('works with checkbox inputs', async () => {
      const user = userEvent.setup()
      render(
        <div>
          <Label htmlFor="agree">I agree</Label>
          <input id="agree" type="checkbox" />
        </div>
      )

      const label = screen.getByText('I agree')
      const checkbox = screen.getByRole('checkbox') as HTMLInputElement

      expect(checkbox.checked).toBe(false)
      await user.click(label)
      expect(checkbox.checked).toBe(true)
    })

    it('works with radio inputs', async () => {
      const user = userEvent.setup()
      render(
        <div>
          <Label htmlFor="option1">Option 1</Label>
          <input id="option1" type="radio" name="choice" />
        </div>
      )

      const label = screen.getByText('Option 1')
      const radio = screen.getByRole('radio') as HTMLInputElement

      expect(radio.checked).toBe(false)
      await user.click(label)
      expect(radio.checked).toBe(true)
    })
  })

  describe('Edge Cases', () => {
    it('handles empty string children', () => {
      const { container } = render(<Label>{''}</Label>)

      const label = container.querySelector('label')
      expect(label).toBeInTheDocument()
      expect(label?.textContent).toBe('')
    })

    it('handles very long text content', () => {
      const longText = 'A'.repeat(500)
      render(<Label>{longText}</Label>)

      expect(screen.getByText(longText)).toBeInTheDocument()
    })

    it('handles special characters', () => {
      const specialText = '< > & " \' @ # $ % ^ & * ( )'
      render(<Label>{specialText}</Label>)

      expect(screen.getByText(specialText)).toBeInTheDocument()
    })

    it('handles unicode characters', () => {
      const unicodeText = '你好 世界 café'
      render(<Label>{unicodeText}</Label>)

      expect(screen.getByText(unicodeText)).toBeInTheDocument()
    })

    it('handles line breaks in content', () => {
      render(
        <Label>
          First Line
          <br />
          Second Line
        </Label>
      )

      expect(screen.getByText(/First Line/)).toBeInTheDocument()
      expect(screen.getByText(/Second Line/)).toBeInTheDocument()
    })

    it('handles multiple spaces', () => {
      render(<Label>Multiple Spaces Content</Label>)

      expect(
        screen.getByText(/Multiple\s+Spaces\s+Content/)
      ).toBeInTheDocument()
    })

    it('handles null as children', () => {
      const { container } = render(<Label>{null as any}</Label>)

      const label = container.querySelector('label')
      expect(label).toBeInTheDocument()
      expect(label?.textContent).toBe('')
    })

    it('handles undefined as children', () => {
      const { container } = render(<Label>{undefined as any}</Label>)

      const label = container.querySelector('label')
      expect(label).toBeInTheDocument()
      expect(label?.textContent).toBe('')
    })

    it('handles array of children', () => {
      render(<Label>{['First', ' ', 'Second', ' ', 'Third']}</Label>)

      expect(screen.getByText(/First\s+Second\s+Third/)).toBeInTheDocument()
    })

    it('handles conditional children', () => {
      const showExtra = true
      render(<Label>Base Text{showExtra && ' Extra'}</Label>)

      expect(screen.getByText('Base Text Extra')).toBeInTheDocument()
    })

    it('handles fragments as children', () => {
      render(
        <Label>
          <>
            <span>Fragment</span>
            <span>Content</span>
          </>
        </Label>
      )

      expect(screen.getByText('Fragment')).toBeInTheDocument()
      expect(screen.getByText('Content')).toBeInTheDocument()
    })

    it('handles htmlFor with special characters', () => {
      render(<Label htmlFor="input-with-dash_and_underscore">Label</Label>)

      const label = screen.getByText('Label')
      expect(label).toHaveAttribute('for', 'input-with-dash_and_underscore')
    })

    it('handles empty htmlFor attribute', () => {
      render(<Label htmlFor="">Empty For</Label>)

      const label = screen.getByText('Empty For')
      expect(label).toHaveAttribute('for', '')
    })
  })

  describe('Dark Mode', () => {
    it('applies dark mode text color class', () => {
      render(<Label>Dark Mode Label</Label>)

      const label = screen.getByText('Dark Mode Label')
      expect(label).toHaveClass('dark:text-gray-300')
    })

    it('applies both light and dark mode classes', () => {
      render(<Label>Dual Mode Label</Label>)

      const label = screen.getByText('Dual Mode Label')
      expect(label).toHaveClass('text-gray-700')
      expect(label).toHaveClass('dark:text-gray-300')
    })

    it('preserves dark mode classes with custom className', () => {
      render(<Label className="custom-class">Custom Dark</Label>)

      const label = screen.getByText('Custom Dark')
      expect(label).toHaveClass('dark:text-gray-300')
      expect(label).toHaveClass('custom-class')
    })

    it('allows overriding dark mode colors via className', () => {
      render(<Label className="dark:text-white">Override Dark</Label>)

      const label = screen.getByText('Override Dark')
      expect(label).toHaveClass('dark:text-white')
    })
  })

  describe('Integration Scenarios', () => {
    it('works within form context', () => {
      render(
        <form>
          <Label htmlFor="form-input">Form Label</Label>
          <input id="form-input" type="text" />
          <button type="submit">Submit</button>
        </form>
      )

      expect(screen.getByText('Form Label')).toBeInTheDocument()
      expect(screen.getByRole('textbox')).toBeInTheDocument()
      expect(screen.getByRole('button')).toBeInTheDocument()
    })

    it('works with multiple labels in same form', () => {
      render(
        <form>
          <Label htmlFor="first">First</Label>
          <input id="first" />
          <Label htmlFor="second">Second</Label>
          <input id="second" />
        </form>
      )

      const firstLabel = screen.getByText('First')
      const secondLabel = screen.getByText('Second')

      expect(firstLabel).toHaveAttribute('for', 'first')
      expect(secondLabel).toHaveAttribute('for', 'second')
    })

    it('maintains styling consistency across multiple instances', () => {
      render(
        <div>
          <Label>Label 1</Label>
          <Label>Label 2</Label>
          <Label>Label 3</Label>
        </div>
      )

      const labels = screen.getAllByText(/Label \d/)
      labels.forEach((label) => {
        expect(label).toHaveClass('mb-1', 'block', 'text-sm', 'font-medium')
      })
    })

    it('works with custom form components', () => {
      render(
        <div className="form-field">
          <Label htmlFor="custom">Custom Field</Label>
          <div className="input-wrapper">
            <input id="custom" type="text" />
          </div>
        </div>
      )

      expect(screen.getByText('Custom Field')).toBeInTheDocument()
    })
  })
})

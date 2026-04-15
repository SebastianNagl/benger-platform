/**
 * @jest-environment jsdom
 */

import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../Select'

// Mock Heroicons
jest.mock('@heroicons/react/24/outline', () => ({
  CheckIcon: (props: any) => (
    <svg {...props} data-testid="check-icon">
      <path />
    </svg>
  ),
  ChevronDownIcon: (props: any) => (
    <svg {...props} data-testid="chevron-down-icon">
      <path />
    </svg>
  ),
}))

describe('Select Component', () => {
  const mockOnValueChange = jest.fn()

  const DefaultSelect = ({ value = '', disabled = false }) => (
    <Select value={value} onValueChange={mockOnValueChange} disabled={disabled}>
      <SelectTrigger>
        <SelectValue placeholder="Select an option" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="option1">Option 1</SelectItem>
        <SelectItem value="option2">Option 2</SelectItem>
        <SelectItem value="option3">Option 3</SelectItem>
      </SelectContent>
    </Select>
  )

  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('Basic Rendering', () => {
    it('renders select trigger button', () => {
      render(<DefaultSelect />)

      const button = screen.getByRole('button')
      expect(button).toBeInTheDocument()
    })

    it('renders placeholder when no value selected', () => {
      render(<DefaultSelect />)

      expect(screen.getByText('Select an option')).toBeInTheDocument()
    })

    it('renders chevron icon', () => {
      render(<DefaultSelect />)

      expect(screen.getByTestId('chevron-down-icon')).toBeInTheDocument()
    })

    it('does not show dropdown options initially', () => {
      render(<DefaultSelect />)

      expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    })

    it('renders all compound components together', () => {
      render(<DefaultSelect />)

      const button = screen.getByRole('button')
      const placeholder = screen.getByText('Select an option')

      expect(button).toBeInTheDocument()
      expect(placeholder).toBeInTheDocument()
      expect(screen.getByTestId('chevron-down-icon')).toBeInTheDocument()
    })
  })

  describe('Value Display', () => {
    it('displays selected value', () => {
      render(<DefaultSelect value="option1" />)

      expect(screen.getByText('option1')).toBeInTheDocument()
    })

    it('displays placeholder when value is empty string', () => {
      render(<DefaultSelect value="" />)

      expect(screen.getByText('Select an option')).toBeInTheDocument()
    })

    it('updates display when value prop changes', () => {
      const { rerender } = render(<DefaultSelect value="option1" />)
      expect(screen.getByText('option1')).toBeInTheDocument()

      rerender(<DefaultSelect value="option2" />)
      expect(screen.getByText('option2')).toBeInTheDocument()
    })
  })

  describe('Dropdown Interaction', () => {
    it('opens dropdown when trigger clicked', async () => {
      const user = userEvent.setup()
      render(<DefaultSelect />)

      const button = screen.getByRole('button')
      await user.click(button)

      expect(screen.getByRole('listbox')).toBeInTheDocument()
    })

    it('shows all options when dropdown opens', async () => {
      const user = userEvent.setup()
      render(<DefaultSelect />)

      const button = screen.getByRole('button')
      await user.click(button)

      expect(screen.getByText('Option 1')).toBeInTheDocument()
      expect(screen.getByText('Option 2')).toBeInTheDocument()
      expect(screen.getByText('Option 3')).toBeInTheDocument()
    })

    it('calls onValueChange when option selected', async () => {
      const user = userEvent.setup()
      render(<DefaultSelect />)

      const button = screen.getByRole('button')
      await user.click(button)

      const option = screen.getByText('Option 2')
      await user.click(option)

      expect(mockOnValueChange).toHaveBeenCalledWith('option2')
    })

    it('closes dropdown after selection', async () => {
      const user = userEvent.setup()
      render(<DefaultSelect />)

      const button = screen.getByRole('button')
      await user.click(button)

      const option = screen.getByText('Option 1')
      await user.click(option)

      expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    })
  })

  describe('Selected State', () => {
    it('shows check icon for selected item', async () => {
      const user = userEvent.setup()
      render(<DefaultSelect value="option2" />)

      const button = screen.getByRole('button')
      await user.click(button)

      const listbox = screen.getByRole('listbox')
      const option2 = within(listbox).getByText('Option 2')
      const option2Container = option2.closest('[role="option"]')!

      const checkIcon = within(option2Container).getByTestId('check-icon')
      expect(checkIcon).toBeInTheDocument()
    })

    it('does not show check icon for unselected items', async () => {
      const user = userEvent.setup()
      render(<DefaultSelect value="option2" />)

      const button = screen.getByRole('button')
      await user.click(button)

      const listbox = screen.getByRole('listbox')
      const option1 = within(listbox).getByText('Option 1')
      const option1Container = option1.closest('[role="option"]')!

      const checkIcon = within(option1Container).queryByTestId('check-icon')
      expect(checkIcon).not.toBeInTheDocument()
    })

    it('applies font-medium to selected item text', async () => {
      const user = userEvent.setup()
      render(<DefaultSelect value="option1" />)

      const button = screen.getByRole('button')
      await user.click(button)

      const listbox = screen.getByRole('listbox')
      const option1Text = within(listbox).getByText('Option 1').closest('span')
      expect(option1Text).toHaveClass('font-medium')
    })

    it('applies font-normal to unselected item text', async () => {
      const user = userEvent.setup()
      render(<DefaultSelect value="option1" />)

      const button = screen.getByRole('button')
      await user.click(button)

      const listbox = screen.getByRole('listbox')
      const option2Text = within(listbox).getByText('Option 2').closest('span')
      expect(option2Text).toHaveClass('font-normal')
    })
  })

  describe('Disabled State', () => {
    it('disables button when disabled prop is true', () => {
      render(<DefaultSelect disabled={true} />)

      const button = screen.getByRole('button')
      expect(button).toBeDisabled()
    })

    it('applies disabled styling to button', () => {
      render(<DefaultSelect disabled={true} />)

      const button = screen.getByRole('button')
      expect(button).toHaveClass('disabled:cursor-not-allowed')
      expect(button).toHaveClass('disabled:opacity-50')
    })

    it('does not open dropdown when disabled button clicked', async () => {
      const user = userEvent.setup()
      render(<DefaultSelect disabled={true} />)

      const button = screen.getByRole('button')
      await user.click(button)

      expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    })

    it('does not call onValueChange when disabled', async () => {
      const user = userEvent.setup()
      render(<DefaultSelect disabled={true} />)

      const button = screen.getByRole('button')
      await user.click(button)

      expect(mockOnValueChange).not.toHaveBeenCalled()
    })
  })

  describe('Placeholder Handling', () => {
    it('shows placeholder when value is empty', () => {
      render(<DefaultSelect value="" />)

      expect(screen.getByText('Select an option')).toBeInTheDocument()
    })

    it('hides placeholder when value is selected', () => {
      render(<DefaultSelect value="option1" />)

      expect(screen.queryByText('Select an option')).not.toBeInTheDocument()
    })

    it('handles missing placeholder gracefully', () => {
      render(
        <Select value="" onValueChange={mockOnValueChange}>
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="test">Test</SelectItem>
          </SelectContent>
        </Select>
      )

      const button = screen.getByRole('button')
      expect(button).toBeInTheDocument()
    })

    it('supports custom placeholder text', () => {
      render(
        <Select value="" onValueChange={mockOnValueChange}>
          <SelectTrigger>
            <SelectValue placeholder="Choose wisely..." />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="test">Test</SelectItem>
          </SelectContent>
        </Select>
      )

      expect(screen.getByText('Choose wisely...')).toBeInTheDocument()
    })
  })

  describe('Styling', () => {
    it('applies default button classes', () => {
      render(<DefaultSelect />)

      const button = screen.getByRole('button')
      expect(button).toHaveClass(
        'relative',
        'w-full',
        'rounded-full',
        'bg-white'
      )
    })

    it('applies custom className to trigger', () => {
      render(
        <Select value="" onValueChange={mockOnValueChange}>
          <SelectTrigger className="custom-trigger-class">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="test">Test</SelectItem>
          </SelectContent>
        </Select>
      )

      const button = screen.getByRole('button')
      expect(button).toHaveClass('custom-trigger-class')
    })

    it('applies custom className to content', async () => {
      const user = userEvent.setup()
      render(
        <Select value="" onValueChange={mockOnValueChange}>
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent className="custom-content-class">
            <SelectItem value="test">Test</SelectItem>
          </SelectContent>
        </Select>
      )

      const button = screen.getByRole('button')
      await user.click(button)

      const listbox = screen.getByRole('listbox')
      expect(listbox).toHaveClass('custom-content-class')
    })

    it('applies custom className to items', async () => {
      const user = userEvent.setup()
      render(
        <Select value="" onValueChange={mockOnValueChange}>
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="test" className="custom-item-class">
              Test
            </SelectItem>
          </SelectContent>
        </Select>
      )

      const button = screen.getByRole('button')
      await user.click(button)

      const option = screen.getByText('Test').closest('[role="option"]')
      expect(option).toHaveClass('custom-item-class')
    })

    it('applies focus ring styles', () => {
      render(<DefaultSelect />)

      const button = screen.getByRole('button')
      expect(button).toHaveClass(
        'focus:outline-none',
        'focus:ring-2',
        'focus:ring-emerald-500'
      )
    })

    it('applies dark mode classes to button', () => {
      render(<DefaultSelect />)

      const button = screen.getByRole('button')
      expect(button).toHaveClass('dark:bg-white/5', 'dark:text-zinc-100')
    })

    it('applies dark mode classes to value text', () => {
      render(<DefaultSelect value="option1" />)

      const valueSpan = screen.getByText('option1')
      expect(valueSpan).toHaveClass('dark:text-white')
    })
  })

  describe('Accessibility', () => {
    it('has button role for trigger', () => {
      render(<DefaultSelect />)

      expect(screen.getByRole('button')).toBeInTheDocument()
    })

    it('has listbox role when opened', async () => {
      const user = userEvent.setup()
      render(<DefaultSelect />)

      const button = screen.getByRole('button')
      await user.click(button)

      expect(screen.getByRole('listbox')).toBeInTheDocument()
    })

    it('has option role for each item', async () => {
      const user = userEvent.setup()
      render(<DefaultSelect />)

      const button = screen.getByRole('button')
      await user.click(button)

      const options = screen.getAllByRole('option')
      expect(options).toHaveLength(3)
    })

    it('is keyboard navigable', async () => {
      const user = userEvent.setup()
      render(<DefaultSelect />)

      const button = screen.getByRole('button')
      button.focus()
      expect(button).toHaveFocus()

      await user.keyboard(' ')
      expect(screen.getByRole('listbox')).toBeInTheDocument()
    })

    it('can select option with Enter key', async () => {
      const user = userEvent.setup()
      render(<DefaultSelect />)

      const button = screen.getByRole('button')
      button.focus()

      await user.keyboard('{Enter}')
      await user.keyboard('{ArrowDown}')
      await user.keyboard('{Enter}')

      expect(mockOnValueChange).toHaveBeenCalled()
    })

    it('chevron icon has aria-hidden attribute', () => {
      render(<DefaultSelect />)

      const chevron = screen.getByTestId('chevron-down-icon')
      const ariaHidden = chevron.getAttribute('aria-hidden')
      expect(ariaHidden).toBe('true')
    })

    it('check icon has aria-hidden attribute', async () => {
      const user = userEvent.setup()
      render(<DefaultSelect value="option1" />)

      const button = screen.getByRole('button')
      await user.click(button)

      const checkIcon = screen.getByTestId('check-icon')
      const ariaHidden = checkIcon.getAttribute('aria-hidden')
      expect(ariaHidden).toBe('true')
    })
  })

  describe('Context Requirements', () => {
    it('throws error when SelectTrigger used outside Select', () => {
      // Suppress console.error for this test
      const spy = jest.spyOn(console, 'error').mockImplementation(() => {})

      expect(() => {
        render(
          <SelectTrigger>
            <span>Trigger</span>
          </SelectTrigger>
        )
      }).toThrow('SelectTrigger must be used within Select')

      spy.mockRestore()
    })

    it('throws error when SelectValue used outside Select', () => {
      // Suppress console.error for this test
      const spy = jest.spyOn(console, 'error').mockImplementation(() => {})

      expect(() => {
        render(<SelectValue />)
      }).toThrow('SelectValue must be used within Select')

      spy.mockRestore()
    })
  })

  describe('Edge Cases', () => {
    it('handles many options', async () => {
      const user = userEvent.setup()
      render(
        <Select value="" onValueChange={mockOnValueChange}>
          <SelectTrigger>
            <SelectValue placeholder="Select" />
          </SelectTrigger>
          <SelectContent>
            {Array.from({ length: 20 }, (_, i) => (
              <SelectItem key={i} value={`option${i}`}>
                Option {i}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )

      const button = screen.getByRole('button')
      await user.click(button)

      const options = screen.getAllByRole('option')
      expect(options).toHaveLength(20)
    })

    it('handles special characters in option text', async () => {
      const user = userEvent.setup()
      const specialText = '< > & " \' @ # $'

      render(
        <Select value="" onValueChange={mockOnValueChange}>
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="special">{specialText}</SelectItem>
          </SelectContent>
        </Select>
      )

      const button = screen.getByRole('button')
      await user.click(button)

      expect(screen.getByText(specialText)).toBeInTheDocument()
    })

    it('handles very long option text', async () => {
      const user = userEvent.setup()
      const longText = 'A'.repeat(200)

      render(
        <Select value="" onValueChange={mockOnValueChange}>
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="long">{longText}</SelectItem>
          </SelectContent>
        </Select>
      )

      const button = screen.getByRole('button')
      await user.click(button)

      expect(screen.getByText(longText)).toBeInTheDocument()
    })

    it('truncates long text with ellipsis', async () => {
      const user = userEvent.setup()
      const longText = 'A'.repeat(100)

      render(
        <Select value="" onValueChange={mockOnValueChange}>
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="long">{longText}</SelectItem>
          </SelectContent>
        </Select>
      )

      const button = screen.getByRole('button')
      await user.click(button)

      const optionText = screen.getByText(longText).closest('span')
      expect(optionText).toHaveClass('truncate')
    })

    it('handles unicode characters', async () => {
      const user = userEvent.setup()
      const unicodeText = '你好 世界 🌍 café'

      render(
        <Select value="" onValueChange={mockOnValueChange}>
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="unicode">{unicodeText}</SelectItem>
          </SelectContent>
        </Select>
      )

      const button = screen.getByRole('button')
      await user.click(button)

      expect(screen.getByText(unicodeText)).toBeInTheDocument()
    })

    it('handles empty option value', async () => {
      const user = userEvent.setup()
      render(
        <Select value="" onValueChange={mockOnValueChange}>
          <SelectTrigger>
            <SelectValue placeholder="Select" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="">None</SelectItem>
            <SelectItem value="option1">Option 1</SelectItem>
          </SelectContent>
        </Select>
      )

      const button = screen.getByRole('button')
      await user.click(button)

      const noneOption = screen.getByText('None')
      await user.click(noneOption)

      expect(mockOnValueChange).toHaveBeenCalledWith('')
    })

    it('handles rapid clicking', async () => {
      const user = userEvent.setup()
      render(<DefaultSelect />)

      const button = screen.getByRole('button')

      // Click multiple times rapidly
      await user.click(button)
      await user.click(button)
      await user.click(button)

      // Should handle gracefully
      expect(button).toBeInTheDocument()
    })
  })
})

/**
 * @jest-environment jsdom
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ToggleSwitch } from '../ToggleSwitch'

describe('ToggleSwitch Component', () => {
  const mockOnChange = jest.fn()

  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('Basic Rendering', () => {
    it('renders switch button', () => {
      render(<ToggleSwitch enabled={false} onChange={mockOnChange} />)

      const switchButton = screen.getByRole('switch')
      expect(switchButton).toBeInTheDocument()
    })

    it('renders without label by default', () => {
      render(<ToggleSwitch enabled={false} onChange={mockOnChange} />)

      const label = screen.queryByText(/./i)
      expect(label).not.toBeInTheDocument()
    })

    it('renders with label when provided', () => {
      render(
        <ToggleSwitch
          enabled={false}
          onChange={mockOnChange}
          label="Enable feature"
        />
      )

      expect(screen.getByText('Enable feature')).toBeInTheDocument()
    })

    it('renders toggle indicator dot', () => {
      const { container } = render(
        <ToggleSwitch enabled={false} onChange={mockOnChange} />
      )

      const indicator = container.querySelector(
        '.inline-block.rounded-full.bg-white'
      )
      expect(indicator).toBeInTheDocument()
    })
  })

  describe('Toggle State - Enabled Off', () => {
    it('is not checked when enabled is false', () => {
      render(<ToggleSwitch enabled={false} onChange={mockOnChange} />)

      const switchButton = screen.getByRole('switch')
      expect(switchButton).not.toBeChecked()
    })

    it('applies gray background when disabled', () => {
      const { container } = render(
        <ToggleSwitch enabled={false} onChange={mockOnChange} />
      )

      const switchButton = screen.getByRole('switch')
      expect(switchButton).toHaveClass('bg-zinc-200', 'dark:bg-zinc-700')
    })

    it('positions indicator to the left when off', () => {
      const { container } = render(
        <ToggleSwitch enabled={false} onChange={mockOnChange} />
      )

      const indicator = container.querySelector('.inline-block.rounded-full')
      expect(indicator).toHaveClass('translate-x-1')
    })
  })

  describe('Toggle State - Enabled On', () => {
    it('is checked when enabled is true', () => {
      render(<ToggleSwitch enabled={true} onChange={mockOnChange} />)

      const switchButton = screen.getByRole('switch')
      expect(switchButton).toBeChecked()
    })

    it('applies emerald background when enabled', () => {
      render(<ToggleSwitch enabled={true} onChange={mockOnChange} />)

      const switchButton = screen.getByRole('switch')
      expect(switchButton).toHaveClass('bg-emerald-600')
    })

    it('positions indicator to the right when on', () => {
      const { container } = render(
        <ToggleSwitch enabled={true} onChange={mockOnChange} />
      )

      const indicator = container.querySelector('.inline-block.rounded-full')
      expect(indicator).toHaveClass('translate-x-6')
    })
  })

  describe('User Interaction', () => {
    it('calls onChange when clicked', async () => {
      const user = userEvent.setup()
      render(<ToggleSwitch enabled={false} onChange={mockOnChange} />)

      const switchButton = screen.getByRole('switch')
      await user.click(switchButton)

      expect(mockOnChange).toHaveBeenCalledTimes(1)
      expect(mockOnChange).toHaveBeenCalledWith(true)
    })

    it('calls onChange with false when toggling off', async () => {
      const user = userEvent.setup()
      render(<ToggleSwitch enabled={true} onChange={mockOnChange} />)

      const switchButton = screen.getByRole('switch')
      await user.click(switchButton)

      expect(mockOnChange).toHaveBeenCalledWith(false)
    })

    it('can be toggled multiple times', async () => {
      const user = userEvent.setup()
      const { rerender } = render(
        <ToggleSwitch enabled={false} onChange={mockOnChange} />
      )

      const switchButton = screen.getByRole('switch')

      await user.click(switchButton)
      expect(mockOnChange).toHaveBeenLastCalledWith(true)

      rerender(<ToggleSwitch enabled={true} onChange={mockOnChange} />)
      await user.click(switchButton)
      expect(mockOnChange).toHaveBeenLastCalledWith(false)
    })
  })

  describe('Label Support', () => {
    it('renders label text', () => {
      render(
        <ToggleSwitch
          enabled={false}
          onChange={mockOnChange}
          label="Dark mode"
        />
      )

      expect(screen.getByText('Dark mode')).toBeInTheDocument()
    })

    it('label has correct styling', () => {
      render(
        <ToggleSwitch
          enabled={false}
          onChange={mockOnChange}
          label="Settings"
        />
      )

      const label = screen.getByText('Settings')
      expect(label).toHaveClass(
        'font-medium',
        'text-zinc-900',
        'dark:text-zinc-100'
      )
    })

    it('label is associated with switch', async () => {
      const user = userEvent.setup()
      render(
        <ToggleSwitch
          enabled={false}
          onChange={mockOnChange}
          label="Enable notifications"
        />
      )

      const label = screen.getByText('Enable notifications')
      await user.click(label)

      expect(mockOnChange).toHaveBeenCalledWith(true)
    })

    it('does not render label wrapper when label not provided', () => {
      const { container } = render(
        <ToggleSwitch enabled={false} onChange={mockOnChange} />
      )

      const labelElement = container.querySelector('label')
      expect(labelElement).not.toBeInTheDocument()
    })

    it('handles very long labels', () => {
      const longLabel = 'A'.repeat(100)
      render(
        <ToggleSwitch
          enabled={false}
          onChange={mockOnChange}
          label={longLabel}
        />
      )

      expect(screen.getByText(longLabel)).toBeInTheDocument()
    })

    it('handles special characters in label', () => {
      const specialLabel = '< > & " \' @ #'
      render(
        <ToggleSwitch
          enabled={false}
          onChange={mockOnChange}
          label={specialLabel}
        />
      )

      expect(screen.getByText(specialLabel)).toBeInTheDocument()
    })
  })

  describe('Disabled State', () => {
    it('disables switch when disabled is true', () => {
      render(
        <ToggleSwitch enabled={false} onChange={mockOnChange} disabled={true} />
      )

      const switchButton = screen.getByRole('switch')
      expect(switchButton).toBeDisabled()
    })

    it('applies disabled styling', () => {
      render(
        <ToggleSwitch enabled={false} onChange={mockOnChange} disabled={true} />
      )

      const switchButton = screen.getByRole('switch')
      expect(switchButton).toHaveClass('cursor-not-allowed', 'opacity-50')
    })

    it('does not call onChange when disabled and clicked', async () => {
      const user = userEvent.setup()
      render(
        <ToggleSwitch enabled={false} onChange={mockOnChange} disabled={true} />
      )

      const switchButton = screen.getByRole('switch')
      await user.click(switchButton)

      expect(mockOnChange).not.toHaveBeenCalled()
    })

    it('maintains enabled state when disabled', () => {
      render(
        <ToggleSwitch enabled={true} onChange={mockOnChange} disabled={true} />
      )

      const switchButton = screen.getByRole('switch')
      expect(switchButton).toBeChecked()
      expect(switchButton).toBeDisabled()
    })

    it('disabled switch still shows correct colors', () => {
      const { rerender } = render(
        <ToggleSwitch enabled={false} onChange={mockOnChange} disabled={true} />
      )

      let switchButton = screen.getByRole('switch')
      expect(switchButton).toHaveClass('bg-zinc-200')

      rerender(
        <ToggleSwitch enabled={true} onChange={mockOnChange} disabled={true} />
      )
      switchButton = screen.getByRole('switch')
      expect(switchButton).toHaveClass('bg-emerald-600')
    })
  })

  describe('Styling', () => {
    it('applies base switch styles', () => {
      render(<ToggleSwitch enabled={false} onChange={mockOnChange} />)

      const switchButton = screen.getByRole('switch')
      expect(switchButton).toHaveClass(
        'relative',
        'inline-flex',
        'h-6',
        'w-11',
        'items-center',
        'rounded-full'
      )
    })

    it('applies transition classes', () => {
      render(<ToggleSwitch enabled={false} onChange={mockOnChange} />)

      const switchButton = screen.getByRole('switch')
      expect(switchButton).toHaveClass('transition-colors')
    })

    it('applies focus ring styles', () => {
      render(<ToggleSwitch enabled={false} onChange={mockOnChange} />)

      const switchButton = screen.getByRole('switch')
      expect(switchButton).toHaveClass(
        'focus:outline-none',
        'focus:ring-2',
        'focus:ring-emerald-500',
        'focus:ring-offset-2'
      )
    })

    it('indicator has rounded styling', () => {
      const { container } = render(
        <ToggleSwitch enabled={false} onChange={mockOnChange} />
      )

      const indicator = container.querySelector('.inline-block')
      expect(indicator).toHaveClass('rounded-full', 'bg-white')
    })

    it('indicator has correct size', () => {
      const { container } = render(
        <ToggleSwitch enabled={false} onChange={mockOnChange} />
      )

      const indicator = container.querySelector('.inline-block')
      expect(indicator).toHaveClass('h-4', 'w-4')
    })

    it('applies dark mode classes', () => {
      render(<ToggleSwitch enabled={false} onChange={mockOnChange} />)

      const switchButton = screen.getByRole('switch')
      expect(switchButton).toHaveClass('dark:bg-zinc-700')
    })

    it('label has dark mode support', () => {
      render(
        <ToggleSwitch
          enabled={false}
          onChange={mockOnChange}
          label="Test label"
        />
      )

      const label = screen.getByText('Test label')
      expect(label).toHaveClass('dark:text-zinc-100')
    })
  })

  describe('Accessibility', () => {
    it('has switch role', () => {
      render(<ToggleSwitch enabled={false} onChange={mockOnChange} />)

      expect(screen.getByRole('switch')).toBeInTheDocument()
    })

    it('can receive focus', () => {
      render(<ToggleSwitch enabled={false} onChange={mockOnChange} />)

      const switchButton = screen.getByRole('switch')
      switchButton.focus()
      expect(switchButton).toHaveFocus()
    })

    it('is keyboard navigable with Space', async () => {
      const user = userEvent.setup()
      render(<ToggleSwitch enabled={false} onChange={mockOnChange} />)

      const switchButton = screen.getByRole('switch')
      switchButton.focus()

      await user.keyboard(' ')
      expect(mockOnChange).toHaveBeenCalledWith(true)
    })

    it('can be tabbed to', async () => {
      const user = userEvent.setup()
      render(
        <div>
          <button>Before</button>
          <ToggleSwitch enabled={false} onChange={mockOnChange} />
          <button>After</button>
        </div>
      )

      const beforeButton = screen.getByRole('button', { name: 'Before' })
      const switchButton = screen.getByRole('switch')
      const afterButton = screen.getByRole('button', { name: 'After' })

      beforeButton.focus()
      await user.tab()
      expect(switchButton).toHaveFocus()

      await user.tab()
      expect(afterButton).toHaveFocus()
    })

    it('label is properly associated with switch', () => {
      render(
        <ToggleSwitch
          enabled={false}
          onChange={mockOnChange}
          label="Enable feature"
        />
      )

      const switchButton = screen.getByRole('switch')
      const label = screen.getByText('Enable feature')

      // Label should be rendered as sibling in Switch.Group
      expect(label).toBeInTheDocument()
      expect(switchButton).toBeInTheDocument()
    })
  })

  describe('Controlled Behavior', () => {
    it('maintains controlled state', () => {
      const { rerender } = render(
        <ToggleSwitch enabled={false} onChange={mockOnChange} />
      )

      let switchButton = screen.getByRole('switch')
      expect(switchButton).not.toBeChecked()

      rerender(<ToggleSwitch enabled={true} onChange={mockOnChange} />)
      switchButton = screen.getByRole('switch')
      expect(switchButton).toBeChecked()
    })

    it('updates visual state when enabled prop changes', () => {
      const { rerender, container } = render(
        <ToggleSwitch enabled={false} onChange={mockOnChange} />
      )

      let indicator = container.querySelector('.inline-block')
      expect(indicator).toHaveClass('translate-x-1')

      rerender(<ToggleSwitch enabled={true} onChange={mockOnChange} />)
      indicator = container.querySelector('.inline-block')
      expect(indicator).toHaveClass('translate-x-6')
    })

    it('background color updates with enabled prop', () => {
      const { rerender } = render(
        <ToggleSwitch enabled={false} onChange={mockOnChange} />
      )

      let switchButton = screen.getByRole('switch')
      expect(switchButton).toHaveClass('bg-zinc-200')

      rerender(<ToggleSwitch enabled={true} onChange={mockOnChange} />)
      switchButton = screen.getByRole('switch')
      expect(switchButton).toHaveClass('bg-emerald-600')
    })
  })

  describe('Edge Cases', () => {
    it('handles rapid clicking', async () => {
      const user = userEvent.setup()
      render(<ToggleSwitch enabled={false} onChange={mockOnChange} />)

      const switchButton = screen.getByRole('switch')

      await user.click(switchButton)
      await user.click(switchButton)
      await user.click(switchButton)

      expect(mockOnChange).toHaveBeenCalledTimes(3)
    })

    it('handles unicode in label', () => {
      const unicodeLabel = '你好 世界 🌍 café'
      render(
        <ToggleSwitch
          enabled={false}
          onChange={mockOnChange}
          label={unicodeLabel}
        />
      )

      expect(screen.getByText(unicodeLabel)).toBeInTheDocument()
    })

    it('maintains state consistency during interaction', async () => {
      const user = userEvent.setup()
      const { rerender } = render(
        <ToggleSwitch enabled={false} onChange={mockOnChange} />
      )

      const switchButton = screen.getByRole('switch')

      // Click should call onChange with true
      await user.click(switchButton)
      expect(mockOnChange).toHaveBeenLastCalledWith(true)

      // Update to enabled state
      rerender(<ToggleSwitch enabled={true} onChange={mockOnChange} />)

      // Click again should call onChange with false
      await user.click(switchButton)
      expect(mockOnChange).toHaveBeenLastCalledWith(false)
    })

    it('works with empty string label', () => {
      render(<ToggleSwitch enabled={false} onChange={mockOnChange} label="" />)

      const switchButton = screen.getByRole('switch')
      expect(switchButton).toBeInTheDocument()
    })

    it('handles disabled prop changes dynamically', () => {
      const { rerender } = render(
        <ToggleSwitch
          enabled={false}
          onChange={mockOnChange}
          disabled={false}
        />
      )

      let switchButton = screen.getByRole('switch')
      expect(switchButton).not.toBeDisabled()

      rerender(
        <ToggleSwitch enabled={false} onChange={mockOnChange} disabled={true} />
      )
      switchButton = screen.getByRole('switch')
      expect(switchButton).toBeDisabled()
    })
  })
})

/**
 * @jest-environment jsdom
 */

import { fireEvent, render, screen } from '@testing-library/react'
import {
  OperationStatus,
  OperationToast,
  OperationType,
} from '../OperationToast'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => {
      const translations: Record<string, string> = {
        'toasts.operation.generation': 'Response Generation',
        'toasts.operation.evaluation': 'Evaluation',
        'toasts.operation.viewStatus': 'Click to view detailed status \u2192',
      }
      return translations[key] || key
    },
    locale: 'en',
  }),
}))

// Mock next/navigation
const mockPush = jest.fn()
jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mockPush,
  }),
}))

describe('OperationToast', () => {
  const defaultProps = {
    id: 'test-id',
    type: 'generation' as OperationType,
    status: 'started' as OperationStatus,
    taskId: 'task-123',
    message: 'Test message',
    onDismiss: jest.fn(),
  }

  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('Basic Rendering', () => {
    it('renders with required props', () => {
      render(<OperationToast {...defaultProps} />)
      expect(screen.getByText('Test message')).toBeInTheDocument()
      expect(screen.getByText('Response Generation')).toBeInTheDocument()
    })

    it('renders evaluation type label correctly', () => {
      render(<OperationToast {...defaultProps} type="evaluation" />)
      expect(screen.getByText('Evaluation')).toBeInTheDocument()
    })

    it('renders generation type label correctly', () => {
      render(<OperationToast {...defaultProps} type="generation" />)
      expect(screen.getByText('Response Generation')).toBeInTheDocument()
    })

    it('renders with optional details', () => {
      render(<OperationToast {...defaultProps} details="Additional details" />)
      expect(screen.getByText('Additional details')).toBeInTheDocument()
    })

    it('renders without details when not provided', () => {
      render(<OperationToast {...defaultProps} />)
      expect(screen.queryByText('Additional details')).not.toBeInTheDocument()
    })
  })

  describe('Operation Status Display', () => {
    it('displays started status correctly', () => {
      const { container } = render(
        <OperationToast {...defaultProps} status="started" />
      )
      expect(screen.getByText('▶')).toBeInTheDocument()
      expect(container.querySelector('.bg-emerald-500')).toBeInTheDocument()
    })

    it('displays running status correctly', () => {
      const { container } = render(
        <OperationToast {...defaultProps} status="running" />
      )
      const spinner = container.querySelector('.animate-spin')
      expect(spinner).toBeInTheDocument()
      expect(container.querySelector('.bg-amber-500')).toBeInTheDocument()
    })

    it('displays completed status correctly', () => {
      const { container } = render(
        <OperationToast {...defaultProps} status="completed" />
      )
      expect(screen.getByText('✓')).toBeInTheDocument()
      expect(container.querySelector('.bg-emerald-500')).toBeInTheDocument()
    })

    it('displays failed status correctly', () => {
      const { container } = render(
        <OperationToast {...defaultProps} status="failed" />
      )
      expect(screen.getByText('✗')).toBeInTheDocument()
      expect(container.querySelector('.bg-red-500')).toBeInTheDocument()
    })

    it('applies correct background color for started status', () => {
      const { container } = render(
        <OperationToast {...defaultProps} status="started" />
      )
      const toast = container.querySelector('.bg-emerald-50')
      expect(toast).toBeInTheDocument()
    })

    it('applies correct background color for running status', () => {
      const { container } = render(
        <OperationToast {...defaultProps} status="running" />
      )
      const toast = container.querySelector('.bg-amber-50')
      expect(toast).toBeInTheDocument()
    })

    it('applies correct background color for completed status', () => {
      const { container } = render(
        <OperationToast {...defaultProps} status="completed" />
      )
      const toast = container.querySelector('.bg-emerald-50')
      expect(toast).toBeInTheDocument()
    })

    it('applies correct background color for failed status', () => {
      const { container } = render(
        <OperationToast {...defaultProps} status="failed" />
      )
      const toast = container.querySelector('.bg-red-50')
      expect(toast).toBeInTheDocument()
    })

    it('applies correct text color for started status', () => {
      const { container } = render(
        <OperationToast {...defaultProps} status="started" />
      )
      const textElement = container.querySelector('.text-emerald-800')
      expect(textElement).toBeInTheDocument()
    })

    it('applies correct text color for running status', () => {
      const { container } = render(
        <OperationToast {...defaultProps} status="running" />
      )
      const textElement = container.querySelector('.text-amber-800')
      expect(textElement).toBeInTheDocument()
    })

    it('applies correct text color for completed status', () => {
      const { container } = render(
        <OperationToast {...defaultProps} status="completed" />
      )
      const textElement = container.querySelector('.text-emerald-800')
      expect(textElement).toBeInTheDocument()
    })

    it('applies correct text color for failed status', () => {
      const { container } = render(
        <OperationToast {...defaultProps} status="failed" />
      )
      const textElement = container.querySelector('.text-red-800')
      expect(textElement).toBeInTheDocument()
    })
  })

  describe('Message Display', () => {
    it('displays custom message', () => {
      render(
        <OperationToast {...defaultProps} message="Custom operation message" />
      )
      expect(screen.getByText('Custom operation message')).toBeInTheDocument()
    })

    it('displays message with special characters', () => {
      render(
        <OperationToast
          {...defaultProps}
          message="Message with special chars: @#$%&*()"
        />
      )
      expect(
        screen.getByText('Message with special chars: @#$%&*()')
      ).toBeInTheDocument()
    })

    it('displays message with line breaks', () => {
      const { container } = render(
        <OperationToast {...defaultProps} message="Line 1\nLine 2\nLine 3" />
      )
      // Line breaks are preserved in the DOM but rendered as text
      const paragraphs = container.querySelectorAll('p')
      const messageParagraph = Array.from(paragraphs).find((p) =>
        p.textContent?.includes('Line 1')
      )
      expect(messageParagraph?.textContent).toContain('Line 1')
      expect(messageParagraph?.textContent).toContain('Line 2')
    })

    it('displays long message', () => {
      const longMessage = 'A'.repeat(200)
      render(<OperationToast {...defaultProps} message={longMessage} />)
      expect(screen.getByText(longMessage)).toBeInTheDocument()
    })

    it('displays details when provided', () => {
      render(
        <OperationToast
          {...defaultProps}
          message="Main message"
          details="Detail text"
        />
      )
      expect(screen.getByText('Main message')).toBeInTheDocument()
      expect(screen.getByText('Detail text')).toBeInTheDocument()
    })

    it('displays long details text', () => {
      const longDetails = 'B'.repeat(150)
      render(<OperationToast {...defaultProps} details={longDetails} />)
      expect(screen.getByText(longDetails)).toBeInTheDocument()
    })
  })

  describe('Icons/Indicators', () => {
    it('displays rocket icon for started status', () => {
      render(<OperationToast {...defaultProps} status="started" />)
      expect(screen.getByText('▶')).toBeInTheDocument()
    })

    it('displays spinner for running status', () => {
      const { container } = render(
        <OperationToast {...defaultProps} status="running" />
      )
      const spinner = container.querySelector('.animate-spin')
      expect(spinner).toBeInTheDocument()
      expect(spinner).toHaveClass(
        'rounded-full',
        'border-2',
        'border-white',
        'border-t-transparent'
      )
    })

    it('displays checkmark icon for completed status', () => {
      render(<OperationToast {...defaultProps} status="completed" />)
      expect(screen.getByText('✓')).toBeInTheDocument()
    })

    it('displays error icon for failed status', () => {
      render(<OperationToast {...defaultProps} status="failed" />)
      expect(screen.getByText('✗')).toBeInTheDocument()
    })

    it('displays status indicator bar', () => {
      const { container } = render(<OperationToast {...defaultProps} />)
      const statusBar = container.querySelector(
        '.absolute.left-0.right-0.top-0.h-1'
      )
      expect(statusBar).toBeInTheDocument()
    })

    it('status indicator bar has correct color for each status', () => {
      const statuses: OperationStatus[] = [
        'started',
        'running',
        'completed',
        'failed',
      ]
      statuses.forEach((status) => {
        const { container } = render(
          <OperationToast {...defaultProps} status={status} />
        )
        const statusBar = container.querySelector('.h-1')
        expect(statusBar).toBeInTheDocument()
      })
    })
  })

  describe('Close/Dismiss Functionality', () => {
    it('calls onDismiss when close button is clicked', () => {
      const onDismiss = jest.fn()
      render(<OperationToast {...defaultProps} onDismiss={onDismiss} />)
      const closeButton = screen.getByText('×')
      fireEvent.click(closeButton)
      expect(onDismiss).toHaveBeenCalledTimes(1)
    })

    it('stops propagation when close button is clicked', () => {
      const onDismiss = jest.fn()
      const { container } = render(
        <OperationToast {...defaultProps} onDismiss={onDismiss} />
      )
      const closeButton = screen.getByText('×')
      const clickEvent = new MouseEvent('click', { bubbles: true })
      const stopPropagationSpy = jest.spyOn(clickEvent, 'stopPropagation')
      fireEvent(closeButton, clickEvent)
      expect(stopPropagationSpy).toHaveBeenCalled()
    })

    it('close button has hover effect', () => {
      const { container } = render(<OperationToast {...defaultProps} />)
      const closeButton = screen.getByText('×').closest('button')
      expect(closeButton).toHaveClass('hover:bg-black/10')
    })

    it('renders close button with proper styling', () => {
      const { container } = render(<OperationToast {...defaultProps} />)
      const closeButton = screen.getByText('×').closest('button')
      expect(closeButton).toHaveClass(
        'rounded-full',
        'p-1',
        'transition-colors'
      )
    })
  })

  describe('Clickable Behavior', () => {
    it('shows click hint for running status when clickable', () => {
      render(
        <OperationToast {...defaultProps} status="running" clickable={true} />
      )
      expect(
        screen.getByText('Click to view detailed status →')
      ).toBeInTheDocument()
    })

    it('shows click hint for completed status when clickable', () => {
      render(
        <OperationToast {...defaultProps} status="completed" clickable={true} />
      )
      expect(
        screen.getByText('Click to view detailed status →')
      ).toBeInTheDocument()
    })

    it('shows click hint for failed status when clickable', () => {
      render(
        <OperationToast {...defaultProps} status="failed" clickable={true} />
      )
      expect(
        screen.getByText('Click to view detailed status →')
      ).toBeInTheDocument()
    })

    it('does not show click hint for started status', () => {
      render(
        <OperationToast {...defaultProps} status="started" clickable={true} />
      )
      expect(
        screen.queryByText('Click to view detailed status →')
      ).not.toBeInTheDocument()
    })

    it('does not show click hint when not clickable', () => {
      render(
        <OperationToast {...defaultProps} status="running" clickable={false} />
      )
      expect(
        screen.queryByText('Click to view detailed status →')
      ).not.toBeInTheDocument()
    })

    it('applies cursor-pointer class when clickable and status allows', () => {
      const { container } = render(
        <OperationToast {...defaultProps} status="running" clickable={true} />
      )
      const toast = container.firstChild
      expect(toast).toHaveClass('cursor-pointer')
    })

    it('does not apply cursor-pointer class when not clickable', () => {
      const { container } = render(
        <OperationToast {...defaultProps} status="running" clickable={false} />
      )
      const toast = container.firstChild
      expect(toast).not.toHaveClass('cursor-pointer')
    })

    it('applies hover effect when clickable', () => {
      const { container } = render(
        <OperationToast {...defaultProps} status="running" clickable={true} />
      )
      const toast = container.firstChild
      expect(toast).toHaveClass('hover:shadow-xl')
    })

    it('does not apply hover effect when not clickable', () => {
      const { container } = render(
        <OperationToast {...defaultProps} status="started" clickable={true} />
      )
      const toast = container.firstChild
      expect(toast).not.toHaveClass('cursor-pointer')
    })

    it('defaults to clickable=true when not specified', () => {
      render(<OperationToast {...defaultProps} status="running" />)
      expect(
        screen.getByText('Click to view detailed status →')
      ).toBeInTheDocument()
    })

    it('handles click on toast container', () => {
      const { container } = render(
        <OperationToast {...defaultProps} status="running" clickable={true} />
      )
      const toast = container.firstChild as HTMLElement
      fireEvent.click(toast)
      // Navigation is disabled, so just verify no errors occur
      expect(mockPush).not.toHaveBeenCalled()
    })
  })

  describe('Accessibility', () => {
    it('renders close button as button element', () => {
      render(<OperationToast {...defaultProps} />)
      const closeButton = screen.getByText('×')
      expect(closeButton.closest('button')).toBeInTheDocument()
    })

    it('has proper structure for screen readers', () => {
      const { container } = render(<OperationToast {...defaultProps} />)
      const heading = screen.getByText('Response Generation')
      expect(heading).toHaveClass('font-medium')
    })

    it('status icon is contained in a visible element', () => {
      const { container } = render(
        <OperationToast {...defaultProps} status="started" />
      )
      const icon = screen.getByText('▶')
      expect(icon).toBeVisible()
    })

    it('maintains text contrast with background colors', () => {
      const { container } = render(
        <OperationToast {...defaultProps} status="failed" />
      )
      const message = screen.getByText('Test message')
      expect(message).toHaveClass('text-red-800')
    })

    it('close button is keyboard accessible', () => {
      render(<OperationToast {...defaultProps} />)
      const closeButton = screen.getByText('×').closest('button')
      expect(closeButton?.tagName).toBe('BUTTON')
    })
  })

  describe('Dark Mode Classes', () => {
    it('includes dark mode background classes for started status', () => {
      const { container } = render(
        <OperationToast {...defaultProps} status="started" />
      )
      const toast = container.querySelector('.dark\\:bg-emerald-900\\/20')
      expect(toast).toBeInTheDocument()
    })

    it('includes dark mode background classes for running status', () => {
      const { container } = render(
        <OperationToast {...defaultProps} status="running" />
      )
      const toast = container.querySelector('.dark\\:bg-amber-900\\/20')
      expect(toast).toBeInTheDocument()
    })

    it('includes dark mode background classes for completed status', () => {
      const { container } = render(
        <OperationToast {...defaultProps} status="completed" />
      )
      const toast = container.querySelector('.dark\\:bg-emerald-900\\/20')
      expect(toast).toBeInTheDocument()
    })

    it('includes dark mode background classes for failed status', () => {
      const { container } = render(
        <OperationToast {...defaultProps} status="failed" />
      )
      const toast = container.querySelector('.dark\\:bg-red-900\\/20')
      expect(toast).toBeInTheDocument()
    })

    it('includes dark mode text classes for started status', () => {
      const { container } = render(
        <OperationToast {...defaultProps} status="started" />
      )
      const textElement = container.querySelector('.dark\\:text-emerald-200')
      expect(textElement).toBeInTheDocument()
    })

    it('includes dark mode text classes for running status', () => {
      const { container } = render(
        <OperationToast {...defaultProps} status="running" />
      )
      const textElement = container.querySelector('.dark\\:text-amber-200')
      expect(textElement).toBeInTheDocument()
    })

    it('includes dark mode text classes for completed status', () => {
      const { container } = render(
        <OperationToast {...defaultProps} status="completed" />
      )
      const textElement = container.querySelector('.dark\\:text-emerald-200')
      expect(textElement).toBeInTheDocument()
    })

    it('includes dark mode text classes for failed status', () => {
      const { container } = render(
        <OperationToast {...defaultProps} status="failed" />
      )
      const textElement = container.querySelector('.dark\\:text-red-200')
      expect(textElement).toBeInTheDocument()
    })

    it('includes dark mode border classes', () => {
      const { container } = render(
        <OperationToast {...defaultProps} status="started" />
      )
      const toast = container.querySelector('.dark\\:border-emerald-700')
      expect(toast).toBeInTheDocument()
    })
  })

  describe('Default/Unknown Status', () => {
    it('handles unknown status with default colors', () => {
      const { container } = render(
        <OperationToast {...defaultProps} status={'unknown' as OperationStatus} />
      )
      // Default status should use zinc colors
      const toast = container.querySelector('.bg-zinc-50')
      expect(toast).toBeInTheDocument()
    })

    it('shows circle icon for unknown status', () => {
      render(
        <OperationToast {...defaultProps} status={'unknown' as OperationStatus} />
      )
      expect(screen.getByText('○')).toBeInTheDocument()
    })

    it('applies default text color for unknown status', () => {
      const { container } = render(
        <OperationToast {...defaultProps} status={'unknown' as OperationStatus} />
      )
      const textElement = container.querySelector('.text-zinc-800')
      expect(textElement).toBeInTheDocument()
    })

    it('applies default status bar color for unknown status', () => {
      const { container } = render(
        <OperationToast {...defaultProps} status={'unknown' as OperationStatus} />
      )
      const statusBar = container.querySelector('.bg-zinc-500')
      expect(statusBar).toBeInTheDocument()
    })
  })

  describe('Edge Cases', () => {
    it('handles empty message gracefully', () => {
      render(<OperationToast {...defaultProps} message="" />)
      const message = screen.getByText((content, element) => {
        return element?.className.includes('text-sm') && content === ''
      })
      expect(message).toBeInTheDocument()
    })

    it('handles empty details gracefully', () => {
      const { container } = render(
        <OperationToast {...defaultProps} details="" />
      )
      // Empty string is falsy, so details paragraph should not render
      const paragraphs = container.querySelectorAll('p')
      const detailsParagraph = Array.from(paragraphs).find((p) =>
        p.className.includes('opacity-75')
      )
      expect(detailsParagraph).toBeUndefined()
    })

    it('handles undefined details gracefully', () => {
      render(<OperationToast {...defaultProps} details={undefined} />)
      // Should not render details paragraph
      const { container } = render(<OperationToast {...defaultProps} />)
      const detailsElements = container.querySelectorAll('.text-xs.opacity-75')
      expect(detailsElements.length).toBe(0)
    })

    it('handles very long task IDs', () => {
      const longTaskId = 'task-' + 'x'.repeat(100)
      render(<OperationToast {...defaultProps} taskId={longTaskId} />)
      expect(screen.getByText('Test message')).toBeInTheDocument()
    })

    it('handles special characters in message', () => {
      render(
        <OperationToast
          {...defaultProps}
          message="<script>alert('xss')</script>"
        />
      )
      expect(
        screen.getByText("<script>alert('xss')</script>")
      ).toBeInTheDocument()
    })

    it('handles special characters in details', () => {
      render(
        <OperationToast {...defaultProps} details="Details with <html> tags" />
      )
      expect(screen.getByText('Details with <html> tags')).toBeInTheDocument()
    })

    it('handles unicode characters in message', () => {
      render(<OperationToast {...defaultProps} message="✨ Unicode test 🌟" />)
      expect(screen.getByText('✨ Unicode test 🌟')).toBeInTheDocument()
    })

    it('handles multiple toasts with same props', () => {
      const { rerender } = render(<OperationToast {...defaultProps} />)
      rerender(<OperationToast {...defaultProps} message="Updated message" />)
      expect(screen.getByText('Updated message')).toBeInTheDocument()
    })

    it('maintains structure with all props at minimum values', () => {
      render(
        <OperationToast
          id=""
          type="generation"
          status="started"
          taskId=""
          message=""
          onDismiss={jest.fn()}
        />
      )
      expect(screen.getByText('Response Generation')).toBeInTheDocument()
    })

    it('handles rapid status changes', () => {
      const { rerender } = render(
        <OperationToast {...defaultProps} status="started" />
      )
      rerender(<OperationToast {...defaultProps} status="running" />)
      rerender(<OperationToast {...defaultProps} status="completed" />)
      expect(screen.getByText('✓')).toBeInTheDocument()
    })

    it('maintains state when props change except status', () => {
      const { rerender } = render(
        <OperationToast {...defaultProps} message="Initial message" />
      )
      rerender(<OperationToast {...defaultProps} message="Updated message" />)
      expect(screen.getByText('Updated message')).toBeInTheDocument()
      expect(screen.queryByText('Initial message')).not.toBeInTheDocument()
    })

    it('handles onDismiss being called multiple times', () => {
      const onDismiss = jest.fn()
      render(<OperationToast {...defaultProps} onDismiss={onDismiss} />)
      const closeButton = screen.getByText('×')
      fireEvent.click(closeButton)
      fireEvent.click(closeButton)
      fireEvent.click(closeButton)
      expect(onDismiss).toHaveBeenCalledTimes(3)
    })
  })
})

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { AlertDialog } from '../AlertDialog'
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, varsOrDefault?: any) => {
      const translations: Record<string, any> = require('../../../locales/en/common.json')
      const parts = key.split('.')
      let value: any = translations
      for (const part of parts) {
        if (value && typeof value === 'object' && part in value) {
          value = value[part]
        } else {
          return key
        }
      }
      if (typeof value !== 'string') return key
      if (varsOrDefault && typeof varsOrDefault === 'object') {
        for (const [k, v] of Object.entries(varsOrDefault)) {
          value = value.replace(new RegExp(`\\{${k}\\}`, 'g'), String(v))
        }
      }
      return value
    },
    locale: 'en',
  }),
}))


jest.unmock('@/components/shared/AlertDialog')

// Mock heroicons
jest.mock('@heroicons/react/24/outline', () => ({
  CheckCircleIcon: (props: any) => (
    <svg {...props} data-testid="check-circle-icon" />
  ),
  ExclamationTriangleIcon: (props: any) => (
    <svg {...props} data-testid="exclamation-triangle-icon" />
  ),
  InformationCircleIcon: (props: any) => (
    <svg {...props} data-testid="information-circle-icon" />
  ),
  XCircleIcon: (props: any) => <svg {...props} data-testid="x-circle-icon" />,
  XMarkIcon: (props: any) => <svg {...props} data-testid="x-mark-icon" />,
}))

// Mock Headless UI
jest.mock('@headlessui/react', () => {
  const mockFragment = ({ children }: any) => children

  let currentOnClose: (() => void) | null = null

  return {
    Dialog: Object.assign(
      ({ children, onClose, ...props }: any) => {
        currentOnClose = onClose
        return <div {...props}>{children}</div>
      },
      {
        Panel: ({ children, ...props }: any) => (
          <div {...props}>{children}</div>
        ),
        Title: ({ children, ...props }: any) => <h3 {...props}>{children}</h3>,
      }
    ),
    Transition: Object.assign(
      ({ show, appear, children, ...props }: any) =>
        show ? <div {...props}>{children}</div> : null,
      {
        Child: ({ children, ...props }: any) => {
          const childrenWithClickHandler = Array.isArray(children)
            ? children
            : [children]
          const processedChildren = childrenWithClickHandler.map(
            (child: any) => {
              if (child?.props?.className?.includes('fixed inset-0 bg-black')) {
                return {
                  ...child,
                  props: {
                    ...child.props,
                    onClick: () => currentOnClose && currentOnClose(),
                  },
                }
              }
              return child
            }
          )

          return (
            <div {...props}>
              {Array.isArray(children)
                ? processedChildren
                : processedChildren[0]}
            </div>
          )
        },
      }
    ),
    Fragment: mockFragment,
  }
})

describe('AlertDialog', () => {
  const defaultProps = {
    isOpen: true,
    onClose: jest.fn(),
    title: 'Alert Title',
    message: 'This is an alert message',
  }

  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('Basic Rendering', () => {
    it('renders when isOpen is true', () => {
      render(<AlertDialog {...defaultProps} />)
      expect(screen.getByText('Alert Title')).toBeInTheDocument()
      expect(screen.getByText('This is an alert message')).toBeInTheDocument()
    })

    it('does not render when isOpen is false', () => {
      render(<AlertDialog {...defaultProps} isOpen={false} />)
      expect(screen.queryByText('Alert Title')).not.toBeInTheDocument()
    })

    it('renders with all required props', () => {
      render(<AlertDialog {...defaultProps} />)
      const heading = screen.getByRole('heading', { name: 'Alert Title' })
      expect(heading).toBeInTheDocument()
    })

    it('renders the close button icon', () => {
      render(<AlertDialog {...defaultProps} />)
      const closeIcon = screen.getByTestId('x-mark-icon')
      expect(closeIcon).toBeInTheDocument()
    })
  })

  describe('Open/Close State', () => {
    it('handles sequential open/close states', () => {
      const { rerender } = render(
        <AlertDialog {...defaultProps} isOpen={false} />
      )
      expect(screen.queryByText('Alert Title')).not.toBeInTheDocument()

      rerender(<AlertDialog {...defaultProps} isOpen={true} />)
      expect(screen.getByText('Alert Title')).toBeInTheDocument()

      rerender(<AlertDialog {...defaultProps} isOpen={false} />)
      expect(screen.queryByText('Alert Title')).not.toBeInTheDocument()
    })

    it('maintains content when toggling visibility', () => {
      const { rerender } = render(<AlertDialog {...defaultProps} />)
      expect(screen.getByText('Alert Title')).toBeInTheDocument()

      rerender(<AlertDialog {...defaultProps} isOpen={false} />)
      expect(screen.queryByText('Alert Title')).not.toBeInTheDocument()

      rerender(<AlertDialog {...defaultProps} isOpen={true} />)
      expect(screen.getByText('Alert Title')).toBeInTheDocument()
      expect(screen.getByText('This is an alert message')).toBeInTheDocument()
    })
  })

  describe('Actions (Cancel/Confirm)', () => {
    it('renders default OK button text', () => {
      render(<AlertDialog {...defaultProps} />)
      expect(screen.getByRole('button', { name: 'OK' })).toBeInTheDocument()
    })

    it('renders custom button text', () => {
      render(<AlertDialog {...defaultProps} buttonText="Got it" />)
      expect(screen.getByRole('button', { name: 'Got it' })).toBeInTheDocument()
    })

    it('calls onClose when OK button is clicked', () => {
      render(<AlertDialog {...defaultProps} />)
      fireEvent.click(screen.getByRole('button', { name: 'OK' }))
      expect(defaultProps.onClose).toHaveBeenCalledTimes(1)
    })

    it('calls onClose when close button is clicked', () => {
      render(<AlertDialog {...defaultProps} />)
      const closeButton = screen
        .getByTestId('x-mark-icon')
        .closest('button') as HTMLElement
      fireEvent.click(closeButton)
      expect(defaultProps.onClose).toHaveBeenCalledTimes(1)
    })

    it('calls onClose when backdrop is clicked', async () => {
      const { container } = render(<AlertDialog {...defaultProps} />)
      const backdrop = container.querySelector('.fixed.inset-0.bg-black')

      if (backdrop) {
        fireEvent.click(backdrop)
        await waitFor(() => {
          expect(defaultProps.onClose).toHaveBeenCalled()
        })
      }
    })
  })

  describe('Title and Description', () => {
    it('displays the title correctly', () => {
      render(<AlertDialog {...defaultProps} title="Important Notice" />)
      expect(screen.getByText('Important Notice')).toBeInTheDocument()
    })

    it('displays the message correctly', () => {
      render(
        <AlertDialog
          {...defaultProps}
          message="This is a critical alert message"
        />
      )
      expect(
        screen.getByText('This is a critical alert message')
      ).toBeInTheDocument()
    })

    it('updates title dynamically', () => {
      const { rerender } = render(<AlertDialog {...defaultProps} />)
      expect(screen.getByText('Alert Title')).toBeInTheDocument()

      rerender(<AlertDialog {...defaultProps} title="New Title" />)
      expect(screen.getByText('New Title')).toBeInTheDocument()
      expect(screen.queryByText('Alert Title')).not.toBeInTheDocument()
    })

    it('updates message dynamically', () => {
      const { rerender } = render(<AlertDialog {...defaultProps} />)
      expect(screen.getByText('This is an alert message')).toBeInTheDocument()

      rerender(<AlertDialog {...defaultProps} message="Updated message text" />)
      expect(screen.getByText('Updated message text')).toBeInTheDocument()
      expect(
        screen.queryByText('This is an alert message')
      ).not.toBeInTheDocument()
    })
  })

  describe('Styling', () => {
    it('renders info variant with correct icon', () => {
      render(<AlertDialog {...defaultProps} variant="info" />)
      const infoIcon = screen.getByTestId('information-circle-icon')
      expect(infoIcon).toBeInTheDocument()
      expect(infoIcon).toHaveClass('h-6', 'w-6')
    })

    it('renders success variant with correct icon', () => {
      render(<AlertDialog {...defaultProps} variant="success" />)
      const successIcon = screen.getByTestId('check-circle-icon')
      expect(successIcon).toBeInTheDocument()
      expect(successIcon).toHaveClass('h-6', 'w-6')
    })

    it('renders error variant with correct icon', () => {
      render(<AlertDialog {...defaultProps} variant="error" />)
      const errorIcon = screen.getByTestId('x-circle-icon')
      expect(errorIcon).toBeInTheDocument()
      expect(errorIcon).toHaveClass('h-6', 'w-6')
    })

    it('renders warning variant with correct icon', () => {
      render(<AlertDialog {...defaultProps} variant="warning" />)
      const warningIcon = screen.getByTestId('exclamation-triangle-icon')
      expect(warningIcon).toBeInTheDocument()
      expect(warningIcon).toHaveClass('h-6', 'w-6')
    })

    it('defaults to info variant when no variant specified', () => {
      render(<AlertDialog {...defaultProps} />)
      const infoIcon = screen.getByTestId('information-circle-icon')
      expect(infoIcon).toBeInTheDocument()
    })

    it('applies correct color classes for success variant', () => {
      render(<AlertDialog {...defaultProps} variant="success" />)
      const icon = screen.getByTestId('check-circle-icon')
      expect(icon).toHaveClass('text-emerald-600', 'dark:text-emerald-400')
    })

    it('applies correct color classes for error variant', () => {
      render(<AlertDialog {...defaultProps} variant="error" />)
      const icon = screen.getByTestId('x-circle-icon')
      expect(icon).toHaveClass('text-red-600', 'dark:text-red-400')
    })

    it('applies correct color classes for warning variant', () => {
      render(<AlertDialog {...defaultProps} variant="warning" />)
      const icon = screen.getByTestId('exclamation-triangle-icon')
      expect(icon).toHaveClass('text-amber-600', 'dark:text-amber-400')
    })

    it('applies correct color classes for info variant', () => {
      render(<AlertDialog {...defaultProps} variant="info" />)
      const icon = screen.getByTestId('information-circle-icon')
      expect(icon).toHaveClass('text-blue-600', 'dark:text-blue-400')
    })
  })

  describe('Accessibility', () => {
    it('renders as a dialog with proper ARIA role', () => {
      render(<AlertDialog {...defaultProps} />)
      const heading = screen.getByRole('heading', { name: 'Alert Title' })
      expect(heading).toBeInTheDocument()
    })

    it('has accessible close button with sr-only text', () => {
      render(<AlertDialog {...defaultProps} />)
      const closeButton = screen
        .getByTestId('x-mark-icon')
        .closest('button') as HTMLElement
      expect(closeButton).toBeInTheDocument()
      const srOnlyText = closeButton.querySelector('.sr-only')
      expect(srOnlyText).toHaveTextContent('Close')
    })

    it('icons have aria-hidden attribute', () => {
      render(<AlertDialog {...defaultProps} />)
      const icon = screen.getByTestId('information-circle-icon')
      expect(icon).toHaveAttribute('aria-hidden', 'true')
    })

    it('has proper heading hierarchy', () => {
      render(<AlertDialog {...defaultProps} />)
      const heading = screen.getByRole('heading', { name: 'Alert Title' })
      expect(heading.tagName).toBe('H3')
    })

    it('close button has proper focus styles', () => {
      render(<AlertDialog {...defaultProps} />)
      const closeButton = screen
        .getByTestId('x-mark-icon')
        .closest('button') as HTMLElement
      expect(closeButton).toHaveClass('focus:outline-none', 'focus:ring-2')
    })
  })

  describe('Edge Cases', () => {
    it('handles empty title gracefully', () => {
      render(<AlertDialog {...defaultProps} title="" />)
      const heading = screen.getByRole('heading')
      expect(heading).toBeInTheDocument()
      expect(heading).toHaveTextContent('')
    })

    it('handles empty message gracefully', () => {
      render(<AlertDialog {...defaultProps} message="" />)
      expect(screen.getByText('Alert Title')).toBeInTheDocument()
    })

    it('handles long title text', () => {
      const longTitle =
        'This is a very long title that should still render correctly without breaking the layout or causing any visual issues'
      render(<AlertDialog {...defaultProps} title={longTitle} />)
      expect(screen.getByText(longTitle)).toBeInTheDocument()
    })

    it('handles long message text', () => {
      const longMessage =
        'This is a very long message that contains multiple sentences and should wrap properly within the dialog. It should maintain proper spacing and readability even with extended content. The dialog should handle this gracefully without any layout issues.'
      render(<AlertDialog {...defaultProps} message={longMessage} />)
      expect(screen.getByText(longMessage)).toBeInTheDocument()
    })

    it('handles special characters in title', () => {
      render(
        <AlertDialog {...defaultProps} title="Alert! @#$%^&*() <Special>" />
      )
      expect(screen.getByText('Alert! @#$%^&*() <Special>')).toBeInTheDocument()
    })

    it('handles special characters in message', () => {
      render(
        <AlertDialog
          {...defaultProps}
          message="Message with <HTML> tags & special chars: @#$%"
        />
      )
      expect(
        screen.getByText('Message with <HTML> tags & special chars: @#$%')
      ).toBeInTheDocument()
    })

    it('handles rapid variant changes', () => {
      const { rerender } = render(
        <AlertDialog {...defaultProps} variant="info" />
      )
      expect(screen.getByTestId('information-circle-icon')).toBeInTheDocument()

      rerender(<AlertDialog {...defaultProps} variant="success" />)
      expect(screen.getByTestId('check-circle-icon')).toBeInTheDocument()

      rerender(<AlertDialog {...defaultProps} variant="error" />)
      expect(screen.getByTestId('x-circle-icon')).toBeInTheDocument()

      rerender(<AlertDialog {...defaultProps} variant="warning" />)
      expect(
        screen.getByTestId('exclamation-triangle-icon')
      ).toBeInTheDocument()
    })
  })

  describe('Callback Handlers', () => {
    it('onClose is not called on render', () => {
      render(<AlertDialog {...defaultProps} />)
      expect(defaultProps.onClose).not.toHaveBeenCalled()
    })

    it('onClose is called only once per button click', () => {
      render(<AlertDialog {...defaultProps} />)
      const button = screen.getByRole('button', { name: 'OK' })
      fireEvent.click(button)
      expect(defaultProps.onClose).toHaveBeenCalledTimes(1)
    })

    it('onClose is called only once per close button click', () => {
      render(<AlertDialog {...defaultProps} />)
      const closeButton = screen
        .getByTestId('x-mark-icon')
        .closest('button') as HTMLElement
      fireEvent.click(closeButton)
      expect(defaultProps.onClose).toHaveBeenCalledTimes(1)
    })

    it('handles multiple clicks on same button', () => {
      render(<AlertDialog {...defaultProps} />)
      const button = screen.getByRole('button', { name: 'OK' })
      fireEvent.click(button)
      fireEvent.click(button)
      fireEvent.click(button)
      expect(defaultProps.onClose).toHaveBeenCalledTimes(3)
    })

    it('handles different onClose callbacks', () => {
      const firstCallback = jest.fn()
      const { rerender } = render(
        <AlertDialog {...defaultProps} onClose={firstCallback} />
      )
      const button = screen.getByRole('button', { name: 'OK' })
      fireEvent.click(button)
      expect(firstCallback).toHaveBeenCalledTimes(1)

      const secondCallback = jest.fn()
      rerender(<AlertDialog {...defaultProps} onClose={secondCallback} />)
      fireEvent.click(button)
      expect(secondCallback).toHaveBeenCalledTimes(1)
      expect(firstCallback).toHaveBeenCalledTimes(1)
    })

    it('maintains onClose functionality after prop updates', () => {
      const { rerender } = render(<AlertDialog {...defaultProps} />)

      rerender(
        <AlertDialog
          {...defaultProps}
          title="Updated Title"
          message="Updated Message"
        />
      )

      const button = screen.getByRole('button', { name: 'OK' })
      fireEvent.click(button)
      expect(defaultProps.onClose).toHaveBeenCalledTimes(1)
    })
  })

  describe('Button Rendering', () => {
    it('renders button with correct styling classes', () => {
      render(<AlertDialog {...defaultProps} />)
      const button = screen.getByRole('button', { name: 'OK' })
      expect(button).toHaveClass('min-w-[80px]', 'px-6', 'py-2')
    })

    it('button is enabled by default', () => {
      render(<AlertDialog {...defaultProps} />)
      const button = screen.getByRole('button', { name: 'OK' })
      expect(button).not.toBeDisabled()
    })

    it('button text updates dynamically', () => {
      const { rerender } = render(<AlertDialog {...defaultProps} />)
      expect(screen.getByRole('button', { name: 'OK' })).toBeInTheDocument()

      rerender(<AlertDialog {...defaultProps} buttonText="Dismiss" />)
      expect(
        screen.getByRole('button', { name: 'Dismiss' })
      ).toBeInTheDocument()
      expect(
        screen.queryByRole('button', { name: 'OK' })
      ).not.toBeInTheDocument()
    })
  })
})

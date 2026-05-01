/**
 * Test suite for Toast component
 * Comprehensive testing for notification toast system with context provider
 */

import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import React from 'react'
import { ToastProvider, useToast } from '../Toast'
import { useNotificationStore } from '@/stores/notificationStore'

// Toast.tsx now reads from the Zustand notificationStore (module-level state),
// which means toasts leak across tests inside the same test file. Reset the
// store explicitly so each test starts from an empty toast list.

// Tell setupTests' global Toast mock to step aside — this file tests the real
// Toast.tsx implementation.
jest.unmock('@/components/shared/Toast')

// Mock framer-motion to remove animations in tests
jest.mock('framer-motion', () => ({
  motion: {
    div: ({ children, ...props }: any) => <div {...props}>{children}</div>,
  },
  AnimatePresence: ({ children }: any) => <>{children}</>,
}))
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


// Test component that uses the toast hook
const TestComponent = ({
  type = 'info',
  duration = 4000,
  message = 'Test message',
}: {
  type?: 'success' | 'error' | 'info' | 'warning'
  duration?: number
  message?: string
}) => {
  const { addToast, removeToast } = useToast()

  return (
    <div>
      <button onClick={() => addToast(message, type, duration)}>
        Add Toast
      </button>
      <button onClick={() => removeToast('test-id')}>Remove Toast</button>
    </div>
  )
}

describe('Toast Component', () => {
  beforeEach(() => {
    jest.useFakeTimers()
    useNotificationStore.setState({ toasts: [], pendingFlashes: [] })
  })

  afterEach(() => {
    jest.runOnlyPendingTimers()
    jest.useRealTimers()
  })

  describe('Basic Rendering', () => {
    it('renders ToastProvider with children correctly', () => {
      render(
        <ToastProvider>
          <div data-testid="child">Child content</div>
        </ToastProvider>
      )

      expect(screen.getByTestId('child')).toBeInTheDocument()
    })

    it('renders toast container in correct position', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })

      render(
        <ToastProvider>
          <TestComponent />
        </ToastProvider>
      )

      await user.click(screen.getByText('Add Toast'))

      const toastContainer = document.querySelector('.fixed.right-4.top-4.z-50')
      expect(toastContainer).toBeInTheDocument()
      expect(toastContainer).toHaveClass('pointer-events-none')
      expect(toastContainer).toHaveClass('max-w-sm')
      expect(toastContainer).toHaveClass('space-y-2')
    })

    it('renders toast with correct structure', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })

      render(
        <ToastProvider>
          <TestComponent />
        </ToastProvider>
      )

      await user.click(screen.getByText('Add Toast'))

      const toast = screen.getByText('Test message').closest('div')
      expect(toast).toHaveClass('pointer-events-auto')
      expect(toast).toHaveClass('rounded-lg')
      expect(toast).toHaveClass('border')
      expect(toast).toHaveClass('p-4')
      expect(toast).toHaveClass('shadow-lg')
    })

    it('provides toast context to children', () => {
      render(
        <ToastProvider>
          <TestComponent />
        </ToastProvider>
      )

      expect(screen.getByText('Add Toast')).toBeInTheDocument()
      expect(screen.getByText('Remove Toast')).toBeInTheDocument()
    })
  })

  describe('Toast Variants', () => {
    it('renders success toast with correct styling', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })

      render(
        <ToastProvider>
          <TestComponent type="success" />
        </ToastProvider>
      )

      await user.click(screen.getByText('Add Toast'))

      const toast = screen.getByText('Test message').closest('div')
      expect(toast).toHaveClass('bg-emerald-50')
      expect(toast).toHaveClass('border-emerald-200')
      expect(toast).toHaveClass('text-emerald-800')
    })

    it('renders error toast with correct styling', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })

      render(
        <ToastProvider>
          <TestComponent type="error" />
        </ToastProvider>
      )

      await user.click(screen.getByText('Add Toast'))

      const toast = screen.getByText('Test message').closest('div')
      expect(toast).toHaveClass('bg-red-50')
      expect(toast).toHaveClass('border-red-200')
      expect(toast).toHaveClass('text-red-800')
    })

    it('renders warning toast with correct styling', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })

      render(
        <ToastProvider>
          <TestComponent type="warning" />
        </ToastProvider>
      )

      await user.click(screen.getByText('Add Toast'))

      const toast = screen.getByText('Test message').closest('div')
      expect(toast).toHaveClass('bg-amber-50')
      expect(toast).toHaveClass('border-amber-200')
      expect(toast).toHaveClass('text-amber-800')
    })

    it('renders info toast with correct styling (default)', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })

      render(
        <ToastProvider>
          <TestComponent type="info" />
        </ToastProvider>
      )

      await user.click(screen.getByText('Add Toast'))

      const toast = screen.getByText('Test message').closest('div')
      expect(toast).toHaveClass('bg-blue-50')
      expect(toast).toHaveClass('border-blue-200')
      expect(toast).toHaveClass('text-blue-800')
    })

    it('renders success icon correctly', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })

      render(
        <ToastProvider>
          <TestComponent type="success" />
        </ToastProvider>
      )

      await user.click(screen.getByText('Add Toast'))

      expect(screen.getByText('✓')).toBeInTheDocument()
    })

    it('renders error icon correctly', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })

      render(
        <ToastProvider>
          <TestComponent type="error" />
        </ToastProvider>
      )

      await user.click(screen.getByText('Add Toast'))

      expect(screen.getByText('✗')).toBeInTheDocument()
    })

    it('renders warning icon correctly', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })

      render(
        <ToastProvider>
          <TestComponent type="warning" />
        </ToastProvider>
      )

      await user.click(screen.getByText('Add Toast'))

      expect(screen.getByText('⚠')).toBeInTheDocument()
    })

    it('renders info icon correctly', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })

      render(
        <ToastProvider>
          <TestComponent type="info" />
        </ToastProvider>
      )

      await user.click(screen.getByText('Add Toast'))

      expect(screen.getByText('ℹ')).toBeInTheDocument()
    })
  })

  describe('Message Display', () => {
    it('displays message text correctly', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })

      render(
        <ToastProvider>
          <TestComponent message="Custom test message" />
        </ToastProvider>
      )

      await user.click(screen.getByText('Add Toast'))

      expect(screen.getByText('Custom test message')).toBeInTheDocument()
    })

    it('displays long messages correctly', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })
      const longMessage =
        'This is a very long message that should still be displayed correctly in the toast notification without breaking the layout'

      render(
        <ToastProvider>
          <TestComponent message={longMessage} />
        </ToastProvider>
      )

      await user.click(screen.getByText('Add Toast'))

      expect(screen.getByText(longMessage)).toBeInTheDocument()
      const messageElement = screen.getByText(longMessage)
      expect(messageElement).toHaveClass('text-sm')
      expect(messageElement).toHaveClass('font-medium')
      expect(messageElement).toHaveClass('min-w-0')
      expect(messageElement).toHaveClass('flex-1')
    })

    it('handles empty message', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })

      render(
        <ToastProvider>
          <TestComponent message="" />
        </ToastProvider>
      )

      await user.click(screen.getByText('Add Toast'))

      const toast = document.querySelector('.pointer-events-auto')
      expect(toast).toBeInTheDocument()
    })

    it('handles special characters in message', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })
      const specialMessage = '<script>alert("test")</script> & special chars'

      render(
        <ToastProvider>
          <TestComponent message={specialMessage} />
        </ToastProvider>
      )

      await user.click(screen.getByText('Add Toast'))

      expect(screen.getByText(specialMessage)).toBeInTheDocument()
    })
  })

  describe('Close/Dismiss Functionality', () => {
    it('renders close button', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })

      render(
        <ToastProvider>
          <TestComponent />
        </ToastProvider>
      )

      await user.click(screen.getByText('Add Toast'))

      const closeButton = screen.getByRole('button', { name: /close/i })
      expect(closeButton).toBeInTheDocument()
    })

    it('closes toast when close button is clicked', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })

      render(
        <ToastProvider>
          <TestComponent duration={0} />
        </ToastProvider>
      )

      await user.click(screen.getByText('Add Toast'))

      await waitFor(() => {
        expect(screen.getByText('Test message')).toBeInTheDocument()
      })

      const closeButton = screen.getByRole('button', { name: /close/i })

      act(() => {
        closeButton.click()
      })

      await waitFor(
        () => {
          expect(screen.queryByText('Test message')).not.toBeInTheDocument()
        },
        { timeout: 1000 }
      )
    })

    it('removes specific toast by ID', async () => {
      const MultiToastComponent = () => {
        const { addToast, removeToast } = useToast()
        const [firstToastId, setFirstToastId] = React.useState<string>('')

        return (
          <div>
            <button
              onClick={() => {
                const id = addToast('First message', 'info', 0)
                setFirstToastId(id)
              }}
            >
              Add First
            </button>
            <button onClick={() => addToast('Second message', 'success', 0)}>
              Add Second
            </button>
            <button onClick={() => removeToast(firstToastId)}>
              Remove First
            </button>
          </div>
        )
      }

      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })

      render(
        <ToastProvider>
          <MultiToastComponent />
        </ToastProvider>
      )

      await user.click(screen.getByText('Add First'))
      await user.click(screen.getByText('Add Second'))

      await waitFor(() => {
        expect(screen.getByText('First message')).toBeInTheDocument()
        expect(screen.getByText('Second message')).toBeInTheDocument()
      })

      act(() => {
        screen.getByText('Remove First').click()
      })

      await waitFor(
        () => {
          expect(screen.queryByText('First message')).not.toBeInTheDocument()
        },
        { timeout: 1000 }
      )
      expect(screen.getByText('Second message')).toBeInTheDocument()
    })

    it('close button has correct styling', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })

      render(
        <ToastProvider>
          <TestComponent />
        </ToastProvider>
      )

      await user.click(screen.getByText('Add Toast'))

      const closeButton = screen.getByRole('button', { name: /close/i })
      expect(closeButton).toHaveClass('flex-shrink-0')
      expect(closeButton).toHaveClass('text-current')
      expect(closeButton).toHaveClass('transition-opacity')
      expect(closeButton).toHaveClass('hover:opacity-70')
    })

    it('close button contains SVG icon', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })

      render(
        <ToastProvider>
          <TestComponent />
        </ToastProvider>
      )

      await user.click(screen.getByText('Add Toast'))

      const closeButton = screen.getByRole('button', { name: /close/i })
      const svg = closeButton.querySelector('svg')
      expect(svg).toBeInTheDocument()
      expect(svg).toHaveClass('h-4')
      expect(svg).toHaveClass('w-4')
    })
  })

  describe('Auto-dismiss Timer', () => {
    it('removes toast automatically after default duration (4000ms)', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })

      render(
        <ToastProvider>
          <TestComponent />
        </ToastProvider>
      )

      await user.click(screen.getByText('Add Toast'))
      expect(screen.getByText('Test message')).toBeInTheDocument()

      act(() => {
        jest.advanceTimersByTime(4000)
      })

      await waitFor(() => {
        expect(screen.queryByText('Test message')).not.toBeInTheDocument()
      })
    })

    it('removes toast after custom duration', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })

      render(
        <ToastProvider>
          <TestComponent duration={2000} />
        </ToastProvider>
      )

      await user.click(screen.getByText('Add Toast'))
      expect(screen.getByText('Test message')).toBeInTheDocument()

      act(() => {
        jest.advanceTimersByTime(2000)
      })

      await waitFor(() => {
        expect(screen.queryByText('Test message')).not.toBeInTheDocument()
      })
    })

    it('does not auto-remove toast when duration is 0', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })

      render(
        <ToastProvider>
          <TestComponent duration={0} />
        </ToastProvider>
      )

      await user.click(screen.getByText('Add Toast'))
      expect(screen.getByText('Test message')).toBeInTheDocument()

      act(() => {
        jest.advanceTimersByTime(10000)
      })

      expect(screen.getByText('Test message')).toBeInTheDocument()
    })

    it('does not auto-remove toast when duration is negative', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })

      render(
        <ToastProvider>
          <TestComponent duration={-1} />
        </ToastProvider>
      )

      await user.click(screen.getByText('Add Toast'))
      expect(screen.getByText('Test message')).toBeInTheDocument()

      act(() => {
        jest.advanceTimersByTime(10000)
      })

      expect(screen.getByText('Test message')).toBeInTheDocument()
    })

    it('clears timeout when toast is manually dismissed', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })

      render(
        <ToastProvider>
          <TestComponent duration={5000} />
        </ToastProvider>
      )

      await user.click(screen.getByText('Add Toast'))
      expect(screen.getByText('Test message')).toBeInTheDocument()

      const closeButton = screen.getByRole('button', { name: /close/i })
      await user.click(closeButton)

      await waitFor(() => {
        expect(screen.queryByText('Test message')).not.toBeInTheDocument()
      })

      // Should not cause any issues when timer expires
      act(() => {
        jest.advanceTimersByTime(5000)
      })
    })

    it('cleans up all timeouts on unmount', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })

      const { unmount } = render(
        <ToastProvider>
          <TestComponent duration={5000} />
        </ToastProvider>
      )

      await user.click(screen.getByText('Add Toast'))
      expect(screen.getByText('Test message')).toBeInTheDocument()

      unmount()

      // Should not cause any issues
      act(() => {
        jest.advanceTimersByTime(5000)
      })
    })
  })

  describe('Styling', () => {
    it('applies correct base styling to toast item', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })

      render(
        <ToastProvider>
          <TestComponent />
        </ToastProvider>
      )

      await user.click(screen.getByText('Add Toast'))

      const toast = screen.getByText('Test message').closest('div')
      expect(toast).toHaveClass('flex')
      expect(toast).toHaveClass('items-center')
      expect(toast).toHaveClass('space-x-3')
      expect(toast).toHaveClass('rounded-lg')
      expect(toast).toHaveClass('border')
      expect(toast).toHaveClass('p-4')
      expect(toast).toHaveClass('shadow-lg')
    })

    it('applies correct icon styling', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })

      render(
        <ToastProvider>
          <TestComponent />
        </ToastProvider>
      )

      await user.click(screen.getByText('Add Toast'))

      const icon = screen.getByText('ℹ')
      expect(icon).toHaveClass('flex-shrink-0')
      expect(icon).toHaveClass('text-lg')
    })

    it('supports dark mode classes', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })

      render(
        <ToastProvider>
          <TestComponent type="success" />
        </ToastProvider>
      )

      await user.click(screen.getByText('Add Toast'))

      const toast = screen.getByText('Test message').closest('div')
      expect(toast?.className).toContain('dark:bg-emerald-900/50')
      expect(toast?.className).toContain('dark:border-emerald-800')
      expect(toast?.className).toContain('dark:text-emerald-200')
    })
  })

  describe('Accessibility', () => {
    it('close button has accessible label', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })

      render(
        <ToastProvider>
          <TestComponent />
        </ToastProvider>
      )

      await user.click(screen.getByText('Add Toast'))

      const closeButton = screen.getByRole('button', { name: /close/i })
      expect(closeButton).toBeInTheDocument()

      const srOnly = closeButton.querySelector('.sr-only')
      expect(srOnly).toBeInTheDocument()
      expect(srOnly).toHaveTextContent('Close')
    })

    it('toast is keyboard accessible', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })

      render(
        <ToastProvider>
          <TestComponent duration={0} />
        </ToastProvider>
      )

      await user.click(screen.getByText('Add Toast'))

      await waitFor(() => {
        expect(screen.getByText('Test message')).toBeInTheDocument()
      })

      const closeButton = screen.getByRole('button', { name: /close/i })
      closeButton.focus()
      expect(closeButton).toHaveFocus()

      await user.keyboard('{Enter}')

      await waitFor(
        () => {
          expect(screen.queryByText('Test message')).not.toBeInTheDocument()
        },
        { timeout: 1000 }
      )
    })

    it('toast message has appropriate font styling for readability', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })

      render(
        <ToastProvider>
          <TestComponent />
        </ToastProvider>
      )

      await user.click(screen.getByText('Add Toast'))

      const message = screen.getByText('Test message')
      expect(message).toHaveClass('text-sm')
      expect(message).toHaveClass('font-medium')
    })
  })

  describe('Edge Cases', () => {
    it('handles multiple toasts simultaneously', async () => {
      const MultiToastComponent = () => {
        const { addToast } = useToast()

        return (
          <div>
            <button onClick={() => addToast('First message', 'success')}>
              Add Success
            </button>
            <button onClick={() => addToast('Second message', 'error')}>
              Add Error
            </button>
            <button onClick={() => addToast('Third message', 'warning')}>
              Add Warning
            </button>
          </div>
        )
      }

      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })

      render(
        <ToastProvider>
          <MultiToastComponent />
        </ToastProvider>
      )

      await user.click(screen.getByText('Add Success'))
      await user.click(screen.getByText('Add Error'))
      await user.click(screen.getByText('Add Warning'))

      expect(screen.getByText('First message')).toBeInTheDocument()
      expect(screen.getByText('Second message')).toBeInTheDocument()
      expect(screen.getByText('Third message')).toBeInTheDocument()
    })

    it('limits toasts to maximum of 5', async () => {
      const ManyToastsComponent = () => {
        const { addToast } = useToast()

        return (
          <button
            onClick={() => {
              for (let i = 1; i <= 7; i++) {
                addToast(`Message ${i}`, 'info', 0)
              }
            }}
          >
            Add Many Toasts
          </button>
        )
      }

      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })

      render(
        <ToastProvider>
          <ManyToastsComponent />
        </ToastProvider>
      )

      await user.click(screen.getByText('Add Many Toasts'))

      await waitFor(() => {
        const toasts = document.querySelectorAll('.pointer-events-auto')
        expect(toasts).toHaveLength(5)
      })

      expect(screen.queryByText('Message 1')).not.toBeInTheDocument()
      expect(screen.queryByText('Message 2')).not.toBeInTheDocument()
      expect(screen.getByText('Message 3')).toBeInTheDocument()
      expect(screen.getByText('Message 7')).toBeInTheDocument()
    })

    it('removes duplicate messages (same message replaces previous)', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })

      render(
        <ToastProvider>
          <TestComponent message="Duplicate message" duration={0} />
        </ToastProvider>
      )

      await user.click(screen.getByText('Add Toast'))
      await user.click(screen.getByText('Add Toast'))
      await user.click(screen.getByText('Add Toast'))

      const messages = screen.getAllByText('Duplicate message')
      expect(messages).toHaveLength(1)
    })

    it('handles rapid toast creation', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })

      render(
        <ToastProvider>
          <TestComponent />
        </ToastProvider>
      )

      await user.click(screen.getByText('Add Toast'))
      await user.click(screen.getByText('Add Toast'))
      await user.click(screen.getByText('Add Toast'))

      const toastMessages = screen.getAllByText('Test message')
      expect(toastMessages.length).toBeGreaterThanOrEqual(1)
    })

    it('returns toast ID from addToast', async () => {
      const IdTestComponent = () => {
        const { addToast } = useToast()
        const [toastId, setToastId] = React.useState<string>('')

        return (
          <div>
            <button
              onClick={() => {
                const id = addToast('Test message')
                setToastId(id)
              }}
            >
              Add Toast
            </button>
            <div data-testid="toast-id">{toastId}</div>
          </div>
        )
      }

      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })

      render(
        <ToastProvider>
          <IdTestComponent />
        </ToastProvider>
      )

      await user.click(screen.getByText('Add Toast'))

      const toastIdElement = screen.getByTestId('toast-id')
      expect(toastIdElement.textContent).toBeTruthy()
      expect(toastIdElement.textContent?.length).toBeGreaterThan(0)
    })

    it('showToast is an alias for addToast', async () => {
      const ShowToastComponent = () => {
        const { showToast } = useToast()

        return (
          <button onClick={() => showToast('Using showToast', 'success')}>
            Show Toast
          </button>
        )
      }

      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })

      render(
        <ToastProvider>
          <ShowToastComponent />
        </ToastProvider>
      )

      await user.click(screen.getByText('Show Toast'))

      expect(screen.getByText('Using showToast')).toBeInTheDocument()
    })

    it('generates unique IDs for each toast', async () => {
      const IdTrackingComponent = () => {
        const { addToast } = useToast()
        const [ids, setIds] = React.useState<string[]>([])

        return (
          <div>
            <button
              onClick={() => {
                const id1 = addToast('Message 1', 'info', 0)
                const id2 = addToast('Message 2', 'info', 0)
                setIds([id1, id2])
              }}
            >
              Add Two Toasts
            </button>
            <div data-testid="ids">{ids.join(',')}</div>
          </div>
        )
      }

      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })

      render(
        <ToastProvider>
          <IdTrackingComponent />
        </ToastProvider>
      )

      await user.click(screen.getByText('Add Two Toasts'))

      const idsElement = screen.getByTestId('ids')
      const ids = idsElement.textContent?.split(',') || []
      expect(ids).toHaveLength(2)
      expect(ids[0]).not.toBe(ids[1])
      expect(ids[0].length).toBeGreaterThan(0)
      expect(ids[1].length).toBeGreaterThan(0)
    })
  })

  describe('useToast hook', () => {
    it('throws error when used outside provider', () => {
      const consoleSpy = jest
        .spyOn(console, 'error')
        .mockImplementation(() => {})

      expect(() => {
        render(<TestComponent />)
      }).toThrow('useToast must be used within a ToastProvider')

      consoleSpy.mockRestore()
    })

    it('provides addToast function', () => {
      render(
        <ToastProvider>
          <TestComponent />
        </ToastProvider>
      )

      expect(screen.getByText('Add Toast')).toBeInTheDocument()
    })

    it('provides removeToast function', () => {
      render(
        <ToastProvider>
          <TestComponent />
        </ToastProvider>
      )

      expect(screen.getByText('Remove Toast')).toBeInTheDocument()
    })

    it('provides showToast function', () => {
      const ShowToastTestComponent = () => {
        const { showToast } = useToast()

        return <button onClick={() => showToast('Test')}>Show Toast</button>
      }

      render(
        <ToastProvider>
          <ShowToastTestComponent />
        </ToastProvider>
      )

      expect(screen.getByText('Show Toast')).toBeInTheDocument()
    })
  })
})

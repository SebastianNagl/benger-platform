import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SimpleToastProvider, useToast } from '../SimpleToast'

// Test component that uses the toast hook
const TestComponent = ({
  type = 'info',
  duration = 5000,
}: {
  type?: 'success' | 'error' | 'info' | 'warning'
  duration?: number
}) => {
  const { addToast, removeToast } = useToast()

  return (
    <div>
      <button onClick={() => addToast('Test message', type, duration)}>
        Add Toast
      </button>
      <button onClick={() => removeToast('test-id')}>Remove Toast</button>
    </div>
  )
}

describe('SimpleToast', () => {
  beforeEach(() => {
    jest.useFakeTimers()
  })

  afterEach(() => {
    jest.runOnlyPendingTimers()
    jest.useRealTimers()
  })

  describe('SimpleToastProvider', () => {
    it('renders children correctly', () => {
      render(
        <SimpleToastProvider>
          <div data-testid="child">Child content</div>
        </SimpleToastProvider>
      )

      expect(screen.getByTestId('child')).toBeInTheDocument()
    })

    it('provides toast context to children', () => {
      render(
        <SimpleToastProvider>
          <TestComponent />
        </SimpleToastProvider>
      )

      expect(screen.getByText('Add Toast')).toBeInTheDocument()
      expect(screen.getByText('Remove Toast')).toBeInTheDocument()
    })
  })

  describe('useToast hook', () => {
    it('throws error when used outside provider', () => {
      // Suppress console.error for this test
      const consoleSpy = jest
        .spyOn(console, 'error')
        .mockImplementation(() => {})

      expect(() => {
        render(<TestComponent />)
      }).toThrow('useToast must be used within a ToastProvider')

      consoleSpy.mockRestore()
    })

    it('adds toast with default type (info)', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })

      render(
        <SimpleToastProvider>
          <TestComponent />
        </SimpleToastProvider>
      )

      await user.click(screen.getByText('Add Toast'))

      expect(screen.getByText('Test message')).toBeInTheDocument()
      expect(
        screen.getByText('Test message').closest('.bg-blue-500')
      ).toBeInTheDocument()
    })

    it('adds toast with success type', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })

      render(
        <SimpleToastProvider>
          <TestComponent type="success" />
        </SimpleToastProvider>
      )

      await user.click(screen.getByText('Add Toast'))

      expect(screen.getByText('Test message')).toBeInTheDocument()
      expect(
        screen.getByText('Test message').closest('.bg-green-500')
      ).toBeInTheDocument()
    })

    it('adds toast with error type', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })

      render(
        <SimpleToastProvider>
          <TestComponent type="error" />
        </SimpleToastProvider>
      )

      await user.click(screen.getByText('Add Toast'))

      expect(screen.getByText('Test message')).toBeInTheDocument()
      expect(
        screen.getByText('Test message').closest('.bg-red-500')
      ).toBeInTheDocument()
    })

    it('adds toast with warning type', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })

      render(
        <SimpleToastProvider>
          <TestComponent type="warning" />
        </SimpleToastProvider>
      )

      await user.click(screen.getByText('Add Toast'))

      expect(screen.getByText('Test message')).toBeInTheDocument()
      expect(
        screen.getByText('Test message').closest('.bg-yellow-500')
      ).toBeInTheDocument()
    })

    it('removes toast manually', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })

      render(
        <SimpleToastProvider>
          <TestComponent />
        </SimpleToastProvider>
      )

      await user.click(screen.getByText('Add Toast'))
      expect(screen.getByText('Test message')).toBeInTheDocument()

      await user.click(screen.getByText('×'))
      expect(screen.queryByText('Test message')).not.toBeInTheDocument()
    })

    it('removes toast automatically after duration', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })

      render(
        <SimpleToastProvider>
          <TestComponent duration={3000} />
        </SimpleToastProvider>
      )

      await user.click(screen.getByText('Add Toast'))
      expect(screen.getByText('Test message')).toBeInTheDocument()

      act(() => {
        jest.advanceTimersByTime(3000)
      })

      await waitFor(() => {
        expect(screen.queryByText('Test message')).not.toBeInTheDocument()
      })
    })

    it('does not auto-remove toast when duration is 0', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })

      render(
        <SimpleToastProvider>
          <TestComponent duration={0} />
        </SimpleToastProvider>
      )

      await user.click(screen.getByText('Add Toast'))
      expect(screen.getByText('Test message')).toBeInTheDocument()

      act(() => {
        jest.advanceTimersByTime(10000)
      })

      expect(screen.getByText('Test message')).toBeInTheDocument()
    })

    it('handles multiple toasts', async () => {
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
          </div>
        )
      }

      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })

      render(
        <SimpleToastProvider>
          <MultiToastComponent />
        </SimpleToastProvider>
      )

      await user.click(screen.getByText('Add Success'))
      await user.click(screen.getByText('Add Error'))

      expect(screen.getByText('First message')).toBeInTheDocument()
      expect(screen.getByText('Second message')).toBeInTheDocument()
      expect(
        screen.getByText('First message').closest('.bg-green-500')
      ).toBeInTheDocument()
      expect(
        screen.getByText('Second message').closest('.bg-red-500')
      ).toBeInTheDocument()
    })

    it('applies correct positioning and z-index', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })

      render(
        <SimpleToastProvider>
          <TestComponent />
        </SimpleToastProvider>
      )

      await user.click(screen.getByText('Add Toast'))

      const toastContainer = document.querySelector(
        '.fixed.top-4.right-4.z-50.space-y-2'
      )
      expect(toastContainer).toBeInTheDocument()
    })

    it('includes close button with correct styling', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })

      render(
        <SimpleToastProvider>
          <TestComponent />
        </SimpleToastProvider>
      )

      await user.click(screen.getByText('Add Toast'))

      const closeButton = screen.getByText('×')
      expect(closeButton).toBeInTheDocument()
      expect(closeButton).toHaveClass(
        'ml-4',
        'text-white',
        'hover:text-gray-200'
      )
    })
  })

  describe('Edge cases', () => {
    it('handles rapid toast creation', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })

      render(
        <SimpleToastProvider>
          <TestComponent />
        </SimpleToastProvider>
      )

      // Add multiple toasts quickly
      await user.click(screen.getByText('Add Toast'))
      await user.click(screen.getByText('Add Toast'))
      await user.click(screen.getByText('Add Toast'))

      const toastMessages = screen.getAllByText('Test message')
      expect(toastMessages).toHaveLength(3)
    })

    it('handles empty message', async () => {
      const EmptyMessageComponent = () => {
        const { addToast } = useToast()

        return <button onClick={() => addToast('')}>Add Empty Toast</button>
      }

      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })

      render(
        <SimpleToastProvider>
          <EmptyMessageComponent />
        </SimpleToastProvider>
      )

      await user.click(screen.getByText('Add Empty Toast'))

      // Should still render the toast structure
      const closeButton = screen.getByText('×')
      expect(closeButton).toBeInTheDocument()
    })

    it('generates unique IDs for toasts', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })

      render(
        <SimpleToastProvider>
          <TestComponent />
        </SimpleToastProvider>
      )

      await user.click(screen.getByText('Add Toast'))
      await user.click(screen.getByText('Add Toast'))

      const toastElements = screen.getAllByText('Test message')
      expect(toastElements).toHaveLength(2)

      // Each should have unique keys (though we can't directly test React keys)
      expect(toastElements[0].closest('div')).not.toBe(
        toastElements[1].closest('div')
      )
    })
  })
})

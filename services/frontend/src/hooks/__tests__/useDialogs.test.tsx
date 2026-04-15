/**
 * @jest-environment jsdom
 */

/**
 * Tests for useDialogs hooks
 * Verifies dialog state management, promise handling, and convenience hooks
 */

import {
  act,
  render,
  renderHook,
  screen,
  waitFor,
} from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import React, { ReactNode } from 'react'

 

// UNMOCK the global useDialogs mock from setupTests.ts
jest.unmock('@/hooks/useDialogs')

// Mock the dialog components BEFORE importing the hooks
jest.mock('@/components/shared/AlertDialog', () => ({
  AlertDialog: ({ isOpen, onClose, title, message, buttonText }: any) => {
    if (!isOpen) return null
    return (
      <div data-testid="alert-dialog" role="alertdialog">
        <div data-testid="alert-title">{title}</div>
        <div data-testid="alert-message">{message}</div>
        <button onClick={onClose} role="button">
          {buttonText || 'OK'}
        </button>
      </div>
    )
  },
}))

jest.mock('@/components/shared/ConfirmationDialog', () => ({
  ConfirmationDialog: ({
    isOpen,
    onClose,
    onConfirm,
    title,
    message,
    confirmText,
    cancelText,
  }: any) => {
    if (!isOpen) return null
    return (
      <div data-testid="confirmation-dialog" role="dialog">
        <div data-testid="confirm-title">{title}</div>
        <div data-testid="confirm-message">{message}</div>
        <button onClick={onConfirm} role="button">
          {confirmText || 'Confirm'}
        </button>
        <button onClick={onClose} role="button">
          {cancelText || 'Cancel'}
        </button>
      </div>
    )
  },
}))

// NOW import the actual hooks
import {
  DialogProvider,
  useAlert,
  useConfirm,
  useDeleteConfirm,
  useErrorAlert,
  useSuccessAlert,
  useWarningAlert,
} from '../useDialogs'

const wrapper = ({ children }: { children: ReactNode }) => (
  <DialogProvider>{children}</DialogProvider>
)

describe('useDialogs', () => {
  describe('Basic Hook Behavior', () => {
    it('should throw error when useAlert is used outside DialogProvider', () => {
      const consoleSpy = jest.spyOn(console, 'error').mockImplementation()

      try {
        renderHook(() => useAlert())
        expect(true).toBe(false)
      } catch (error: any) {
        expect(error.message).toBe(
          'useAlert must be used within a DialogProvider'
        )
      }

      consoleSpy.mockRestore()
    })

    it('should throw error when useConfirm is used outside DialogProvider', () => {
      const consoleSpy = jest.spyOn(console, 'error').mockImplementation()

      try {
        renderHook(() => useConfirm())
        expect(true).toBe(false)
      } catch (error: any) {
        expect(error.message).toBe(
          'useConfirm must be used within a DialogProvider'
        )
      }

      consoleSpy.mockRestore()
    })

    it('should return alert function when used within DialogProvider', () => {
      const { result } = renderHook(() => useAlert(), { wrapper })
      expect(typeof result.current).toBe('function')
    })

    it('should return confirm function when used within DialogProvider', () => {
      const { result } = renderHook(() => useConfirm(), { wrapper })
      expect(typeof result.current).toBe('function')
    })
  })

  describe('Alert Dialog State Management', () => {
    it('should open alert dialog with correct options', async () => {
      const { result } = renderHook(() => useAlert(), { wrapper })

      act(() => {
        result.current({
          title: 'Test Alert',
          message: 'This is a test message',
          variant: 'info',
        })
      })

      await waitFor(() => {
        expect(screen.getByTestId('alert-title')).toHaveTextContent(
          'Test Alert'
        )
        expect(screen.getByTestId('alert-message')).toHaveTextContent(
          'This is a test message'
        )
      })
    })

    it('should display alert with success variant', async () => {
      const { result } = renderHook(() => useAlert(), { wrapper })

      act(() => {
        result.current({
          title: 'Success',
          message: 'Operation completed',
          variant: 'success',
        })
      })

      await waitFor(() => {
        expect(screen.getByTestId('alert-title')).toHaveTextContent('Success')
        expect(screen.getByTestId('alert-message')).toHaveTextContent(
          'Operation completed'
        )
      })
    })

    it('should display alert with error variant', async () => {
      const { result } = renderHook(() => useAlert(), { wrapper })

      act(() => {
        result.current({
          title: 'Error',
          message: 'Something went wrong',
          variant: 'error',
        })
      })

      await waitFor(() => {
        expect(screen.getByTestId('alert-title')).toHaveTextContent('Error')
        expect(screen.getByTestId('alert-message')).toHaveTextContent(
          'Something went wrong'
        )
      })
    })

    it('should display alert with warning variant', async () => {
      const { result } = renderHook(() => useAlert(), { wrapper })

      act(() => {
        result.current({
          title: 'Warning',
          message: 'Please be careful',
          variant: 'warning',
        })
      })

      await waitFor(() => {
        expect(screen.getByTestId('alert-title')).toHaveTextContent('Warning')
        expect(screen.getByTestId('alert-message')).toHaveTextContent(
          'Please be careful'
        )
      })
    })

    it('should display alert with custom button text', async () => {
      const { result } = renderHook(() => useAlert(), { wrapper })

      act(() => {
        result.current({
          title: 'Alert',
          message: 'Message',
          buttonText: 'Got it',
        })
      })

      await waitFor(() => {
        expect(screen.getByText('Got it')).toBeInTheDocument()
      })
    })
  })

  describe('Confirmation Dialog State Management', () => {
    it('should open confirmation dialog with correct options', async () => {
      const { result } = renderHook(() => useConfirm(), { wrapper })

      act(() => {
        result.current({
          title: 'Confirm Action',
          message: 'Are you sure?',
        })
      })

      await waitFor(() => {
        expect(screen.getByTestId('confirm-title')).toHaveTextContent(
          'Confirm Action'
        )
        expect(screen.getByTestId('confirm-message')).toHaveTextContent(
          'Are you sure?'
        )
      })
    })

    it('should display confirmation with danger variant', async () => {
      const { result } = renderHook(() => useConfirm(), { wrapper })

      act(() => {
        result.current({
          title: 'Delete Item',
          message: 'This cannot be undone',
          variant: 'danger',
        })
      })

      await waitFor(() => {
        expect(screen.getByTestId('confirm-title')).toHaveTextContent(
          'Delete Item'
        )
        expect(screen.getByTestId('confirm-message')).toHaveTextContent(
          'This cannot be undone'
        )
      })
    })

    it('should display confirmation with custom button texts', async () => {
      const { result } = renderHook(() => useConfirm(), { wrapper })

      act(() => {
        result.current({
          title: 'Confirm',
          message: 'Are you sure?',
          confirmText: 'Yes, proceed',
          cancelText: 'No, cancel',
        })
      })

      await waitFor(() => {
        expect(screen.getByText('Yes, proceed')).toBeInTheDocument()
        expect(screen.getByText('No, cancel')).toBeInTheDocument()
      })
    })
  })

  describe('Promise Resolution', () => {
    it('should resolve alert promise when closed', async () => {
      const { result } = renderHook(() => useAlert(), { wrapper })
      const user = userEvent.setup()

      let resolved = false
      act(() => {
        result
          .current({
            title: 'Alert',
            message: 'Message',
          })
          .then(() => {
            resolved = true
          })
      })

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /ok/i })).toBeInTheDocument()
      })

      await user.click(screen.getByRole('button', { name: /ok/i }))

      await waitFor(() => {
        expect(resolved).toBe(true)
      })
    })

    it('should resolve confirm promise with false when cancelled', async () => {
      const { result } = renderHook(() => useConfirm(), { wrapper })
      const user = userEvent.setup()

      let confirmResult: boolean | null = null
      act(() => {
        result
          .current({
            title: 'Confirm',
            message: 'Proceed?',
          })
          .then((confirmed) => {
            confirmResult = confirmed
          })
      })

      await waitFor(() => {
        expect(
          screen.getByRole('button', { name: /cancel/i })
        ).toBeInTheDocument()
      })

      await user.click(screen.getByRole('button', { name: /cancel/i }))

      await waitFor(() => {
        expect(confirmResult).toBe(false)
      })
    })

    it('should resolve confirm promise with true when confirmed', async () => {
      const { result } = renderHook(() => useConfirm(), { wrapper })
      const user = userEvent.setup()

      let confirmResult: boolean | null = null
      act(() => {
        result
          .current({
            title: 'Confirm',
            message: 'Proceed?',
          })
          .then((confirmed) => {
            confirmResult = confirmed
          })
      })

      await waitFor(() => {
        expect(
          screen.getByRole('button', { name: /confirm/i })
        ).toBeInTheDocument()
      })

      await user.click(screen.getByRole('button', { name: /confirm/i }))

      await waitFor(() => {
        expect(confirmResult).toBe(true)
      })
    })
  })

  describe('Convenience Hooks', () => {
    describe('useErrorAlert', () => {
      it('should create error alert with default title', async () => {
        const { result } = renderHook(() => useErrorAlert(), { wrapper })

        act(() => {
          result.current('Something went wrong')
        })

        await waitFor(() => {
          expect(screen.getByTestId('alert-title')).toHaveTextContent('Error')
          expect(screen.getByTestId('alert-message')).toHaveTextContent(
            'Something went wrong'
          )
        })
      })

      it('should create error alert with custom title', async () => {
        const { result } = renderHook(() => useErrorAlert(), { wrapper })

        act(() => {
          result.current('Operation failed', 'Custom Error')
        })

        await waitFor(() => {
          expect(screen.getByTestId('alert-title')).toHaveTextContent(
            'Custom Error'
          )
        })
      })
    })

    describe('useSuccessAlert', () => {
      it('should create success alert with default title', async () => {
        const { result } = renderHook(() => useSuccessAlert(), { wrapper })

        act(() => {
          result.current('Operation completed')
        })

        await waitFor(() => {
          expect(screen.getByTestId('alert-title')).toHaveTextContent('Success')
          expect(screen.getByTestId('alert-message')).toHaveTextContent(
            'Operation completed'
          )
        })
      })

      it('should create success alert with custom title', async () => {
        const { result } = renderHook(() => useSuccessAlert(), { wrapper })

        act(() => {
          result.current('Saved successfully', 'All Done')
        })

        await waitFor(() => {
          expect(screen.getByTestId('alert-title')).toHaveTextContent(
            'All Done'
          )
        })
      })
    })

    describe('useWarningAlert', () => {
      it('should create warning alert with default title', async () => {
        const { result } = renderHook(() => useWarningAlert(), { wrapper })

        act(() => {
          result.current('Please be careful')
        })

        await waitFor(() => {
          expect(screen.getByTestId('alert-title')).toHaveTextContent('Warning')
          expect(screen.getByTestId('alert-message')).toHaveTextContent(
            'Please be careful'
          )
        })
      })

      it('should create warning alert with custom title', async () => {
        const { result } = renderHook(() => useWarningAlert(), { wrapper })

        act(() => {
          result.current('Check your input', 'Attention Required')
        })

        await waitFor(() => {
          expect(screen.getByTestId('alert-title')).toHaveTextContent(
            'Attention Required'
          )
        })
      })
    })

    describe('useDeleteConfirm', () => {
      it('should create delete confirmation with default item name', async () => {
        const { result } = renderHook(() => useDeleteConfirm(), { wrapper })

        act(() => {
          result.current()
        })

        await waitFor(() => {
          expect(screen.getByTestId('confirm-title')).toHaveTextContent(
            'Confirm Deletion'
          )
          expect(screen.getByTestId('confirm-message')).toHaveTextContent(
            /this item/i
          )
          expect(screen.getByText('Delete')).toBeInTheDocument()
        })
      })

      it('should create delete confirmation with custom item name', async () => {
        const { result } = renderHook(() => useDeleteConfirm(), { wrapper })

        act(() => {
          result.current('user account')
        })

        await waitFor(() => {
          expect(screen.getByTestId('confirm-message')).toHaveTextContent(
            /user account/i
          )
        })
      })

      it('should return true when delete is confirmed', async () => {
        const { result } = renderHook(() => useDeleteConfirm(), { wrapper })
        const user = userEvent.setup()

        let deleteConfirmed: boolean | null = null
        act(() => {
          result.current('test item').then((confirmed) => {
            deleteConfirmed = confirmed
          })
        })

        await waitFor(() => {
          expect(screen.getByText('Delete')).toBeInTheDocument()
        })

        await user.click(screen.getByText('Delete'))

        await waitFor(() => {
          expect(deleteConfirmed).toBe(true)
        })
      })

      it('should return false when delete is cancelled', async () => {
        const { result } = renderHook(() => useDeleteConfirm(), { wrapper })
        const user = userEvent.setup()

        let deleteConfirmed: boolean | null = null
        act(() => {
          result.current('test item').then((confirmed) => {
            deleteConfirmed = confirmed
          })
        })

        await waitFor(() => {
          expect(
            screen.getByRole('button', { name: /cancel/i })
          ).toBeInTheDocument()
        })

        await user.click(screen.getByRole('button', { name: /cancel/i }))

        await waitFor(() => {
          expect(deleteConfirmed).toBe(false)
        })
      })
    })
  })

  describe('Edge Cases', () => {
    it('should handle rapid successive alert calls', async () => {
      const { result } = renderHook(() => useAlert(), { wrapper })

      act(() => {
        result.current({ title: 'Alert 1', message: 'Message 1' })
      })
      act(() => {
        result.current({ title: 'Alert 2', message: 'Message 2' })
      })
      act(() => {
        result.current({ title: 'Alert 3', message: 'Message 3' })
      })

      await waitFor(() => {
        expect(screen.getByTestId('alert-title')).toHaveTextContent('Alert 3')
      })
    })

    it('should handle alert with empty strings', async () => {
      const { result } = renderHook(() => useAlert(), { wrapper })

      act(() => {
        result.current({
          title: '',
          message: '',
        })
      })

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /ok/i })).toBeInTheDocument()
      })
    })

    it('should handle confirmation with empty strings', async () => {
      const { result } = renderHook(() => useConfirm(), { wrapper })

      act(() => {
        result.current({
          title: '',
          message: '',
        })
      })

      await waitFor(() => {
        expect(
          screen.getByRole('button', { name: /cancel/i })
        ).toBeInTheDocument()
      })
    })

    it('should handle very long titles and messages', async () => {
      const { result } = renderHook(() => useAlert(), { wrapper })
      const longTitle = 'A'.repeat(200)
      const longMessage = 'B'.repeat(500)

      act(() => {
        result.current({
          title: longTitle,
          message: longMessage,
        })
      })

      await waitFor(() => {
        expect(screen.getByTestId('alert-title')).toHaveTextContent(longTitle)
        expect(screen.getByTestId('alert-message')).toHaveTextContent(
          longMessage
        )
      })
    })

    it('should handle special characters in text', async () => {
      const { result } = renderHook(() => useAlert(), { wrapper })
      const specialTitle = '<script>alert("xss")</script>'
      const specialMessage = '&lt;&gt;&amp;"\'`'

      act(() => {
        result.current({
          title: specialTitle,
          message: specialMessage,
        })
      })

      await waitFor(() => {
        expect(screen.getByTestId('alert-title')).toHaveTextContent(
          specialTitle
        )
        expect(screen.getByTestId('alert-message')).toHaveTextContent(
          specialMessage
        )
      })
    })
  })

  describe('Cleanup', () => {
    it('should cleanup alert state on unmount', async () => {
      const TestComponent = () => {
        const alert = useAlert()
        React.useEffect(() => {
          alert({ title: 'Alert', message: 'Message' })
        }, [alert])
        return null
      }

      const { unmount } = render(
        <DialogProvider>
          <TestComponent />
        </DialogProvider>
      )

      await waitFor(() => {
        expect(screen.getByTestId('alert-title')).toBeInTheDocument()
      })

      unmount()

      expect(screen.queryByTestId('alert-title')).not.toBeInTheDocument()
    })

    it('should cleanup confirmation state on unmount', async () => {
      const TestComponent = () => {
        const confirm = useConfirm()
        React.useEffect(() => {
          confirm({ title: 'Confirm Delete', message: 'Are you sure?' })
        }, [confirm])
        return null
      }

      const { unmount } = render(
        <DialogProvider>
          <TestComponent />
        </DialogProvider>
      )

      await waitFor(() => {
        expect(screen.getByTestId('confirm-title')).toBeInTheDocument()
      })

      unmount()

      expect(screen.queryByTestId('confirm-title')).not.toBeInTheDocument()
    })
  })

  describe('Multiple Dialog Instances', () => {
    it('should handle switching between different alert types', async () => {
      const { result } = renderHook(() => useAlert(), { wrapper })
      const user = userEvent.setup()

      act(() => {
        result.current({ title: 'First Alert', message: 'Message 1' })
      })

      await waitFor(() => {
        expect(screen.getByTestId('alert-title')).toHaveTextContent(
          'First Alert'
        )
      })

      await user.click(screen.getByRole('button', { name: /ok/i }))

      await waitFor(() => {
        expect(screen.queryByTestId('alert-title')).not.toBeInTheDocument()
      })

      act(() => {
        result.current({ title: 'Second Alert', message: 'Message 2' })
      })

      await waitFor(() => {
        expect(screen.getByTestId('alert-title')).toHaveTextContent(
          'Second Alert'
        )
      })
    })

    it('should handle alert followed by confirmation', async () => {
      const TestComponent = () => {
        const alert = useAlert()
        const confirm = useConfirm()
        const [step, setStep] = React.useState(0)

        React.useEffect(() => {
          if (step === 0) {
            alert({ title: 'Alert First', message: 'Starting' }).then(() => {
              setStep(1)
            })
          } else if (step === 1) {
            confirm({ title: 'Confirm Second', message: 'Continue?' })
          }
        }, [step, alert, confirm])

        return null
      }

      const user = userEvent.setup()

      render(
        <DialogProvider>
          <TestComponent />
        </DialogProvider>
      )

      await waitFor(() => {
        expect(screen.getByTestId('alert-title')).toHaveTextContent(
          'Alert First'
        )
      })

      await user.click(screen.getByRole('button', { name: /ok/i }))

      await waitFor(() => {
        expect(screen.getByTestId('confirm-title')).toHaveTextContent(
          'Confirm Second'
        )
      })
    })
  })

  describe('Provider Stability', () => {
    it('should maintain stable callback references', () => {
      const { result, rerender } = renderHook(() => useAlert(), { wrapper })

      const firstCallback = result.current
      rerender()

      expect(result.current).toBe(firstCallback)
    })

    it('should work with nested providers', () => {
      const { result } = renderHook(() => useAlert(), {
        wrapper: ({ children }) => (
          <DialogProvider>
            <DialogProvider>{children}</DialogProvider>
          </DialogProvider>
        ),
      })

      expect(typeof result.current).toBe('function')
    })
  })
})

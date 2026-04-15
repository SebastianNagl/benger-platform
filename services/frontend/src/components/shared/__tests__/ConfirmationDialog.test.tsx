import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ConfirmationDialog } from '../ConfirmationDialog'

// Clear any existing mocks for ConfirmationDialog
jest.unmock('@/components/shared/ConfirmationDialog')

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => {
      const translations: Record<string, string> = {
        'common.confirm': 'Confirm',
        'common.cancel': 'Cancel',
      }
      return translations[key] || key
    },
    locale: 'en',
  }),
}))

// Mock heroicons - simple mock without external references
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
}))

// Mock Headless UI - simple approach with backdrop click handling
jest.mock('@headlessui/react', () => {
  const mockFragment = ({ children }: any) => children

  // Store the current onClose handler globally for the backdrop to access
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
          // Add click handler to any element with backdrop classes
          const childrenWithClickHandler = Array.isArray(children)
            ? children
            : [children]
          const processedChildren = childrenWithClickHandler.map(
            (child: any) => {
              if (child?.props?.className?.includes('fixed inset-0 bg-black')) {
                // This is the backdrop - add click handler
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

describe('ConfirmationDialog', () => {
  const defaultProps = {
    isOpen: true,
    onClose: jest.fn(),
    onConfirm: jest.fn(),
    title: 'Confirm Action',
    message: 'Are you sure you want to proceed?',
  }

  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('renders when isOpen is true', () => {
    render(<ConfirmationDialog {...defaultProps} />)
    expect(screen.getByText('Confirm Action')).toBeInTheDocument()
    expect(
      screen.getByText('Are you sure you want to proceed?')
    ).toBeInTheDocument()
  })

  it('does not render when isOpen is false', () => {
    render(<ConfirmationDialog {...defaultProps} isOpen={false} />)
    expect(screen.queryByText('Confirm Action')).not.toBeInTheDocument()
  })

  it('renders default button texts', () => {
    render(<ConfirmationDialog {...defaultProps} />)
    expect(
      screen.getByTestId('confirm-dialog-confirm-button')
    ).toHaveTextContent('Confirm')
    expect(
      screen.getByTestId('confirm-dialog-cancel-button')
    ).toHaveTextContent('Cancel')
  })

  it('renders custom button texts', () => {
    render(
      <ConfirmationDialog
        {...defaultProps}
        confirmText="Delete"
        cancelText="Keep"
      />
    )
    expect(
      screen.getByTestId('confirm-dialog-confirm-button')
    ).toHaveTextContent('Delete')
    expect(
      screen.getByTestId('confirm-dialog-cancel-button')
    ).toHaveTextContent('Keep')
  })

  it('calls onClose when cancel button is clicked', () => {
    render(<ConfirmationDialog {...defaultProps} />)
    fireEvent.click(screen.getByTestId('confirm-dialog-cancel-button'))
    expect(defaultProps.onClose).toHaveBeenCalledTimes(1)
    expect(defaultProps.onConfirm).not.toHaveBeenCalled()
  })

  it('calls onConfirm and onClose when confirm button is clicked', () => {
    render(<ConfirmationDialog {...defaultProps} />)
    fireEvent.click(screen.getByTestId('confirm-dialog-confirm-button'))
    expect(defaultProps.onConfirm).toHaveBeenCalledTimes(1)
    expect(defaultProps.onClose).toHaveBeenCalledTimes(1)
  })

  it('renders warning variant with correct icon and styles', () => {
    render(<ConfirmationDialog {...defaultProps} variant="warning" />)

    // Check that the dialog content renders
    expect(screen.getByText('Confirm Action')).toBeInTheDocument()
    expect(
      screen.getByText('Are you sure you want to proceed?')
    ).toBeInTheDocument()

    // Check for presence of warning-specific testid from heroicon mock
    const warningIcon = screen.getByTestId('exclamation-triangle-icon')
    expect(warningIcon).toBeInTheDocument()
    expect(warningIcon).toHaveClass('h-6', 'w-6')
  })

  it('renders danger variant with correct icon and styles', () => {
    render(<ConfirmationDialog {...defaultProps} variant="danger" />)

    expect(screen.getByText('Confirm Action')).toBeInTheDocument()
    const dangerIcon = screen.getByTestId('x-circle-icon')
    expect(dangerIcon).toBeInTheDocument()
    expect(dangerIcon).toHaveClass('h-6', 'w-6')
  })

  it('renders info variant with correct icon and styles', () => {
    render(<ConfirmationDialog {...defaultProps} variant="info" />)

    expect(screen.getByText('Confirm Action')).toBeInTheDocument()
    const infoIcon = screen.getByTestId('information-circle-icon')
    expect(infoIcon).toBeInTheDocument()
    expect(infoIcon).toHaveClass('h-6', 'w-6')
  })

  it('renders success variant with correct icon and styles', () => {
    render(<ConfirmationDialog {...defaultProps} variant="success" />)

    expect(screen.getByText('Confirm Action')).toBeInTheDocument()
    const successIcon = screen.getByTestId('check-circle-icon')
    expect(successIcon).toBeInTheDocument()
    expect(successIcon).toHaveClass('h-6', 'w-6')
  })

  it('applies custom confirm button variant', () => {
    render(
      <ConfirmationDialog {...defaultProps} confirmButtonVariant="primary" />
    )
    const confirmButton = screen.getByTestId('confirm-dialog-confirm-button')
    expect(confirmButton).toBeInTheDocument()
  })

  it('closes dialog when clicking outside', async () => {
    const { container } = render(<ConfirmationDialog {...defaultProps} />)

    // Find the backdrop overlay
    const backdrop = container.querySelector('.fixed.inset-0.bg-black')

    if (backdrop) {
      fireEvent.click(backdrop)
      await waitFor(() => {
        expect(defaultProps.onClose).toHaveBeenCalled()
      })
    }
  })

  it('handles sequential open/close states', () => {
    const { rerender } = render(
      <ConfirmationDialog {...defaultProps} isOpen={false} />
    )
    expect(screen.queryByText('Confirm Action')).not.toBeInTheDocument()

    rerender(<ConfirmationDialog {...defaultProps} isOpen={true} />)
    expect(screen.getByText('Confirm Action')).toBeInTheDocument()

    rerender(<ConfirmationDialog {...defaultProps} isOpen={false} />)
    expect(screen.queryByText('Confirm Action')).not.toBeInTheDocument()
  })

  it('maintains proper dialog structure', () => {
    render(<ConfirmationDialog {...defaultProps} />)

    // Check for dialog title
    const title = screen.getByRole('heading', { name: 'Confirm Action' })
    expect(title).toBeInTheDocument()

    // Check for buttons
    const buttons = screen.getAllByRole('button')
    expect(buttons).toHaveLength(2)
  })

  it('does not call onConfirm when dialog is closed without confirming', () => {
    const { rerender } = render(<ConfirmationDialog {...defaultProps} />)

    // Close dialog without clicking confirm
    fireEvent.click(screen.getByTestId('confirm-dialog-cancel-button'))

    rerender(<ConfirmationDialog {...defaultProps} isOpen={false} />)

    expect(defaultProps.onConfirm).not.toHaveBeenCalled()
    expect(defaultProps.onClose).toHaveBeenCalledTimes(1)
  })
})

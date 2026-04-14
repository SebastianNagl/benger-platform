/**
 * @jest-environment jsdom
 */

import { ModelError } from '@/hooks/useModels'
import { fireEvent, render, screen } from '@testing-library/react'
import {
  AuthenticationError,
  ErrorState,
  ServerErrorWithRetry,
} from '../ErrorStates'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => {
      const translations: Record<string, string> = {
        'errors.states.noApiKeys.title': 'No API Keys Configured',
        'errors.states.noApiKeys.message': 'You need to configure at least one API key to access LLM models.',
        'errors.states.noApiKeys.configureKeys': 'Configure API Keys',
        'errors.states.noApiKeys.supportedProviders': 'Supported providers:',
        'errors.states.authFailed.title': 'Authentication Failed',
        'errors.states.authFailed.message': 'Your session has expired. Please log in again to continue.',
        'errors.states.authFailed.refreshPage': 'Refresh Page',
        'errors.states.serverError.title': 'Server Error',
        'errors.states.serverError.defaultMessage': 'The server encountered an error. This might be temporary.',
        'errors.states.serverError.tryAgain': 'Try Again',
        'errors.states.networkError.title': 'Connection Error',
        'errors.states.networkError.message': 'Unable to connect to the server. Please check your internet connection and try again.',
        'errors.states.networkError.retryConnection': 'Retry Connection',
        'errors.states.taskNotFound.title': 'Task Not Found',
        'errors.states.taskNotFound.defaultMessage': 'The requested task does not exist or has been deleted.',
        'errors.states.taskNotFound.backToProjects': 'Back to Projects',
        'errors.states.accessDenied.title': 'Access Denied',
        'errors.states.accessDenied.defaultMessage': 'You do not have permission to access this task.',
        'errors.states.accessDenied.backToProjects': 'Back to Projects',
        'errors.states.configError.title': 'Configuration Error',
        'errors.states.configError.defaultMessage': 'There was an error with the task configuration.',
        'errors.states.configError.tryAgain': 'Try Again',
        'errors.states.default.title': 'Something went wrong',
        'errors.states.default.defaultMessage': 'An unexpected error occurred.',
        'errors.states.default.tryAgain': 'Try Again',
        'errors.states.authenticationError.message': 'Authentication failed',
        'errors.states.authenticationError.details': 'Your session has expired. Please log in again to continue.',
        'errors.states.serverErrorWithRetry.message': 'Server error',
        'errors.states.serverErrorWithRetry.defaultDetails': 'The server encountered an error. Please try again.',
      }
      return translations[key] || key
    },
    locale: 'en',
  }),
}))

// Mock Next.js Link component
jest.mock('next/link', () => {
  const MockLink = ({ children, href, ...props }: any) => (
    <a href={href} {...props}>
      {children}
    </a>
  )
  MockLink.displayName = 'MockLink'
  return MockLink
})

// Mock Button component
jest.mock('../Button', () => ({
  Button: ({ children, onClick, variant, className, ...props }: any) => (
    <button
      onClick={onClick}
      data-variant={variant}
      className={className}
      {...props}
    >
      {children}
    </button>
  ),
}))

describe('ErrorState Component', () => {
  // ===== BASIC RENDERING =====
  describe('Basic Rendering', () => {
    it('renders error state container correctly', () => {
      const error: ModelError = {
        type: 'SERVER_ERROR',
        message: 'Test error',
      }
      render(<ErrorState error={error} />)
      expect(screen.getByTestId('error-state')).toBeInTheDocument()
    })

    it('renders with default className', () => {
      const error: ModelError = {
        type: 'SERVER_ERROR',
        message: 'Test error',
      }
      const { container } = render(<ErrorState error={error} />)
      const errorState = container.querySelector('[data-testid="error-state"]')
      expect(errorState).toHaveClass('px-4')
      expect(errorState).toHaveClass('py-12')
      expect(errorState).toHaveClass('text-center')
    })

    it('renders with custom className', () => {
      const error: ModelError = {
        type: 'SERVER_ERROR',
        message: 'Test error',
      }
      render(<ErrorState error={error} className="custom-error-class" />)
      const errorState = screen.getByTestId('error-state')
      expect(errorState).toHaveClass('custom-error-class')
    })

    it('renders inner container with max-width constraint', () => {
      const error: ModelError = {
        type: 'SERVER_ERROR',
        message: 'Test error',
      }
      const { container } = render(<ErrorState error={error} />)
      const innerContainer = container.querySelector('.max-w-md')
      expect(innerContainer).toBeInTheDocument()
    })
  })

  // ===== ERROR TYPES/VARIANTS =====
  describe('Error Types/Variants', () => {
    describe('NO_API_KEYS Error', () => {
      it('renders NO_API_KEYS error correctly', () => {
        const error: ModelError = {
          type: 'NO_API_KEYS',
          message: 'No API keys configured',
        }
        render(<ErrorState error={error} />)
        expect(screen.getByText('No API Keys Configured')).toBeInTheDocument()
        expect(
          screen.getByText(
            /You need to configure at least one API key to access LLM models/
          )
        ).toBeInTheDocument()
      })

      it('renders Configure API Keys button for NO_API_KEYS', () => {
        const error: ModelError = {
          type: 'NO_API_KEYS',
          message: 'No API keys configured',
        }
        render(<ErrorState error={error} />)
        expect(screen.getByText('Configure API Keys')).toBeInTheDocument()
      })

      it('renders supported providers for NO_API_KEYS', () => {
        const error: ModelError = {
          type: 'NO_API_KEYS',
          message: 'No API keys configured',
        }
        render(<ErrorState error={error} />)
        expect(screen.getByText('OpenAI')).toBeInTheDocument()
        expect(screen.getByText('Anthropic')).toBeInTheDocument()
        expect(screen.getByText('Google')).toBeInTheDocument()
        expect(screen.getByText('DeepInfra')).toBeInTheDocument()
      })

      it('links to profile page for NO_API_KEYS', () => {
        const error: ModelError = {
          type: 'NO_API_KEYS',
          message: 'No API keys configured',
        }
        render(<ErrorState error={error} />)
        const link = screen.getByText('Configure API Keys').closest('a')
        expect(link).toHaveAttribute('href', '/profile')
      })
    })

    describe('AUTH_FAILED Error', () => {
      it('renders AUTH_FAILED error correctly', () => {
        const error: ModelError = {
          type: 'AUTH_FAILED',
          message: 'Authentication failed',
        }
        render(<ErrorState error={error} />)
        expect(screen.getByText('Authentication Failed')).toBeInTheDocument()
        expect(
          screen.getByText(/Your session has expired. Please log in again/)
        ).toBeInTheDocument()
      })

      it('renders Refresh Page button for AUTH_FAILED', () => {
        const error: ModelError = {
          type: 'AUTH_FAILED',
          message: 'Authentication failed',
        }
        render(<ErrorState error={error} />)
        expect(screen.getByText('Refresh Page')).toBeInTheDocument()
      })

      it('has clickable Refresh Page button for AUTH_FAILED', () => {
        const error: ModelError = {
          type: 'AUTH_FAILED',
          message: 'Authentication failed',
        }

        render(<ErrorState error={error} />)
        const button = screen.getByTestId('retry-button')
        expect(button).toBeInTheDocument()
        expect(button).toHaveAttribute('data-variant', 'filled')

        // Verify button is clickable (not disabled)
        expect(button).not.toBeDisabled()

        // Verify it's actually a button element
        expect(button.tagName).toBe('BUTTON')
      })
    })

    describe('SERVER_ERROR Error', () => {
      it('renders SERVER_ERROR error correctly', () => {
        const error: ModelError = {
          type: 'SERVER_ERROR',
          message: 'Server error occurred',
        }
        render(<ErrorState error={error} />)
        expect(screen.getByText('Server Error')).toBeInTheDocument()
      })

      it('renders default message for SERVER_ERROR without details', () => {
        const error: ModelError = {
          type: 'SERVER_ERROR',
          message: 'Server error',
        }
        render(<ErrorState error={error} />)
        expect(
          screen.getByText(
            'The server encountered an error. This might be temporary.'
          )
        ).toBeInTheDocument()
      })

      it('renders custom details for SERVER_ERROR', () => {
        const error: ModelError = {
          type: 'SERVER_ERROR',
          message: 'Server error',
          details: 'Custom server error details',
        }
        render(<ErrorState error={error} />)
        expect(
          screen.getByText('Custom server error details')
        ).toBeInTheDocument()
      })

      it('renders Try Again button when onRetry is provided for SERVER_ERROR', () => {
        const error: ModelError = {
          type: 'SERVER_ERROR',
          message: 'Server error',
        }
        const handleRetry = jest.fn()
        render(<ErrorState error={error} onRetry={handleRetry} />)
        expect(screen.getByText('Try Again')).toBeInTheDocument()
      })

      it('does not render button when onRetry is not provided for SERVER_ERROR', () => {
        const error: ModelError = {
          type: 'SERVER_ERROR',
          message: 'Server error',
        }
        render(<ErrorState error={error} />)
        expect(screen.queryByTestId('retry-button')).not.toBeInTheDocument()
      })
    })

    describe('NETWORK_ERROR Error', () => {
      it('renders NETWORK_ERROR error correctly', () => {
        const error: ModelError = {
          type: 'NETWORK_ERROR',
          message: 'Network error occurred',
        }
        render(<ErrorState error={error} />)
        expect(screen.getByText('Connection Error')).toBeInTheDocument()
        expect(
          screen.getByText(
            /Unable to connect to the server. Please check your internet/
          )
        ).toBeInTheDocument()
      })

      it('renders Retry Connection button when onRetry is provided for NETWORK_ERROR', () => {
        const error: ModelError = {
          type: 'NETWORK_ERROR',
          message: 'Network error',
        }
        const handleRetry = jest.fn()
        render(<ErrorState error={error} onRetry={handleRetry} />)
        expect(screen.getByText('Retry Connection')).toBeInTheDocument()
      })

      it('does not render button when onRetry is not provided for NETWORK_ERROR', () => {
        const error: ModelError = {
          type: 'NETWORK_ERROR',
          message: 'Network error',
        }
        render(<ErrorState error={error} />)
        expect(screen.queryByTestId('retry-button')).not.toBeInTheDocument()
      })
    })

    describe('TASK_NOT_FOUND Error', () => {
      it('renders TASK_NOT_FOUND error correctly', () => {
        const error = {
          type: 'TASK_NOT_FOUND' as const,
          message: 'Task not found',
        }
        render(<ErrorState error={error} />)
        expect(screen.getByText('Task Not Found')).toBeInTheDocument()
      })

      it('renders default message for TASK_NOT_FOUND without details', () => {
        const error = {
          type: 'TASK_NOT_FOUND' as const,
          message: 'Task not found',
        }
        render(<ErrorState error={error} />)
        expect(
          screen.getByText(
            'The requested task does not exist or has been deleted.'
          )
        ).toBeInTheDocument()
      })

      it('renders custom details for TASK_NOT_FOUND', () => {
        const error = {
          type: 'TASK_NOT_FOUND' as const,
          message: 'Task not found',
          details: 'Task was removed by administrator',
        }
        render(<ErrorState error={error} />)
        expect(
          screen.getByText('Task was removed by administrator')
        ).toBeInTheDocument()
      })

      it('renders Back to Projects button for TASK_NOT_FOUND', () => {
        const error = {
          type: 'TASK_NOT_FOUND' as const,
          message: 'Task not found',
        }
        render(<ErrorState error={error} />)
        expect(screen.getByText('Back to Projects')).toBeInTheDocument()
      })

      it('links to projects page for TASK_NOT_FOUND', () => {
        const error = {
          type: 'TASK_NOT_FOUND' as const,
          message: 'Task not found',
        }
        render(<ErrorState error={error} />)
        const link = screen.getByText('Back to Projects').closest('a')
        expect(link).toHaveAttribute('href', '/projects')
      })
    })

    describe('ACCESS_DENIED Error', () => {
      it('renders ACCESS_DENIED error correctly', () => {
        const error = {
          type: 'ACCESS_DENIED' as const,
          message: 'Access denied',
        }
        render(<ErrorState error={error} />)
        expect(screen.getByText('Access Denied')).toBeInTheDocument()
      })

      it('renders default message for ACCESS_DENIED without details', () => {
        const error = {
          type: 'ACCESS_DENIED' as const,
          message: 'Access denied',
        }
        render(<ErrorState error={error} />)
        expect(
          screen.getByText('You do not have permission to access this task.')
        ).toBeInTheDocument()
      })

      it('renders custom details for ACCESS_DENIED', () => {
        const error = {
          type: 'ACCESS_DENIED' as const,
          message: 'Access denied',
          details: 'Contact admin for access',
        }
        render(<ErrorState error={error} />)
        expect(screen.getByText('Contact admin for access')).toBeInTheDocument()
      })

      it('renders Back to Projects button for ACCESS_DENIED', () => {
        const error = {
          type: 'ACCESS_DENIED' as const,
          message: 'Access denied',
        }
        render(<ErrorState error={error} />)
        expect(screen.getByText('Back to Projects')).toBeInTheDocument()
      })

      it('links to projects page for ACCESS_DENIED', () => {
        const error = {
          type: 'ACCESS_DENIED' as const,
          message: 'Access denied',
        }
        render(<ErrorState error={error} />)
        const link = screen.getByText('Back to Projects').closest('a')
        expect(link).toHaveAttribute('href', '/projects')
      })
    })

    describe('CONFIG_ERROR Error', () => {
      it('renders CONFIG_ERROR error correctly', () => {
        const error = {
          type: 'CONFIG_ERROR' as const,
          message: 'Configuration error',
        }
        render(<ErrorState error={error} />)
        expect(screen.getByText('Configuration Error')).toBeInTheDocument()
      })

      it('renders details for CONFIG_ERROR when provided', () => {
        const error = {
          type: 'CONFIG_ERROR' as const,
          message: 'Config error',
          details: 'Invalid configuration found',
        }
        render(<ErrorState error={error} />)
        expect(
          screen.getByText('Invalid configuration found')
        ).toBeInTheDocument()
      })

      it('renders message when details not provided for CONFIG_ERROR', () => {
        const error = {
          type: 'CONFIG_ERROR' as const,
          message: 'Custom config message',
        }
        render(<ErrorState error={error} />)
        expect(screen.getByText('Custom config message')).toBeInTheDocument()
      })

      it('renders default message when neither details nor message for CONFIG_ERROR', () => {
        const error = {
          type: 'CONFIG_ERROR' as const,
          message: '',
        }
        render(<ErrorState error={error} />)
        expect(
          screen.getByText('There was an error with the task configuration.')
        ).toBeInTheDocument()
      })

      it('renders Try Again button when onRetry is provided for CONFIG_ERROR', () => {
        const error = {
          type: 'CONFIG_ERROR' as const,
          message: 'Config error',
        }
        const handleRetry = jest.fn()
        render(<ErrorState error={error} onRetry={handleRetry} />)
        expect(screen.getByText('Try Again')).toBeInTheDocument()
      })
    })

    describe('Default/Unknown Error', () => {
      it('renders default error state for unknown error type', () => {
        const error = {
          type: 'UNKNOWN_ERROR' as any,
          message: 'Unknown error occurred',
        }
        render(<ErrorState error={error} />)
        expect(screen.getByText('Something went wrong')).toBeInTheDocument()
      })

      it('renders custom message for default error state', () => {
        const error = {
          type: 'UNKNOWN_ERROR' as any,
          message: 'Custom error message',
        }
        render(<ErrorState error={error} />)
        expect(screen.getByText('Custom error message')).toBeInTheDocument()
      })

      it('renders default message when message is empty', () => {
        const error = {
          type: 'UNKNOWN_ERROR' as any,
          message: '',
        }
        render(<ErrorState error={error} />)
        expect(
          screen.getByText('An unexpected error occurred.')
        ).toBeInTheDocument()
      })

      it('renders Try Again button when onRetry is provided for default error', () => {
        const error = {
          type: 'UNKNOWN_ERROR' as any,
          message: 'Unknown error',
        }
        const handleRetry = jest.fn()
        render(<ErrorState error={error} onRetry={handleRetry} />)
        expect(screen.getByText('Try Again')).toBeInTheDocument()
      })
    })
  })

  // ===== ERROR MESSAGE DISPLAY =====
  describe('Error Message Display', () => {
    it('displays error message with data-testid', () => {
      const error: ModelError = {
        type: 'SERVER_ERROR',
        message: 'Server error',
        details: 'Test error details',
      }
      render(<ErrorState error={error} />)
      expect(screen.getByTestId('error-message')).toHaveTextContent(
        'Test error details'
      )
    })

    it('handles empty error message', () => {
      const error: ModelError = {
        type: 'SERVER_ERROR',
        message: '',
      }
      render(<ErrorState error={error} />)
      expect(screen.getByTestId('error-message')).toBeInTheDocument()
    })

    it('handles special characters in error message', () => {
      const ampersand = '&'
      const lessThan = '<'
      const greaterThan = '>'
      const error: ModelError = {
        type: 'SERVER_ERROR',
        message: 'Server error',
        details: `Error ${ampersand} ${lessThan}details${greaterThan}`,
      }
      render(<ErrorState error={error} />)
      expect(screen.getByTestId('error-message')).toHaveTextContent(
        `Error ${ampersand} ${lessThan}details${greaterThan}`
      )
    })

    it('handles very long error messages', () => {
      const longMessage = 'A'.repeat(500)
      const error: ModelError = {
        type: 'SERVER_ERROR',
        message: 'Server error',
        details: longMessage,
      }
      render(<ErrorState error={error} />)
      expect(screen.getByTestId('error-message')).toHaveTextContent(longMessage)
    })
  })

  // ===== ACTION BUTTONS =====
  describe('Action Buttons', () => {
    it('calls onRetry when retry button is clicked', () => {
      const handleRetry = jest.fn()
      const error: ModelError = {
        type: 'SERVER_ERROR',
        message: 'Server error',
      }
      render(<ErrorState error={error} onRetry={handleRetry} />)
      const button = screen.getByTestId('retry-button')
      fireEvent.click(button)
      expect(handleRetry).toHaveBeenCalledTimes(1)
    })

    it('calls onRetry multiple times on multiple clicks', () => {
      const handleRetry = jest.fn()
      const error: ModelError = {
        type: 'SERVER_ERROR',
        message: 'Server error',
      }
      render(<ErrorState error={error} onRetry={handleRetry} />)
      const button = screen.getByTestId('retry-button')
      fireEvent.click(button)
      fireEvent.click(button)
      fireEvent.click(button)
      expect(handleRetry).toHaveBeenCalledTimes(3)
    })

    it('renders button with correct variant', () => {
      const handleRetry = jest.fn()
      const error: ModelError = {
        type: 'SERVER_ERROR',
        message: 'Server error',
      }
      render(<ErrorState error={error} onRetry={handleRetry} />)
      const button = screen.getByTestId('retry-button')
      expect(button).toHaveAttribute('data-variant', 'filled')
    })

    it('does not render retry button when onRetry is undefined', () => {
      const error: ModelError = {
        type: 'SERVER_ERROR',
        message: 'Server error',
      }
      render(<ErrorState error={error} />)
      expect(screen.queryByTestId('retry-button')).not.toBeInTheDocument()
    })
  })

  // ===== PROPS/ATTRIBUTES =====
  describe('Props/Attributes', () => {
    it('accepts and applies className prop', () => {
      const error: ModelError = {
        type: 'SERVER_ERROR',
        message: 'Server error',
      }
      render(
        <ErrorState error={error} className="custom-class another-class" />
      )
      const errorState = screen.getByTestId('error-state')
      expect(errorState).toHaveClass('custom-class')
      expect(errorState).toHaveClass('another-class')
    })

    it('merges custom className with default classes', () => {
      const error: ModelError = {
        type: 'SERVER_ERROR',
        message: 'Server error',
      }
      render(<ErrorState error={error} className="custom-class" />)
      const errorState = screen.getByTestId('error-state')
      expect(errorState).toHaveClass('custom-class')
      expect(errorState).toHaveClass('px-4')
      expect(errorState).toHaveClass('py-12')
      expect(errorState).toHaveClass('text-center')
    })

    it('handles undefined className prop', () => {
      const error: ModelError = {
        type: 'SERVER_ERROR',
        message: 'Server error',
      }
      render(<ErrorState error={error} className={undefined} />)
      const errorState = screen.getByTestId('error-state')
      expect(errorState).toBeInTheDocument()
    })

    it('handles empty string className prop', () => {
      const error: ModelError = {
        type: 'SERVER_ERROR',
        message: 'Server error',
      }
      render(<ErrorState error={error} className="" />)
      const errorState = screen.getByTestId('error-state')
      expect(errorState).toHaveClass('px-4')
    })
  })

  // ===== STYLING =====
  describe('Styling', () => {
    it('applies correct icon background color for NO_API_KEYS', () => {
      const error: ModelError = {
        type: 'NO_API_KEYS',
        message: 'No API keys',
      }
      const { container } = render(<ErrorState error={error} />)
      const iconContainer = container.querySelector('.bg-blue-100')
      expect(iconContainer).toBeInTheDocument()
    })

    it('applies correct icon background color for AUTH_FAILED', () => {
      const error: ModelError = {
        type: 'AUTH_FAILED',
        message: 'Auth failed',
      }
      const { container } = render(<ErrorState error={error} />)
      const iconContainer = container.querySelector('.bg-red-100')
      expect(iconContainer).toBeInTheDocument()
    })

    it('applies correct icon background color for SERVER_ERROR', () => {
      const error: ModelError = {
        type: 'SERVER_ERROR',
        message: 'Server error',
      }
      const { container } = render(<ErrorState error={error} />)
      const iconContainer = container.querySelector('.bg-orange-100')
      expect(iconContainer).toBeInTheDocument()
    })

    it('applies correct icon background color for NETWORK_ERROR', () => {
      const error: ModelError = {
        type: 'NETWORK_ERROR',
        message: 'Network error',
      }
      const { container } = render(<ErrorState error={error} />)
      const iconContainer = container.querySelector('.bg-yellow-100')
      expect(iconContainer).toBeInTheDocument()
    })

    it('applies dark mode classes to icon container', () => {
      const error: ModelError = {
        type: 'SERVER_ERROR',
        message: 'Server error',
      }
      const { container } = render(<ErrorState error={error} />)
      const iconContainer = container.querySelector(
        '.dark\\:bg-orange-900\\/30'
      )
      expect(iconContainer).toBeInTheDocument()
    })

    it('applies dark mode classes to heading', () => {
      const error: ModelError = {
        type: 'SERVER_ERROR',
        message: 'Server error',
      }
      const { container } = render(<ErrorState error={error} />)
      const heading = container.querySelector('.dark\\:text-white')
      expect(heading).toBeInTheDocument()
    })

    it('applies dark mode classes to description text', () => {
      const error: ModelError = {
        type: 'SERVER_ERROR',
        message: 'Server error',
      }
      const { container } = render(<ErrorState error={error} />)
      const description = container.querySelector('.dark\\:text-zinc-400')
      expect(description).toBeInTheDocument()
    })

    it('renders SVG icons with correct size classes', () => {
      const error: ModelError = {
        type: 'SERVER_ERROR',
        message: 'Server error',
      }
      const { container } = render(<ErrorState error={error} />)
      const svg = container.querySelector('svg')
      expect(svg).toHaveClass('h-8')
      expect(svg).toHaveClass('w-8')
    })

    it('renders icon container with rounded-full class', () => {
      const error: ModelError = {
        type: 'SERVER_ERROR',
        message: 'Server error',
      }
      const { container } = render(<ErrorState error={error} />)
      const iconContainer = container.querySelector('.rounded-full')
      expect(iconContainer).toBeInTheDocument()
    })

    it('applies correct sizing to icon container', () => {
      const error: ModelError = {
        type: 'SERVER_ERROR',
        message: 'Server error',
      }
      const { container } = render(<ErrorState error={error} />)
      const iconContainer = container.querySelector('.h-16.w-16')
      expect(iconContainer).toBeInTheDocument()
    })
  })

  // ===== ACCESSIBILITY =====
  describe('Accessibility', () => {
    it('uses semantic heading elements', () => {
      const error: ModelError = {
        type: 'SERVER_ERROR',
        message: 'Server error',
      }
      render(<ErrorState error={error} />)
      const heading = screen.getByText('Server Error')
      expect(heading.tagName).toBe('H3')
    })

    it('provides descriptive button text', () => {
      const error: ModelError = {
        type: 'SERVER_ERROR',
        message: 'Server error',
      }
      const handleRetry = jest.fn()
      render(<ErrorState error={error} onRetry={handleRetry} />)
      expect(screen.getByText('Try Again')).toBeInTheDocument()
    })

    it('includes data-testid for programmatic access', () => {
      const error: ModelError = {
        type: 'SERVER_ERROR',
        message: 'Server error',
      }
      render(<ErrorState error={error} />)
      expect(screen.getByTestId('error-state')).toBeInTheDocument()
    })

    it('provides accessible button for retry action', () => {
      const error: ModelError = {
        type: 'SERVER_ERROR',
        message: 'Server error',
      }
      const handleRetry = jest.fn()
      render(<ErrorState error={error} onRetry={handleRetry} />)
      const button = screen.getByTestId('retry-button')
      expect(button.tagName).toBe('BUTTON')
    })

    it('provides accessible link navigation', () => {
      const error = {
        type: 'TASK_NOT_FOUND' as const,
        message: 'Task not found',
      }
      render(<ErrorState error={error} />)
      const link = screen.getByText('Back to Projects').closest('a')
      expect(link).toHaveAttribute('href', '/projects')
    })
  })

  // ===== EDGE CASES =====
  describe('Edge Cases', () => {
    it('handles error object with only type property', () => {
      const error = {
        type: 'SERVER_ERROR' as const,
        message: '',
      }
      render(<ErrorState error={error} />)
      expect(screen.getByText('Server Error')).toBeInTheDocument()
    })

    it('handles error with undefined details', () => {
      const error: ModelError = {
        type: 'SERVER_ERROR',
        message: 'Server error',
        details: undefined,
      }
      render(<ErrorState error={error} />)
      expect(
        screen.getByText(
          'The server encountered an error. This might be temporary.'
        )
      ).toBeInTheDocument()
    })

    it('handles null onRetry callback gracefully', () => {
      const error: ModelError = {
        type: 'SERVER_ERROR',
        message: 'Server error',
      }
      render(<ErrorState error={error} onRetry={undefined} />)
      expect(screen.queryByTestId('retry-button')).not.toBeInTheDocument()
    })

    it('handles empty error message string', () => {
      const error = {
        type: 'UNKNOWN_ERROR' as any,
        message: '',
      }
      render(<ErrorState error={error} />)
      expect(
        screen.getByText('An unexpected error occurred.')
      ).toBeInTheDocument()
    })

    it('handles error with very long details text', () => {
      const longDetails = 'Error: ' + 'x'.repeat(1000)
      const error: ModelError = {
        type: 'SERVER_ERROR',
        message: 'Server error',
        details: longDetails,
      }
      const { container } = render(<ErrorState error={error} />)
      const message = screen.getByTestId('error-message')
      expect(message).toHaveTextContent(longDetails)
    })

    it('handles rapid button clicks correctly', () => {
      const handleRetry = jest.fn()
      const error: ModelError = {
        type: 'SERVER_ERROR',
        message: 'Server error',
      }
      render(<ErrorState error={error} onRetry={handleRetry} />)
      const button = screen.getByTestId('retry-button')

      for (let i = 0; i < 10; i++) {
        fireEvent.click(button)
      }

      expect(handleRetry).toHaveBeenCalledTimes(10)
    })

    it('handles error type case sensitivity', () => {
      const error = {
        type: 'server_error' as any,
        message: 'Test error',
      }
      render(<ErrorState error={error} />)
      // Should fall back to default error state
      expect(screen.getByText('Something went wrong')).toBeInTheDocument()
    })

    it('renders provider badges with correct styling for NO_API_KEYS', () => {
      const error: ModelError = {
        type: 'NO_API_KEYS',
        message: 'No API keys',
      }
      const { container } = render(<ErrorState error={error} />)
      const openAIBadge = screen.getByText('OpenAI')
      expect(openAIBadge).toHaveClass('bg-blue-100')
      expect(openAIBadge).toHaveClass('text-blue-700')
    })

    it('handles CONFIG_ERROR with empty message and details', () => {
      const error = {
        type: 'CONFIG_ERROR' as const,
        message: '',
        details: '',
      }
      render(<ErrorState error={error} />)
      expect(
        screen.getByText('There was an error with the task configuration.')
      ).toBeInTheDocument()
    })
  })
})

// ===== AUTHENTICATIONERROR COMPONENT =====
describe('AuthenticationError Component', () => {
  it('renders AuthenticationError correctly', () => {
    render(<AuthenticationError />)
    expect(screen.getByText('Authentication Failed')).toBeInTheDocument()
    expect(
      screen.getByText(/Your session has expired. Please log in again/)
    ).toBeInTheDocument()
  })

  it('accepts custom className', () => {
    render(<AuthenticationError className="custom-auth-class" />)
    const errorState = screen.getByTestId('error-state')
    expect(errorState).toHaveClass('custom-auth-class')
  })

  it('renders Refresh Page button', () => {
    render(<AuthenticationError />)
    expect(screen.getByText('Refresh Page')).toBeInTheDocument()
  })

  it('has clickable Refresh Page button', () => {
    render(<AuthenticationError />)
    const button = screen.getByTestId('retry-button')
    expect(button).toBeInTheDocument()
    expect(button).toHaveAttribute('data-variant', 'filled')

    // Verify button is clickable (not disabled)
    expect(button).not.toBeDisabled()

    // Verify it's actually a button element
    expect(button.tagName).toBe('BUTTON')
  })

  it('renders with default empty className', () => {
    const { container } = render(<AuthenticationError />)
    expect(
      container.querySelector('[data-testid="error-state"]')
    ).toBeInTheDocument()
  })
})

// ===== SERVERERRORWITHRETRY COMPONENT =====
describe('ServerErrorWithRetry Component', () => {
  it('renders ServerErrorWithRetry correctly', () => {
    const handleRetry = jest.fn()
    render(<ServerErrorWithRetry onRetry={handleRetry} />)
    expect(screen.getByText('Server Error')).toBeInTheDocument()
  })

  it('renders default message when no custom message provided', () => {
    const handleRetry = jest.fn()
    render(<ServerErrorWithRetry onRetry={handleRetry} />)
    expect(
      screen.getByText('The server encountered an error. Please try again.')
    ).toBeInTheDocument()
  })

  it('renders custom message when provided', () => {
    const handleRetry = jest.fn()
    render(
      <ServerErrorWithRetry
        onRetry={handleRetry}
        message="Custom server error message"
      />
    )
    expect(screen.getByText('Custom server error message')).toBeInTheDocument()
  })

  it('calls onRetry when button is clicked', () => {
    const handleRetry = jest.fn()
    render(<ServerErrorWithRetry onRetry={handleRetry} />)
    const button = screen.getByTestId('retry-button')
    fireEvent.click(button)
    expect(handleRetry).toHaveBeenCalledTimes(1)
  })

  it('accepts custom className', () => {
    const handleRetry = jest.fn()
    render(
      <ServerErrorWithRetry
        onRetry={handleRetry}
        className="custom-server-class"
      />
    )
    const errorState = screen.getByTestId('error-state')
    expect(errorState).toHaveClass('custom-server-class')
  })

  it('renders with default empty className', () => {
    const handleRetry = jest.fn()
    const { container } = render(<ServerErrorWithRetry onRetry={handleRetry} />)
    expect(
      container.querySelector('[data-testid="error-state"]')
    ).toBeInTheDocument()
  })

  it('renders Try Again button', () => {
    const handleRetry = jest.fn()
    render(<ServerErrorWithRetry onRetry={handleRetry} />)
    expect(screen.getByText('Try Again')).toBeInTheDocument()
  })

  it('handles empty string message', () => {
    const handleRetry = jest.fn()
    render(<ServerErrorWithRetry onRetry={handleRetry} message="" />)
    expect(
      screen.getByText('The server encountered an error. Please try again.')
    ).toBeInTheDocument()
  })

  it('handles special characters in custom message', () => {
    const handleRetry = jest.fn()
    const ampersand = '&'
    const message = `Server error ${ampersand} retry needed`
    render(<ServerErrorWithRetry onRetry={handleRetry} message={message} />)
    expect(screen.getByText(message)).toBeInTheDocument()
  })

  it('handles very long custom message', () => {
    const handleRetry = jest.fn()
    const longMessage = 'Error: ' + 'x'.repeat(500)
    render(<ServerErrorWithRetry onRetry={handleRetry} message={longMessage} />)
    expect(screen.getByText(longMessage)).toBeInTheDocument()
  })
})

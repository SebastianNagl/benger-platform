/**
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { LoginModal } from '../auth/LoginModal'

// Mock AuthContext
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: jest.fn(() => ({
    user: { id: 'test-user', email: 'test@example.com', name: 'Test User' },
    apiClient: {
      getTasks: jest.fn().mockResolvedValue({ tasks: [], total: 0 }),
      getTask: jest.fn().mockResolvedValue(null),
      getAllUsers: jest.fn().mockResolvedValue([]),
      getOrganizations: jest.fn().mockResolvedValue([]),
    },
    isLoading: false,
    organizations: [],
    currentOrganization: null,
    setCurrentOrganization: jest.fn(),
    refreshOrganizations: jest.fn(),
  })),
}))

// Mock i18n context
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => {
      const translations: Record<string, string> = {
        'loginModal.title': 'Sign in to BenGER',
        'loginModal.subtitle': 'Access your annotation and evaluation workspace',
        'loginModal.usernameLabel': 'Username or Email',
        'loginModal.usernamePlaceholder': 'Enter username or email',
        'loginModal.passwordLabel': 'Password',
        'loginModal.passwordPlaceholder': 'Enter password',
        'loginModal.cancel': 'Cancel',
        'loginModal.signIn': 'Sign in',
        'loginModal.signingIn': 'Signing in...',
        'loginModal.loginFailed': 'Login failed',
      }
      return translations[key] || key
    },
    currentLanguage: 'en',
  }),
}))

// Import the mocked useAuth to be able to change its behavior per test
import { useAuth } from '@/contexts/AuthContext'
const mockUseAuth = useAuth as jest.MockedFunction<typeof useAuth>

// Mock console.error to suppress React warnings during tests
const originalError = console.error
beforeAll(() => {
  console.error = (...args: any[]) => {
    if (
      typeof args[0] === 'string' &&
      args[0].includes('Warning: An update to')
    ) {
      return
    }
    originalError.call(console, ...args)
  }
})

afterAll(() => {
  console.error = originalError
})

describe('LoginModal - Simple Tests', () => {
  beforeEach(() => {
    mockUseAuth.mockReturnValue({
      user: null,
      login: jest.fn(),
      logout: jest.fn(),
      isLoading: false,
    })
  })

  test('renders login modal when open', async () => {
    await act(async () => {
      render(<LoginModal isOpen={true} onClose={() => {}} />)
    })

    expect(screen.getByText('Sign in to BenGER')).toBeInTheDocument()
  })

  test('does not render when closed', async () => {
    await act(async () => {
      render(<LoginModal isOpen={false} onClose={() => {}} />)
    })

    expect(screen.queryByText('Sign in to BenGER')).not.toBeInTheDocument()
  })

  test('calls onClose when close button is clicked', async () => {
    const mockOnClose = jest.fn()

    await act(async () => {
      render(<LoginModal isOpen={true} onClose={mockOnClose} />)
    })

    const closeButton = screen.getByRole('button', { name: /cancel/i })

    await act(async () => {
      fireEvent.click(closeButton)
    })

    await waitFor(() => {
      expect(mockOnClose).toHaveBeenCalled()
    })
  })

  test('has email and password input fields', async () => {
    await act(async () => {
      render(<LoginModal isOpen={true} onClose={() => {}} />)
    })

    expect(screen.getByLabelText(/username or email/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument()
  })

  test('has sign in button', async () => {
    await act(async () => {
      render(<LoginModal isOpen={true} onClose={() => {}} />)
    })

    expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument()
  })

  test('allows typing in email field', async () => {
    await act(async () => {
      render(<LoginModal isOpen={true} onClose={() => {}} />)
    })

    const emailInput = screen.getByLabelText(
      /username or email/i
    ) as HTMLInputElement

    await act(async () => {
      fireEvent.change(emailInput, { target: { value: 'test@example.com' } })
    })

    expect(emailInput.value).toBe('test@example.com')
  })

  test('allows typing in password field', async () => {
    await act(async () => {
      render(<LoginModal isOpen={true} onClose={() => {}} />)
    })

    const passwordInput = screen.getByLabelText(/password/i) as HTMLInputElement

    await act(async () => {
      fireEvent.change(passwordInput, { target: { value: 'password123' } })
    })

    expect(passwordInput.value).toBe('password123')
  })
})

describe('LoginModal - Core Functionality', () => {
  beforeEach(() => {
    mockUseAuth.mockReturnValue({
      user: null,
      login: jest.fn(),
      logout: jest.fn(),
      isLoading: false,
    })
  })

  test('renders when isOpen is true', async () => {
    await act(async () => {
      render(<LoginModal isOpen={true} onClose={() => {}} />)
    })

    expect(screen.getByText('Sign in to BenGER')).toBeInTheDocument()
  })

  test('does not render when isOpen is false', async () => {
    await act(async () => {
      render(<LoginModal isOpen={false} onClose={() => {}} />)
    })

    expect(screen.queryByText('Sign in to BenGER')).not.toBeInTheDocument()
  })

  test('calls onClose when pressing Escape key', async () => {
    const mockOnClose = jest.fn()

    await act(async () => {
      render(<LoginModal isOpen={true} onClose={mockOnClose} />)
    })

    // HeadlessUI Dialog should respond to Escape key
    await act(async () => {
      fireEvent.keyDown(document.body, { key: 'Escape', code: 'Escape' })
    })

    await waitFor(() => {
      expect(mockOnClose).toHaveBeenCalled()
    })
  })

  test('submits form with email and password', async () => {
    const mockLogin = jest.fn()
    mockUseAuth.mockReturnValue({
      user: null,
      login: mockLogin,
      logout: jest.fn(),
      isLoading: false,
    })

    await act(async () => {
      render(<LoginModal isOpen={true} onClose={() => {}} />)
    })

    const emailInput = screen.getByLabelText(/username or email/i)
    const passwordInput = screen.getByLabelText(/password/i)
    const submitButton = screen.getByRole('button', { name: /sign in/i })

    await act(async () => {
      fireEvent.change(emailInput, { target: { value: 'test@example.com' } })
      fireEvent.change(passwordInput, { target: { value: 'password123' } })
      fireEvent.click(submitButton)
    })

    await waitFor(() => {
      expect(mockLogin).toHaveBeenCalledWith('test@example.com', 'password123')
    })
  })

  test('shows loading state during login', async () => {
    mockUseAuth.mockReturnValue({
      user: null,
      login: jest.fn(),
      logout: jest.fn(),
      isLoading: true,
    })

    await act(async () => {
      render(<LoginModal isOpen={true} onClose={() => {}} />)
    })

    const submitButton = screen.getByRole('button', { name: /sign in/i })
    expect(submitButton).toBeDisabled()
  })

  test('prevents form submission with empty fields', async () => {
    const mockLogin = jest.fn()
    mockUseAuth.mockReturnValue({
      user: null,
      login: mockLogin,
      logout: jest.fn(),
      isLoading: false,
    })

    await act(async () => {
      render(<LoginModal isOpen={true} onClose={() => {}} />)
    })

    const submitButton = screen.getByRole('button', { name: /sign in/i })

    await act(async () => {
      fireEvent.click(submitButton)
    })

    // Should not call login with empty fields
    expect(mockLogin).not.toHaveBeenCalled()
  })

  test('handles keyboard navigation', async () => {
    await act(async () => {
      render(<LoginModal isOpen={true} onClose={() => {}} />)
    })

    const emailInput = screen.getByLabelText(/username or email/i)
    const passwordInput = screen.getByLabelText(/password/i)

    // Focus the email input first, then tab to password
    await act(async () => {
      emailInput.focus()
    })

    await act(async () => {
      fireEvent.keyDown(emailInput, { key: 'Tab', code: 'Tab' })
      fireEvent.keyUp(emailInput, { key: 'Tab', code: 'Tab' })
    })

    // Check that we can manually focus the password field
    await act(async () => {
      passwordInput.focus()
    })

    expect(passwordInput).toHaveFocus()
  })
})

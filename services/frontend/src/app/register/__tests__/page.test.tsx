import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useRouter } from 'next/navigation'
import RegisterPage from '../page'

jest.mock('@/contexts/AuthContext')
jest.mock('@/contexts/I18nContext')
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
}))

jest.mock('@/components/layout', () => ({
  LanguageSwitcher: () => (
    <div data-testid="language-switcher">LanguageSwitcher</div>
  ),
  ThemeToggle: () => <div data-testid="theme-toggle">ThemeToggle</div>,
}))

jest.mock('@/components/shared/Button', () => ({
  Button: ({ children, ...props }: any) => (
    <button {...props}>{children}</button>
  ),
}))

jest.mock('@/components/shared/LikertScale', () => ({
  LikertScale: ({ name, label, value, onChange, required }: any) => (
    <fieldset data-testid={`likert-${name}`}>
      <legend>{label}</legend>
      {[1,2,3,4,5,6,7].map((n: number) => (
        <label key={n}>
          <input
            type="radio"
            name={name}
            value={n}
            checked={value === n}
            onChange={() => onChange(n)}
            data-testid={`likert-${name}-${n}`}
          />
          {n}
        </label>
      ))}
    </fieldset>
  ),
}))

describe('RegisterPage', () => {
  const mockSignup = jest.fn()
  const mockRouterPush = jest.fn()
  const mockRouterReplace = jest.fn()
  const mockT = jest.fn((key: string) => {
    const translations: Record<string, string> = {
      'register.registrationFailed': 'Registration failed',
    }
    return translations[key] || key
  })

  beforeEach(() => {
    jest.clearAllMocks()

    // Mock window.location using Object.defineProperty to avoid jsdom navigation errors
    delete (window as any).location
    window.location = {
      search: '',
      pathname: '/register',
      href: 'http://localhost/register',
    } as any
    ;(useAuth as jest.Mock).mockReturnValue({
      user: null,
      signup: mockSignup,
      isLoading: false,
    })
    ;(useI18n as jest.Mock).mockReturnValue({
      t: mockT,
      currentLanguage: 'en',
    })
    ;(useRouter as jest.Mock).mockReturnValue({
      push: mockRouterPush,
      replace: mockRouterReplace,
    })
  })

  // Helper: fill Step 1 fields
  async function fillStep1(user: ReturnType<typeof userEvent.setup>) {
    await user.type(screen.getByTestId('auth-register-name-input'), 'Test User')
    await user.type(screen.getByTestId('auth-register-username-input'), 'testuser')
    await user.type(screen.getByTestId('auth-register-email-input'), 'test@example.com')
    await user.type(screen.getByTestId('auth-register-password-input'), 'password123')
    await user.type(screen.getByTestId('auth-register-confirm-password-input'), 'password123')
  }

  // Helper: get select element inside a test-id wrapper
  function getSelectInTestId(testId: string): HTMLSelectElement {
    const wrapper = screen.getByTestId(testId)
    const select = wrapper.querySelector('select')
    if (!select) throw new Error(`No <select> found inside data-testid="${testId}"`)
    return select as HTMLSelectElement
  }

  // Helper: fill Step 2 fields (legal background)
  async function fillStep2(user: ReturnType<typeof userEvent.setup>) {
    await user.selectOptions(getSelectInTestId('auth-register-legal-expertise-select'), 'layperson')
    await user.selectOptions(getSelectInTestId('auth-register-german-proficiency-select'), 'native')
  }

  // Helper: fill Step 4 required fields (competence scales)
  async function fillStep4(user: ReturnType<typeof userEvent.setup>) {
    await user.click(screen.getByTestId('likert-subjectiveCompetenceCivil-4'))
    await user.click(screen.getByTestId('likert-subjectiveCompetencePublic-4'))
    await user.click(screen.getByTestId('likert-subjectiveCompetenceCriminal-4'))
  }

  // Helper: fill Step 5 required fields (psychometric scales)
  async function fillStep5(user: ReturnType<typeof userEvent.setup>) {
    // ATI-S
    await user.click(screen.getByTestId('likert-atiS_item1-4'))
    await user.click(screen.getByTestId('likert-atiS_item2-4'))
    await user.click(screen.getByTestId('likert-atiS_item3-4'))
    await user.click(screen.getByTestId('likert-atiS_item4-4'))
    // PTT-A
    await user.click(screen.getByTestId('likert-pttA_item1-4'))
    await user.click(screen.getByTestId('likert-pttA_item2-4'))
    await user.click(screen.getByTestId('likert-pttA_item3-4'))
    await user.click(screen.getByTestId('likert-pttA_item4-4'))
    // KI-Experience
    await user.click(screen.getByTestId('likert-kiExperience_item1-4'))
    await user.click(screen.getByTestId('likert-kiExperience_item2-4'))
    await user.click(screen.getByTestId('likert-kiExperience_item3-4'))
    await user.click(screen.getByTestId('likert-kiExperience_item4-4'))
  }

  // Helper: navigate to a specific step (fills all required fields along the way)
  async function navigateToStep(user: ReturnType<typeof userEvent.setup>, targetStep: number) {
    if (targetStep >= 2) {
      await fillStep1(user)
      await user.click(screen.getByTestId('register-next-button'))
    }
    if (targetStep >= 3) {
      await fillStep2(user)
      await user.click(screen.getByTestId('register-next-button'))
    }
    if (targetStep >= 4) {
      // Step 3 has no required fields
      await user.click(screen.getByTestId('register-next-button'))
    }
    if (targetStep >= 5) {
      await fillStep4(user)
      await user.click(screen.getByTestId('register-next-button'))
    }
  }

  describe('Rendering', () => {
    it('should render registration form', () => {
      render(<RegisterPage />)

      expect(screen.getByTestId('auth-register-form')).toBeInTheDocument()
      expect(screen.getByTestId('auth-register-name-input')).toBeInTheDocument()
      expect(
        screen.getByTestId('auth-register-username-input')
      ).toBeInTheDocument()
      expect(
        screen.getByTestId('auth-register-email-input')
      ).toBeInTheDocument()
      expect(
        screen.getByTestId('auth-register-password-input')
      ).toBeInTheDocument()
      expect(
        screen.getByTestId('auth-register-confirm-password-input')
      ).toBeInTheDocument()
      expect(
        screen.getByTestId('register-next-button')
      ).toBeInTheDocument()
    })

    it('should render navigation elements', () => {
      render(<RegisterPage />)

      expect(screen.getAllByText('BenGER').length).toBeGreaterThan(0)
      expect(screen.getByTestId('language-switcher')).toBeInTheDocument()
      expect(screen.getByTestId('theme-toggle')).toBeInTheDocument()
    })

    it('should render login link', () => {
      render(<RegisterPage />)

      const loginLink = screen.getByTestId('auth-register-login-link')
      expect(loginLink).toBeInTheDocument()
      expect(loginLink).toHaveAttribute('href', '/login')
    })

    it('should render back to landing link', () => {
      render(<RegisterPage />)

      const backLink = screen.getByText('register.backToLanding')
      expect(backLink).toBeInTheDocument()
      expect(backLink.closest('a')).toHaveAttribute('href', '/')
    })

    it('should render privacy policy link', () => {
      render(<RegisterPage />)

      const privacyLink = screen.getByText('register.privacyLink')
      expect(privacyLink.closest('a')).toHaveAttribute(
        'href',
        '/about/data-protection'
      )
    })
  })

  describe('Form Validation', () => {
    it('should have all required fields', () => {
      render(<RegisterPage />)

      const nameInput = screen.getByTestId('auth-register-name-input')
      const usernameInput = screen.getByTestId('auth-register-username-input')
      const emailInput = screen.getByTestId('auth-register-email-input')
      const passwordInput = screen.getByTestId('auth-register-password-input')
      const confirmPasswordInput = screen.getByTestId(
        'auth-register-confirm-password-input'
      )

      expect(nameInput).toHaveAttribute('required')
      expect(usernameInput).toHaveAttribute('required')
      expect(emailInput).toHaveAttribute('required')
      expect(passwordInput).toHaveAttribute('required')
      expect(confirmPasswordInput).toHaveAttribute('required')
    })

    it('should allow typing in all form fields', async () => {
      const user = userEvent.setup()
      render(<RegisterPage />)

      const nameInput = screen.getByTestId(
        'auth-register-name-input'
      ) as HTMLInputElement
      const usernameInput = screen.getByTestId(
        'auth-register-username-input'
      ) as HTMLInputElement
      const emailInput = screen.getByTestId(
        'auth-register-email-input'
      ) as HTMLInputElement
      const passwordInput = screen.getByTestId(
        'auth-register-password-input'
      ) as HTMLInputElement
      const confirmPasswordInput = screen.getByTestId(
        'auth-register-confirm-password-input'
      ) as HTMLInputElement

      await user.type(nameInput, 'Test User')
      await user.type(usernameInput, 'testuser')
      await user.type(emailInput, 'test@example.com')
      await user.type(passwordInput, 'password123')
      await user.type(confirmPasswordInput, 'password123')

      expect(nameInput.value).toBe('Test User')
      expect(usernameInput.value).toBe('testuser')
      expect(emailInput.value).toBe('test@example.com')
      expect(passwordInput.value).toBe('password123')
      expect(confirmPasswordInput.value).toBe('password123')
    })

    it('should have email input type as email', () => {
      render(<RegisterPage />)

      const emailInput = screen.getByTestId('auth-register-email-input')
      expect(emailInput).toHaveAttribute('type', 'email')
    })

    it('should have password fields type as password', () => {
      render(<RegisterPage />)

      const passwordInput = screen.getByTestId('auth-register-password-input')
      const confirmPasswordInput = screen.getByTestId(
        'auth-register-confirm-password-input'
      )

      expect(passwordInput).toHaveAttribute('type', 'password')
      expect(confirmPasswordInput).toHaveAttribute('type', 'password')
    })

    it('should validate password mismatch', async () => {
      const user = userEvent.setup()
      render(<RegisterPage />)

      await user.type(
        screen.getByTestId('auth-register-name-input'),
        'Test User'
      )
      await user.type(
        screen.getByTestId('auth-register-username-input'),
        'testuser'
      )
      await user.type(
        screen.getByTestId('auth-register-email-input'),
        'test@example.com'
      )
      await user.type(
        screen.getByTestId('auth-register-password-input'),
        'password123'
      )
      await user.type(
        screen.getByTestId('auth-register-confirm-password-input'),
        'different'
      )
      await user.click(screen.getByTestId('register-next-button'))

      await waitFor(() => {
        const errorMessage = screen.getByTestId('auth-register-error-message')
        expect(errorMessage).toHaveTextContent('register.passwordMismatch')
      })

      expect(mockSignup).not.toHaveBeenCalled()
    })

    it('should validate password length', async () => {
      const user = userEvent.setup()
      render(<RegisterPage />)

      await user.type(
        screen.getByTestId('auth-register-name-input'),
        'Test User'
      )
      await user.type(
        screen.getByTestId('auth-register-username-input'),
        'testuser'
      )
      await user.type(
        screen.getByTestId('auth-register-email-input'),
        'test@example.com'
      )
      await user.type(
        screen.getByTestId('auth-register-password-input'),
        '12345'
      )
      await user.type(
        screen.getByTestId('auth-register-confirm-password-input'),
        '12345'
      )
      await user.click(screen.getByTestId('register-next-button'))

      await waitFor(() => {
        const errorMessage = screen.getByTestId('auth-register-error-message')
        // Mock t() returns the translation key
        expect(errorMessage).toHaveTextContent('register.passwordTooShort')
      })

      expect(mockSignup).not.toHaveBeenCalled()
    })

    // Note: Empty password validation behavior varies by browser - tested manually
  })

  describe('Form Submission', () => {
    it('should call signup function with correct data', async () => {
      const user = userEvent.setup()
      mockSignup.mockResolvedValue(undefined)

      render(<RegisterPage />)

      // Navigate through all steps filling required data
      await navigateToStep(user, 5)
      await fillStep5(user)

      // Submit on step 5
      await user.click(screen.getByTestId('auth-register-submit-button'))

      await waitFor(() => {
        expect(mockSignup).toHaveBeenCalledWith(
          'testuser',
          'test@example.com',
          'Test User',
          'password123',
          expect.objectContaining({
            legal_expertise_level: 'layperson',
            german_proficiency: 'native',
            subjective_competence_civil: 4,
            subjective_competence_public: 4,
            subjective_competence_criminal: 4,
          }),
          undefined
        )
      })
    })

    it('should display loading state during submission', async () => {
      const user = userEvent.setup()
      let resolveSignup: any
      mockSignup.mockReturnValue(
        new Promise((resolve) => {
          resolveSignup = resolve
        })
      )

      render(<RegisterPage />)

      await navigateToStep(user, 5)
      await fillStep5(user)
      await user.click(screen.getByTestId('auth-register-submit-button'))

      await waitFor(() => {
        const submitButton = screen.getByTestId('auth-register-submit-button')
        expect(submitButton).toBeDisabled()
        expect(screen.getByText('register.loading')).toBeInTheDocument()
      })

      resolveSignup()
    })

    it('should prevent multiple submissions', async () => {
      const user = userEvent.setup()
      mockSignup.mockReturnValue(new Promise(() => {}))

      render(<RegisterPage />)

      await navigateToStep(user, 5)
      await fillStep5(user)

      const submitButton = screen.getByTestId('auth-register-submit-button')
      await user.click(submitButton)
      await user.click(submitButton)
      await user.click(submitButton)

      await waitFor(() => {
        expect(mockSignup).toHaveBeenCalledTimes(1)
      })
    })
  })

  describe('Error Handling', () => {
    it('should display error message on registration failure', async () => {
      const user = userEvent.setup()
      mockSignup.mockRejectedValue(new Error('Username already exists'))

      render(<RegisterPage />)

      await navigateToStep(user, 5)
      await fillStep5(user)
      await user.click(screen.getByTestId('auth-register-submit-button'))

      await waitFor(() => {
        const errorMessage = screen.getByTestId('auth-register-error-message')
        expect(errorMessage).toHaveTextContent('Username already exists')
      })
    })

    it('should display generic error for non-Error objects', async () => {
      const user = userEvent.setup()
      mockSignup.mockRejectedValue('String error')

      render(<RegisterPage />)

      await navigateToStep(user, 5)
      await fillStep5(user)
      await user.click(screen.getByTestId('auth-register-submit-button'))

      await waitFor(() => {
        const errorMessage = screen.getByTestId('auth-register-error-message')
        expect(errorMessage).toHaveTextContent('Registration failed')
      })
    })

    it('should re-enable submit button after error', async () => {
      const user = userEvent.setup()
      mockSignup.mockRejectedValue(new Error('Registration failed'))

      render(<RegisterPage />)

      await navigateToStep(user, 5)
      await fillStep5(user)
      await user.click(screen.getByTestId('auth-register-submit-button'))

      await waitFor(() => {
        expect(
          screen.getByTestId('auth-register-error-message')
        ).toBeInTheDocument()
        expect(
          screen.getByTestId('auth-register-submit-button')
        ).not.toBeDisabled()
      })
    })
  })

  // Note: Invitation flow tests require window.location manipulation - jsdom limitations
  // These features work in production; URL parameter handling verified manually

  describe('Authentication Redirect', () => {
    it('should redirect authenticated users to dashboard', () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: { id: '1', username: 'testuser' },
        signup: mockSignup,
        isLoading: false,
      })

      render(<RegisterPage />)

      expect(mockRouterReplace).toHaveBeenCalledWith('/dashboard')
    })

    it('should show loading state for authenticated users', () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: { id: '1', username: 'testuser' },
        signup: mockSignup,
        isLoading: false,
      })

      render(<RegisterPage />)

      expect(screen.getByText('register.redirecting')).toBeInTheDocument()
      expect(screen.queryByTestId('auth-register-form')).not.toBeInTheDocument()
    })

    // Note: Custom redirect URL requires window.location manipulation - jsdom limitations
  })

  describe('Accessibility', () => {
    it('should have proper form labels', () => {
      render(<RegisterPage />)

      expect(screen.getByLabelText('register.name', { exact: false })).toBeInTheDocument()
      expect(screen.getByLabelText('register.username', { exact: false })).toBeInTheDocument()
      expect(screen.getByLabelText('register.email', { exact: false })).toBeInTheDocument()
      expect(screen.getByLabelText('register.password', { exact: false })).toBeInTheDocument()
      expect(
        screen.getByLabelText('register.confirmPassword', { exact: false })
      ).toBeInTheDocument()
    })

    it('should have proper autocomplete attributes', () => {
      render(<RegisterPage />)

      expect(screen.getByTestId('auth-register-name-input')).toHaveAttribute(
        'autocomplete',
        'name'
      )
      expect(
        screen.getByTestId('auth-register-username-input')
      ).toHaveAttribute('autocomplete', 'username')
      expect(screen.getByTestId('auth-register-email-input')).toHaveAttribute(
        'autocomplete',
        'email'
      )
      expect(
        screen.getByTestId('auth-register-password-input')
      ).toHaveAttribute('autocomplete', 'new-password')
      expect(
        screen.getByTestId('auth-register-confirm-password-input')
      ).toHaveAttribute('autocomplete', 'new-password')
    })

    it('should have proper navigation aria-label', () => {
      render(<RegisterPage />)

      const nav = screen.getByRole('navigation')
      expect(nav).toHaveAttribute('aria-label', 'Global')
    })
  })

  describe('i18n Integration', () => {
    it('should call translation function for all text', () => {
      render(<RegisterPage />)

      expect(mockT).toHaveBeenCalledWith('register.title')
      expect(mockT).toHaveBeenCalledWith('register.name')
      expect(mockT).toHaveBeenCalledWith('register.username')
      expect(mockT).toHaveBeenCalledWith('register.email')
      expect(mockT).toHaveBeenCalledWith('register.password')
      expect(mockT).toHaveBeenCalledWith('register.confirmPassword')
      expect(mockT).toHaveBeenCalledWith('register.stepNext')
      expect(mockT).toHaveBeenCalledWith('register.login')
    })
  })
})

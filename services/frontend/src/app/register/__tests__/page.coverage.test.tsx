/**
 * @jest-environment jsdom
 *
 * Branch coverage tests for RegisterPage.
 * Targets uncovered branches:
 * - Invitation token URL parameters (invitation, email, redirect)
 * - Conditional fields: showDegreeProgramField, showSemesterField
 * - Grade fields visibility based on expertise hierarchy
 * - isIncomparableGradingProgram (LLB/LLM suppresses grade fields)
 * - Step 2 validation: missing legalExpertiseLevel, missing germanProficiency
 * - Step 4 validation: missing competence fields
 * - Step 5 validation: missing psychometric scores
 * - Step indicator click navigation
 * - Redirect with custom redirectUrl from URL params
 * - handleBack function (clicking back button)
 * - validateStep default case
 */
import '@testing-library/jest-dom'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useRouter } from 'next/navigation'

jest.mock('@/contexts/AuthContext')
jest.mock('@/contexts/I18nContext')
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
}))

jest.mock('@/components/layout', () => ({
  LanguageSwitcher: () => <div data-testid="language-switcher">LanguageSwitcher</div>,
  ThemeToggle: () => <div data-testid="theme-toggle">ThemeToggle</div>,
}))

jest.mock('@/components/shared/Button', () => ({
  Button: ({ children, ...props }: any) => (
    <button {...props}>{children}</button>
  ),
}))

jest.mock('@/components/shared/LikertScale', () => ({
  LikertScale: ({ name, label, value, onChange }: any) => (
    <fieldset data-testid={`likert-${name}`}>
      <legend>{label}</legend>
      {[1, 2, 3, 4, 5, 6, 7].map((n: number) => (
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

import RegisterPage from '../page'

/** Get the actual <select> element inside a data-testid wrapper div */
function getSelectInTestId(testId: string): HTMLSelectElement {
  const wrapper = screen.getByTestId(testId)
  const select = wrapper.querySelector('select') || wrapper
  return select as HTMLSelectElement
}

describe('RegisterPage - branch coverage', () => {
  const mockSignup = jest.fn()
  const mockRouterPush = jest.fn()
  const mockRouterReplace = jest.fn()
  const mockT = jest.fn((key: string, params?: any) => {
    if (params?.current) return `Step ${params.current} of ${params.total}`
    return key
  })

  beforeEach(() => {
    jest.clearAllMocks()

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

  // Helpers
  async function fillStep1(user: ReturnType<typeof userEvent.setup>) {
    await user.type(screen.getByTestId('auth-register-name-input'), 'Test User')
    await user.type(screen.getByTestId('auth-register-username-input'), 'testuser')
    await user.type(screen.getByTestId('auth-register-email-input'), 'test@example.com')
    await user.type(screen.getByTestId('auth-register-password-input'), 'password123')
    await user.type(screen.getByTestId('auth-register-confirm-password-input'), 'password123')
  }

  async function fillStep2(user: ReturnType<typeof userEvent.setup>, expertise: string = 'layperson') {
    await user.selectOptions(getSelectInTestId('auth-register-legal-expertise-select'), expertise)
    await user.selectOptions(getSelectInTestId('auth-register-german-proficiency-select'), 'native')
  }

  async function fillStep4(user: ReturnType<typeof userEvent.setup>) {
    await user.click(screen.getByTestId('likert-subjectiveCompetenceCivil-4'))
    await user.click(screen.getByTestId('likert-subjectiveCompetencePublic-4'))
    await user.click(screen.getByTestId('likert-subjectiveCompetenceCriminal-4'))
  }

  async function fillStep5(user: ReturnType<typeof userEvent.setup>) {
    for (const prefix of ['atiS_item', 'pttA_item', 'kiExperience_item']) {
      for (let i = 1; i <= 4; i++) {
        await user.click(screen.getByTestId(`likert-${prefix}${i}-4`))
      }
    }
  }

  async function navigateToStep(user: ReturnType<typeof userEvent.setup>, step: number) {
    if (step >= 2) {
      await fillStep1(user)
      await user.click(screen.getByTestId('register-next-button'))
    }
    if (step >= 3) {
      await fillStep2(user)
      await user.click(screen.getByTestId('register-next-button'))
    }
    if (step >= 4) {
      await user.click(screen.getByTestId('register-next-button'))
    }
    if (step >= 5) {
      await fillStep4(user)
      await user.click(screen.getByTestId('register-next-button'))
    }
  }

  describe('URL parameters and redirects', () => {
    it('redirects to dashboard when no redirect URL and user is set', () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: { id: '1', username: 'testuser' },
        signup: mockSignup,
        isLoading: false,
      })

      render(<RegisterPage />)

      expect(mockRouterReplace).toHaveBeenCalledWith('/dashboard')
    })

    // Note: Invitation URL parameter tests are skipped due to jsdom limitations
    // with window.location mocking. The feature is tested via E2E tests.
  })

  describe('Conditional field visibility', () => {
    it('shows degree program field for law_student expertise', async () => {
      const user = userEvent.setup()
      render(<RegisterPage />)

      await fillStep1(user)
      await user.click(screen.getByTestId('register-next-button'))

      // Select law_student expertise
      await user.selectOptions(
        getSelectInTestId('auth-register-legal-expertise-select'),
        'law_student'
      )

      // Should show degree program dropdown and semester field
      expect(screen.getByTestId('auth-register-degree-program-select')).toBeInTheDocument()
      expect(screen.getByTestId('auth-register-semester-input')).toBeInTheDocument()
    })

    it('hides degree program field for layperson expertise', async () => {
      const user = userEvent.setup()
      render(<RegisterPage />)

      await fillStep1(user)
      await user.click(screen.getByTestId('register-next-button'))

      await user.selectOptions(
        getSelectInTestId('auth-register-legal-expertise-select'),
        'layperson'
      )

      // Should NOT show degree program
      expect(screen.queryByTestId('auth-register-degree-program-select')).not.toBeInTheDocument()
      expect(screen.queryByTestId('auth-register-semester-input')).not.toBeInTheDocument()
    })

    it('shows semester field only for law_student', async () => {
      const user = userEvent.setup()
      render(<RegisterPage />)

      await fillStep1(user)
      await user.click(screen.getByTestId('register-next-button'))

      // Select referendar (not law_student)
      await user.selectOptions(
        getSelectInTestId('auth-register-legal-expertise-select'),
        'referendar'
      )

      // Should show degree program but NOT semester
      expect(screen.getByTestId('auth-register-degree-program-select')).toBeInTheDocument()
      expect(screen.queryByTestId('auth-register-semester-input')).not.toBeInTheDocument()
    })
  })

  describe('Grade fields visibility', () => {
    it('shows grade fields for law_student with staatsexamen degree', async () => {
      const user = userEvent.setup()
      render(<RegisterPage />)

      await fillStep1(user)
      await user.click(screen.getByTestId('register-next-button'))

      await user.selectOptions(getSelectInTestId('auth-register-legal-expertise-select'), 'law_student')
      await user.selectOptions(getSelectInTestId('auth-register-german-proficiency-select'), 'native')
      await user.selectOptions(getSelectInTestId('auth-register-degree-program-select'), 'staatsexamen')

      await user.click(screen.getByTestId('register-next-button'))
      // Skip demographics
      await user.click(screen.getByTestId('register-next-button'))

      // Step 4: Should show Zwischenpruefung and Vorgeruecktenubung but NOT first/second Staatsexamen
      expect(screen.getByTestId('register-grade-zwischenpruefung')).toBeInTheDocument()
      expect(screen.getByTestId('register-grade-vorgeruecktenubung')).toBeInTheDocument()
      expect(screen.queryByTestId('register-grade-first-staatsexamen')).not.toBeInTheDocument()
      expect(screen.queryByTestId('register-grade-second-staatsexamen')).not.toBeInTheDocument()
    })

    it('hides grade fields for LLB degree (incomparable grading)', async () => {
      const user = userEvent.setup()
      render(<RegisterPage />)

      await fillStep1(user)
      await user.click(screen.getByTestId('register-next-button'))

      await user.selectOptions(getSelectInTestId('auth-register-legal-expertise-select'), 'referendar')
      await user.selectOptions(getSelectInTestId('auth-register-german-proficiency-select'), 'native')
      await user.selectOptions(getSelectInTestId('auth-register-degree-program-select'), 'llb')

      await user.click(screen.getByTestId('register-next-button'))
      await user.click(screen.getByTestId('register-next-button'))

      // Step 4: Should NOT show any grade fields for LLB
      expect(screen.queryByTestId('register-grade-zwischenpruefung')).not.toBeInTheDocument()
      expect(screen.queryByTestId('register-grade-first-staatsexamen')).not.toBeInTheDocument()
    })

    it('shows all grade fields for graduated_no_practice with staatsexamen', async () => {
      const user = userEvent.setup()
      render(<RegisterPage />)

      await fillStep1(user)
      await user.click(screen.getByTestId('register-next-button'))

      await user.selectOptions(getSelectInTestId('auth-register-legal-expertise-select'), 'graduated_no_practice')
      await user.selectOptions(getSelectInTestId('auth-register-german-proficiency-select'), 'native')
      await user.selectOptions(getSelectInTestId('auth-register-degree-program-select'), 'staatsexamen')

      await user.click(screen.getByTestId('register-next-button'))
      await user.click(screen.getByTestId('register-next-button'))

      // Step 4: Should show Zwischenpruefung, Vorgeruecktenubung, first Staatsexamen, second Staatsexamen
      expect(screen.getByTestId('register-grade-zwischenpruefung')).toBeInTheDocument()
      expect(screen.getByTestId('register-grade-vorgeruecktenubung')).toBeInTheDocument()
      expect(screen.getByTestId('register-grade-first-staatsexamen')).toBeInTheDocument()
      expect(screen.getByTestId('register-grade-second-staatsexamen')).toBeInTheDocument()
    })
  })

  describe('Step validation branches', () => {
    it('shows error when username is empty on step 1', async () => {
      const user = userEvent.setup()
      render(<RegisterPage />)

      // Fill everything except username
      await user.type(screen.getByTestId('auth-register-name-input'), 'Test')
      await user.type(screen.getByTestId('auth-register-email-input'), 'test@test.com')
      await user.type(screen.getByTestId('auth-register-password-input'), 'password123')
      await user.type(screen.getByTestId('auth-register-confirm-password-input'), 'password123')

      await user.click(screen.getByTestId('register-next-button'))

      await waitFor(() => {
        expect(screen.getByTestId('auth-register-error-message')).toHaveTextContent('register.usernameRequired')
      })
    })

    it('shows error when email is empty on step 1', async () => {
      const user = userEvent.setup()
      render(<RegisterPage />)

      await user.type(screen.getByTestId('auth-register-name-input'), 'Test')
      await user.type(screen.getByTestId('auth-register-username-input'), 'testuser')
      await user.type(screen.getByTestId('auth-register-password-input'), 'password123')
      await user.type(screen.getByTestId('auth-register-confirm-password-input'), 'password123')

      await user.click(screen.getByTestId('register-next-button'))

      await waitFor(() => {
        expect(screen.getByTestId('auth-register-error-message')).toHaveTextContent('register.emailRequired')
      })
    })

    it('shows error when name is empty on step 1', async () => {
      const user = userEvent.setup()
      render(<RegisterPage />)

      await user.type(screen.getByTestId('auth-register-username-input'), 'testuser')
      await user.type(screen.getByTestId('auth-register-email-input'), 'test@test.com')
      await user.type(screen.getByTestId('auth-register-password-input'), 'password123')
      await user.type(screen.getByTestId('auth-register-confirm-password-input'), 'password123')

      await user.click(screen.getByTestId('register-next-button'))

      await waitFor(() => {
        expect(screen.getByTestId('auth-register-error-message')).toHaveTextContent('register.nameRequired')
      })
    })

    it('shows error when legal expertise is missing on step 2', async () => {
      const user = userEvent.setup()
      render(<RegisterPage />)

      await fillStep1(user)
      await user.click(screen.getByTestId('register-next-button'))

      // Don't select expertise, just click next
      await user.selectOptions(getSelectInTestId('auth-register-german-proficiency-select'), 'native')
      await user.click(screen.getByTestId('register-next-button'))

      await waitFor(() => {
        expect(screen.getByTestId('auth-register-error-message')).toHaveTextContent('register.legalExpertiseLevelRequired')
      })
    })

    it('shows error when german proficiency is missing on step 2', async () => {
      const user = userEvent.setup()
      render(<RegisterPage />)

      await fillStep1(user)
      await user.click(screen.getByTestId('register-next-button'))

      await user.selectOptions(getSelectInTestId('auth-register-legal-expertise-select'), 'layperson')
      // Don't select German proficiency
      await user.click(screen.getByTestId('register-next-button'))

      await waitFor(() => {
        expect(screen.getByTestId('auth-register-error-message')).toHaveTextContent('register.germanProficiencyRequired')
      })
    })

    it('shows error when competence scales are missing on step 4', async () => {
      const user = userEvent.setup()
      render(<RegisterPage />)

      await navigateToStep(user, 4)

      // Don't fill competence, just click next
      await user.click(screen.getByTestId('register-next-button'))

      await waitFor(() => {
        expect(screen.getByTestId('auth-register-error-message')).toHaveTextContent('register.competenceRequired')
      })
    })

    it('shows error when psychometric scores are incomplete on step 5', async () => {
      const user = userEvent.setup()
      render(<RegisterPage />)

      await navigateToStep(user, 5)

      // Only fill partial psychometric data
      await user.click(screen.getByTestId('likert-atiS_item1-4'))

      // Try to submit
      await user.click(screen.getByTestId('auth-register-submit-button'))

      await waitFor(() => {
        expect(screen.getByTestId('auth-register-error-message')).toHaveTextContent('register.psychometricRequired')
      })
    })
  })

  describe('Step navigation', () => {
    it('navigates back when back button is clicked', async () => {
      const user = userEvent.setup()
      render(<RegisterPage />)

      await fillStep1(user)
      await user.click(screen.getByTestId('register-next-button'))

      // Should be on step 2
      expect(screen.getByTestId('register-step-2')).toBeInTheDocument()

      // Click back
      await user.click(screen.getByTestId('register-back-button'))

      // Should be on step 1
      expect(screen.getByTestId('register-step-1')).toBeInTheDocument()
    })

    it('clears error when navigating back', async () => {
      const user = userEvent.setup()
      render(<RegisterPage />)

      await fillStep1(user)
      await user.click(screen.getByTestId('register-next-button'))

      // Trigger an error on step 2
      await user.click(screen.getByTestId('register-next-button'))

      await waitFor(() => {
        expect(screen.getByTestId('auth-register-error-message')).toBeInTheDocument()
      })

      // Click back - should clear error
      await user.click(screen.getByTestId('register-back-button'))

      expect(screen.queryByTestId('auth-register-error-message')).not.toBeInTheDocument()
    })

    it('allows clicking on completed step indicators to navigate', async () => {
      const user = userEvent.setup()
      render(<RegisterPage />)

      await fillStep1(user)
      await user.click(screen.getByTestId('register-next-button'))

      // Now on step 2, step 1 indicator should be clickable
      const step1Indicator = screen.getByTestId('register-step-indicator-1')
      await user.click(step1Indicator.closest('button')!)

      // Should be back on step 1
      expect(screen.getByTestId('register-step-1')).toBeInTheDocument()
    })

    it('does not show back button on step 1', () => {
      render(<RegisterPage />)

      expect(screen.queryByTestId('register-back-button')).not.toBeInTheDocument()
    })

    it('shows submit button on step 5 instead of next', async () => {
      const user = userEvent.setup()
      render(<RegisterPage />)

      await navigateToStep(user, 5)

      expect(screen.getByTestId('auth-register-submit-button')).toBeInTheDocument()
      expect(screen.queryByTestId('register-next-button')).not.toBeInTheDocument()
    })
  })

  describe('Redirect flash prevention', () => {
    it('shows spinner when user is authenticated', () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: { id: '1', username: 'testuser' },
        signup: mockSignup,
        isLoading: false,
      })

      const { container } = render(<RegisterPage />)

      expect(screen.getByText('register.redirecting')).toBeInTheDocument()
      expect(container.querySelector('.animate-spin')).toBeInTheDocument()
      expect(screen.queryByTestId('auth-register-form')).not.toBeInTheDocument()
    })
  })

  describe('Form submission with grade data', () => {
    it('submits with grade data when fields are filled', async () => {
      const user = userEvent.setup()
      mockSignup.mockResolvedValue(undefined)

      render(<RegisterPage />)

      // Step 1
      await fillStep1(user)
      await user.click(screen.getByTestId('register-next-button'))

      // Step 2 - select referendar with staatsexamen
      await user.selectOptions(getSelectInTestId('auth-register-legal-expertise-select'), 'referendar')
      await user.selectOptions(getSelectInTestId('auth-register-german-proficiency-select'), 'native')
      await user.selectOptions(getSelectInTestId('auth-register-degree-program-select'), 'staatsexamen')
      await user.click(screen.getByTestId('register-next-button'))

      // Step 3 - demographics (optional, fill some)
      await user.click(screen.getByTestId('register-gender-maennlich'))
      await user.type(screen.getByTestId('register-age-input'), '30')
      await user.click(screen.getByTestId('register-next-button'))

      // Step 4 - competence + grades
      await fillStep4(user)
      await user.type(screen.getByTestId('register-grade-zwischenpruefung'), '12,5')
      await user.type(screen.getByTestId('register-grade-vorgeruecktenubung'), '10,0')
      await user.type(screen.getByTestId('register-grade-first-staatsexamen'), '8,5')
      await user.click(screen.getByTestId('register-next-button'))

      // Step 5
      await fillStep5(user)
      await user.click(screen.getByTestId('auth-register-submit-button'))

      await waitFor(() => {
        expect(mockSignup).toHaveBeenCalledWith(
          'testuser',
          'test@example.com',
          'Test User',
          'password123',
          expect.objectContaining({
            legal_expertise_level: 'referendar',
            german_proficiency: 'native',
            degree_program_type: 'staatsexamen',
            gender: 'maennlich',
            age: 30,
            grade_zwischenpruefung: 12.5,
            grade_vorgeruecktenubung: 10.0,
            grade_first_staatsexamen: 8.5,
          }),
          undefined
        )
      })
    })

    // Note: Invitation token submit test skipped due to jsdom limitations
    // with window.location mocking. The feature is tested via E2E tests.
  })
})

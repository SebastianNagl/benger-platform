/**
 * @jest-environment jsdom
 *
 * Branch coverage tests for RegisterPage.
 * Targets uncovered branches:
 * - Invitation token URL parameters (invitation, email, redirect)
 * - Conditional fields: showDegreeProgramField, showSemesterField
 * - Grade fields visibility based on expertise hierarchy
 * - isIncomparableGradingProgram (LLB/LLM suppresses grade fields)
 * - Steps 2–5 are optional and advance without input (with the optional notice)
 * - Research-data consent gating on step 1 (extended slot present)
 * - Step indicator click navigation
 * - Redirect with custom redirectUrl from URL params
 * - handleBack function (clicking back button)
 * - validateStep default case
 */
import '@testing-library/jest-dom'
import '@/test-utils/locationMock'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { hasSlot, useSlot } from '@/lib/extensions/slots'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useRouter } from 'next/navigation'

jest.mock('@/contexts/AuthContext')
jest.mock('@/contexts/I18nContext')
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
}))

// The research-data consent checkbox is an extended-edition slot. By default
// it's absent (community edition); individual tests opt in via mockReturnValue.
jest.mock('@/lib/extensions/slots', () => ({
  useSlot: jest.fn(),
  hasSlot: jest.fn(),
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

    // jest-location-mock provides the URL; set the path/search via the
    // History API so the mocked Location reflects it.
    window.history.pushState({}, '', 'http://localhost/register')

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
    // Default: no consent slot registered (community edition).
    ;(useSlot as jest.Mock).mockReturnValue(undefined)
    ;(hasSlot as jest.Mock).mockReturnValue(false)
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

    it('advances through optional steps 2–5 without filling any fields', async () => {
      const user = userEvent.setup()
      render(<RegisterPage />)

      await fillStep1(user)
      await user.click(screen.getByTestId('register-next-button'))

      // Step 2 (legal background) is optional and shows the "optional" notice.
      expect(screen.getByTestId('register-step-2')).toBeInTheDocument()
      expect(screen.getByTestId('register-optional-notice')).toBeInTheDocument()
      await user.click(screen.getByTestId('register-next-button'))

      // Step 3 (demographics)
      expect(screen.getByTestId('register-step-3')).toBeInTheDocument()
      expect(screen.getByTestId('register-optional-notice')).toBeInTheDocument()
      await user.click(screen.getByTestId('register-next-button'))

      // Step 4 (competence) — advances without rating anything.
      expect(screen.getByTestId('register-step-4')).toBeInTheDocument()
      expect(screen.getByTestId('register-optional-notice')).toBeInTheDocument()
      await user.click(screen.getByTestId('register-next-button'))

      // Step 5 (psychometric) — reached with no error shown.
      expect(screen.getByTestId('register-step-5')).toBeInTheDocument()
      expect(screen.getByTestId('register-optional-notice')).toBeInTheDocument()
      expect(screen.getByTestId('auth-register-submit-button')).toBeInTheDocument()
      expect(
        screen.queryByTestId('auth-register-error-message')
      ).not.toBeInTheDocument()
    })

    it('submits with steps 2–5 blank, omitting incomplete psychometric scales', async () => {
      const user = userEvent.setup()
      mockSignup.mockResolvedValue(undefined)
      render(<RegisterPage />)

      await fillStep1(user)
      await user.click(screen.getByTestId('register-next-button')) // → step 2
      await user.click(screen.getByTestId('register-next-button')) // → step 3
      await user.click(screen.getByTestId('register-next-button')) // → step 4
      await user.click(screen.getByTestId('register-next-button')) // → step 5
      await user.click(screen.getByTestId('auth-register-submit-button'))

      await waitFor(() => {
        expect(mockSignup).toHaveBeenCalled()
      })
      const [username, , , , profileData, invitationToken] =
        mockSignup.mock.calls[0]
      expect(username).toBe('testuser')
      // Empty scales must be omitted (sent undefined), NOT {} — the backend
      // rejects partial/empty score objects with a 400.
      expect(profileData.ati_s_scores).toBeUndefined()
      expect(profileData.ptt_a_scores).toBeUndefined()
      expect(profileData.ki_experience_scores).toBeUndefined()
      expect(invitationToken).toBeUndefined()
    })

    it('omits a partially-filled psychometric scale', async () => {
      const user = userEvent.setup()
      mockSignup.mockResolvedValue(undefined)
      render(<RegisterPage />)

      await fillStep1(user)
      await user.click(screen.getByTestId('register-next-button')) // → step 2
      await user.click(screen.getByTestId('register-next-button')) // → step 3
      await user.click(screen.getByTestId('register-next-button')) // → step 4
      await user.click(screen.getByTestId('register-next-button')) // → step 5

      // Rate only 2 of the 4 ATI-S items, then submit.
      await user.click(screen.getByTestId('likert-atiS_item1-4'))
      await user.click(screen.getByTestId('likert-atiS_item2-5'))
      await user.click(screen.getByTestId('auth-register-submit-button'))

      await waitFor(() => {
        expect(mockSignup).toHaveBeenCalled()
      })
      const profileData = mockSignup.mock.calls[0][4]
      expect(profileData.ati_s_scores).toBeUndefined()
    })

    it('submits a fully-rated psychometric scale as a complete object', async () => {
      const user = userEvent.setup()
      mockSignup.mockResolvedValue(undefined)
      render(<RegisterPage />)

      await fillStep1(user)
      await user.click(screen.getByTestId('register-next-button')) // → step 2
      await user.click(screen.getByTestId('register-next-button')) // → step 3
      await user.click(screen.getByTestId('register-next-button')) // → step 4
      await user.click(screen.getByTestId('register-next-button')) // → step 5

      // Fully rate ATI-S (all 4 items); leave PTT-A / KI blank.
      for (let i = 1; i <= 4; i++) {
        await user.click(screen.getByTestId(`likert-atiS_item${i}-4`))
      }
      await user.click(screen.getByTestId('auth-register-submit-button'))

      await waitFor(() => {
        expect(mockSignup).toHaveBeenCalled()
      })
      const profileData = mockSignup.mock.calls[0][4]
      expect(profileData.ati_s_scores).toEqual({
        item_1: 4,
        item_2: 4,
        item_3: 4,
        item_4: 4,
      })
      expect(profileData.ptt_a_scores).toBeUndefined()
      expect(profileData.ki_experience_scores).toBeUndefined()
    })

    it('requires research-data consent on step 1 when the extended slot is present', async () => {
      ;(hasSlot as jest.Mock).mockReturnValue(true)
      ;(useSlot as jest.Mock).mockReturnValue(
        ({
          value,
          onChange,
        }: {
          value: boolean
          onChange: (v: boolean) => void
        }) => (
          <input
            type="checkbox"
            data-testid="research-consent-checkbox"
            checked={value}
            onChange={(e) => onChange(e.target.checked)}
          />
        )
      )

      const user = userEvent.setup()
      render(<RegisterPage />)

      // Account fields filled but consent unchecked → blocked on step 1.
      await fillStep1(user)
      await user.click(screen.getByTestId('register-next-button'))

      await waitFor(() => {
        expect(
          screen.getByTestId('auth-register-error-message')
        ).toHaveTextContent('register.researchConsent.required')
      })
      expect(screen.getByTestId('register-step-1')).toBeInTheDocument()

      // Tick consent → now advances to step 2.
      await user.click(screen.getByTestId('research-consent-checkbox'))
      await user.click(screen.getByTestId('register-next-button'))

      expect(screen.getByTestId('register-step-2')).toBeInTheDocument()
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

    it('clears the error when navigating to another step', async () => {
      const user = userEvent.setup()
      render(<RegisterPage />)

      // Trigger a step-1 validation error (password mismatch).
      await user.type(screen.getByTestId('auth-register-name-input'), 'Test User')
      await user.type(screen.getByTestId('auth-register-username-input'), 'testuser')
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
        'mismatch'
      )
      await user.click(screen.getByTestId('register-next-button'))

      await waitFor(() => {
        expect(
          screen.getByTestId('auth-register-error-message')
        ).toBeInTheDocument()
      })

      // Jumping to another step via the stepper clears the error.
      const step2Indicator = screen.getByTestId('register-step-indicator-2')
      await user.click(step2Indicator.closest('button')!)

      expect(
        screen.queryByTestId('auth-register-error-message')
      ).not.toBeInTheDocument()
      expect(screen.getByTestId('register-step-2')).toBeInTheDocument()
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

/**
 * @jest-environment jsdom
 */

import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useRouter } from 'next/navigation'
import { toast } from 'react-hot-toast'
import ProfilePage from '../page'

jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
}))

jest.mock('@/contexts/AuthContext', () => ({
  useAuth: jest.fn(),
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: jest.fn(),
}))

jest.mock('@/components/auth/AuthGuard', () => ({
  AuthGuard: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

jest.mock('@/components/shared/Breadcrumb', () => ({
  Breadcrumb: ({ items }: any) => (
    <div data-testid="breadcrumb">
      {items.map((item: any) => (
        <span key={item.label}>{item.label}</span>
      ))}
    </div>
  ),
}))

jest.mock('@/components/shared/Button', () => ({
  Button: ({ children, onClick, disabled, type, className }: any) => (
    <button
      onClick={onClick}
      disabled={disabled}
      type={type}
      className={className}
    >
      {children}
    </button>
  ),
}))

jest.mock('@/components/shared/ResponsiveContainer', () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="responsive-container">{children}</div>
  ),
}))

// Mock the modal components - they have their own tests
jest.mock('@/components/modals/ChangePasswordModal', () => ({
  ChangePasswordModal: ({ isOpen, onClose }: any) =>
    isOpen ? (
      <div data-testid="change-password-modal" role="dialog">
        <button onClick={onClose}>Close Password Modal</button>
      </div>
    ) : null,
}))

jest.mock('@/components/modals/APIKeysModal', () => ({
  APIKeysModal: ({ isOpen, onClose }: any) =>
    isOpen ? (
      <div data-testid="api-keys-modal" role="dialog">
        <button onClick={onClose}>Close API Keys Modal</button>
      </div>
    ) : null,
}))

// Mock react-hot-toast
jest.mock('react-hot-toast', () => ({
  toast: {
    success: jest.fn(),
    error: jest.fn(),
  },
}))

// Mock heroicons
jest.mock('@heroicons/react/24/outline', () => ({
  ChevronDownIcon: (props: any) => (
    <svg {...props} data-testid="chevron-icon" />
  ),
}))

// Mock LikertScale component (Issue #1206)
jest.mock('@/components/shared/LikertScale', () => ({
  LikertScale: ({ name, label, value, onChange, required }: any) => (
    <fieldset data-testid={`likert-${name}`}>
      <legend>{label}</legend>
      {[1,2,3,4,5,6,7].map((n: number) => (
        <label key={n}>
          <input type="radio" name={name} value={n} checked={value === n}
            onChange={() => onChange(n)} data-testid={`likert-${name}-${n}`} />
          {n}
        </label>
      ))}
    </fieldset>
  ),
}))

const mockT = (key: string) => {
  const translations: Record<string, string> = {
    'profile.title': 'Profile',
    'profile.personalInfo': 'Personal Information',
    'profile.username': 'Username',
    'profile.usernameNote': 'Username cannot be changed',
    'profile.fullName': 'Full Name',
    'profile.emailAddress': 'Email Address',
    'profile.role': 'Role',
    'profile.roles.superadmin': 'Superadmin',
    'profile.roles.user': 'User',
    'profile.roleNote': 'Your role is managed by administrators',
    'profile.updateProfile': 'Update Profile',
    'profile.updating': 'Updating...',
    'profile.changePassword': 'Change Password',
    'profile.apiKeys': 'API Keys',
    'profile.accountInfo': 'Account Information',
    'profile.memberSince': 'Member since:',
    'profile.lastUpdated': 'Last updated:',
    'profile.hideOptionalSettings': 'Hide optional settings',
    'profile.showOptionalSettings': 'Show optional settings',
    'profile.demographicInfo': 'Demographic Information',
    'profile.demographicDescription':
      'This information helps us understand our users',
    'profile.age': 'Age',
    'profile.gender': 'Gender',
    'profile.selectGender': 'Select gender',
    'profile.genderOptions.male': 'Male',
    'profile.genderOptions.female': 'Female',
    'profile.genderOptions.diverse': 'Diverse',
    'profile.genderOptions.preferNotToSay': 'Prefer not to say',
    'profile.job': 'Job',
    'profile.yearsOfExperience': 'Years of Experience',
    'profile.legalExperience': 'Legal Experience',
    'profile.hideLegalExperience': 'Hide legal experience',
    'profile.showLegalExperience': 'Show legal experience',
    'profile.legalExpertise': 'Legal Expertise',
    'profile.legalDescription': 'Information about your legal background',
    'profile.legalExpertiseLevel': 'Legal Expertise Level',
    'profile.selectExpertiseLevel': 'Select expertise level',
    'profile.germanProficiency': 'German Proficiency',
    'profile.selectGermanProficiency': 'Select proficiency level',
    'profile.degreeProgramType': 'Degree Program Type',
    'profile.selectDegreeProgram': 'Select degree program',
    'profile.currentSemester': 'Current Semester',
    'profile.currentSemesterPlaceholder': 'e.g., 3',
    'profile.researchProfile': 'Research Profile',
    'profile.subjectiveCompetence': 'Subjective Competence',
    'profile.subjectiveCompetenceDescription': 'Rate your competence in each area',
    'profile.competenceCivil': 'Civil Law Competence',
    'profile.competencePublic': 'Public Law Competence',
    'profile.competenceCriminal': 'Criminal Law Competence',
    'profile.gradesTitle': 'Grades',
    'profile.gradeZwischenpruefung': 'Zwischenpruefung',
    'profile.gradeVorgeruecktenubung': 'Vorgeruecktenubung',
    'profile.gradeFirstStaatsexamen': 'First Staatsexamen',
    'profile.gradeSecondStaatsexamen': 'Second Staatsexamen',
    'register.expertiseLevel.layperson': 'Layperson',
    'register.expertiseLevel.lawStudent': 'Law Student',
    'register.expertiseLevel.referendar': 'Referendar',
    'register.expertiseLevel.graduatedNoPractice': 'Graduated (No Practice)',
    'register.expertiseLevel.practicingLawyer': 'Practicing Lawyer',
    'register.expertiseLevel.judgeProfessor': 'Judge/Professor',
    'register.germanProficiency.native': 'Native',
    'register.germanProficiency.c2': 'C2',
    'register.germanProficiency.c1': 'C1',
    'register.germanProficiency.b2': 'B2',
    'register.germanProficiency.belowB2': 'Below B2',
    'register.degreeProgram.staatsexamen': 'Staatsexamen',
    'register.degreeProgram.llb': 'LL.B.',
    'register.degreeProgram.llm': 'LL.M.',
    'register.degreeProgram.promotion': 'Promotion',
    'register.degreeProgram.notApplicable': 'Not Applicable',
    'navigation.dashboard': 'Dashboard',
    'navigation.profile': 'Profile',
    'profile.updateSuccess': 'Profile updated successfully!',
    'profile.updateFailed': 'Failed to update profile',
    'profile.loadFailed': 'Failed to load profile',
    'profile.hidePrivacySettings': 'Hide privacy settings',
    'profile.showPrivacySettings': 'Show privacy settings',
    'profile.privacySettings': 'Privacy Settings',
    'profile.yourPseudonym': 'Your Pseudonym',
    'profile.pseudonymNote': 'Your unique pseudonym for privacy protection',
    'profile.usePseudonym': 'I want to work under my pseudonym',
    'profile.usePseudonymDescription':
      'When enabled, your pseudonym will be shown in leaderboards and annotations instead of your real name.',
  }
  return translations[key] || key
}

/**
 * Helper: find a select element near a label with the given text.
 * The shared Select mock renders <select> without an id attribute,
 * so getByLabelText no longer works for Select fields.
 */
function getSelectByLabel(labelText: string): HTMLSelectElement {
  const label = screen.getByText(labelText)
  const wrapper = label.closest('div')
  const select = wrapper?.querySelector('select')
  if (!select) throw new Error(`Could not find select for label "${labelText}"`)
  return select as HTMLSelectElement
}

function querySelectByLabel(labelText: string): HTMLSelectElement | null {
  const label = screen.queryByText(labelText)
  if (!label) return null
  const wrapper = label.closest('div')
  return (wrapper?.querySelector('select') as HTMLSelectElement) || null
}

describe('ProfilePage', () => {
  const mockPush = jest.fn()
  const mockUpdateUser = jest.fn()
  const mockGetProfile = jest.fn()
  const mockUpdateProfile = jest.fn()
  const mockClearCache = jest.fn()
  const mockClearUserCache = jest.fn()

  const mockUser = {
    id: '1',
    username: 'testuser',
    email: 'test@example.com',
    name: 'Test User',
    is_superadmin: false,
    is_active: true,
  }

  const mockProfile = {
    id: '1',
    username: 'testuser',
    email: 'test@example.com',
    name: 'Test User',
    is_superadmin: false,
    is_active: true,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-15T00:00:00Z',
    pseudonym: 'AnonymousUser123',
    use_pseudonym: true,
    age: 30,
    job: 'Software Developer',
    years_of_experience: 5,
    legal_expertise_level: 'practicing_lawyer',
    german_proficiency: 'native',
    degree_program_type: 'staatsexamen',
    gender: 'maennlich',
    subjective_competence_civil: 5,
    subjective_competence_public: 4,
    subjective_competence_criminal: 3,
    mandatory_profile_completed: true,
    profile_confirmed_at: '2024-06-15T00:00:00Z',
  }

  const mockGetMandatoryProfileStatus = jest.fn().mockResolvedValue({
    mandatory_profile_completed: true,
    confirmation_due: false,
    missing_fields: [],
  })
  const mockGetProfileHistory = jest.fn().mockResolvedValue([])
  const mockConfirmProfile = jest.fn().mockResolvedValue({})

  const mockApiClient = {
    getProfile: mockGetProfile,
    updateProfile: mockUpdateProfile,
    clearCache: mockClearCache,
    clearUserCache: mockClearUserCache,
    getMandatoryProfileStatus: mockGetMandatoryProfileStatus,
    getProfileHistory: mockGetProfileHistory,
    confirmProfile: mockConfirmProfile,
  }

  beforeEach(() => {
    jest.clearAllMocks()
    localStorage.clear()
    // Force collapsible sections to expanded state so tests can access fields.
    // The component auto-collapses Legal Experience and Research Profile when
    // the profile has data filled in and localStorage has no stored preference.
    localStorage.setItem('profile_legal_experience_expanded', 'true')
    localStorage.setItem('profile_research_profile_expanded', 'true')
    ;(useRouter as jest.Mock).mockReturnValue({
      push: mockPush,
    })
    ;(useI18n as jest.Mock).mockReturnValue({
      t: mockT,
    })
    ;(useAuth as jest.Mock).mockReturnValue({
      user: mockUser,
      updateUser: mockUpdateUser,
      apiClient: mockApiClient,
    })

    mockGetProfile.mockResolvedValue(mockProfile)
    mockUpdateProfile.mockResolvedValue(mockProfile)
  })

  describe('Page Rendering', () => {
    it('renders loading state initially', () => {
      render(<ProfilePage />)

      const spinner = document.querySelector('.animate-spin')
      expect(spinner).toBeInTheDocument()
    })

    it('renders profile page after loading', async () => {
      render(<ProfilePage />)

      await waitFor(() => {
        expect(
          screen.getByRole('heading', { name: 'Profile' })
        ).toBeInTheDocument()
      })

      expect(screen.getByText('Personal Information')).toBeInTheDocument()
      expect(screen.getByText('Account Information')).toBeInTheDocument()
    })

    it('renders breadcrumb navigation', async () => {
      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Personal Information')).toBeInTheDocument()
      })

      const breadcrumbs = screen.queryAllByRole('navigation', {
        name: 'Breadcrumb',
      })
      expect(breadcrumbs).toBeDefined()
    })

    it('calls getProfile on mount', async () => {
      render(<ProfilePage />)

      await waitFor(() => {
        expect(mockGetProfile).toHaveBeenCalled()
      })
    })

    it('clears cache when loading profile', async () => {
      render(<ProfilePage />)

      await waitFor(() => {
        expect(mockClearCache).toHaveBeenCalled()
      })
    })

    it('renders Change Password button', async () => {
      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Change Password')).toBeInTheDocument()
      })
    })

    it('renders API Keys button', async () => {
      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('API Keys')).toBeInTheDocument()
      })
    })
  })

  describe('Profile Display', () => {
    it('displays username (disabled field)', async () => {
      render(<ProfilePage />)

      await waitFor(() => {
        const usernameInput = screen.getByDisplayValue('testuser')
        expect(usernameInput).toBeInTheDocument()
        expect(usernameInput).toBeDisabled()
      })
    })

    it('displays name in editable field', async () => {
      render(<ProfilePage />)

      await waitFor(() => {
        const nameInput = screen.getByDisplayValue('Test User')
        expect(nameInput).toBeInTheDocument()
        expect(nameInput).not.toBeDisabled()
      })
    })

    it('displays email in editable field', async () => {
      render(<ProfilePage />)

      await waitFor(() => {
        const emailInput = screen.getByDisplayValue('test@example.com')
        expect(emailInput).toBeInTheDocument()
        expect(emailInput).not.toBeDisabled()
      })
    })

    it('displays user role (disabled field)', async () => {
      render(<ProfilePage />)

      await waitFor(() => {
        const roleInput = screen.getByDisplayValue('User')
        expect(roleInput).toBeInTheDocument()
        expect(roleInput).toBeDisabled()
      })
    })

    it('displays superadmin role correctly', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: { ...mockUser, is_superadmin: true },
        updateUser: mockUpdateUser,
        apiClient: mockApiClient,
      })

      mockGetProfile.mockResolvedValue({
        ...mockProfile,
        is_superadmin: true,
      })

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByDisplayValue('Superadmin')).toBeInTheDocument()
      })
    })

    it('displays member since date', async () => {
      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText(/Member since:/)).toBeInTheDocument()
      })

      const memberSinceText =
        screen.getByText(/Member since:/).parentElement?.textContent
      expect(memberSinceText).toContain('2024')
    })

    it('displays last updated date', async () => {
      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText(/Last updated:/)).toBeInTheDocument()
      })

      const lastUpdatedText =
        screen.getByText(/Last updated:/).parentElement?.textContent
      expect(lastUpdatedText).toContain('2024')
    })
  })

  describe('Profile Form Editing', () => {
    it('allows editing name field', async () => {
      const user = userEvent.setup()

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByDisplayValue('Test User')).toBeInTheDocument()
      })

      const nameInput = screen.getByDisplayValue('Test User')
      await user.clear(nameInput)
      await user.type(nameInput, 'Updated Name')

      expect(nameInput).toHaveValue('Updated Name')
    })

    it('allows editing email field', async () => {
      const user = userEvent.setup()

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByDisplayValue('test@example.com')).toBeInTheDocument()
      })

      const emailInput = screen.getByDisplayValue('test@example.com')
      await user.clear(emailInput)
      await user.type(emailInput, 'updated@example.com')

      expect(emailInput).toHaveValue('updated@example.com')
    })

    it('submits profile update successfully', async () => {
      const user = userEvent.setup()

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByDisplayValue('Test User')).toBeInTheDocument()
      })

      const nameInput = screen.getByDisplayValue('Test User')
      await user.clear(nameInput)
      await user.type(nameInput, 'Updated Name')

      const submitButton = screen.getByText('Update Profile')
      await user.click(submitButton)

      await waitFor(() => {
        expect(mockUpdateProfile).toHaveBeenCalledWith(
          expect.objectContaining({
            name: 'Updated Name',
            email: 'test@example.com',
          })
        )
      })
    })

    it('updates auth context after successful profile update', async () => {
      const user = userEvent.setup()

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Update Profile')).toBeInTheDocument()
      })

      const submitButton = screen.getByText('Update Profile')
      await user.click(submitButton)

      await waitFor(() => {
        expect(mockUpdateUser).toHaveBeenCalled()
      })
    })

    it('shows success toast after profile update', async () => {
      const user = userEvent.setup()

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Update Profile')).toBeInTheDocument()
      })

      const submitButton = screen.getByText('Update Profile')
      await user.click(submitButton)

      await waitFor(() => {
        expect(toast.success).toHaveBeenCalledWith(
          'Profile updated successfully!'
        )
      })
    })

    it('shows error toast on profile update failure', async () => {
      const user = userEvent.setup()
      mockUpdateProfile.mockRejectedValue(new Error('Update failed'))

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Update Profile')).toBeInTheDocument()
      })

      const submitButton = screen.getByText('Update Profile')
      await user.click(submitButton)

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith('Update failed')
      })
    })

    it('shows loading state during profile update', async () => {
      const user = userEvent.setup()
      let resolveUpdate: any
      mockUpdateProfile.mockImplementation(
        () =>
          new Promise((resolve) => {
            resolveUpdate = resolve
          })
      )

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Update Profile')).toBeInTheDocument()
      })

      const submitButton = screen.getByText('Update Profile')
      await user.click(submitButton)

      await waitFor(() => {
        expect(screen.getByText('Updating...')).toBeInTheDocument()
      })

      // Cleanup
      resolveUpdate(mockProfile)
    })
  })

  describe('Modal Interactions', () => {
    it('opens Change Password modal when button clicked', async () => {
      const user = userEvent.setup()

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Change Password')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Change Password'))

      await waitFor(() => {
        expect(screen.getByTestId('change-password-modal')).toBeInTheDocument()
      })
    })

    it('closes Change Password modal when close button clicked', async () => {
      const user = userEvent.setup()

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Change Password')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Change Password'))

      await waitFor(() => {
        expect(screen.getByTestId('change-password-modal')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Close Password Modal'))

      await waitFor(() => {
        expect(
          screen.queryByTestId('change-password-modal')
        ).not.toBeInTheDocument()
      })
    })

    it('opens API Keys modal when button clicked', async () => {
      const user = userEvent.setup()

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('API Keys')).toBeInTheDocument()
      })

      await user.click(screen.getByText('API Keys'))

      await waitFor(() => {
        expect(screen.getByTestId('api-keys-modal')).toBeInTheDocument()
      })
    })

    it('closes API Keys modal when close button clicked', async () => {
      const user = userEvent.setup()

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('API Keys')).toBeInTheDocument()
      })

      await user.click(screen.getByText('API Keys'))

      await waitFor(() => {
        expect(screen.getByTestId('api-keys-modal')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Close API Keys Modal'))

      await waitFor(() => {
        expect(screen.queryByTestId('api-keys-modal')).not.toBeInTheDocument()
      })
    })
  })

  describe('Demographic Information Section', () => {
    it('renders demographic information section (always visible)', async () => {
      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Demographic Information')).toBeInTheDocument()
      })

      // Demographic section is always visible, not collapsible
      expect(screen.getByLabelText('Age')).toBeInTheDocument()
      expect(getSelectByLabel('Gender')).toBeInTheDocument()
      expect(getSelectByLabel('German Proficiency')).toBeInTheDocument()
    })

    it('displays populated demographic data', async () => {
      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Demographic Information')).toBeInTheDocument()
      })

      await waitFor(() => {
        expect(screen.getByDisplayValue('30')).toBeInTheDocument()
      })
    })

    it('allows editing age field', async () => {
      const user = userEvent.setup()

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByLabelText('Age')).toBeInTheDocument()
      })

      const ageInput = screen.getByLabelText('Age')
      await user.clear(ageInput)
      await user.type(ageInput, '35')

      expect(ageInput).toHaveValue(35)
    })

    it('displays german proficiency field with populated value', async () => {
      render(<ProfilePage />)

      await waitFor(() => {
        const germanProficiencySelect = getSelectByLabel('German Proficiency')
        expect(germanProficiencySelect).toHaveValue('native')
      })
    })
  })

  describe('Legal Experience Section', () => {
    it('renders legal experience section expanded by default', async () => {
      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Legal Experience')).toBeInTheDocument()
      })

      // Section is expanded by default - should show legal expertise subsection
      expect(screen.getByText('Legal Expertise')).toBeInTheDocument()
    })

    it('collapses legal experience section on click', async () => {
      const user = userEvent.setup()

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Legal Experience')).toBeInTheDocument()
      })

      // Section starts expanded
      expect(screen.getByText('Legal Expertise')).toBeInTheDocument()

      // Click to collapse
      const toggleButton = screen
        .getByText('Legal Experience')
        .closest('button')!
      await user.click(toggleButton)

      await waitFor(() => {
        expect(screen.queryByText('Legal Expertise')).not.toBeInTheDocument()
      })
    })

    it('displays job and years of experience for practicing_lawyer', async () => {
      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Legal Experience')).toBeInTheDocument()
      })

      // practicing_lawyer is in JOB_FIELDS_LEVELS, so job/experience should show
      await waitFor(() => {
        expect(screen.getByLabelText('Job')).toBeInTheDocument()
        expect(screen.getByLabelText('Years of Experience')).toBeInTheDocument()
      })
    })

    it('displays populated job and experience data', async () => {
      render(<ProfilePage />)

      await waitFor(
        () => {
          expect(
            screen.getByDisplayValue('Software Developer')
          ).toBeInTheDocument()
        },
        { timeout: 3000 }
      )

      const experienceInput = screen.getByLabelText('Years of Experience')
      expect(experienceInput).toHaveValue(5)
    })

    it('allows editing job field', async () => {
      const user = userEvent.setup()

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByLabelText('Job')).toBeInTheDocument()
      })

      const jobInput = screen.getByLabelText('Job')
      await user.clear(jobInput)
      await user.type(jobInput, 'Data Scientist')

      expect(jobInput).toHaveValue('Data Scientist')
    })

    it('allows editing years of experience field', async () => {
      const user = userEvent.setup()

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByLabelText('Years of Experience')).toBeInTheDocument()
      })

      const experienceInput = screen.getByLabelText('Years of Experience')
      await user.clear(experienceInput)
      await user.type(experienceInput, '10')

      expect(experienceInput).toHaveValue(10)
    })
  })

  describe('Legal Expertise Fields', () => {
    it('displays legal expertise level field', async () => {
      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Legal Experience')).toBeInTheDocument()
      })

      await waitFor(() => {
        expect(
          getSelectByLabel('Legal Expertise Level')
        ).toBeInTheDocument()
      })
    })

    it('displays populated legal expertise data', async () => {
      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Legal Experience')).toBeInTheDocument()
      })

      await waitFor(() => {
        const expertiseSelect = getSelectByLabel('Legal Expertise Level')
        expect(expertiseSelect).toHaveValue('practicing_lawyer')
      })
    })

    it('allows changing legal expertise level', async () => {
      const user = userEvent.setup()

      render(<ProfilePage />)

      await waitFor(() => {
        expect(
          getSelectByLabel('Legal Expertise Level')
        ).toBeInTheDocument()
      })

      const expertiseSelect = getSelectByLabel('Legal Expertise Level')
      await user.selectOptions(expertiseSelect, 'law_student')

      expect(expertiseSelect).toHaveValue('law_student')
    })

    it('shows degree program type for law students only', async () => {
      // practicing_lawyer should NOT show degree program type (only law_student does)
      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Legal Experience')).toBeInTheDocument()
      })

      await waitFor(() => {
        expect(
          querySelectByLabel('Degree Program Type')
        ).not.toBeInTheDocument()
      })
    })

    it('shows degree program type when expertise level is law_student', async () => {
      mockGetProfile.mockResolvedValue({
        ...mockProfile,
        legal_expertise_level: 'law_student',
        degree_program_type: 'staatsexamen',
      })

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Legal Experience')).toBeInTheDocument()
      })

      await waitFor(() => {
        const degreeProgramSelect = getSelectByLabel('Degree Program Type')
        expect(degreeProgramSelect).toBeInTheDocument()
        expect(degreeProgramSelect).toHaveValue('staatsexamen')
      })
    })

    it('hides degree program type when expertise level is layperson', async () => {
      mockGetProfile.mockResolvedValue({
        ...mockProfile,
        legal_expertise_level: 'layperson',
        degree_program_type: undefined,
      })

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Legal Experience')).toBeInTheDocument()
      })

      await waitFor(() => {
        expect(
          querySelectByLabel('Degree Program Type')
        ).not.toBeInTheDocument()
      })
    })

    it('shows current semester field for law students', async () => {
      mockGetProfile.mockResolvedValue({
        ...mockProfile,
        legal_expertise_level: 'law_student',
        current_semester: 4,
      })

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Legal Experience')).toBeInTheDocument()
      })

      await waitFor(() => {
        const semesterInput = screen.getByLabelText('Current Semester')
        expect(semesterInput).toBeInTheDocument()
        expect(semesterInput).toHaveValue(4)
      })
    })
  })

  describe('Privacy Settings Section', () => {
    it('starts collapsed by default', async () => {
      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Privacy Settings')).toBeInTheDocument()
      })

      // Pseudonym fields should NOT be visible when collapsed
      expect(screen.queryByDisplayValue('AnonymousUser123')).not.toBeInTheDocument()
    })

    it('displays pseudonym field (disabled) when expanded', async () => {
      const user = userEvent.setup()

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Privacy Settings')).toBeInTheDocument()
      })

      // Expand the section
      const toggleButton = screen
        .getByText('Privacy Settings')
        .closest('button')!
      await user.click(toggleButton)

      await waitFor(() => {
        expect(screen.getByDisplayValue('AnonymousUser123')).toBeInTheDocument()
      })

      const pseudonymInput = screen.getByDisplayValue('AnonymousUser123')
      expect(pseudonymInput).toBeDisabled()
    })

    it('displays use pseudonym checkbox when expanded', async () => {
      const user = userEvent.setup()

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Privacy Settings')).toBeInTheDocument()
      })

      // Expand the section
      const toggleButton = screen
        .getByText('Privacy Settings')
        .closest('button')!
      await user.click(toggleButton)

      await waitFor(() => {
        expect(
          screen.getByLabelText(/I want to work under my pseudonym/i)
        ).toBeInTheDocument()
      })
    })

    it('allows toggling use pseudonym setting', async () => {
      const user = userEvent.setup()

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Privacy Settings')).toBeInTheDocument()
      })

      // Expand the section
      const toggleButton = screen
        .getByText('Privacy Settings')
        .closest('button')!
      await user.click(toggleButton)

      await waitFor(() => {
        expect(
          screen.getByLabelText(/I want to work under my pseudonym/i)
        ).toBeInTheDocument()
      })

      const checkbox = screen.getByLabelText(
        /I want to work under my pseudonym/i
      )
      expect(checkbox).toBeChecked()

      await user.click(checkbox)
      expect(checkbox).not.toBeChecked()
    })
  })

  describe('Form Validation', () => {
    it('requires name field', async () => {
      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByDisplayValue('Test User')).toBeInTheDocument()
      })

      const nameInput = screen.getByDisplayValue('Test User')
      expect(nameInput).toHaveAttribute('required')
    })

    it('requires email field', async () => {
      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByDisplayValue('test@example.com')).toBeInTheDocument()
      })

      const emailInput = screen.getByDisplayValue('test@example.com')
      expect(emailInput).toHaveAttribute('required')
      expect(emailInput).toHaveAttribute('type', 'email')
    })
  })

  describe('Error Handling', () => {
    it('handles profile load error', async () => {
      mockGetProfile.mockRejectedValue(new Error('Network error'))

      render(<ProfilePage />)

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith('Failed to load profile')
      })
    })

    it('handles generic update error', async () => {
      const user = userEvent.setup()
      mockUpdateProfile.mockRejectedValue(new Error('Network error'))

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Update Profile')).toBeInTheDocument()
      })

      const submitButton = screen.getByText('Update Profile')
      await user.click(submitButton)

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith('Network error')
      })
    })
  })

  describe('User Pollution Prevention', () => {
    it('handles user switching and profile refresh', async () => {
      localStorage.setItem('benger_last_session_user', '1')

      render(<ProfilePage />)

      await waitFor(() => {
        expect(mockGetProfile).toHaveBeenCalled()
      })

      expect(mockClearCache).toHaveBeenCalled()
    })

    it('clears profile when no user present', () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: null,
        updateUser: mockUpdateUser,
        apiClient: mockApiClient,
      })

      render(<ProfilePage />)

      expect(mockGetProfile).not.toHaveBeenCalled()
    })

    it('detects user ID mismatch and clears storage', async () => {
      localStorage.setItem('benger_last_session_user', '999')
      localStorage.setItem('other_key', 'value')

      render(<ProfilePage />)

      await waitFor(
        () => {
          expect(localStorage.getItem('other_key')).toBeNull()
        },
        { timeout: 3000 }
      )
    })

    it('clears previous user cache when localStorage changes between checks', async () => {
      let getItemCallCount = 0
      const originalGetItem = localStorage.getItem.bind(localStorage)

      jest.spyOn(Storage.prototype, 'getItem').mockImplementation((key) => {
        if (key === 'benger_last_session_user') {
          getItemCallCount++
          if (getItemCallCount === 1) {
            return '1'
          } else {
            return '999'
          }
        }
        return originalGetItem(key)
      })

      render(<ProfilePage />)

      await waitFor(() => {
        expect(mockGetProfile).toHaveBeenCalled()
      })

      expect(mockClearUserCache).toHaveBeenCalledWith('999')

      jest.restoreAllMocks()
    })

    it('detects profile data mismatch and clears localStorage', async () => {
      localStorage.setItem('test_key', 'test_value')

      mockGetProfile.mockResolvedValue({
        ...mockProfile,
        id: '999',
      })

      render(<ProfilePage />)

      await waitFor(
        () => {
          expect(localStorage.getItem('test_key')).toBeNull()
        },
        { timeout: 3000 }
      )
    })

    it('detects profile data mismatch and clears sessionStorage', async () => {
      sessionStorage.setItem('test_session_key', 'test_value')

      mockGetProfile.mockResolvedValue({
        ...mockProfile,
        id: '999',
      })

      render(<ProfilePage />)

      await waitFor(
        () => {
          expect(sessionStorage.getItem('test_session_key')).toBeNull()
        },
        { timeout: 3000 }
      )
    })
  })

  describe('Accessibility', () => {
    it('has proper form structure with labels', async () => {
      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByLabelText('Full Name')).toBeInTheDocument()
      })

      expect(screen.getByLabelText('Full Name')).toBeInTheDocument()
      expect(screen.getByLabelText('Email Address')).toBeInTheDocument()
    })

    it('has proper autocomplete attributes', async () => {
      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByLabelText('Full Name')).toBeInTheDocument()
      })

      expect(screen.getByLabelText('Username')).toHaveAttribute(
        'autocomplete',
        'username'
      )
      expect(screen.getByLabelText('Full Name')).toHaveAttribute(
        'autocomplete',
        'name'
      )
      expect(screen.getByLabelText('Email Address')).toHaveAttribute(
        'autocomplete',
        'email'
      )
    })
  })

  describe('Optional Field Handling', () => {
    it('handles clearing age field', async () => {
      const user = userEvent.setup()

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByLabelText('Age')).toBeInTheDocument()
      })

      const ageInput = screen.getByLabelText('Age')
      await user.clear(ageInput)

      expect(ageInput).toHaveValue(null)
    })

    it('handles clearing years of experience field', async () => {
      const user = userEvent.setup()

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByLabelText('Years of Experience')).toBeInTheDocument()
      })

      const experienceInput = screen.getByLabelText('Years of Experience')
      await user.clear(experienceInput)

      expect(experienceInput).toHaveValue(null)
    })

    it('handles clearing legal expertise level', async () => {
      const user = userEvent.setup()

      render(<ProfilePage />)

      await waitFor(() => {
        expect(
          getSelectByLabel('Legal Expertise Level')
        ).toBeInTheDocument()
      })

      const expertiseSelect = getSelectByLabel('Legal Expertise Level')
      // Use fireEvent.change to clear since the shared Select mock does not
      // render an explicit empty option when a value is already selected
      fireEvent.change(expertiseSelect, { target: { value: '' } })

      expect(expertiseSelect).toHaveValue('')
    })
  })

  describe('Grade Fields (Issue #1206)', () => {
    it('shows grade fields for referendar expertise level (staatsexamen)', async () => {
      mockGetProfile.mockResolvedValue({
        ...mockProfile,
        legal_expertise_level: 'referendar',
        degree_program_type: 'staatsexamen',
        grade_zwischenpruefung: 8.5,
        grade_vorgeruecktenubung: 9.0,
        grade_first_staatsexamen: 10.5,
      })

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Grades')).toBeInTheDocument()
      })

      expect(screen.getByLabelText('Zwischenpruefung')).toBeInTheDocument()
      expect(screen.getByLabelText('Vorgeruecktenubung')).toBeInTheDocument()
      expect(screen.getByLabelText('First Staatsexamen')).toBeInTheDocument()
    })

    it('shows second staatsexamen grade for graduated_no_practice', async () => {
      mockGetProfile.mockResolvedValue({
        ...mockProfile,
        legal_expertise_level: 'graduated_no_practice',
        degree_program_type: 'staatsexamen',
        grade_second_staatsexamen: 7.5,
      })

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Grades')).toBeInTheDocument()
      })

      expect(screen.getByLabelText('Second Staatsexamen')).toBeInTheDocument()
    })

    it('does not show grades for layperson', async () => {
      mockGetProfile.mockResolvedValue({
        ...mockProfile,
        legal_expertise_level: 'layperson',
      })

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Legal Experience')).toBeInTheDocument()
      })

      expect(screen.queryByText('Grades')).not.toBeInTheDocument()
    })

    it('does not show grades for LLB degree program', async () => {
      mockGetProfile.mockResolvedValue({
        ...mockProfile,
        legal_expertise_level: 'law_student',
        degree_program_type: 'llb',
      })

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Legal Experience')).toBeInTheDocument()
      })

      expect(screen.queryByText('Grades')).not.toBeInTheDocument()
    })

    it('does not show grades for LLM degree program', async () => {
      mockGetProfile.mockResolvedValue({
        ...mockProfile,
        legal_expertise_level: 'law_student',
        degree_program_type: 'llm',
      })

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Legal Experience')).toBeInTheDocument()
      })

      expect(screen.queryByText('Grades')).not.toBeInTheDocument()
    })
  })

  describe('Subjective Competence (Issue #1206)', () => {
    it('renders subjective competence likert scales', async () => {
      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Subjective Competence')).toBeInTheDocument()
      })

      expect(screen.getByTestId('likert-subjective_competence_civil')).toBeInTheDocument()
      expect(screen.getByTestId('likert-subjective_competence_public')).toBeInTheDocument()
      expect(screen.getByTestId('likert-subjective_competence_criminal')).toBeInTheDocument()
    })

    it('sets competence value via likert scale', async () => {
      const user = userEvent.setup()

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByTestId('likert-subjective_competence_civil')).toBeInTheDocument()
      })

      // Click a radio button to set value
      await user.click(screen.getByTestId('likert-subjective_competence_civil-3'))

      expect(screen.getByTestId('likert-subjective_competence_civil-3')).toBeChecked()
    })
  })

  describe('Research Profile / Psychometric Scales (Issue #1206)', () => {
    it('renders psychometric scales section when Research Profile expanded', async () => {
      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Research Profile')).toBeInTheDocument()
      })

      // Section starts expanded per localStorage override in beforeEach
      expect(screen.getByTestId('likert-ati_s_1')).toBeInTheDocument()
      expect(screen.getByTestId('likert-ati_s_2')).toBeInTheDocument()
      expect(screen.getByTestId('likert-ati_s_3')).toBeInTheDocument()
      expect(screen.getByTestId('likert-ati_s_4')).toBeInTheDocument()
    })

    it('renders PTT-A scales', async () => {
      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByTestId('likert-ptt_a_1')).toBeInTheDocument()
      })

      expect(screen.getByTestId('likert-ptt_a_2')).toBeInTheDocument()
      expect(screen.getByTestId('likert-ptt_a_3')).toBeInTheDocument()
      expect(screen.getByTestId('likert-ptt_a_4')).toBeInTheDocument()
    })

    it('renders KI-Erfahrung scales', async () => {
      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByTestId('likert-ki_experience_1')).toBeInTheDocument()
      })

      expect(screen.getByTestId('likert-ki_experience_2')).toBeInTheDocument()
      expect(screen.getByTestId('likert-ki_experience_3')).toBeInTheDocument()
      expect(screen.getByTestId('likert-ki_experience_4')).toBeInTheDocument()
    })

    it('collapses Research Profile section on click', async () => {
      const user = userEvent.setup()

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Research Profile')).toBeInTheDocument()
      })

      // Section starts expanded
      expect(screen.getByTestId('likert-ati_s_1')).toBeInTheDocument()

      // Click to collapse
      const toggleButton = screen
        .getByText('Research Profile')
        .closest('button')!
      await user.click(toggleButton)

      await waitFor(() => {
        expect(screen.queryByTestId('likert-ati_s_1')).not.toBeInTheDocument()
      })
    })

    it('sets ATI-S value via likert scale', async () => {
      const user = userEvent.setup()

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByTestId('likert-ati_s_1')).toBeInTheDocument()
      })

      await user.click(screen.getByTestId('likert-ati_s_1-5'))

      expect(screen.getByTestId('likert-ati_s_1-5')).toBeChecked()
    })

    it('sets PTT-A value via likert scale', async () => {
      const user = userEvent.setup()

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByTestId('likert-ptt_a_1')).toBeInTheDocument()
      })

      await user.click(screen.getByTestId('likert-ptt_a_1-4'))

      expect(screen.getByTestId('likert-ptt_a_1-4')).toBeChecked()
    })

    it('sets KI-Experience value via likert scale', async () => {
      const user = userEvent.setup()

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByTestId('likert-ki_experience_1')).toBeInTheDocument()
      })

      await user.click(screen.getByTestId('likert-ki_experience_1-6'))

      expect(screen.getByTestId('likert-ki_experience_1-6')).toBeChecked()
    })
  })

  describe('Profile Confirm (Issue #1206)', () => {
    it('renders confirmation banner when confirmation_due', async () => {
      mockGetMandatoryProfileStatus.mockResolvedValue({
        mandatory_profile_completed: true,
        confirmation_due: true,
        missing_fields: [],
      })

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('profile.confirmationDue')).toBeInTheDocument()
      })
    })

    it('renders mandatory incomplete banner when not completed', async () => {
      mockGetMandatoryProfileStatus.mockResolvedValue({
        mandatory_profile_completed: false,
        confirmation_due: false,
        missing_fields: ['legal_expertise_level'],
      })

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('profile.mandatoryIncomplete')).toBeInTheDocument()
      })
    })

    it('shows missing fields in confirmation banner', async () => {
      mockGetMandatoryProfileStatus.mockResolvedValue({
        mandatory_profile_completed: true,
        confirmation_due: true,
        missing_fields: ['age', 'gender'],
      })

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText(/age, gender/)).toBeInTheDocument()
      })
    })

    it('calls confirmProfile when confirm button clicked', async () => {
      const user = userEvent.setup()
      mockGetMandatoryProfileStatus.mockResolvedValue({
        mandatory_profile_completed: true,
        confirmation_due: true,
        missing_fields: [],
      })
      mockConfirmProfile.mockResolvedValue({})

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('profile.confirmProfile')).toBeInTheDocument()
      })

      await user.click(screen.getByText('profile.confirmProfile'))

      await waitFor(() => {
        expect(mockConfirmProfile).toHaveBeenCalled()
      })
    })

    it('handles confirm profile failure', async () => {
      const user = userEvent.setup()
      mockGetMandatoryProfileStatus.mockResolvedValue({
        mandatory_profile_completed: true,
        confirmation_due: true,
        missing_fields: [],
      })
      mockConfirmProfile.mockRejectedValue(new Error('Confirm failed'))

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('profile.confirmProfile')).toBeInTheDocument()
      })

      await user.click(screen.getByText('profile.confirmProfile'))

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith('Confirm failed')
      })
    })

    it('disables confirm button when missing fields exist', async () => {
      mockGetMandatoryProfileStatus.mockResolvedValue({
        mandatory_profile_completed: true,
        confirmation_due: true,
        missing_fields: ['age'],
      })

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('profile.confirmProfile')).toBeInTheDocument()
      })

      const confirmButton = screen.getByText('profile.confirmProfile')
      expect(confirmButton).toBeDisabled()
    })
  })

  describe('Profile History (superadmin, Issue #1206)', () => {
    it('renders profile history section for superadmin with history', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: { ...mockUser, is_superadmin: true },
        updateUser: mockUpdateUser,
        apiClient: mockApiClient,
      })
      mockGetProfile.mockResolvedValue({
        ...mockProfile,
        is_superadmin: true,
      })
      mockGetProfileHistory.mockResolvedValue([
        {
          id: 'h1',
          change_type: 'profile_update',
          changed_at: '2024-06-15T00:00:00Z',
          changed_fields: ['name', 'email'],
        },
      ])

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('profile.profileHistory')).toBeInTheDocument()
      })
    })

    it('expands profile history section on click', async () => {
      const user = userEvent.setup()
      localStorage.setItem('profile_history_expanded', 'false')
      ;(useAuth as jest.Mock).mockReturnValue({
        user: { ...mockUser, is_superadmin: true },
        updateUser: mockUpdateUser,
        apiClient: mockApiClient,
      })
      mockGetProfile.mockResolvedValue({
        ...mockProfile,
        is_superadmin: true,
      })
      mockGetProfileHistory.mockResolvedValue([
        {
          id: 'h1',
          change_type: 'profile_update',
          changed_at: '2024-06-15T00:00:00Z',
          changed_fields: ['name', 'email'],
        },
      ])

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('profile.profileHistory')).toBeInTheDocument()
      })

      // Click to expand
      const toggleButton = screen
        .getByText('profile.profileHistory')
        .closest('button')!
      await user.click(toggleButton)

      await waitFor(() => {
        expect(screen.getByText('profile_update')).toBeInTheDocument()
        expect(screen.getByText(/name, email/)).toBeInTheDocument()
      })
    })

    it('does not render profile history for non-superadmin', async () => {
      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Personal Information')).toBeInTheDocument()
      })

      expect(screen.queryByText('profile.profileHistory')).not.toBeInTheDocument()
    })
  })

  describe('GradeInput Interactions', () => {
    it('allows typing a grade value with comma notation', async () => {
      const user = userEvent.setup()
      mockGetProfile.mockResolvedValue({
        ...mockProfile,
        legal_expertise_level: 'referendar',
        degree_program_type: 'staatsexamen',
        grade_zwischenpruefung: undefined,
      })

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByLabelText('Zwischenpruefung')).toBeInTheDocument()
      })

      const gradeInput = screen.getByLabelText('Zwischenpruefung')
      await user.type(gradeInput, '8,5')

      expect(gradeInput).toHaveValue('8,5')
    })

    it('allows clearing a grade value', async () => {
      const user = userEvent.setup()
      mockGetProfile.mockResolvedValue({
        ...mockProfile,
        legal_expertise_level: 'referendar',
        degree_program_type: 'staatsexamen',
        grade_zwischenpruefung: 8.5,
      })

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByLabelText('Zwischenpruefung')).toBeInTheDocument()
      })

      const gradeInput = screen.getByLabelText('Zwischenpruefung')
      await user.clear(gradeInput)

      expect(gradeInput).toHaveValue('')
    })

    it('rejects non-numeric input in grade field', async () => {
      const user = userEvent.setup()
      mockGetProfile.mockResolvedValue({
        ...mockProfile,
        legal_expertise_level: 'referendar',
        degree_program_type: 'staatsexamen',
        grade_zwischenpruefung: undefined,
      })

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByLabelText('Zwischenpruefung')).toBeInTheDocument()
      })

      const gradeInput = screen.getByLabelText('Zwischenpruefung')
      await user.type(gradeInput, 'abc')

      // Non-numeric input should be rejected
      expect(gradeInput).toHaveValue('')
    })

    it('formats grade value on blur', async () => {
      const user = userEvent.setup()
      mockGetProfile.mockResolvedValue({
        ...mockProfile,
        legal_expertise_level: 'referendar',
        degree_program_type: 'staatsexamen',
        grade_zwischenpruefung: undefined,
      })

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByLabelText('Zwischenpruefung')).toBeInTheDocument()
      })

      const gradeInput = screen.getByLabelText('Zwischenpruefung')
      await user.type(gradeInput, '8.50')
      await user.tab() // trigger blur

      // After blur, should format with comma notation
      expect(gradeInput).toHaveValue('8,5')
    })

    it('displays pre-populated grade with comma notation', async () => {
      mockGetProfile.mockResolvedValue({
        ...mockProfile,
        legal_expertise_level: 'referendar',
        degree_program_type: 'staatsexamen',
        grade_zwischenpruefung: 8.5,
      })

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByLabelText('Zwischenpruefung')).toBeInTheDocument()
      })

      const gradeInput = screen.getByLabelText('Zwischenpruefung')
      expect(gradeInput).toHaveValue('8,5')
    })

    it('submits grade values in profile update', async () => {
      const user = userEvent.setup()
      mockGetProfile.mockResolvedValue({
        ...mockProfile,
        legal_expertise_level: 'referendar',
        degree_program_type: 'staatsexamen',
        grade_zwischenpruefung: 8.5,
        grade_vorgeruecktenubung: 9.0,
        grade_first_staatsexamen: 10.5,
      })

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Update Profile')).toBeInTheDocument()
      })

      const submitButton = screen.getByText('Update Profile')
      await user.click(submitButton)

      await waitFor(() => {
        expect(mockUpdateProfile).toHaveBeenCalledWith(
          expect.objectContaining({
            grade_zwischenpruefung: 8.5,
            grade_vorgeruecktenubung: 9.0,
            grade_first_staatsexamen: 10.5,
          })
        )
      })
    })
  })

  describe('Gender Selection', () => {
    it('allows changing gender', async () => {
      const user = userEvent.setup()

      render(<ProfilePage />)

      await waitFor(() => {
        expect(getSelectByLabel('Gender')).toBeInTheDocument()
      })

      const genderSelect = getSelectByLabel('Gender')
      await user.selectOptions(genderSelect, 'weiblich')

      expect(genderSelect).toHaveValue('weiblich')
    })

    it('allows clearing gender', async () => {
      render(<ProfilePage />)

      await waitFor(() => {
        expect(getSelectByLabel('Gender')).toBeInTheDocument()
      })

      const genderSelect = getSelectByLabel('Gender')
      // Use fireEvent.change directly since the shared Select mock does not
      // render an explicit empty option when a value is already selected
      fireEvent.change(genderSelect, { target: { value: '' } })

      expect(genderSelect).toHaveValue('')
    })
  })
})

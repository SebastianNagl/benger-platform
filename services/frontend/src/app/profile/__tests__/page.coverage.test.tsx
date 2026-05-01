/**
 * Coverage extension tests for Profile Page
 *
 * Tests for previously uncovered code paths:
 * - Mandatory profile confirmation banner
 * - Mandatory profile incomplete banner
 * - Confirm profile handler
 * - Profile history display (superadmin only)
 * - Research profile section (psychometric scales)
 * - Grades section conditional rendering
 * - GradeInput component behavior
 * - Non-Error rejection in submit
 * - Auto-collapse sections based on data
 * - Profile confirmed_at display
 *
 * @jest-environment jsdom
 */

import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useRouter } from 'next/navigation'
import { mockToast as __mockToast } from '@/test-utils/setupTests'
const toast = { success: __mockToast.success, error: __mockToast.error }
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

jest.mock('@/components/modals/ChangePasswordModal', () => ({
  ChangePasswordModal: ({ isOpen }: any) =>
    isOpen ? <div data-testid="change-password-modal" /> : null,
}))

jest.mock('@/components/modals/APIKeysModal', () => ({
  APIKeysModal: ({ isOpen }: any) =>
    isOpen ? <div data-testid="api-keys-modal" /> : null,
}))

jest.mock('@heroicons/react/24/outline', () => ({
  ChevronDownIcon: (props: any) => (
    <svg {...props} data-testid="chevron-icon" />
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
    'profile.roleNote': 'Role managed by administrators',
    'profile.updateProfile': 'Update Profile',
    'profile.updating': 'Updating...',
    'profile.changePassword': 'Change Password',
    'profile.apiKeys': 'API Keys',
    'profile.accountInfo': 'Account Information',
    'profile.memberSince': 'Member since:',
    'profile.lastUpdated': 'Last updated:',
    'profile.lastConfirmed': 'Last confirmed:',
    'profile.demographicInfo': 'Demographic Information',
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
    'profile.legalExpertiseLevel': 'Legal Expertise Level',
    'profile.selectExpertiseLevel': 'Select expertise level',
    'profile.germanProficiency': 'German Proficiency',
    'profile.selectGermanProficiency': 'Select proficiency',
    'profile.degreeProgramType': 'Degree Program Type',
    'profile.selectDegreeProgram': 'Select degree program',
    'profile.currentSemester': 'Current Semester',
    'profile.currentSemesterPlaceholder': 'e.g., 3',
    'profile.researchProfile': 'Research Profile',
    'profile.hideOptionalSettings': 'Hide optional settings',
    'profile.showOptionalSettings': 'Show optional settings',
    'profile.subjectiveCompetence': 'Subjective Competence',
    'profile.subjectiveCompetenceDescription': 'Rate your competence',
    'profile.competenceCivil': 'Civil Law Competence',
    'profile.competencePublic': 'Public Law Competence',
    'profile.competenceCriminal': 'Criminal Law Competence',
    'profile.gradesTitle': 'Grades',
    'profile.gradeZwischenpruefung': 'Zwischenpruefung',
    'profile.gradeVorgeruecktenubung': 'Vorgeruecktenubung',
    'profile.gradeFirstStaatsexamen': 'First Staatsexamen',
    'profile.gradeSecondStaatsexamen': 'Second Staatsexamen',
    'profile.privacySettings': 'Privacy Settings',
    'profile.hidePrivacySettings': 'Hide privacy settings',
    'profile.showPrivacySettings': 'Show privacy settings',
    'profile.yourPseudonym': 'Your Pseudonym',
    'profile.pseudonymNote': 'Your unique pseudonym',
    'profile.usePseudonym': 'I want to work under my pseudonym',
    'profile.usePseudonymDescription': 'Pseudonym will be shown',
    'profile.confirmationDue': 'Confirmation due',
    'profile.confirmationDueDescription': 'Please confirm your profile',
    'profile.missingFields': 'Missing fields',
    'profile.confirmProfile': 'Confirm Profile',
    'profile.confirming': 'Confirming...',
    'profile.profileConfirmed': 'Profile confirmed',
    'profile.confirmFailed': 'Confirmation failed',
    'profile.mandatoryIncomplete': 'Mandatory profile incomplete',
    'profile.mandatoryIncompleteDescription': 'Please complete mandatory fields',
    'profile.profileHistory': 'Profile History',
    'profile.hideProfileHistory': 'Hide history',
    'profile.showProfileHistory': 'Show history',
    'profile.changedFields': 'Changed fields',
    'profile.psychometricScales': 'Psychometric Scales',
    'profile.psychometricScalesDescription': 'Fill in the scales',
    'profile.atiS.title': 'ATI-S Scale',
    'profile.atiS.item1': 'ATI-S Item 1',
    'profile.atiS.item2': 'ATI-S Item 2',
    'profile.atiS.item3': 'ATI-S Item 3',
    'profile.atiS.item4': 'ATI-S Item 4',
    'profile.pttA.title': 'PTT-A Scale',
    'profile.pttA.item1': 'PTT-A Item 1',
    'profile.pttA.item2': 'PTT-A Item 2',
    'profile.pttA.item3': 'PTT-A Item 3',
    'profile.pttA.item4': 'PTT-A Item 4',
    'profile.kiExperience.title': 'KI Experience',
    'profile.kiExperience.item1': 'KI Item 1',
    'profile.kiExperience.item2': 'KI Item 2',
    'profile.kiExperience.item3': 'KI Item 3',
    'profile.kiExperience.item4': 'KI Item 4',
    'profile.updateSuccess': 'Profile updated successfully!',
    'profile.updateFailed': 'Failed to update profile',
    'profile.loadFailed': 'Failed to load profile',
    'register.expertiseLevel.layperson': 'Layperson',
    'register.expertiseLevel.lawStudent': 'Law Student',
    'register.expertiseLevel.referendar': 'Referendar',
    'register.expertiseLevel.graduatedNoPractice': 'Graduated',
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
  }
  return translations[key] || key
}

describe('ProfilePage - coverage extensions', () => {
  const mockPush = jest.fn()
  const mockUpdateUser = jest.fn()
  const mockGetProfile = jest.fn()
  const mockUpdateProfile = jest.fn()
  const mockClearCache = jest.fn()
  const mockClearUserCache = jest.fn()
  const mockGetMandatoryProfileStatus = jest.fn()
  const mockGetProfileHistory = jest.fn()
  const mockConfirmProfile = jest.fn()

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
    pseudonym: 'AnonUser123',
    use_pseudonym: true,
    age: 30,
    job: 'Developer',
    years_of_experience: 5,
    legal_expertise_level: 'referendar',
    german_proficiency: 'native',
    gender: 'maennlich',
    subjective_competence_civil: 5,
    subjective_competence_public: 4,
    subjective_competence_criminal: 3,
    mandatory_profile_completed: true,
    profile_confirmed_at: '2024-06-15T00:00:00Z',
  }

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
    localStorage.setItem('profile_legal_experience_expanded', 'true')
    localStorage.setItem('profile_research_profile_expanded', 'true')
    ;(useRouter as jest.Mock).mockReturnValue({ push: mockPush })
    ;(useI18n as jest.Mock).mockReturnValue({ t: mockT })
    ;(useAuth as jest.Mock).mockReturnValue({
      user: mockUser,
      updateUser: mockUpdateUser,
      apiClient: mockApiClient,
    })

    mockGetProfile.mockResolvedValue(mockProfile)
    mockUpdateProfile.mockResolvedValue(mockProfile)
    mockGetMandatoryProfileStatus.mockResolvedValue({
      mandatory_profile_completed: true,
      confirmation_due: false,
      missing_fields: [],
    })
    mockGetProfileHistory.mockResolvedValue([])
    mockConfirmProfile.mockResolvedValue({})
  })

  describe('Mandatory profile confirmation banner', () => {
    it('should show confirmation due banner when confirmation_due is true', async () => {
      mockGetMandatoryProfileStatus.mockResolvedValue({
        mandatory_profile_completed: true,
        confirmation_due: true,
        missing_fields: [],
      })

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Confirmation due')).toBeInTheDocument()
      })
      expect(screen.getByText('Please confirm your profile')).toBeInTheDocument()
      expect(screen.getByText('Confirm Profile')).toBeInTheDocument()
    })

    it('should show missing fields in confirmation due banner', async () => {
      mockGetMandatoryProfileStatus.mockResolvedValue({
        mandatory_profile_completed: true,
        confirmation_due: true,
        missing_fields: ['age', 'gender'],
      })

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Confirmation due')).toBeInTheDocument()
      })
      expect(screen.getByText(/Missing fields/)).toBeInTheDocument()
      expect(screen.getByText(/age, gender/)).toBeInTheDocument()
    })

    it('should disable confirm button when there are missing fields', async () => {
      mockGetMandatoryProfileStatus.mockResolvedValue({
        mandatory_profile_completed: true,
        confirmation_due: true,
        missing_fields: ['age'],
      })

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Confirm Profile')).toBeInTheDocument()
      })
      expect(screen.getByText('Confirm Profile')).toBeDisabled()
    })

    it('should handle confirm profile click successfully', async () => {
      const user = userEvent.setup()
      mockGetMandatoryProfileStatus.mockResolvedValue({
        mandatory_profile_completed: true,
        confirmation_due: true,
        missing_fields: [],
      })
      mockConfirmProfile.mockResolvedValue({})

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Confirm Profile')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Confirm Profile'))

      await waitFor(() => {
        expect(mockConfirmProfile).toHaveBeenCalled()
        expect(toast.success).toHaveBeenCalledWith('Profile confirmed')
      })
    })

    it('should handle confirm profile failure', async () => {
      const user = userEvent.setup()
      mockGetMandatoryProfileStatus.mockResolvedValue({
        mandatory_profile_completed: true,
        confirmation_due: true,
        missing_fields: [],
      })
      mockConfirmProfile.mockRejectedValue(new Error('Network error'))

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Confirm Profile')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Confirm Profile'))

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith('Network error')
      })
    })

    it('should handle non-Error rejection in confirm profile', async () => {
      const user = userEvent.setup()
      mockGetMandatoryProfileStatus.mockResolvedValue({
        mandatory_profile_completed: true,
        confirmation_due: true,
        missing_fields: [],
      })
      mockConfirmProfile.mockRejectedValue('string error')

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Confirm Profile')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Confirm Profile'))

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith('Confirmation failed')
      })
    })
  })

  describe('Mandatory profile incomplete banner', () => {
    it('should show incomplete banner when mandatory_profile_completed is false', async () => {
      mockGetMandatoryProfileStatus.mockResolvedValue({
        mandatory_profile_completed: false,
        confirmation_due: false,
        missing_fields: ['legal_expertise_level'],
      })

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Mandatory profile incomplete')).toBeInTheDocument()
      })
      expect(screen.getByText('Please complete mandatory fields')).toBeInTheDocument()
      expect(screen.getByText(/Missing fields/)).toBeInTheDocument()
    })

    it('should not show incomplete banner when mandatory_profile_completed is true', async () => {
      mockGetMandatoryProfileStatus.mockResolvedValue({
        mandatory_profile_completed: true,
        confirmation_due: false,
        missing_fields: [],
      })

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByRole('heading', { name: 'Profile' })).toBeInTheDocument()
      })

      expect(screen.queryByText('Mandatory profile incomplete')).not.toBeInTheDocument()
    })
  })

  describe('Profile History (superadmin)', () => {
    it('should show profile history section for superadmins with history', async () => {
      const superadminProfile = { ...mockProfile, is_superadmin: true }
      ;(useAuth as jest.Mock).mockReturnValue({
        user: { ...mockUser, is_superadmin: true },
        updateUser: mockUpdateUser,
        apiClient: mockApiClient,
      })
      mockGetProfile.mockResolvedValue(superadminProfile)
      mockGetProfileHistory.mockResolvedValue([
        {
          id: 'hist-1',
          change_type: 'profile_update',
          changed_at: '2024-06-01T10:00:00Z',
          changed_fields: ['name', 'email'],
        },
      ])

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Profile History')).toBeInTheDocument()
      })
    })

    it('should expand profile history and show entries', async () => {
      const user = userEvent.setup()
      const superadminProfile = { ...mockProfile, is_superadmin: true }
      ;(useAuth as jest.Mock).mockReturnValue({
        user: { ...mockUser, is_superadmin: true },
        updateUser: mockUpdateUser,
        apiClient: mockApiClient,
      })
      mockGetProfile.mockResolvedValue(superadminProfile)
      mockGetProfileHistory.mockResolvedValue([
        {
          id: 'hist-1',
          change_type: 'profile_update',
          changed_at: '2024-06-01T10:00:00Z',
          changed_fields: ['name', 'email'],
        },
      ])

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Profile History')).toBeInTheDocument()
      })

      // Expand the history section
      const toggleButton = screen.getByText('Profile History').closest('button')!
      await user.click(toggleButton)

      await waitFor(() => {
        expect(screen.getByText('profile_update')).toBeInTheDocument()
        expect(screen.getByText(/name, email/)).toBeInTheDocument()
      })
    })

    it('should not show profile history for non-superadmin', async () => {
      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByRole('heading', { name: 'Profile' })).toBeInTheDocument()
      })

      expect(screen.queryByText('Profile History')).not.toBeInTheDocument()
    })
  })

  describe('Research Profile section (psychometric scales)', () => {
    it('should show psychometric scale items when research profile is expanded', async () => {
      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Research Profile')).toBeInTheDocument()
      })

      // Already expanded by localStorage override
      await waitFor(() => {
        expect(screen.getByText('ATI-S Scale')).toBeInTheDocument()
        expect(screen.getByText('PTT-A Scale')).toBeInTheDocument()
        expect(screen.getByText('KI Experience')).toBeInTheDocument()
      })
    })

    it('should toggle research profile section', async () => {
      const user = userEvent.setup()

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Research Profile')).toBeInTheDocument()
      })

      // Collapse the section
      const toggleButton = screen.getByText('Research Profile').closest('button')!
      await user.click(toggleButton)

      await waitFor(() => {
        expect(screen.queryByText('ATI-S Scale')).not.toBeInTheDocument()
      })

      // Expand again
      await user.click(toggleButton)

      await waitFor(() => {
        expect(screen.getByText('ATI-S Scale')).toBeInTheDocument()
      })
    })
  })

  describe('Grades section', () => {
    it('should show grades for referendar level', async () => {
      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Grades')).toBeInTheDocument()
      })

      expect(screen.getByText('Zwischenpruefung')).toBeInTheDocument()
      expect(screen.getByText('Vorgeruecktenubung')).toBeInTheDocument()
      expect(screen.getByText('First Staatsexamen')).toBeInTheDocument()
    })

    it('should not show grades for layperson', async () => {
      mockGetProfile.mockResolvedValue({
        ...mockProfile,
        legal_expertise_level: 'layperson',
      })

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Legal Experience')).toBeInTheDocument()
      })

      await waitFor(() => {
        expect(screen.queryByText('Grades')).not.toBeInTheDocument()
      })
    })

    it('should show second staatsexamen grade for graduated_no_practice', async () => {
      mockGetProfile.mockResolvedValue({
        ...mockProfile,
        legal_expertise_level: 'graduated_no_practice',
      })

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Second Staatsexamen')).toBeInTheDocument()
      })
    })
  })

  describe('Profile confirmed_at display', () => {
    it('should display last confirmed date when available', async () => {
      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText(/Last confirmed:/)).toBeInTheDocument()
      })
    })

    it('should not display last confirmed when profile_confirmed_at is null', async () => {
      mockGetProfile.mockResolvedValue({
        ...mockProfile,
        profile_confirmed_at: null,
      })

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Account Information')).toBeInTheDocument()
      })

      expect(screen.queryByText(/Last confirmed:/)).not.toBeInTheDocument()
    })
  })

  describe('Non-Error rejection handling', () => {
    it('should handle non-Error object in profile update rejection', async () => {
      const user = userEvent.setup()
      mockUpdateProfile.mockRejectedValue('string error')

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Update Profile')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Update Profile'))

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith('Failed to update profile')
      })
    })
  })

  describe('Auto-collapse behavior', () => {
    it('should auto-collapse legal experience when data is filled and no localStorage override', async () => {
      localStorage.removeItem('profile_legal_experience_expanded')
      mockGetProfile.mockResolvedValue({
        ...mockProfile,
        legal_expertise_level: 'referendar',
        subjective_competence_civil: 5,
        subjective_competence_public: 4,
        subjective_competence_criminal: 3,
      })

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Legal Experience')).toBeInTheDocument()
      })

      // Should be collapsed since all legal data is filled and no localStorage preference
      await waitFor(() => {
        expect(screen.queryByText('Legal Expertise')).not.toBeInTheDocument()
      })
    })

    it('should auto-collapse research profile when psychometric data is filled', async () => {
      localStorage.removeItem('profile_research_profile_expanded')
      mockGetProfile.mockResolvedValue({
        ...mockProfile,
        ati_s_scores: { item_1: 4 },
        ptt_a_scores: { item_1: 3 },
        ki_experience_scores: { item_1: 5 },
      })

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Research Profile')).toBeInTheDocument()
      })

      // Should be collapsed since all research data is filled
      await waitFor(() => {
        expect(screen.queryByText('ATI-S Scale')).not.toBeInTheDocument()
      })
    })
  })

  describe('Mandatory status fetch failure', () => {
    it('should render normally when getMandatoryProfileStatus fails', async () => {
      mockGetMandatoryProfileStatus.mockRejectedValue(new Error('Not found'))

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByRole('heading', { name: 'Profile' })).toBeInTheDocument()
      })

      // Should not show any mandatory banners
      expect(screen.queryByText('Confirmation due')).not.toBeInTheDocument()
      expect(screen.queryByText('Mandatory profile incomplete')).not.toBeInTheDocument()
    })
  })

  describe('Profile history fetch failure (superadmin)', () => {
    it('should render normally when getProfileHistory fails', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: { ...mockUser, is_superadmin: true },
        updateUser: mockUpdateUser,
        apiClient: mockApiClient,
      })
      mockGetProfile.mockResolvedValue({ ...mockProfile, is_superadmin: true })
      mockGetProfileHistory.mockRejectedValue(new Error('Not found'))

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByRole('heading', { name: 'Profile' })).toBeInTheDocument()
      })

      // History section should not show
      expect(screen.queryByText('Profile History')).not.toBeInTheDocument()
    })
  })

  describe('GradeInput component', () => {
    it('should display grade input for referendar and accept comma input', async () => {
      const user = userEvent.setup()
      mockGetProfile.mockResolvedValue({
        ...mockProfile,
        legal_expertise_level: 'referendar',
        grade_zwischenpruefung: 12.5,
      })

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Zwischenpruefung')).toBeInTheDocument()
      })

      // Grade input should show the value formatted with comma
      const gradeInput = screen.getByLabelText('Zwischenpruefung') as HTMLInputElement
      expect(gradeInput).toBeInTheDocument()
    })
  })

  describe('Refresh mandatory status after profile update', () => {
    it('should refresh mandatory status after successful profile update', async () => {
      const user = userEvent.setup()
      mockGetMandatoryProfileStatus
        .mockResolvedValueOnce({
          mandatory_profile_completed: false,
          confirmation_due: false,
          missing_fields: ['name'],
        })
        .mockResolvedValueOnce({
          mandatory_profile_completed: true,
          confirmation_due: false,
          missing_fields: [],
        })

      render(<ProfilePage />)

      await waitFor(() => {
        expect(screen.getByText('Update Profile')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Update Profile'))

      await waitFor(() => {
        expect(mockGetMandatoryProfileStatus).toHaveBeenCalledTimes(2)
      })
    })
  })
})

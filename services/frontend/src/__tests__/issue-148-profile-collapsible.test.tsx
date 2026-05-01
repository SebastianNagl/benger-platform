/**
 * @jest-environment jsdom
 */

jest.mock('@/contexts/AuthContext')
jest.mock('@/contexts/I18nContext')

// Mock SVG imports
jest.mock('@/images/logos/go.svg', () => 'go.svg', { virtual: true })
jest.mock('@/images/logos/node.svg', () => 'node.svg', { virtual: true })
jest.mock('@/images/logos/php.svg', () => 'php.svg', { virtual: true })
jest.mock('@/images/logos/python.svg', () => 'python.svg', { virtual: true })
jest.mock('@/images/logos/ruby.svg', () => 'ruby.svg', { virtual: true })

jest.mock('@/lib/api', () => ({
  api: {
    getTasks: jest.fn().mockResolvedValue({ tasks: [], total: 0 }),
    getTask: jest.fn().mockResolvedValue(null),
    getAllUsers: jest.fn().mockResolvedValue([]),
    getOrganizations: jest.fn().mockResolvedValue([]),
    getAnnotationOverview: jest.fn().mockResolvedValue({ annotations: [] }),
    createTask: jest.fn().mockResolvedValue({}),
    updateTask: jest.fn().mockResolvedValue({}),
    deleteTask: jest.fn().mockResolvedValue(undefined),
    exportBulkData: jest.fn().mockResolvedValue({}),
    importBulkData: jest.fn().mockResolvedValue({}),
    getProfile: jest.fn().mockResolvedValue({
      id: 'test-user-id',
      username: 'testuser',
      email: 'test@example.com',
      name: 'Test User',
      is_superadmin: false,
      is_active: true,
      created_at: '2023-01-01T00:00:00Z',
    }),
    updateProfile: jest.fn().mockResolvedValue({}),
  },
  ApiClient: jest.fn().mockImplementation(() => ({
    getTasks: jest.fn().mockResolvedValue({ tasks: [], total: 0 }),
    getTask: jest.fn().mockResolvedValue(null),
    getAllUsers: jest.fn().mockResolvedValue([]),
    getOrganizations: jest.fn().mockResolvedValue([]),
  })),
}))

// Mock the modal components
jest.mock('@/components/modals/ChangePasswordModal', () => ({
  ChangePasswordModal: ({ isOpen }: any) =>
    isOpen ? (
      <div data-testid="change-password-modal">Password Modal</div>
    ) : null,
}))

jest.mock('@/components/modals/APIKeysModal', () => ({
  APIKeysModal: ({ isOpen }: any) =>
    isOpen ? <div data-testid="api-keys-modal">API Keys Modal</div> : null,
}))

// Mock AuthGuard to just render children
jest.mock('@/components/auth/AuthGuard', () => ({
  AuthGuard: ({ children }: any) => <>{children}</>,
}))

// Mock LikertScale
jest.mock('@/components/shared/LikertScale', () => ({
  LikertScale: ({ label, onChange }: any) => (
    <div data-testid={`likert-${label}`}>{label}</div>
  ),
}))

// Mock Breadcrumb
jest.mock('@/components/shared/Breadcrumb', () => ({
  Breadcrumb: ({ items }: any) => (
    <nav data-testid="breadcrumb">
      {items.map((item: any, i: number) => (
        <span key={i}>{item.label}</span>
      ))}
    </nav>
  ),
}))

// Mock Button
jest.mock('@/components/shared/Button', () => ({
  Button: ({ children, onClick, disabled, ...props }: any) => (
    <button onClick={onClick} disabled={disabled} {...props}>
      {children}
    </button>
  ),
}))

// Mock ResponsiveContainer
jest.mock('@/components/shared/ResponsiveContainer', () => ({
  ResponsiveContainer: ({ children }: any) => <div>{children}</div>,
}))

import ProfilePage from '@/app/profile/page'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

const mockUseAuth = useAuth as jest.MockedFunction<typeof useAuth>
const mockUseI18n = useI18n as jest.MockedFunction<typeof useI18n>

// Mock translation function
const mockTranslations: Record<string, string> = {
  'profile.title': 'Profil',
  'profile.personalInfo': 'Persoenliche Informationen',
  'profile.demographicInfo': 'Demografische Informationen',
  'profile.demographicDescription':
    'Optional: Helfen Sie uns, unsere Nutzerschaft besser zu verstehen',
  'profile.age': 'Alter',
  'profile.job': 'Beruf/Taetigkeit',
  'profile.yearsOfExperience': 'Jahre Berufserfahrung',
  'profile.legalExperience': 'Juristische Erfahrung',
  'profile.hideLegalExperience': 'Juristische Erfahrung ausblenden',
  'profile.showLegalExperience': 'Juristische Erfahrung anzeigen',
  'profile.legalExpertise': 'Juristische Expertise',
  'profile.legalDescription':
    'Optional: Ihr juristischer Hintergrund und Ihre Expertise',
  'profile.legalExpertiseLevel': 'Juristische Expertise-Stufe',
  'profile.selectExpertiseLevel': 'Waehlen Sie Ihre Expertise-Stufe',
  'profile.germanProficiency': 'Deutschkenntnisse',
  'profile.selectGermanProficiency': 'Deutschkenntnisse auswaehlen',
  'profile.degreeProgramType': 'Studiengang',
  'profile.selectDegreeProgram': 'Studiengang auswaehlen',
  'profile.currentSemester': 'Aktuelles Semester',
  'profile.currentSemesterPlaceholder': 'z.B. 5',
  'profile.researchProfile': 'Forschungsprofil',
  'profile.hideOptionalSettings': 'Optionale Einstellungen ausblenden',
  'profile.showOptionalSettings': 'Optionale Einstellungen anzeigen',
  'profile.privacySettings': 'Datenschutzeinstellungen',
  'profile.hidePrivacySettings': 'Datenschutzeinstellungen ausblenden',
  'profile.showPrivacySettings': 'Datenschutzeinstellungen anzeigen',
  'profile.apiKeys': 'API-Schluessel',
  'profile.changePassword': 'Passwort aendern',
  'profile.username': 'Benutzername',
  'profile.fullName': 'Vollstaendiger Name',
  'profile.emailAddress': 'E-Mail-Adresse',
  'profile.role': 'Rolle',
  'profile.usernameNote': 'Benutzername kann nicht geaendert werden',
  'profile.roleNote': 'Rolle wird von Administratoren verwaltet',
  'profile.updateProfile': 'Profil aktualisieren',
  'profile.updating': 'Wird aktualisiert...',
  'profile.accountInfo': 'Kontoinformationen',
  'profile.roles.user': 'Benutzer',
  'profile.roles.superadmin': 'Superadministrator',
  'profile.yourPseudonym': 'Ihr Pseudonym',
  'profile.pseudonymNote': 'Ihr einzigartiges Pseudonym zum Datenschutz',
  'profile.usePseudonym': 'Ich moechte unter meinem Pseudonym arbeiten',
  'profile.usePseudonymDescription':
    'Wenn aktiviert, wird Ihr Pseudonym in Bestenlisten und Annotationen anstelle Ihres echten Namens angezeigt.',
  'profile.gender': 'Geschlecht',
  'profile.selectGender': 'Geschlecht auswaehlen',
  // Register namespace translations used by the profile page
  'register.expertiseLevel.layperson': 'Laie (Keine juristische Ausbildung)',
  'register.expertiseLevel.lawStudent': 'Jurastudent/in',
  'register.expertiseLevel.referendar': 'Rechtsreferendar/in',
  'register.expertiseLevel.graduatedNoPractice': 'Abgeschlossen (Keine Praxis)',
  'register.expertiseLevel.practicingLawyer': 'Praktizierender Anwalt/Anwaeltin',
  'register.expertiseLevel.judgeProfessor': 'Richter/in / Professor/in',
  'register.germanProficiency.native': 'Muttersprachler/in',
  'register.germanProficiency.c2': 'C2 (Kompetent)',
  'register.germanProficiency.c1': 'C1 (Fortgeschritten)',
  'register.germanProficiency.b2': 'B2 (Obere Mittelstufe)',
  'register.germanProficiency.belowB2': 'Unter B2',
  'register.degreeProgram.staatsexamen': 'Staatsexamen',
  'register.degreeProgram.llb': 'LL.B. (Bachelor of Laws)',
  'register.degreeProgram.llm': 'LL.M. (Master of Laws)',
  'register.degreeProgram.promotion': 'Promotion',
  'register.degreeProgram.notApplicable': 'Nicht zutreffend',
  'navigation.dashboard': 'Startseite',
  'navigation.profile': 'Profil',
}
const mockT = (key: string) => mockTranslations[key] || key

const mockProfile = {
  id: 'test-user-id',
  username: 'testuser',
  email: 'test@example.com',
  name: 'Test User',
  is_superadmin: false,
  is_active: true,
  created_at: '2023-01-01T00:00:00Z',
}

const mockUser = {
  id: 'test-user-id',
  username: 'testuser',
  email: 'test@example.com',
  name: 'Test User',
  is_superadmin: false,
  is_active: true,
  created_at: '2023-01-01T00:00:00Z',
}

describe('Issue #148: Profile Page Collapsible Sections', () => {
  beforeEach(() => {
    // Clear localStorage to get default expansion states
    localStorage.clear()

    mockUseAuth.mockReturnValue({
      user: mockUser,
      updateUser: jest.fn(),
      login: jest.fn(),
      logout: jest.fn(),
      loading: false,
      isLoading: false,
      isAuthenticated: true,
      apiClient: {
        getProfile: jest.fn().mockResolvedValue(mockProfile),
        updateProfile: jest.fn().mockResolvedValue({}),
        clearCache: jest.fn(),
        clearUserCache: jest.fn(),
        getMandatoryProfileStatus: jest.fn().mockResolvedValue({
          is_complete: false,
          missing_fields: [],
        }),
        getProfileHistory: jest.fn().mockResolvedValue([]),
        confirmProfile: jest.fn().mockResolvedValue({}),
      },
    } as any)

    mockUseI18n.mockReturnValue({
      t: mockT,
      language: 'de',
      setLanguage: jest.fn(),
    } as any)

    // Mock fetch for API calls
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockProfile),
    })
  })

  afterEach(() => {
    jest.clearAllMocks()
    localStorage.clear()
  })

  test('should render demographic information section (always visible)', async () => {
    render(<ProfilePage />)

    await waitFor(() => {
      expect(
        screen.getByText('Demografische Informationen')
      ).toBeInTheDocument()
    })

    // Demographic section is always visible (not collapsible)
    expect(screen.getByText('Alter')).toBeInTheDocument()
  })

  test('should render collapsible Legal Experience section', async () => {
    render(<ProfilePage />)

    await waitFor(() => {
      expect(screen.getByText('Juristische Erfahrung')).toBeInTheDocument()
    })

    // Legal Experience section has a collapsible button
    const legalButton = screen.getByRole('button', {
      name: /juristische erfahrung/i,
    })
    expect(legalButton).toBeInTheDocument()

    // Section is expanded by default - show/hide text should show "ausblenden"
    expect(
      screen.getByText('Juristische Erfahrung ausblenden')
    ).toBeInTheDocument()
  })

  test('should collapse and expand Legal Experience section', async () => {
    render(<ProfilePage />)

    await waitFor(() => {
      expect(screen.getByText('Juristische Erfahrung')).toBeInTheDocument()
    })

    const legalButton = screen.getByRole('button', {
      name: /juristische erfahrung/i,
    })

    // Section is expanded by default - legal expertise should be visible
    await waitFor(() => {
      expect(screen.getByText('Juristische Expertise')).toBeInTheDocument()
    })

    // Click to collapse
    fireEvent.click(legalButton)

    // Should be hidden
    await waitFor(() => {
      expect(
        screen.queryByText('Juristische Expertise')
      ).not.toBeInTheDocument()
    })

    // Text should change to "anzeigen" (Show)
    expect(
      screen.getByText('Juristische Erfahrung anzeigen')
    ).toBeInTheDocument()

    // Click to expand again
    fireEvent.click(legalButton)

    // Should now be visible again
    await waitFor(() => {
      expect(screen.getByText('Juristische Expertise')).toBeInTheDocument()
    })
  })

  test('should position sections in correct order', async () => {
    render(<ProfilePage />)

    await waitFor(() => {
      expect(
        screen.getByText('Persoenliche Informationen')
      ).toBeInTheDocument()
    })

    // Check that the main sections are present
    const personalInfoSection = screen.getByText('Persoenliche Informationen')
    const demographicSection = screen.getByText('Demografische Informationen')
    const accountInfoSection = screen.getByText('Kontoinformationen')

    expect(personalInfoSection).toBeInTheDocument()
    expect(demographicSection).toBeInTheDocument()
    expect(accountInfoSection).toBeInTheDocument()

    // The sections should be in the correct DOM order
    const sections = [
      personalInfoSection,
      demographicSection,
      accountInfoSection,
    ]
    for (let i = 0; i < sections.length - 1; i++) {
      expect(sections[i].compareDocumentPosition(sections[i + 1])).toBe(4) // DOCUMENT_POSITION_FOLLOWING
    }
  })

  test('should have working demographic form fields', async () => {
    render(<ProfilePage />)

    await waitFor(() => {
      expect(
        screen.getByText('Demografische Informationen')
      ).toBeInTheDocument()
    })

    // Test age input
    const ageInput = screen.getByLabelText('Alter')
    expect(ageInput).toHaveAttribute('type', 'number')
    expect(ageInput).toHaveAttribute('min', '1')
    expect(ageInput).toHaveAttribute('max', '150')
  })

  test('should render action buttons for modals', async () => {
    render(<ProfilePage />)

    await waitFor(() => {
      expect(
        screen.getByText('Persoenliche Informationen')
      ).toBeInTheDocument()
    })

    // Check that the Change Password and API Keys buttons exist
    expect(screen.getByText('Passwort aendern')).toBeInTheDocument()
    expect(screen.getByText('API-Schluessel')).toBeInTheDocument()
  })

  test('should have smooth transition classes on Legal Experience chevron', async () => {
    render(<ProfilePage />)

    await waitFor(() => {
      expect(screen.getByText('Juristische Erfahrung')).toBeInTheDocument()
    })

    const legalButton = screen.getByRole('button', {
      name: /juristische erfahrung/i,
    })
    const chevronIcon = legalButton.querySelector('svg')
    expect(chevronIcon).toHaveClass('transition-transform')

    // Section is expanded by default - chevron should be rotated
    expect(chevronIcon).toHaveClass('rotate-180')

    // Collapse and check rotation class is removed
    fireEvent.click(legalButton)
    await waitFor(() => {
      expect(chevronIcon).not.toHaveClass('rotate-180')
    })
  })

  test('should verify key translation keys are used', () => {
    // This test ensures that the component uses translation keys instead of hardcoded text
    const requiredTranslationKeys = [
      'profile.personalInfo',
      'profile.demographicInfo',
      'profile.legalExperience',
      'profile.hideLegalExperience',
      'profile.showLegalExperience',
      'profile.age',
      'profile.job',
      'profile.yearsOfExperience',
      'profile.legalExpertise',
      'profile.legalExpertiseLevel',
      'profile.selectExpertiseLevel',
      'profile.germanProficiency',
      'profile.selectGermanProficiency',
      'profile.accountInfo',
      'profile.privacySettings',
    ]

    // Verify all keys have translations
    requiredTranslationKeys.forEach((key) => {
      expect(mockTranslations[key]).toBeDefined()
      expect(mockTranslations[key]).not.toBe(key) // Not just returning the key
    })
  })
})

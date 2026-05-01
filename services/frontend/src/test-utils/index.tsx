/**
 * Centralized test utilities for BenGER frontend tests
 * Provides common mocks and helpers to ensure consistent test setup
 */

import { ApiClient } from '@/lib/api'
import { RenderOptions, render as rtlRender } from '@testing-library/react'
import React from 'react'

// Create mock contexts
const AuthContext = React.createContext<any>(null)
const I18nContext = React.createContext<any>(null)

// Mock Next.js navigation
jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: jest.fn(),
    back: jest.fn(),
    forward: jest.fn(),
    refresh: jest.fn(),
    replace: jest.fn(),
    prefetch: jest.fn(),
    pathname: '/',
  }),
  usePathname: () => '/',
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({}),
}))

// Mock Next.js dynamic
jest.mock('next/dynamic', () => ({
  __esModule: true,
  default: (fn: () => Promise<any>) => {
    const Component = fn as any
    Component.preload = () => {}
    return Component
  },
}))

// Create comprehensive mock API client
export const createMockApiClient = () => {
  const mockApiClient = new ApiClient()

  // Mock all common API methods to prevent "is not a function" errors
  const mockMethods = [
    'getAllUsers',
    'getOrganizationMembers',
    'listInvitations',
    'getOrganizationInvitations',
    'createOrganization',
    'updateOrganization',
    'addUserToOrganization',
    'updateMemberRole',
    'removeMember',
    'createInvitation',
    'cancelInvitation',
    'getUser',
    'login',
    'logout',
    'getOrganizations',
    'getProjects',
    'getProject',
    'getEvaluations',
    'generateResponses',
    'getModels',
    'getPrompts',
    'updateUserSuperadminStatus',
    'deleteUser',
    'getCurrentUser',
    'getAnnotationOverview',
    'getAnnotationProjectStatistics',
    'createAnnotation',
    'updateAnnotation',
    'getAnnotations',
    'exportBulkData',
    'importBulkData',
    // Prompt methods removed in Issue #759
    'refresh',
  ]

  // Set up default return values for each method
  const defaultReturns: Record<string, any> = {
    getAllUsers: [],
    getOrganizationMembers: [],
    listInvitations: [],
    getOrganizationInvitations: [],
    getOrganizations: [],
    getProjects: [],
    getProject: null,
    getEvaluations: [],
    getModels: [],
    getPrompts: [],
    getCurrentUser: null,
    getAnnotationOverview: { annotations: [] },
    getAnnotationProjectStatistics: {},
    getAnnotations: [],
  }

  // Apply mocks to all methods
  mockMethods.forEach((method) => {
    const returnValue =
      defaultReturns[method] !== undefined ? defaultReturns[method] : {}
    ;(mockApiClient as any)[method] = jest.fn().mockResolvedValue(returnValue)
  })

  return mockApiClient
}

// Default mock user
export const mockUser = {
  id: 'test-user-id',
  username: 'testuser',
  email: 'test@example.com',
  name: 'Test User',
  is_superadmin: false,
  is_active: true,
  created_at: '2024-01-01',
  updated_at: '2024-01-01',
}

// Default mock organization
export const mockOrganization = {
  id: 'test-org-id',
  name: 'Test Organization',
  slug: 'test-org',
  description: 'Test Organization Description',
  created_at: '2024-01-01',
  updated_at: '2024-01-01',
}

// Create mock AuthContext value
export const createMockAuthContext = (overrides = {}) => ({
  user: mockUser,
  login: jest.fn(),
  signup: jest.fn(),
  logout: jest.fn(),
  updateUser: jest.fn(),
  isLoading: false,
  refreshAuth: jest.fn(),
  apiClient: createMockApiClient(),
  organizations: [mockOrganization],
  currentOrganization: mockOrganization,
  setCurrentOrganization: jest.fn(),
  refreshOrganizations: jest.fn(),
  ...overrides,
})

// Comprehensive translation mock
const DEFAULT_TRANSLATIONS: Record<string, string> = {
  // Auth translations
  'auth.signIn': 'Sign In',
  'auth.signUp': 'Sign Up',
  'auth.signOut': 'Sign Out',
  'auth.profileSettings': 'Profile Settings',
  'auth.notificationSettings': 'Notification Settings',
  'auth.userManagement': 'User Management',

  // Navigation
  'navigation.organizations': 'Organizations',

  // Admin
  'admin.usersOrganizations': 'Users & Organizations',
  'admin.defaultConfiguration': 'Default Configuration',
  'admin.featureFlags': 'Feature Flags',

  // Common
  'common.search': 'Search',
  'common.loading': 'Loading...',
  'common.save': 'Save',
  'common.cancel': 'Cancel',
  'common.delete': 'Delete',
  'common.edit': 'Edit',
  'common.create': 'Create',
  'common.update': 'Update',
  'common.close': 'Close',

  // Projects
  'projects.searchPlaceholder': 'Search projects...',
  'projects.noProjects': 'No projects found',
  'projects.loading': 'Loading projects...',

  // Other
  'annotations.loading': 'Loading annotations...',
  'annotations.noAnnotations': 'No annotations found',
  'quality.title': 'Quality Control',
  'quality.loading': 'Loading quality metrics...',
  'analytics.title': 'Analytics',
  'analytics.loading': 'Loading analytics...',
}

// Create mock I18nContext value with comprehensive translations
export const createMockI18nContext = (overrides = {}) => ({
  t: (key: string) => DEFAULT_TRANSLATIONS[key] || key,
  changeLanguage: jest.fn(),
  currentLanguage: 'en',
  languages: ['en', 'de'],
  ...overrides,
})

// Mock useAuth hook
export const mockUseAuth = (overrides = {}) => {
  const mockAuthContext = createMockAuthContext(overrides)
  ;(require('@/contexts/AuthContext').useAuth as jest.Mock).mockReturnValue(
    mockAuthContext
  )
  return mockAuthContext
}

// Mock useI18n hook
export const mockUseI18n = (overrides = {}) => {
  const mockI18nContext = createMockI18nContext(overrides)
  ;(require('@/contexts/I18nContext').useI18n as jest.Mock).mockReturnValue(
    mockI18nContext
  )
  return mockI18nContext
}

// Create mock provider contexts

export const createMockFeatureFlagContext = (overrides = {}) => ({
  flags: {},
  isLoading: false,
  error: null,
  isEnabled: jest.fn().mockReturnValue(true),
  refreshFlags: jest.fn(),
  checkFlag: jest.fn().mockResolvedValue(true),
  lastUpdate: Date.now(),
  ...overrides,
})

export const createMockProgressContext = (overrides = {}) => ({
  startProgress: jest.fn(),
  updateProgress: jest.fn(),
  completeProgress: jest.fn(),
  errorProgress: jest.fn(),
  resetProgress: jest.fn(),
  progress: null,
  ...overrides,
})

export const createMockToastContext = (overrides = {}) => ({
  addToast: jest.fn(),
  removeToast: jest.fn(),
  toasts: [],
  ...overrides,
})

// Enhanced render function with all providers
interface EnhancedRenderOptions extends Omit<RenderOptions, 'wrapper'> {
  authContextValue?: ReturnType<typeof createMockAuthContext>
  i18nContextValue?: ReturnType<typeof createMockI18nContext>
  featureFlagContextValue?: ReturnType<typeof createMockFeatureFlagContext>
  progressContextValue?: ReturnType<typeof createMockProgressContext>
  toastContextValue?: ReturnType<typeof createMockToastContext>
  includeAllProviders?: boolean
}

export function renderWithProviders(
  ui: React.ReactElement,
  {
    authContextValue = createMockAuthContext(),
    i18nContextValue = createMockI18nContext(),
    ...renderOptions
  }: Omit<EnhancedRenderOptions, 'includeAllProviders'> = {}
) {
  function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <AuthContext.Provider value={authContextValue}>
        <I18nContext.Provider value={i18nContextValue}>
          {children}
        </I18nContext.Provider>
      </AuthContext.Provider>
    )
  }

  return rtlRender(ui, { wrapper: Wrapper, ...renderOptions })
}

// Comprehensive render function with ALL providers
export function renderWithAllProviders(
  ui: React.ReactElement,
  {
    authContextValue = createMockAuthContext(),
    i18nContextValue = createMockI18nContext(),
    featureFlagContextValue = createMockFeatureFlagContext(),
    progressContextValue = createMockProgressContext(),
    toastContextValue = createMockToastContext(),
    ...renderOptions
  }: EnhancedRenderOptions = {}
) {
  // Mock provider components
  const MockSectionProvider = ({ children }: { children: React.ReactNode }) => (
    <div data-testid="section-provider">{children}</div>
  )

  const MockFeatureFlagProvider = ({
    children,
  }: {
    children: React.ReactNode
  }) => {
    // Create a mock context that provides the FeatureFlagContext
    const FeatureFlagContext = React.createContext(featureFlagContextValue)
    return (
      <FeatureFlagContext.Provider value={featureFlagContextValue}>
        <div data-testid="feature-flag-provider">{children}</div>
      </FeatureFlagContext.Provider>
    )
  }

  const MockProgressProvider = ({
    children,
  }: {
    children: React.ReactNode
  }) => <div data-testid="progress-provider">{children}</div>

  const MockToastProvider = ({ children }: { children: React.ReactNode }) => (
    <div data-testid="toast-provider">{children}</div>
  )

  function AllProvidersWrapper({ children }: { children: React.ReactNode }) {
    return (
      <AuthContext.Provider value={authContextValue}>
        <I18nContext.Provider value={i18nContextValue}>
          <MockToastProvider>
            <MockProgressProvider>
              <MockFeatureFlagProvider>
                <MockSectionProvider>{children}</MockSectionProvider>
              </MockFeatureFlagProvider>
            </MockProgressProvider>
          </MockToastProvider>
        </I18nContext.Provider>
      </AuthContext.Provider>
    )
  }

  return rtlRender(ui, { wrapper: AllProvidersWrapper, ...renderOptions })
}

// Mock all context providers
jest.mock('@/contexts/AuthContext', () => ({
  ...jest.requireActual('@/contexts/AuthContext'),
  useAuth: jest.fn(),
  AuthProvider: ({ children }: { children: React.ReactNode }) => (
    <>{children}</>
  ),
}))

jest.mock('@/contexts/I18nContext', () => ({
  ...jest.requireActual('@/contexts/I18nContext'),
  useI18n: jest.fn(),
  I18nProvider: ({ children }: { children: React.ReactNode }) => (
    <>{children}</>
  ),
}))

// Mock additional context providers with inline values
jest.mock('@/contexts/FeatureFlagContext', () => ({
  useFeatureFlags: () => ({
    flags: {},
    isLoading: false,
    error: null,
    isEnabled: jest.fn().mockReturnValue(true),
    refreshFlags: jest.fn(),
    checkFlag: jest.fn().mockResolvedValue(true),
    lastUpdate: Date.now(),
  }),
  useFeatureFlag: () => true,
  FeatureFlagProvider: ({ children }: { children: React.ReactNode }) => (
    <>{children}</>
  ),
}))

jest.mock('@/contexts/ProgressContext', () => ({
  useProgress: () => ({
    startProgress: jest.fn(),
    updateProgress: jest.fn(),
    completeProgress: jest.fn(),
    errorProgress: jest.fn(),
    resetProgress: jest.fn(),
    progress: null,
  }),
  ProgressProvider: ({ children }: { children: React.ReactNode }) => (
    <>{children}</>
  ),
}))

// Toast mock lives in setupTests.ts — see mockStableToastSuccess/Error there.
// Tests that need to assert on toast calls should import mockToast from
// @/test-utils/setupTests.

// Mock hooks
jest.mock('@/hooks/useDialogs', () => ({
  useErrorAlert: () => jest.fn(),
  useDeleteConfirm: () => jest.fn().mockResolvedValue(true),
  useConfirm: () => jest.fn().mockResolvedValue(true),
}))

// Mock commonly problematic components
jest.mock('@/components/auth/AuthGuard', () => ({
  AuthGuard: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

// Note: Only mock components from @/components/shared if they're actually imported in the test

// Create comprehensive mock API for consistent testing
export const createMockApi = (overrides = {}) => ({
  getAllUsers: jest.fn().mockResolvedValue([]),
  getOrganizations: jest.fn().mockResolvedValue([]),
  getAnnotationOverview: jest.fn().mockResolvedValue({ annotations: [] }),
  getAnnotationProjectStatistics: jest.fn().mockResolvedValue({}),
  exportBulkData: jest.fn().mockResolvedValue({}),
  importBulkData: jest.fn().mockResolvedValue({}),
  getCurrentUser: jest.fn().mockResolvedValue({ id: 'test-user' }),
  // Prompt methods removed in Issue #759
  ...overrides,
})

// Mock the API module
jest.mock('@/lib/api', () => ({
  api: {},
  ApiClient: jest.fn(),
}))

// Utility function to setup global API mocks
export const setupApiMocks = (customApi = {}) => {
  const mockApi = createMockApi(customApi)
  return mockApi
}

// Helper to wait for async operations
export const waitForAsync = () =>
  new Promise((resolve) => setTimeout(resolve, 0))

// Test utilities for common scenarios
export const testUtils = {
  // Create a superadmin user for testing
  createSuperadminUser: (overrides = {}) => ({
    ...mockUser,
    is_superadmin: true,
    ...overrides,
  }),

  // Create test project data
  createTestProject: (overrides = {}) => ({
    id: 'test-project',
    name: 'Test Project',
    description: 'Test Description',
    created_at: '2024-01-01T00:00:00Z',
    ...overrides,
  }),
}

// Export everything from testing library for convenience
export * from '@testing-library/react'
export { default as userEvent } from '@testing-library/user-event'

// Export render function that tests should use
export { renderWithAllProviders as render }

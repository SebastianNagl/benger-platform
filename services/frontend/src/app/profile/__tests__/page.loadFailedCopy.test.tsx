/**
 * A profile that cannot be loaded shows a translated toast from the real
 * catalogs: profile.loadFailed existed in no catalog, so users saw the raw
 * key.
 *
 * @jest-environment jsdom
 */

import { mockToast } from '@/test-utils/setupTests'
import { render, waitFor } from '@testing-library/react'
import ProfilePage from '../page'

let mockLocale: 'en' | 'de' = 'en'
jest.mock('@/contexts/I18nContext', () =>
  require('@/test-utils/i18nMock').i18nMock(() => mockLocale),
)
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn(), replace: jest.fn() }),
}))
jest.mock('@/components/auth/AuthGuard', () => ({
  AuthGuard: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

const mockApiClient = {
  getProfile: jest.fn(),
  clearCache: jest.fn(),
  clearUserCache: jest.fn(),
  getMandatoryProfileStatus: jest.fn().mockResolvedValue({
    mandatory_profile_completed: true,
    confirmation_due: false,
    missing_fields: [],
  }),
  getProfileHistory: jest.fn().mockResolvedValue([]),
}
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 'u1', is_superadmin: false },
    updateUser: jest.fn(),
    apiClient: mockApiClient,
    organizations: [],
  }),
}))

describe('ProfilePage load failure', () => {
  beforeEach(() => {
    jest.spyOn(console, 'error').mockImplementation(() => {})
    mockApiClient.getProfile.mockRejectedValue(new Error('Network error'))
  })

  it.each([
    ['en', 'Failed to load profile'],
    ['de', 'Profil konnte nicht geladen werden'],
  ] as const)('shows the %s copy in the error toast', async (locale, text) => {
    mockLocale = locale
    render(<ProfilePage />)
    await waitFor(() =>
      expect(mockToast.addToast).toHaveBeenCalledWith(text, 'error'),
    )
  })
})

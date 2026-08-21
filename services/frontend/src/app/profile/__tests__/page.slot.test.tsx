/**
 * @jest-environment jsdom
 *
 * The profile page hosts the 'profile-settings-extended' slot for extended-only
 * self-saving settings sections (the "Interface" section with the exam
 * interface picker). Community edition: slot unregistered -> nothing renders.
 * The section renders after the legal-experience section but saves OUTSIDE
 * the profile-form save path (own save buttons, dedicated endpoints).
 */

import { render, screen, waitFor } from '@testing-library/react'

let mockSlots: Record<string, unknown> = {}

jest.mock('@/lib/extensions/slots', () => ({
  useSlot: (name: string) => mockSlots[name] ?? null,
  hasSlot: (name: string) => !!mockSlots[name],
  registerSlot: (name: string, component: unknown) => {
    mockSlots[name] = component
  },
}))

// Stable identities: a fresh apiClient per useAuth() call would re-fire the
// page's load effect forever and pin it on the loading spinner.
const mockGetProfile = jest.fn()
const mockAuthValue = {
  user: { id: 'user-1', username: 'tester' },
  updateUser: jest.fn(),
  apiClient: {
    clearCache: jest.fn(),
    getProfile: mockGetProfile,
  },
}

jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockAuthValue,
}))
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({ t: (key: string) => key, locale: 'en' }),
}))
jest.mock('@/components/auth/AuthGuard', () => ({
  AuthGuard: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))
jest.mock('@/components/shared/Breadcrumb', () => ({
  Breadcrumb: () => <div data-testid="breadcrumb" />,
}))
jest.mock('@/components/shared/Button', () => ({
  Button: ({ children }: any) => <button type="button">{children}</button>,
}))
jest.mock('@/components/shared/ResponsiveContainer', () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
}))
jest.mock('@/components/modals/ChangePasswordModal', () => ({
  ChangePasswordModal: () => null,
}))
jest.mock('@/components/modals/APIKeysModal', () => ({
  APIKeysModal: () => null,
}))
jest.mock('@/components/profile/ProfilePersonalSection', () => ({
  ProfilePersonalSection: () => <div data-testid="section-personal" />,
}))
jest.mock('@/components/profile/ProfileDemographicSection', () => ({
  ProfileDemographicSection: () => null,
}))
jest.mock('@/components/profile/ProfileLegalExperienceSection', () => ({
  ProfileLegalExperienceSection: () => null,
}))
jest.mock('@/components/profile/ProfileResearchSection', () => ({
  ProfileResearchSection: () => null,
}))
jest.mock('@/components/profile/ProfilePrivacySection', () => ({
  ProfilePrivacySection: () => null,
}))
jest.mock('@/components/profile/ProfileHistorySection', () => ({
  ProfileHistorySection: () => null,
}))
jest.mock('@/components/profile/ProfileAccountSection', () => ({
  ProfileAccountSection: () => null,
}))
jest.mock('@heroicons/react/24/outline', () =>
  new Proxy(
    {},
    {
      get: (_target, prop) => {
        if (prop === '__esModule') return true
        return (props: any) => <svg data-testid="icon" {...props} />
      },
    }
  )
)

import ProfilePage from '../page'

describe('profile page profile-settings-extended slot', () => {
  beforeEach(() => {
    mockSlots = {}
    mockGetProfile.mockReset()
    mockGetProfile.mockResolvedValue({
      id: 'user-1',
      username: 'tester',
      email: 't@example.com',
      name: 'Tester',
      is_superadmin: false,
      is_active: true,
    })
  })

  it('renders nothing extra while the slot is unregistered (community)', async () => {
    render(<ProfilePage />)
    await waitFor(() =>
      expect(screen.getByTestId('section-personal')).toBeInTheDocument()
    )
    expect(
      screen.queryByTestId('profile-settings-extended-content')
    ).not.toBeInTheDocument()
  })

  it('renders the registered extended settings section', async () => {
    mockSlots['profile-settings-extended'] = () => (
      <div data-testid="profile-settings-extended-content" />
    )

    render(<ProfilePage />)

    await waitFor(() =>
      expect(
        screen.getByTestId('profile-settings-extended-content')
      ).toBeInTheDocument()
    )
  })
})

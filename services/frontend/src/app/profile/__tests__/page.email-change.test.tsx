/**
 * Email change on the profile page: the new address waits for its mailed
 * confirmation link, and the page says so.
 *
 * Regression for the 2026-11-14 lockout: saving a new address used to
 * replace the login address without any mail, and the page only said
 * "Profile updated".
 *
 * @jest-environment jsdom
 */

import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { mockToast } from '@/test-utils/setupTests'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import ProfilePage from '../page'

jest.mock('next/navigation', () => ({
  useRouter: jest.fn(() => ({ push: jest.fn(), replace: jest.fn() })),
}))
jest.mock('@/contexts/AuthContext', () => ({ useAuth: jest.fn() }))
jest.mock('@/contexts/I18nContext', () => ({ useI18n: jest.fn() }))
jest.mock('@/components/auth/AuthGuard', () => ({
  AuthGuard: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))
jest.mock('@/components/shared/Breadcrumb', () => ({
  Breadcrumb: () => <div data-testid="breadcrumb" />,
}))
jest.mock('@/lib/extensions/slots', () => ({ useSlot: () => null }))
jest.mock('@/hooks/usePublicApiEnabled', () => ({
  usePublicApiEnabled: () => false,
}))
// Only the personal section matters here; the others have their own tests.
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
jest.mock('@/components/profile/ProfileAccountSection', () => ({
  ProfileAccountSection: () => null,
}))
jest.mock('@/components/profile/ProfileHistorySection', () => ({
  ProfileHistorySection: () => null,
}))
jest.mock('@/components/modals/ChangePasswordModal', () => ({
  ChangePasswordModal: () => null,
}))
jest.mock('@/components/modals/APIKeysModal', () => ({
  APIKeysModal: () => null,
}))

const t = (key: string, vars?: Record<string, string>) =>
  vars ? `${key} ${JSON.stringify(vars)}` : key

const baseProfile = {
  id: 'user-1',
  username: 'person',
  email: 'old@example.org',
  name: 'Person',
  is_superadmin: false,
  is_active: true,
  pending_email: null,
  pending_email_sent_at: null,
}

const apiClient = {
  getProfile: jest.fn(),
  updateProfile: jest.fn(),
  resendEmailChange: jest.fn(),
  cancelEmailChange: jest.fn(),
  getProfileHistory: jest.fn(),
  clearCache: jest.fn(),
  clearUserCache: jest.fn(),
}

function setup(profile: Record<string, unknown> = {}) {
  apiClient.getProfile.mockResolvedValue({ ...baseProfile, ...profile })
  ;(useAuth as jest.Mock).mockReturnValue({
    user: { id: 'user-1' },
    updateUser: jest.fn(),
    apiClient,
  })
  ;(useI18n as jest.Mock).mockReturnValue({ t, locale: 'de' })
}

async function renderLoaded() {
  render(<ProfilePage />)
  return screen.findByLabelText('profile.emailAddress')
}

describe('Profile page email change', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    localStorage.clear()
  })

  it('sends the new address with the UI language and says a link was mailed', async () => {
    setup()
    apiClient.updateProfile.mockResolvedValue({
      ...baseProfile,
      pending_email: 'new@example.org',
      pending_email_sent_at: '2026-11-14T22:00:00Z',
    })
    const input = await renderLoaded()

    fireEvent.change(input, { target: { value: 'New@Example.org' } })
    fireEvent.click(screen.getByText('profile.updateProfile'))

    await waitFor(() => {
      expect(apiClient.updateProfile).toHaveBeenCalledWith(
        expect.objectContaining({ email: 'New@Example.org', language: 'de' }),
      )
    })
    await waitFor(() => {
      expect(mockToast.addToast).toHaveBeenCalledWith(
        'profile.emailChangeRequested {"email":"new@example.org"}',
        'success',
      )
    })
    // The field shows the login address again; the notice names both.
    expect(screen.getByLabelText('profile.emailAddress')).toHaveValue(
      'old@example.org',
    )
    expect(
      screen.getByTestId('profile-email-change-pending'),
    ).toHaveTextContent(
      'profile.emailChangeSent {"email":"new@example.org","current":"old@example.org"}',
    )
  })

  it('warns when the confirmation mail could not be sent', async () => {
    setup()
    apiClient.updateProfile.mockResolvedValue({
      ...baseProfile,
      pending_email: 'new@example.org',
      pending_email_sent_at: null,
    })
    const input = await renderLoaded()

    fireEvent.change(input, { target: { value: 'new@example.org' } })
    fireEvent.click(screen.getByText('profile.updateProfile'))

    await waitFor(() => {
      expect(mockToast.addToast).toHaveBeenCalledWith(
        'profile.emailChangeNotSent {"email":"new@example.org"}',
        'warning',
      )
    })
    expect(
      screen.getByTestId('profile-email-change-pending'),
    ).toHaveTextContent('profile.emailChangeNotSent')
  })

  it('keeps the plain success message when the address is unchanged', async () => {
    setup()
    apiClient.updateProfile.mockResolvedValue(baseProfile)
    await renderLoaded()

    fireEvent.click(screen.getByText('profile.updateProfile'))

    await waitFor(() => {
      expect(mockToast.addToast).toHaveBeenCalledWith(
        'profile.updateSuccess',
        'success',
      )
    })
    expect(
      screen.queryByTestId('profile-email-change-pending'),
    ).not.toBeInTheDocument()
  })

  it('resends the link from the pending notice', async () => {
    setup({
      pending_email: 'new@example.org',
      pending_email_sent_at: '2026-11-14T22:00:00Z',
    })
    apiClient.resendEmailChange.mockResolvedValue({
      ...baseProfile,
      pending_email: 'new@example.org',
      pending_email_sent_at: '2026-11-14T22:10:00Z',
    })
    await renderLoaded()

    fireEvent.click(screen.getByTestId('profile-email-change-resend'))

    await waitFor(() => {
      expect(apiClient.resendEmailChange).toHaveBeenCalledWith('de')
    })
    await waitFor(() => {
      expect(mockToast.addToast).toHaveBeenCalledWith(
        'profile.emailChangeResent {"email":"new@example.org"}',
        'success',
      )
    })
    // The buttons sit inside the profile form but never submit it.
    expect(apiClient.updateProfile).not.toHaveBeenCalled()
  })

  it('shows the rate limit when a resend comes too soon', async () => {
    setup({
      pending_email: 'new@example.org',
      pending_email_sent_at: '2026-11-14T22:00:00Z',
    })
    apiClient.resendEmailChange.mockRejectedValue({
      response: {
        status: 429,
        data: { detail: { code: 'rate_limited', retry_after: 240 } },
      },
    })
    await renderLoaded()

    fireEvent.click(screen.getByTestId('profile-email-change-resend'))

    await waitFor(() => {
      expect(mockToast.addToast).toHaveBeenCalledWith(
        expect.not.stringContaining('profile.emailChangeActionFailed'),
        'error',
      )
    })
  })

  it('cancels the pending change', async () => {
    setup({
      pending_email: 'new@example.org',
      pending_email_sent_at: '2026-11-14T22:00:00Z',
    })
    apiClient.cancelEmailChange.mockResolvedValue(baseProfile)
    await renderLoaded()

    fireEvent.click(screen.getByTestId('profile-email-change-cancel'))

    await waitFor(() => {
      expect(
        screen.queryByTestId('profile-email-change-pending'),
      ).not.toBeInTheDocument()
    })
    expect(mockToast.addToast).toHaveBeenCalledWith(
      'profile.emailChangeCancelled',
      'success',
    )
  })
})

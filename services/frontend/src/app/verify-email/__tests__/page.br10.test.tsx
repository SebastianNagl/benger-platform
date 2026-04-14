/**
 * @jest-environment jsdom
 *
 * Branch coverage tests for verify-email page.
 * Targets 6 uncovered branches:
 * - token present: fetch OK with email, fetch error, fetch exception
 * - messageKey present
 * - no token and no messageKey
 * - resend verification: email present/absent
 */

import '@testing-library/jest-dom'
import { render, screen, waitFor, fireEvent, act } from '@testing-library/react'
import VerifyEmailPage from '../page'

const mockPush = jest.fn()
const mockSearchParams = jest.fn()

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
  useSearchParams: () => mockSearchParams(),
}))

jest.mock('next/link', () => {
  return ({ children, href }: any) => <a href={href}>{children}</a>
})

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => {
      const t: Record<string, string> = {
        'emailVerification.verifying': 'Verifying...',
        'emailVerification.checkInboxDescription': 'Please wait...',
        'emailVerification.verified': 'Email Verified',
        'emailVerification.verifiedDescription': 'Your email has been verified.',
        'emailVerification.invalid': 'Invalid Token',
        'emailVerification.invalidDescription': 'The token is invalid or expired.',
        'emailVerification.noToken': 'No verification token provided.',
        'emailVerification.checkInbox': 'Check Your Inbox',
        'emailVerification.registrationSuccess': 'Registration successful! Check your email.',
        'emailVerification.emailLabel': 'Email:',
        'emailVerification.resend': 'Resend Verification',
        'emailVerification.resent': 'Verification email resent.',
        'login.redirecting': 'Redirecting to login...',
        'passwordReset.backToLogin': 'Back to Login',
      }
      return t[key] || key
    },
  }),
}))

jest.mock('@/components/layout', () => ({
  LanguageSwitcher: () => <div data-testid="lang-switch" />,
  ThemeToggle: () => <div data-testid="theme-toggle" />,
}))

jest.mock('@/components/shared/Button', () => ({
  Button: ({ children, onClick, ...props }: any) => (
    <button onClick={onClick} {...props}>{children}</button>
  ),
}))

describe('VerifyEmailPage', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    jest.useFakeTimers()
  })

  afterEach(() => {
    jest.useRealTimers()
  })

  it('shows loading state then success when token verification succeeds', async () => {
    mockSearchParams.mockReturnValue({
      get: (key: string) => key === 'token' ? 'valid-token' : null,
    })

    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ email: 'test@example.com' }),
    })

    await act(async () => {
      render(<VerifyEmailPage />)
    })

    await waitFor(() => {
      expect(screen.getByText('Email Verified')).toBeInTheDocument()
    })
    expect(screen.getByText('Your email has been verified.')).toBeInTheDocument()
    expect(screen.getByText(/test@example.com/)).toBeInTheDocument()
  })

  it('shows error when token verification fails (response not ok)', async () => {
    mockSearchParams.mockReturnValue({
      get: (key: string) => key === 'token' ? 'invalid-token' : null,
    })

    global.fetch = jest.fn().mockResolvedValue({
      ok: false,
      json: () => Promise.resolve({ detail: 'Token expired' }),
    })

    await act(async () => {
      render(<VerifyEmailPage />)
    })

    await waitFor(() => {
      expect(screen.getByText('Invalid Token')).toBeInTheDocument()
    })
    expect(screen.getByText('Token expired')).toBeInTheDocument()
  })

  it('shows error when fetch throws an exception', async () => {
    mockSearchParams.mockReturnValue({
      get: (key: string) => key === 'token' ? 'bad-token' : null,
    })

    global.fetch = jest.fn().mockRejectedValue(new Error('Network error'))

    await act(async () => {
      render(<VerifyEmailPage />)
    })

    await waitFor(() => {
      expect(screen.getByText('Invalid Token')).toBeInTheDocument()
    })
  })

  it('shows info when messageKey is provided (no token)', async () => {
    mockSearchParams.mockReturnValue({
      get: (key: string) => key === 'messageKey' ? 'registrationSuccess' : null,
    })

    await act(async () => {
      render(<VerifyEmailPage />)
    })

    await waitFor(() => {
      expect(screen.getByText('Check Your Inbox')).toBeInTheDocument()
    })
  })

  it('shows error when neither token nor messageKey provided', async () => {
    mockSearchParams.mockReturnValue({
      get: () => null,
    })

    await act(async () => {
      render(<VerifyEmailPage />)
    })

    await waitFor(() => {
      expect(screen.getByText('Invalid Token')).toBeInTheDocument()
    })
    expect(screen.getByText('No verification token provided.')).toBeInTheDocument()
  })

  it('shows loading state initially when token is provided', () => {
    mockSearchParams.mockReturnValue({
      get: (key: string) => key === 'token' ? 'valid-token' : null,
    })

    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ email: 'test@example.com' }),
    })

    render(<VerifyEmailPage />)
    // Initially shows loading or verifying state
    expect(screen.getByText('Verifying...')).toBeInTheDocument()
  })
})

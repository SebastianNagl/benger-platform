import { useI18n } from '@/contexts/I18nContext'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useParams, useRouter } from 'next/navigation'
import ActivateAccountPage from '../page'

jest.mock('@/contexts/I18nContext')
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
  useParams: jest.fn(),
}))

jest.mock('@/components/layout', () => ({
  LanguageSwitcher: () => (
    <div data-testid="language-switcher">LanguageSwitcher</div>
  ),
  ThemeToggle: () => <div data-testid="theme-toggle">ThemeToggle</div>,
}))

jest.mock('@/components/shared/Button', () => ({
  Button: ({ children, ...props }: any) => (
    <button {...props}>{children}</button>
  ),
}))

jest.mock('@/lib/utils/subdomain', () => ({
  getHostBrandName: jest.fn(() => 'Vertretbar'),
  isStudentLockedHost: jest.fn(() => true),
}))

describe('ActivateAccountPage', () => {
  const mockRouterPush = jest.fn()
  const mockT = jest.fn((key: string) => key)

  beforeEach(() => {
    jest.clearAllMocks()
    global.fetch = jest.fn()
    ;(useI18n as jest.Mock).mockReturnValue({
      t: mockT,
      currentLanguage: 'de',
    })
    ;(useRouter as jest.Mock).mockReturnValue({
      push: mockRouterPush,
      replace: jest.fn(),
    })
    ;(useParams as jest.Mock).mockReturnValue({
      token: 'activation-token',
    })
  })

  afterEach(() => {
    jest.restoreAllMocks()
  })

  const fillAndSubmit = async (pw = 'NeuesPasswort1!', confirm = pw) => {
    const user = userEvent.setup()
    await user.type(screen.getByTestId('activate-password'), pw)
    await user.type(screen.getByTestId('activate-password-confirm'), confirm)
    await user.click(screen.getByTestId('activate-submit'))
  }

  it('renders the activation form with brand-aware header', () => {
    render(<ActivateAccountPage />)

    expect(screen.getByText('accountActivation.title')).toBeInTheDocument()
    expect(screen.getAllByText('Vertretbar').length).toBeGreaterThan(0)
    expect(screen.getByTestId('activate-password')).toBeInTheDocument()
    expect(screen.getByTestId('activate-password-confirm')).toBeInTheDocument()
  })

  it('posts token and password, shows success, redirects to login', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: async () => ({ message: 'Account activated' }),
    })
    jest.useFakeTimers({ advanceTimers: true })

    render(<ActivateAccountPage />)
    await fillAndSubmit()

    await waitFor(() =>
      expect(screen.getByTestId('activate-success')).toBeInTheDocument()
    )
    expect(global.fetch).toHaveBeenCalledWith(
      '/api/auth/activate-account',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          token: 'activation-token',
          new_password: 'NeuesPasswort1!',
          confirm_password: 'NeuesPasswort1!',
        }),
      })
    )

    jest.advanceTimersByTime(3000)
    await waitFor(() => expect(mockRouterPush).toHaveBeenCalledWith('/login'))
    jest.useRealTimers()
  })

  it('shows mismatch error without calling the API', async () => {
    render(<ActivateAccountPage />)
    await fillAndSubmit('NeuesPasswort1!', 'Anders!')

    expect(screen.getByTestId('activate-error')).toHaveTextContent(
      'accountActivation.mismatch'
    )
    expect(global.fetch).not.toHaveBeenCalled()
  })

  it('maps invalid_or_expired to the expired message', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValue({
      ok: false,
      json: async () => ({ detail: { code: 'invalid_or_expired' } }),
    })

    render(<ActivateAccountPage />)
    await fillAndSubmit()

    await waitFor(() =>
      expect(screen.getByTestId('activate-error')).toHaveTextContent(
        'accountActivation.expiredDescription'
      )
    )
  })

  it('maps email_taken to its dedicated message', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValue({
      ok: false,
      json: async () => ({ detail: { code: 'email_taken' } }),
    })

    render(<ActivateAccountPage />)
    await fillAndSubmit()

    await waitFor(() =>
      expect(screen.getByTestId('activate-error')).toHaveTextContent(
        'accountActivation.emailTaken'
      )
    )
  })
})

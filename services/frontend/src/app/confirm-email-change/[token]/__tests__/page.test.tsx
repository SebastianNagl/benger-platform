import { useI18n } from '@/contexts/I18nContext'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useParams } from 'next/navigation'
import ConfirmEmailChangePage from '../page'

jest.mock('@/contexts/I18nContext')
jest.mock('next/navigation', () => ({
  useParams: jest.fn(),
}))
jest.mock('@/components/layout', () => ({
  LanguageSwitcher: () => <div data-testid="language-switcher" />,
  ThemeToggle: () => <div data-testid="theme-toggle" />,
}))
jest.mock('@/components/shared/Button', () => ({
  Button: ({ children, ...props }: any) => (
    <button {...props}>{children}</button>
  ),
}))
jest.mock('@/lib/utils/subdomain', () => ({
  getHostBrandName: jest.fn(() => 'BenGER'),
  isStudentLockedHost: jest.fn(() => false),
}))

describe('ConfirmEmailChangePage', () => {
  const t = jest.fn((key: string, vars?: Record<string, string>) =>
    vars ? `${key} ${JSON.stringify(vars)}` : key,
  )

  beforeEach(() => {
    jest.clearAllMocks()
    global.fetch = jest.fn()
    ;(useI18n as jest.Mock).mockReturnValue({ t, locale: 'en' })
    ;(useParams as jest.Mock).mockReturnValue({ token: 'mailed-token' })
  })

  it('uses the token only when the button is pressed', async () => {
    // Mail scanners load the link; loading must not change the address.
    render(<ConfirmEmailChangePage />)

    expect(screen.getByText('emailChange.title')).toBeInTheDocument()
    expect(global.fetch).not.toHaveBeenCalled()
  })

  it('confirms and names the new login address', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({ message: 'ok', email: 'new@example.org' }),
    })
    render(<ConfirmEmailChangePage />)

    await userEvent.click(screen.getByTestId('confirm-email-change-submit'))

    expect(global.fetch).toHaveBeenCalledWith(
      '/api/auth/email-change/confirm',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ token: 'mailed-token' }),
      }),
    )
    expect(
      await screen.findByTestId('confirm-email-change-success'),
    ).toHaveTextContent(
      'emailChange.successDescription {"email":"new@example.org"}',
    )
    expect(
      screen.getByText('emailChange.toLogin').closest('a'),
    ).toHaveAttribute('href', '/login')
  })

  it('explains an invalid or expired link', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: false,
      status: 400,
      json: async () => ({ detail: { code: 'invalid_or_expired' } }),
    })
    render(<ConfirmEmailChangePage />)

    await userEvent.click(screen.getByTestId('confirm-email-change-submit'))

    expect(
      await screen.findByTestId('confirm-email-change-error'),
    ).toHaveTextContent('emailChange.invalid')
    expect(screen.getByTestId('confirm-email-change-submit')).toBeEnabled()
  })

  it('explains an address another account took meanwhile', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: false,
      status: 409,
      json: async () => ({ detail: { code: 'email_taken' } }),
    })
    render(<ConfirmEmailChangePage />)

    await userEvent.click(screen.getByTestId('confirm-email-change-submit'))

    expect(
      await screen.findByTestId('confirm-email-change-error'),
    ).toHaveTextContent('emailChange.taken')
  })

  it('reports a rate limit', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: false,
      status: 429,
      json: async () => ({
        detail: { code: 'rate_limited', retry_after: 120 },
      }),
    })
    render(<ConfirmEmailChangePage />)

    await userEvent.click(screen.getByTestId('confirm-email-change-submit'))

    const error = await screen.findByTestId('confirm-email-change-error')
    expect(error).not.toHaveTextContent('emailChange.invalid')
  })

  it('treats a network failure as an unusable link', async () => {
    ;(global.fetch as jest.Mock).mockRejectedValueOnce(new Error('offline'))
    jest.spyOn(console, 'error').mockImplementation(() => {})
    render(<ConfirmEmailChangePage />)

    await userEvent.click(screen.getByTestId('confirm-email-change-submit'))

    await waitFor(() => {
      expect(
        screen.getByTestId('confirm-email-change-error'),
      ).toHaveTextContent('emailChange.invalid')
    })
  })
})

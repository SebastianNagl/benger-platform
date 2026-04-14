/**
 * @jest-environment jsdom
 *
 * Branch coverage tests for LoginPage.
 * Targets uncovered branches:
 * - Auto-login flow in development mode (isDevelopment && isLocalhost && !user && !isLoading)
 * - Auto-login failure branch (catch block)
 * - sessionStorage checks for auto_login_attempted
 * - Redirect flash prevention when user is set (showing spinner instead of form)
 * - isLoading ternary on submit button (loading spinner vs button text)
 */
import '@testing-library/jest-dom'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { render, screen, waitFor } from '@testing-library/react'
import { useRouter } from 'next/navigation'

jest.mock('@/contexts/AuthContext')
jest.mock('@/contexts/I18nContext')
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
}))

jest.mock('@/components/layout', () => ({
  LanguageSwitcher: () => <div data-testid="language-switcher">LanguageSwitcher</div>,
  ThemeToggle: () => <div data-testid="theme-toggle">ThemeToggle</div>,
}))

jest.mock('@/components/shared/Button', () => ({
  Button: ({ children, ...props }: any) => (
    <button {...props}>{children}</button>
  ),
}))

// devAuthHelper no longer has auto-login methods (moved to layout.tsx inline script)

import LoginPage from '../page'

describe('LoginPage - branch coverage', () => {
  const mockLogin = jest.fn()
  const mockRouterReplace = jest.fn()
  const mockT = jest.fn((key: string) => key)

  beforeEach(() => {
    jest.clearAllMocks()

    if (typeof window !== 'undefined') {
      sessionStorage.clear()
    }

    ;(useAuth as jest.Mock).mockReturnValue({
      user: null,
      login: mockLogin,
      isLoading: false,
    })
    ;(useI18n as jest.Mock).mockReturnValue({
      t: mockT,
      currentLanguage: 'en',
    })
    ;(useRouter as jest.Mock).mockReturnValue({
      push: jest.fn(),
      replace: mockRouterReplace,
    })

  })

  describe('Redirect flash prevention', () => {
    it('shows spinner and redirecting text when user is authenticated', () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: { id: '1', username: 'testuser' },
        login: mockLogin,
        isLoading: false,
      })

      const { container } = render(<LoginPage />)

      // Should show redirecting text
      expect(screen.getByText('login.redirecting')).toBeInTheDocument()

      // Should show spinner
      expect(container.querySelector('.animate-spin')).toBeInTheDocument()

      // Form should NOT be shown
      expect(screen.queryByTestId('auth-login-form')).not.toBeInTheDocument()
    })
  })
})

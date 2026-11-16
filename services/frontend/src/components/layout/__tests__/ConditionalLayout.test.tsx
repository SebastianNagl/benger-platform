import { useAuth } from '@/contexts/AuthContext'
import { act, render, screen } from '@testing-library/react'
import { usePathname } from 'next/navigation'
import { ConditionalLayout } from '../ConditionalLayout'

jest.mock('@/contexts/AuthContext')
jest.mock('next/navigation', () => ({
  usePathname: jest.fn(),
  useRouter: jest.fn(() => ({
    push: jest.fn(),
    replace: jest.fn(),
  })),
}))
jest.mock('../Layout', () => ({
  Layout: ({ children, variant }: any) => (
    <div data-testid={variant === 'public' ? 'public-shell' : 'full-layout'}>
      {children}
    </div>
  ),
}))
jest.mock('@/components/auth/ProtectedRoute', () => ({
  ProtectedRoute: ({ children }: any) => <>{children}</>,
}))

const mockUseAuth = useAuth as jest.MockedFunction<typeof useAuth>
const mockUsePathname = usePathname as jest.Mock

describe('ConditionalLayout', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('Legal pages layout behavior', () => {
    // Keep in sync with ConditionalLayout's legalPages.
    const legalPages = [
      '/about/imprint',
      '/about/data-protection',
      '/changelog',
    ]

    describe('when user is not authenticated', () => {
      beforeEach(() => {
        mockUseAuth.mockReturnValue({
          user: null,
          isLoading: false,
          login: jest.fn(),
          logout: jest.fn(),
          isInitialized: true,
        } as any)
      })

      it.each(legalPages)('should render %s in the visitor shell', (path) => {
        mockUsePathname.mockReturnValue(path)

        render(
          <ConditionalLayout allSections={{}}>
            <div>Legal content</div>
          </ConditionalLayout>,
        )

        expect(screen.getByTestId('public-shell')).toBeInTheDocument()
        expect(screen.queryByTestId('full-layout')).not.toBeInTheDocument()
        expect(screen.getByText('Legal content')).toBeInTheDocument()
      })

      it.each(legalPages)('keeps the prose typography on %s', (path) => {
        mockUsePathname.mockReturnValue(path)

        render(
          <ConditionalLayout allSections={{}}>
            <div>Legal content</div>
          </ConditionalLayout>,
        )

        expect(
          screen.getByText('Legal content').closest('.prose'),
        ).not.toBeNull()
      })
    })

    describe('when user is authenticated', () => {
      beforeEach(() => {
        mockUseAuth.mockReturnValue({
          user: { id: '1', email: 'test@example.com' },
          isLoading: false,
          login: jest.fn(),
          logout: jest.fn(),
          isInitialized: true,
        } as any)
      })

      it.each(legalPages)('should render %s with full layout', (path) => {
        mockUsePathname.mockReturnValue(path)

        render(
          <ConditionalLayout allSections={{}}>
            <div>Legal content</div>
          </ConditionalLayout>,
        )

        expect(screen.getByTestId('full-layout')).toBeInTheDocument()
        expect(screen.queryByTestId('public-shell')).not.toBeInTheDocument()
        expect(screen.getByText('Legal content')).toBeInTheDocument()
      })
    })

    describe('when auth is loading', () => {
      beforeEach(() => {
        mockUseAuth.mockReturnValue({
          user: null,
          isLoading: true,
          login: jest.fn(),
          logout: jest.fn(),
          isInitialized: false,
        } as any)
      })

      it.each(legalPages)(
        'should show the visitor shell for %s while loading (no user)',
        (path) => {
          mockUsePathname.mockReturnValue(path)

          const { container } = render(
            <ConditionalLayout allSections={{}}>
              <div>Legal content</div>
            </ConditionalLayout>,
          )

          // Legal pages show the visitor shell when user is null (even during loading)
          expect(screen.queryByTestId('full-layout')).not.toBeInTheDocument()
          expect(screen.getByTestId('public-shell')).toBeInTheDocument()
          expect(screen.getByText('Legal content')).toBeInTheDocument()
        },
      )
    })
  })

  describe('Public report pages (/reports, /reports/[id])', () => {
    const reportPaths = ['/reports', '/reports/report-123']

    it.each(reportPaths)(
      'renders %s in the visitor shell when unauthenticated',
      (path) => {
        mockUseAuth.mockReturnValue({
          user: null,
          isLoading: false,
          login: jest.fn(),
          logout: jest.fn(),
          isInitialized: true,
        } as any)
        mockUsePathname.mockReturnValue(path)

        render(
          <ConditionalLayout allSections={{}}>
            <div>Report content</div>
          </ConditionalLayout>,
        )

        expect(screen.getByTestId('public-shell')).toBeInTheDocument()
        expect(screen.queryByTestId('full-layout')).not.toBeInTheDocument()
        expect(screen.getByText('Report content')).toBeInTheDocument()
        expect(screen.getByText('Report content').closest('.prose')).toBeNull()
      },
    )

    it.each(reportPaths)(
      'renders %s with the full layout when authenticated',
      (path) => {
        mockUseAuth.mockReturnValue({
          user: { id: '1', email: 'test@example.com' },
          isLoading: false,
          login: jest.fn(),
          logout: jest.fn(),
          isInitialized: true,
        } as any)
        mockUsePathname.mockReturnValue(path)

        render(
          <ConditionalLayout allSections={{}}>
            <div>Report content</div>
          </ConditionalLayout>,
        )

        expect(screen.getByTestId('full-layout')).toBeInTheDocument()
        expect(screen.queryByTestId('public-shell')).not.toBeInTheDocument()
      },
    )

    it('does not treat a look-alike prefix (/reportsfoo) as public content', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: false,
        login: jest.fn(),
        logout: jest.fn(),
        isInitialized: true,
      } as any)
      mockUsePathname.mockReturnValue('/reportsfoo')

      render(
        <ConditionalLayout allSections={{}}>
          <div>Other content</div>
        </ConditionalLayout>,
      )

      expect(screen.getByTestId('full-layout')).toBeInTheDocument()
      expect(screen.queryByTestId('public-shell')).not.toBeInTheDocument()
    })
  })

  describe('Other pages layout behavior', () => {
    describe('dashboard page', () => {
      beforeEach(() => {
        mockUsePathname.mockReturnValue('/dashboard')
      })

      it('should always render with full layout when authenticated', () => {
        mockUseAuth.mockReturnValue({
          user: { id: '1', email: 'test@example.com' },
          isLoading: false,
          login: jest.fn(),
          logout: jest.fn(),
          isInitialized: true,
        } as any)

        render(
          <ConditionalLayout allSections={{}}>
            <div>Dashboard content</div>
          </ConditionalLayout>,
        )

        expect(screen.getByTestId('full-layout')).toBeInTheDocument()
        expect(screen.queryByTestId('public-shell')).not.toBeInTheDocument()
      })
    })

    describe('LMS launch pages', () => {
      // Public LMS steps run before a session exists: no app chrome (no
      // sidebar, student shell or plan modal), and no auth spinner.
      const standaloneLtiPages = [
        '/lti/consent',
        '/lti/link-account',
        '/lti/link-confirm/tok-123',
        '/lti/error',
      ]

      const loadingAuth = {
        user: null,
        isLoading: true,
        login: jest.fn(),
        logout: jest.fn(),
        isInitialized: false,
      } as any

      afterEach(() => {
        jest.useRealTimers()
      })

      it.each(standaloneLtiPages)(
        'renders %s without the app layout, also while auth is loading',
        (path) => {
          jest.useFakeTimers()
          mockUsePathname.mockReturnValue(path)
          mockUseAuth.mockReturnValue(loadingAuth)

          render(
            <ConditionalLayout allSections={{}}>
              <div>LTI step</div>
            </ConditionalLayout>,
          )
          // Past the 200 ms delay after which other pages show the spinner.
          act(() => {
            jest.advanceTimersByTime(300)
          })

          expect(screen.getByText('LTI step')).toBeInTheDocument()
          expect(screen.queryByTestId('full-layout')).not.toBeInTheDocument()
          expect(screen.queryByTestId('public-shell')).not.toBeInTheDocument()
          expect(
            screen.queryByText('common.checkingAuth'),
          ).not.toBeInTheDocument()
        },
      )

      it('shows the auth spinner instead of the teacher picker while auth is loading', () => {
        jest.useFakeTimers()
        mockUsePathname.mockReturnValue('/lti/link')
        mockUseAuth.mockReturnValue(loadingAuth)

        render(
          <ConditionalLayout allSections={{}}>
            <div>Teacher page</div>
          </ConditionalLayout>,
        )
        act(() => {
          jest.advanceTimersByTime(300)
        })

        expect(screen.getByText('common.checkingAuth')).toBeInTheDocument()
        expect(screen.queryByText('Teacher page')).not.toBeInTheDocument()
      })

      it.each(standaloneLtiPages)(
        'keeps %s standalone for a signed-in user',
        (path) => {
          mockUsePathname.mockReturnValue(path)
          mockUseAuth.mockReturnValue({
            user: { id: '1', email: 'test@example.com' },
            isLoading: false,
            login: jest.fn(),
            logout: jest.fn(),
            isInitialized: true,
          } as any)

          render(
            <ConditionalLayout allSections={{}}>
              <div>LTI step</div>
            </ConditionalLayout>,
          )

          expect(screen.queryByTestId('full-layout')).not.toBeInTheDocument()
        },
      )

      it.each(['/lti/link', '/lti/activity'])(
        'keeps the app layout on the teacher page %s',
        (path) => {
          mockUsePathname.mockReturnValue(path)
          mockUseAuth.mockReturnValue({
            user: { id: '1', email: 'test@example.com' },
            isLoading: false,
            login: jest.fn(),
            logout: jest.fn(),
            isInitialized: true,
          } as any)

          render(
            <ConditionalLayout allSections={{}}>
              <div>Teacher page</div>
            </ConditionalLayout>,
          )

          expect(screen.getByTestId('full-layout')).toBeInTheDocument()
        },
      )
    })

    describe('standalone pages', () => {
      const standalonePages = ['/', '/login', '/register']

      it.each(standalonePages)(
        'should render %s without any layout wrapper',
        (path) => {
          mockUsePathname.mockReturnValue(path)
          mockUseAuth.mockReturnValue({
            user: null,
            isLoading: false,
            login: jest.fn(),
            logout: jest.fn(),
            isInitialized: true,
          } as any)

          const { container } = render(
            <ConditionalLayout allSections={{}}>
              <div>Standalone content</div>
            </ConditionalLayout>,
          )

          expect(screen.queryByTestId('full-layout')).not.toBeInTheDocument()
          expect(screen.queryByTestId('public-shell')).not.toBeInTheDocument()
          expect(screen.getByText('Standalone content')).toBeInTheDocument()

          // Should be wrapped in a simple div with w-full class
          const wrapper = container.querySelector('.w-full')
          expect(wrapper).toBeInTheDocument()
        },
      )
    })
  })
})

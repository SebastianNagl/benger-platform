import { useAuth } from '@/contexts/AuthContext'
import { render, screen } from '@testing-library/react'
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
  Layout: ({ children }: any) => (
    <div data-testid="full-layout">{children}</div>
  ),
}))
jest.mock('../MinimalLayout', () => ({
  MinimalLayout: ({ children }: any) => (
    <div data-testid="minimal-layout">{children}</div>
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
    const legalPages = ['/about/imprint', '/about/data-protection']

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

      it.each(legalPages)('should render %s with minimal layout', (path) => {
        mockUsePathname.mockReturnValue(path)

        render(
          <ConditionalLayout allSections={{}}>
            <div>Legal content</div>
          </ConditionalLayout>
        )

        expect(screen.getByTestId('minimal-layout')).toBeInTheDocument()
        expect(screen.queryByTestId('full-layout')).not.toBeInTheDocument()
        expect(screen.getByText('Legal content')).toBeInTheDocument()
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
          </ConditionalLayout>
        )

        expect(screen.getByTestId('full-layout')).toBeInTheDocument()
        expect(screen.queryByTestId('minimal-layout')).not.toBeInTheDocument()
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
        'should show minimal layout for %s while loading (no user)',
        (path) => {
          mockUsePathname.mockReturnValue(path)

          const { container } = render(
            <ConditionalLayout allSections={{}}>
              <div>Legal content</div>
            </ConditionalLayout>
          )

          // Legal pages show minimal layout when user is null (even during loading)
          expect(screen.queryByTestId('full-layout')).not.toBeInTheDocument()
          expect(screen.getByTestId('minimal-layout')).toBeInTheDocument()
          expect(screen.getByText('Legal content')).toBeInTheDocument()
        }
      )
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
          </ConditionalLayout>
        )

        expect(screen.getByTestId('full-layout')).toBeInTheDocument()
        expect(screen.queryByTestId('minimal-layout')).not.toBeInTheDocument()
      })
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
            </ConditionalLayout>
          )

          expect(screen.queryByTestId('full-layout')).not.toBeInTheDocument()
          expect(screen.queryByTestId('minimal-layout')).not.toBeInTheDocument()
          expect(screen.getByText('Standalone content')).toBeInTheDocument()

          // Should be wrapped in a simple div with w-full class
          const wrapper = container.querySelector('.w-full')
          expect(wrapper).toBeInTheDocument()
        }
      )
    })
  })
})

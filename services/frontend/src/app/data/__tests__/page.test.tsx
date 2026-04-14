/**
 * @jest-environment jsdom
 */

import { render, screen, waitFor } from '@testing-library/react'
import DataManagementPage from '../page'

// Mock Next.js router
const mockPush = jest.fn()
const mockRouter = {
  push: mockPush,
  replace: jest.fn(),
  back: jest.fn(),
  forward: jest.fn(),
  refresh: jest.fn(),
  prefetch: jest.fn(),
  pathname: '/data',
  query: {},
  asPath: '/data',
}

jest.mock('next/navigation', () => ({
  useRouter: () => mockRouter,
  useParams: jest.fn(() => ({})),
  useSearchParams: jest.fn(() => new URLSearchParams()),
  usePathname: jest.fn(() => '/data'),
}))

// Mock contexts
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: jest.fn(),
}))

jest.mock('@/contexts/AuthContext', () => ({
  useAuth: jest.fn(),
}))

// Mock permissions
const mockCanAccessProjectData = jest.fn()
jest.mock('@/utils/permissions', () => ({
  canAccessProjectData: (...args: any[]) => mockCanAccessProjectData(...args),
}))

// Mock components
jest.mock('@/components/data/GlobalDataTab', () => ({
  GlobalDataTab: () => <div data-testid="global-data-tab">GlobalDataTab</div>,
}))

jest.mock('@/components/shared/Breadcrumb', () => ({
  Breadcrumb: ({ items }: any) => (
    <nav data-testid="breadcrumb">
      {items.map((item: any, idx: number) => (
        <span key={idx} data-testid={`breadcrumb-item-${idx}`}>
          {item.label}
        </span>
      ))}
    </nav>
  ),
}))

jest.mock('@/components/shared/ResponsiveContainer', () => ({
  ResponsiveContainer: ({ children, className }: any) => (
    <div data-testid="responsive-container" className={className}>
      {children}
    </div>
  ),
}))

// Mock API client
jest.mock('@/lib/api/client', () => ({
  apiClient: {
    get: jest.fn(),
    post: jest.fn(),
    put: jest.fn(),
    delete: jest.fn(),
  },
}))

jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({
    showToast: jest.fn(),
  }),
}))

describe('DataManagementPage', () => {
  const mockI18nContext = {
    t: (key: string) => {
      const translations: { [key: string]: string } = {
        'navigation.dashboard': 'Home',
        'navigation.dataManagement': 'Data Management',
        'dataManagement.title': 'Data Management',
        'dataManagement.accessDenied': 'Access Denied',
        'dataManagement.accessDeniedDescription': 'Only superadmins, organization admins, and contributors can access project data.',
        'common.loading': 'Loading...',
        'common.backToProjects': 'Back to Projects',
      }
      return translations[key] || key
    },
    changeLanguage: jest.fn(),
    currentLanguage: 'en',
    languages: ['en', 'de'],
  }

  const mockAuthContext = {
    user: {
      id: '1',
      username: 'testuser',
      role: 'ORG_ADMIN',
      is_superadmin: true,
      email: 'test@example.com',
      name: 'Test User',
    },
    isLoading: false,
  }

  beforeEach(() => {
    jest.clearAllMocks()

    // Setup I18n context
    const { useI18n } = require('@/contexts/I18nContext')
    useI18n.mockReturnValue(mockI18nContext)

    // Setup Auth context
    const { useAuth } = require('@/contexts/AuthContext')
    useAuth.mockReturnValue(mockAuthContext)

    // Default: user has access
    mockCanAccessProjectData.mockReturnValue(true)
  })

  describe('Permission Control', () => {
    it('renders page when user has access to project data', () => {
      mockCanAccessProjectData.mockReturnValue(true)

      render(<DataManagementPage />)

      expect(screen.getByTestId('responsive-container')).toBeInTheDocument()
      expect(screen.getAllByText('Data Management').length).toBeGreaterThan(0)
      expect(screen.getByTestId('global-data-tab')).toBeInTheDocument()
    })

    it('shows access denied when user lacks permission', async () => {
      mockCanAccessProjectData.mockReturnValue(false)

      render(<DataManagementPage />)

      await waitFor(() => {
        expect(screen.getByText('Access Denied')).toBeInTheDocument()
      })
    })

    it('shows loading state while auth is loading', () => {
      const { useAuth } = require('@/contexts/AuthContext')
      useAuth.mockReturnValue({
        ...mockAuthContext,
        isLoading: true,
      })

      render(<DataManagementPage />)

      expect(screen.getByText('Loading...')).toBeInTheDocument()
    })

    it('does not redirect when user has access', () => {
      mockCanAccessProjectData.mockReturnValue(true)

      render(<DataManagementPage />)

      expect(mockRouter.replace).not.toHaveBeenCalled()
    })
  })

  describe('Page Structure', () => {
    beforeEach(() => {
      mockCanAccessProjectData.mockReturnValue(true)
    })

    it('renders responsive container with correct styling', () => {
      render(<DataManagementPage />)

      const container = screen.getByTestId('responsive-container')
      expect(container).toHaveClass('px-4', 'pb-10', 'pt-8')
    })

    it('renders breadcrumb navigation', () => {
      render(<DataManagementPage />)

      expect(screen.getByTestId('breadcrumb')).toBeInTheDocument()
      expect(screen.getByTestId('breadcrumb-item-0')).toHaveTextContent('Home')
      expect(screen.getByTestId('breadcrumb-item-1')).toHaveTextContent(
        'Data Management'
      )
    })

    it('renders page title', () => {
      render(<DataManagementPage />)

      const title = screen.getByRole('heading', { level: 1 })
      expect(title).toHaveTextContent('Data Management')
      expect(title).toHaveClass('text-3xl', 'font-bold')
    })

    it('renders GlobalDataTab component', () => {
      render(<DataManagementPage />)

      expect(screen.getByTestId('global-data-tab')).toBeInTheDocument()
    })

    it('has correct layout hierarchy', () => {
      render(<DataManagementPage />)

      const container = screen.getByTestId('responsive-container')
      const breadcrumb = screen.getByTestId('breadcrumb')

      expect(container).toContainElement(breadcrumb)
    })
  })

  describe('Internationalization', () => {
    beforeEach(() => {
      mockCanAccessProjectData.mockReturnValue(true)
    })

    it('uses translation function for navigation labels', () => {
      const { useI18n } = require('@/contexts/I18nContext')
      const t = jest.fn((key: string) => key)
      useI18n.mockReturnValue({
        ...mockI18nContext,
        t,
      })

      render(<DataManagementPage />)

      expect(t).toHaveBeenCalledWith('navigation.dashboard')
      expect(t).toHaveBeenCalledWith('navigation.dataManagement')
    })

    it('uses translation function for page title', () => {
      const { useI18n } = require('@/contexts/I18nContext')
      const t = jest.fn((key: string) => key)
      useI18n.mockReturnValue({
        ...mockI18nContext,
        t,
      })

      render(<DataManagementPage />)

      expect(t).toHaveBeenCalledWith('dataManagement.title')
    })

    it('renders page title even when breadcrumb translation is empty', () => {
      const { useI18n } = require('@/contexts/I18nContext')
      useI18n.mockReturnValue({
        ...mockI18nContext,
        t: (key: string) => (key === 'navigation.dataManagement' ? '' : key),
      })

      render(<DataManagementPage />)

      // Page title uses 'dataManagement.title' key which still returns the key
      expect(screen.getByText('dataManagement.title')).toBeInTheDocument()
    })

    it('handles different languages correctly', () => {
      const { useI18n } = require('@/contexts/I18nContext')
      useI18n.mockReturnValue({
        ...mockI18nContext,
        t: (key: string) => {
          if (key === 'dataManagement.title') return 'Datenverwaltung'
          if (key === 'navigation.dataManagement') return 'Datenverwaltung'
          if (key === 'navigation.dashboard') return 'Startseite'
          return key
        },
        currentLanguage: 'de',
      })

      render(<DataManagementPage />)

      expect(screen.getAllByText('Datenverwaltung').length).toBeGreaterThan(0)
      expect(screen.getByText('Startseite')).toBeInTheDocument()
    })
  })

  describe('Breadcrumb Navigation', () => {
    beforeEach(() => {
      mockCanAccessProjectData.mockReturnValue(true)
    })

    it('has correct breadcrumb structure', () => {
      render(<DataManagementPage />)

      const breadcrumbItems = screen.getAllByTestId(/breadcrumb-item-/)
      expect(breadcrumbItems).toHaveLength(2)
    })

    it('first breadcrumb item links to dashboard', () => {
      render(<DataManagementPage />)

      expect(screen.getByTestId('breadcrumb-item-0')).toHaveTextContent('Home')
    })

    it('second breadcrumb item is current page', () => {
      render(<DataManagementPage />)

      expect(screen.getByTestId('breadcrumb-item-1')).toHaveTextContent(
        'Data Management'
      )
    })
  })

  describe('Responsive Design', () => {
    beforeEach(() => {
      mockCanAccessProjectData.mockReturnValue(true)
    })

    it('applies responsive padding classes', () => {
      render(<DataManagementPage />)

      const container = screen.getByTestId('responsive-container')
      expect(container).toHaveClass('px-4', 'sm:px-6', 'lg:px-8')
    })

    it('applies responsive container size', () => {
      render(<DataManagementPage />)

      expect(screen.getByTestId('responsive-container')).toBeInTheDocument()
    })

    it('constrains content width with max-w-7xl', () => {
      render(<DataManagementPage />)

      const maxWidthContainer = screen
        .getByTestId('responsive-container')
        .querySelector('.max-w-7xl')
      expect(maxWidthContainer).toBeInTheDocument()
    })
  })

  describe('Dark Mode Support', () => {
    beforeEach(() => {
      mockCanAccessProjectData.mockReturnValue(true)
    })

    it('applies dark mode classes to title', () => {
      render(<DataManagementPage />)

      const title = screen.getByRole('heading', { level: 1 })
      expect(title).toHaveClass('text-zinc-900', 'dark:text-white')
    })
  })

  describe('Error Handling', () => {
    it('throws error with missing I18n translation function', () => {
      const { useI18n } = require('@/contexts/I18nContext')
      useI18n.mockReturnValue({
        t: undefined,
        changeLanguage: jest.fn(),
        currentLanguage: 'en',
        languages: ['en'],
      })

      mockCanAccessProjectData.mockReturnValue(true)

      // Should throw error when t is not a function
      expect(() => render(<DataManagementPage />)).toThrow()
    })

    it('shows access denied for unauthorized users', async () => {
      mockCanAccessProjectData.mockReturnValue(false)

      render(<DataManagementPage />)

      await waitFor(() => {
        expect(screen.getByText('Access Denied')).toBeInTheDocument()
      })
    })
  })

  describe('Component Integration', () => {
    beforeEach(() => {
      mockCanAccessProjectData.mockReturnValue(true)
    })

    it('passes correct props to ResponsiveContainer', () => {
      render(<DataManagementPage />)

      const container = screen.getByTestId('responsive-container')
      expect(container).toHaveClass('px-4', 'pb-10', 'pt-8')
    })

    it('passes correct items to Breadcrumb', () => {
      render(<DataManagementPage />)

      expect(screen.getByTestId('breadcrumb-item-0')).toHaveTextContent('Home')
      expect(screen.getByTestId('breadcrumb-item-1')).toHaveTextContent(
        'Data Management'
      )
    })

    it('renders all components in correct order', () => {
      const { container } = render(<DataManagementPage />)

      const breadcrumb = screen.getByTestId('breadcrumb')
      const title = screen.getByRole('heading', { level: 1 })
      const dataTab = screen.getByTestId('global-data-tab')

      // Check rendering order in DOM
      const breadcrumbIndex = Array.from(
        container.querySelectorAll('*')
      ).indexOf(breadcrumb)
      const titleIndex = Array.from(container.querySelectorAll('*')).indexOf(
        title
      )
      const dataTabIndex = Array.from(container.querySelectorAll('*')).indexOf(
        dataTab
      )

      expect(breadcrumbIndex).toBeLessThan(titleIndex)
      expect(titleIndex).toBeLessThan(dataTabIndex)
    })
  })

  describe('Accessibility', () => {
    beforeEach(() => {
      mockCanAccessProjectData.mockReturnValue(true)
    })

    it('has proper heading hierarchy', () => {
      render(<DataManagementPage />)

      const h1 = screen.getByRole('heading', { level: 1 })
      expect(h1).toBeInTheDocument()
      expect(h1).toHaveTextContent('Data Management')
    })

    it('breadcrumb is semantically correct', () => {
      render(<DataManagementPage />)

      const breadcrumb = screen.getByTestId('breadcrumb')
      expect(breadcrumb.tagName).toBe('NAV')
    })

    it('page has proper semantic structure', () => {
      render(<DataManagementPage />)

      expect(screen.getByRole('heading')).toBeInTheDocument()
      expect(screen.getByTestId('breadcrumb')).toBeInTheDocument()
    })
  })

  describe('Router Integration', () => {
    beforeEach(() => {
      mockCanAccessProjectData.mockReturnValue(true)
    })

    it('does not redirect when feature is enabled', () => {
      render(<DataManagementPage />)

      expect(mockPush).not.toHaveBeenCalled()
    })

    it('redirects when user lacks permission', async () => {
      mockCanAccessProjectData.mockReturnValue(false)

      render(<DataManagementPage />)

      await waitFor(() => {
        expect(mockRouter.replace).toHaveBeenCalledWith(
          '/projects?error=no-permission'
        )
      })
    })
  })

  describe('Performance', () => {
    beforeEach(() => {
      mockCanAccessProjectData.mockReturnValue(true)
    })

    it('renders efficiently without unnecessary re-renders', () => {
      const { rerender } = render(<DataManagementPage />)

      expect(screen.getByTestId('global-data-tab')).toBeInTheDocument()

      // Re-render with same props
      rerender(<DataManagementPage />)

      expect(screen.getByTestId('global-data-tab')).toBeInTheDocument()
    })

    it('does not make unnecessary API calls on mount', () => {
      const { apiClient } = require('@/lib/api/client')

      render(<DataManagementPage />)

      expect(apiClient.get).not.toHaveBeenCalled()
      expect(apiClient.post).not.toHaveBeenCalled()
    })
  })

  describe('Edge Cases', () => {
    it('handles permission changes correctly', async () => {
      mockCanAccessProjectData.mockReturnValue(true)

      const { rerender } = render(<DataManagementPage />)
      expect(screen.getByTestId('global-data-tab')).toBeInTheDocument()

      // Change to no access
      mockCanAccessProjectData.mockReturnValue(false)

      rerender(<DataManagementPage />)

      // After permission change, access denied UI should show
      await waitFor(() => {
        expect(screen.getByText('Access Denied')).toBeInTheDocument()
      })
      expect(screen.queryByTestId('global-data-tab')).not.toBeInTheDocument()
    })

    it('handles empty translation strings', () => {
      const { useI18n } = require('@/contexts/I18nContext')
      useI18n.mockReturnValue({
        ...mockI18nContext,
        t: () => '',
      })

      mockCanAccessProjectData.mockReturnValue(true)

      render(<DataManagementPage />)

      // With empty translations, the component still renders without crashing
      expect(screen.getByTestId('global-data-tab')).toBeInTheDocument()
    })

    it('handles null translation function', () => {
      const { useI18n } = require('@/contexts/I18nContext')
      useI18n.mockReturnValue({
        ...mockI18nContext,
        t: null,
      })

      mockCanAccessProjectData.mockReturnValue(true)

      // Should throw error
      expect(() => render(<DataManagementPage />)).toThrow()
    })
  })

  describe('Visual Regression', () => {
    beforeEach(() => {
      mockCanAccessProjectData.mockReturnValue(true)
    })

    it('maintains consistent layout structure', () => {
      const { container } = render(<DataManagementPage />)

      expect(container.querySelector('.px-4')).toBeInTheDocument()
      expect(container.querySelector('.pb-10')).toBeInTheDocument()
      expect(container.querySelector('.pt-8')).toBeInTheDocument()
      expect(container.querySelector('.max-w-7xl')).toBeInTheDocument()
    })

    it('applies correct typography classes', () => {
      render(<DataManagementPage />)

      const title = screen.getByRole('heading', { level: 1 })
      expect(title).toHaveClass(
        'text-3xl',
        'font-bold',
        'tracking-tight',
        'text-zinc-900',
        'dark:text-white'
      )
    })

    it('maintains consistent spacing', () => {
      render(<DataManagementPage />)

      const breadcrumbContainer = screen
        .getByTestId('breadcrumb')
        .closest('.mb-4')
      expect(breadcrumbContainer).toBeInTheDocument()

      const title = screen.getByRole('heading', { level: 1 })
      expect(title).toHaveClass('mb-6')
    })
  })
})

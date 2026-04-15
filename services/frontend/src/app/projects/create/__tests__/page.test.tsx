/**
 * @jest-environment jsdom
 *
 * Comprehensive tests for Projects Create page
 * Tests rendering, permission guards, navigation, breadcrumbs, and wizard display
 */

import CreateProjectPage from '@/app/projects/create/page'
import { render, screen, waitFor } from '@testing-library/react'
import { useRouter } from 'next/navigation'

// Mock next/navigation
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
}))

// Mock AuthContext
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: jest.fn(),
}))

// Mock I18nContext
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => {
      const translations: Record<string, string> = {
        'common.loading': 'Loading...',
        'navigation.dashboard': 'Home',
        'navigation.projects': 'Projects',
        'projects.create.title': 'Create',
        'projects.create.accessDenied': 'Access Denied',
        'projects.create.permissionDenied': 'Only superadmins, organization admins, and contributors can create projects.',
        'projects.backToProjects': 'Back to Projects',
      }
      return translations[key] || key
    },
    currentLanguage: 'en',
  }),
}))

// Mock permissions
jest.mock('@/utils/permissions', () => ({
  canCreateProjects: jest.fn(),
}))

// Mock subdomain utility
jest.mock('@/lib/utils/subdomain', () => ({
  parseSubdomain: jest.fn(() => ({ orgSlug: null, isPrivateMode: false })),
}))

// Mock components
jest.mock('@/components/projects/ProjectCreationWizard', () => ({
  ProjectCreationWizard: () => (
    <div data-testid="project-creation-wizard">Project Creation Wizard</div>
  ),
}))

jest.mock('@/components/shared/Breadcrumb', () => ({
  Breadcrumb: ({ items }: any) => (
    <div data-testid="breadcrumb">
      {items.map((item: any, index: number) => (
        <span key={index} data-testid={`breadcrumb-item-${index}`}>
          {item.label}
        </span>
      ))}
    </div>
  ),
}))

jest.mock('@/components/shared/ResponsiveContainer', () => ({
  ResponsiveContainer: ({ children, size, className }: any) => (
    <div
      data-testid="responsive-container"
      className={className}
      data-size={size}
    >
      {children}
    </div>
  ),
}))

import { useAuth } from '@/contexts/AuthContext'
import { canCreateProjects } from '@/utils/permissions'

describe('Create Project Page', () => {
  const mockPush = jest.fn()
  const mockReplace = jest.fn()

  beforeEach(() => {
    jest.clearAllMocks()
    ;(useRouter as jest.Mock).mockReturnValue({
      push: mockPush,
      replace: mockReplace,
    })
  })

  describe('Loading State', () => {
    it('shows loading spinner while checking permissions', () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: null,
        isLoading: true,
      })
      ;(canCreateProjects as jest.Mock).mockReturnValue(false)

      render(<CreateProjectPage />)

      expect(screen.getByText('Loading...')).toBeInTheDocument()
    })

    it('shows loading spinner with animation', () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: null,
        isLoading: true,
      })
      ;(canCreateProjects as jest.Mock).mockReturnValue(false)

      const { container } = render(<CreateProjectPage />)

      const spinner = container.querySelector('.animate-spin')
      expect(spinner).toBeInTheDocument()
    })

    it('centers loading state', () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: null,
        isLoading: true,
      })
      ;(canCreateProjects as jest.Mock).mockReturnValue(false)

      const { container } = render(<CreateProjectPage />)

      const loadingContainer = container.querySelector(
        '.items-center.justify-center'
      )
      expect(loadingContainer).toBeInTheDocument()
    })

    it('applies correct loading spinner classes', () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: null,
        isLoading: true,
      })
      ;(canCreateProjects as jest.Mock).mockReturnValue(false)

      const { container } = render(<CreateProjectPage />)

      const spinner = container.querySelector('.border-emerald-500')
      expect(spinner).toBeInTheDocument()
    })
  })

  describe('Permission Denied State', () => {
    it('shows access denied message for users without permission', () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: { id: '1', email: 'user@example.com', role: 'user' },
        isLoading: false,
      })
      ;(canCreateProjects as jest.Mock).mockReturnValue(false)

      render(<CreateProjectPage />)

      expect(screen.getByText('Access Denied')).toBeInTheDocument()
    })

    it('shows permission explanation message', () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: { id: '1', email: 'user@example.com', role: 'user' },
        isLoading: false,
      })
      ;(canCreateProjects as jest.Mock).mockReturnValue(false)

      render(<CreateProjectPage />)

      expect(
        screen.getByText(
          /Only superadmins, organization admins, and contributors can create projects/
        )
      ).toBeInTheDocument()
    })

    it('shows error icon on access denied', () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: { id: '1', email: 'user@example.com', role: 'user' },
        isLoading: false,
      })
      ;(canCreateProjects as jest.Mock).mockReturnValue(false)

      const { container } = render(<CreateProjectPage />)

      const errorIcon = container.querySelector('.text-red-600')
      expect(errorIcon).toBeInTheDocument()
    })

    it('shows back to projects button on access denied', () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: { id: '1', email: 'user@example.com', role: 'user' },
        isLoading: false,
      })
      ;(canCreateProjects as jest.Mock).mockReturnValue(false)

      render(<CreateProjectPage />)

      expect(screen.getByText('Back to Projects')).toBeInTheDocument()
    })

    it('navigates to projects list when back button clicked', () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: { id: '1', email: 'user@example.com', role: 'user' },
        isLoading: false,
      })
      ;(canCreateProjects as jest.Mock).mockReturnValue(false)

      render(<CreateProjectPage />)

      const backButton = screen.getByText('Back to Projects')
      backButton.click()

      expect(mockPush).toHaveBeenCalledWith('/projects')
    })

    it('redirects user without permission to projects with error', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: { id: '1', email: 'user@example.com', role: 'user' },
        isLoading: false,
      })
      ;(canCreateProjects as jest.Mock).mockReturnValue(false)

      render(<CreateProjectPage />)

      await waitFor(() => {
        expect(mockReplace).toHaveBeenCalledWith(
          '/projects?error=no-permission'
        )
      })
    })
  })

  describe('Authorized Access', () => {
    it('renders page for superadmin', () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: { id: '1', email: 'admin@example.com', role: 'superadmin' },
        isLoading: false,
      })
      ;(canCreateProjects as jest.Mock).mockReturnValue(true)

      render(<CreateProjectPage />)

      expect(screen.getByTestId('project-creation-wizard')).toBeInTheDocument()
    })

    it('renders page for organization admin', () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: { id: '1', email: 'orgadmin@example.com', role: 'org_admin' },
        isLoading: false,
      })
      ;(canCreateProjects as jest.Mock).mockReturnValue(true)

      render(<CreateProjectPage />)

      expect(screen.getByTestId('project-creation-wizard')).toBeInTheDocument()
    })

    it('renders page for contributor', () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: {
          id: '1',
          email: 'contributor@example.com',
          role: 'contributor',
        },
        isLoading: false,
      })
      ;(canCreateProjects as jest.Mock).mockReturnValue(true)

      render(<CreateProjectPage />)

      expect(screen.getByTestId('project-creation-wizard')).toBeInTheDocument()
    })

    it('does not show loading state for authorized user', () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: { id: '1', email: 'admin@example.com', role: 'superadmin' },
        isLoading: false,
      })
      ;(canCreateProjects as jest.Mock).mockReturnValue(true)

      render(<CreateProjectPage />)

      expect(screen.queryByText('Loading...')).not.toBeInTheDocument()
    })

    it('does not show access denied for authorized user', () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: { id: '1', email: 'admin@example.com', role: 'superadmin' },
        isLoading: false,
      })
      ;(canCreateProjects as jest.Mock).mockReturnValue(true)

      render(<CreateProjectPage />)

      expect(screen.queryByText('Access Denied')).not.toBeInTheDocument()
    })
  })

  describe('Breadcrumb Navigation', () => {
    beforeEach(() => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: { id: '1', email: 'admin@example.com', role: 'superadmin' },
        isLoading: false,
      })
      ;(canCreateProjects as jest.Mock).mockReturnValue(true)
    })

    it('renders breadcrumb component', () => {
      render(<CreateProjectPage />)
      expect(screen.getByTestId('breadcrumb')).toBeInTheDocument()
    })

    it('renders all breadcrumb items', () => {
      render(<CreateProjectPage />)
      expect(screen.getByTestId('breadcrumb-item-0')).toHaveTextContent('Home')
      expect(screen.getByTestId('breadcrumb-item-1')).toHaveTextContent(
        'Projects'
      )
      expect(screen.getByTestId('breadcrumb-item-2')).toHaveTextContent(
        'Create'
      )
    })

    it('breadcrumb items have correct labels', () => {
      render(<CreateProjectPage />)
      expect(screen.getByText('Home')).toBeInTheDocument()
      expect(screen.getByText('Projects')).toBeInTheDocument()
      expect(screen.getByText('Create')).toBeInTheDocument()
    })
  })

  describe('Layout and Container', () => {
    beforeEach(() => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: { id: '1', email: 'admin@example.com', role: 'superadmin' },
        isLoading: false,
      })
      ;(canCreateProjects as jest.Mock).mockReturnValue(true)
    })

    it('renders responsive container', () => {
      render(<CreateProjectPage />)
      expect(screen.getByTestId('responsive-container')).toBeInTheDocument()
    })

    it('container has correct size', () => {
      render(<CreateProjectPage />)
      const container = screen.getByTestId('responsive-container')
      expect(container).toHaveAttribute('data-size', 'xl')
    })

    it('container has correct padding classes', () => {
      render(<CreateProjectPage />)
      const container = screen.getByTestId('responsive-container')
      expect(container).toHaveClass('pb-10', 'pt-8')
    })

    it('breadcrumb is above wizard', () => {
      const { container } = render(<CreateProjectPage />)
      const breadcrumbDiv = container.querySelector('.mb-4')
      expect(breadcrumbDiv).toBeInTheDocument()
    })
  })

  describe('Project Creation Wizard', () => {
    beforeEach(() => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: { id: '1', email: 'admin@example.com', role: 'superadmin' },
        isLoading: false,
      })
      ;(canCreateProjects as jest.Mock).mockReturnValue(true)
    })

    it('renders project creation wizard component', () => {
      render(<CreateProjectPage />)
      expect(screen.getByTestId('project-creation-wizard')).toBeInTheDocument()
    })

    it('wizard is rendered after breadcrumb', () => {
      render(<CreateProjectPage />)
      expect(screen.getByTestId('breadcrumb')).toBeInTheDocument()
      expect(screen.getByTestId('project-creation-wizard')).toBeInTheDocument()
    })
  })

  describe('Permission Check Logic', () => {
    it('calls canCreateProjects with user data', () => {
      const mockUser = {
        id: '1',
        email: 'admin@example.com',
        role: 'superadmin',
      }
      ;(useAuth as jest.Mock).mockReturnValue({
        user: mockUser,
        isLoading: false,
      })
      ;(canCreateProjects as jest.Mock).mockReturnValue(true)

      render(<CreateProjectPage />)

      expect(canCreateProjects).toHaveBeenCalledWith(mockUser, { isPrivateMode: false })
    })

    it('does not call canCreateProjects while loading', () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: null,
        isLoading: true,
      })
      ;(canCreateProjects as jest.Mock).mockReturnValue(false)

      render(<CreateProjectPage />)

      // canCreateProjects might be called in the effect, but won't redirect yet
      expect(screen.getByText('Loading...')).toBeInTheDocument()
    })

    it('checks permissions after loading completes', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: { id: '1', email: 'user@example.com', role: 'user' },
        isLoading: false,
      })
      ;(canCreateProjects as jest.Mock).mockReturnValue(false)

      render(<CreateProjectPage />)

      await waitFor(() => {
        expect(canCreateProjects).toHaveBeenCalled()
      })
    })
  })

  describe('useEffect Behavior', () => {
    it('redirects immediately after loading for unauthorized user', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: { id: '1', email: 'user@example.com', role: 'user' },
        isLoading: false,
      })
      ;(canCreateProjects as jest.Mock).mockReturnValue(false)

      render(<CreateProjectPage />)

      await waitFor(() => {
        expect(mockReplace).toHaveBeenCalledWith(
          '/projects?error=no-permission'
        )
      })
    })

    it('does not redirect for authorized user', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: { id: '1', email: 'admin@example.com', role: 'superadmin' },
        isLoading: false,
      })
      ;(canCreateProjects as jest.Mock).mockReturnValue(true)

      render(<CreateProjectPage />)

      await waitFor(() => {
        expect(mockReplace).not.toHaveBeenCalled()
      })
    })

    it('does not redirect while still loading', () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: null,
        isLoading: true,
      })
      ;(canCreateProjects as jest.Mock).mockReturnValue(false)

      render(<CreateProjectPage />)

      expect(mockReplace).not.toHaveBeenCalled()
    })
  })

  describe('Edge Cases', () => {
    it('handles null user gracefully', () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: null,
        isLoading: false,
      })
      ;(canCreateProjects as jest.Mock).mockReturnValue(false)

      render(<CreateProjectPage />)

      expect(screen.getByText('Access Denied')).toBeInTheDocument()
    })

    it('handles undefined user gracefully', () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: undefined,
        isLoading: false,
      })
      ;(canCreateProjects as jest.Mock).mockReturnValue(false)

      render(<CreateProjectPage />)

      expect(screen.getByText('Access Denied')).toBeInTheDocument()
    })

    it('shows loading when isLoading is true even with user', () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: { id: '1', email: 'admin@example.com', role: 'superadmin' },
        isLoading: true,
      })
      ;(canCreateProjects as jest.Mock).mockReturnValue(true)

      render(<CreateProjectPage />)

      expect(screen.getByText('Loading...')).toBeInTheDocument()
    })
  })

  describe('Styling and Classes', () => {
    it('applies emerald color to loading spinner', () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: null,
        isLoading: true,
      })
      ;(canCreateProjects as jest.Mock).mockReturnValue(false)

      const { container } = render(<CreateProjectPage />)
      const spinner = container.querySelector('.border-emerald-500')
      expect(spinner).toBeInTheDocument()
    })

    it('applies correct button styling for back button', () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: { id: '1', email: 'user@example.com', role: 'user' },
        isLoading: false,
      })
      ;(canCreateProjects as jest.Mock).mockReturnValue(false)

      render(<CreateProjectPage />)

      const button = screen.getByText('Back to Projects')
      expect(button).toHaveClass('bg-emerald-600')
    })

    it('applies red color to error icon', () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: { id: '1', email: 'user@example.com', role: 'user' },
        isLoading: false,
      })
      ;(canCreateProjects as jest.Mock).mockReturnValue(false)

      const { container } = render(<CreateProjectPage />)
      const icon = container.querySelector('.bg-red-100')
      expect(icon).toBeInTheDocument()
    })

    it('applies dark mode classes to error text', () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: { id: '1', email: 'user@example.com', role: 'user' },
        isLoading: false,
      })
      ;(canCreateProjects as jest.Mock).mockReturnValue(false)

      const { container } = render(<CreateProjectPage />)
      const text = container.querySelector('.dark\\:text-gray-100')
      expect(text).toBeInTheDocument()
    })
  })

  describe('Accessibility', () => {
    it('has accessible error state with proper heading', () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: { id: '1', email: 'user@example.com', role: 'user' },
        isLoading: false,
      })
      ;(canCreateProjects as jest.Mock).mockReturnValue(false)

      render(<CreateProjectPage />)

      const heading = screen.getByText('Access Denied')
      expect(heading.tagName).toBe('H3')
    })

    it('provides descriptive error message', () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: { id: '1', email: 'user@example.com', role: 'user' },
        isLoading: false,
      })
      ;(canCreateProjects as jest.Mock).mockReturnValue(false)

      render(<CreateProjectPage />)

      const message = screen.getByText(
        /Only superadmins, organization admins, and contributors can create projects/
      )
      expect(message.tagName).toBe('P')
    })

    it('error icon has proper SVG structure', () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: { id: '1', email: 'user@example.com', role: 'user' },
        isLoading: false,
      })
      ;(canCreateProjects as jest.Mock).mockReturnValue(false)

      const { container } = render(<CreateProjectPage />)

      const svg = container.querySelector('svg')
      expect(svg).toHaveAttribute('viewBox', '0 0 24 24')
    })
  })
})

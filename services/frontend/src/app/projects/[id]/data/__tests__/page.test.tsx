/**
 * @jest-environment jsdom
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// Mock React.use() BEFORE any imports that use it
jest.mock('react', () => {
  const actualReact = jest.requireActual('react')
  return {
    ...actualReact,
    use: jest.fn((value: any) => value),
  }
})

// Mock next/navigation
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
  useParams: jest.fn(),
  useSearchParams: jest.fn(),
  usePathname: jest.fn(),
}))

// Mock contexts
jest.mock('@/contexts/AuthContext')
jest.mock('@/contexts/I18nContext')

// Mock store
jest.mock('@/stores/projectStore')

// Mock permissions utility
jest.mock('@/utils/permissions')

// Mock subdomain utility
jest.mock('@/lib/utils/subdomain', () => ({
  parseSubdomain: jest.fn(() => ({ orgSlug: null, isPrivateMode: false })),
}))

// Mock components
jest.mock('@/components/projects/tabs/AnnotationTab', () => ({
  AnnotationTab: ({ projectId }: { projectId: string }) => (
    <div data-testid="annotation-tab">AnnotationTab for {projectId}</div>
  ),
}))

jest.mock('@/components/shared/Breadcrumb', () => ({
  Breadcrumb: ({ items }: { items: any[] }) => (
    <nav data-testid="breadcrumb">
      {items.map((item, i) => (
        <span key={i}>{item.label}</span>
      ))}
    </nav>
  ),
}))

import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { useProjectStore } from '@/stores/projectStore'
import { canAccessProjectData } from '@/utils/permissions'
import { useRouter } from 'next/navigation'
import * as React from 'react'
import ProjectDataPage from '../page'

// Mock data
const mockProject = {
  id: 'test-project-id',
  title: 'Test Project',
  description: 'Test Description',
  created_at: '2025-01-01T00:00:00Z',
  updated_at: '2025-01-01T00:00:00Z',
}

const mockUser = {
  id: 'test-user-id',
  username: 'testuser',
  email: 'test@example.com',
  name: 'Test User',
  is_superadmin: false,
  is_active: true,
  role: 'CONTRIBUTOR',
}

describe('ProjectDataPage', () => {
  const mockRouter = {
    push: jest.fn(),
    replace: jest.fn(),
    back: jest.fn(),
    forward: jest.fn(),
    refresh: jest.fn(),
    prefetch: jest.fn(),
  }

  const mockT = jest.fn((key: string) => key)
  const mockFetchProject = jest.fn()

  beforeEach(() => {
    jest.clearAllMocks()

    // Setup React.use mock to unwrap promises
    ;(React.use as jest.Mock).mockImplementation((value: any) => {
      if (value && typeof value.then === 'function') {
        // For Promises, return resolved value
        return { id: 'test-project-id' }
      }
      return value
    })

    // Setup router mock
    ;(useRouter as jest.Mock).mockReturnValue(mockRouter)

    // Setup i18n mock
    ;(useI18n as jest.Mock).mockReturnValue({
      t: mockT,
      changeLanguage: jest.fn(),
      currentLanguage: 'en',
      languages: ['en', 'de'],
    })

    // Setup auth mock
    ;(useAuth as jest.Mock).mockReturnValue({
      user: mockUser,
      isLoading: false,
    })

    // Setup project store mock
    ;(useProjectStore as jest.Mock).mockReturnValue({
      currentProject: mockProject,
      fetchProject: mockFetchProject,
    })

    // Setup permissions mock
    ;(canAccessProjectData as jest.Mock).mockReturnValue(true)
  })

  describe('Loading States', () => {
    it('should render loading state when auth is loading', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: null,
        isLoading: true,
      })

      const params = Promise.resolve({ id: 'test-project-id' })
      render(<ProjectDataPage params={params} />)

      await waitFor(() => {
        expect(screen.getByText('project.loading')).toBeInTheDocument()
      })

      const spinner = document.querySelector('.animate-spin')
      expect(spinner).toBeInTheDocument()
    })

    it('should render loading state when project is not loaded', async () => {
      ;(useProjectStore as jest.Mock).mockReturnValue({
        currentProject: null,
        fetchProject: mockFetchProject,
      })

      const params = Promise.resolve({ id: 'test-project-id' })
      render(<ProjectDataPage params={params} />)

      await waitFor(() => {
        expect(screen.getByText('project.loading')).toBeInTheDocument()
      })
    })

    it('should show loading spinner while checking permissions', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: null,
        isLoading: true,
      })

      const params = Promise.resolve({ id: 'test-project-id' })
      render(<ProjectDataPage params={params} />)

      await waitFor(() => {
        const spinner = document.querySelector('.animate-spin')
        expect(spinner).toBeInTheDocument()
        expect(spinner).toHaveClass('border-emerald-500')
      })
    })
  })

  describe('Permission Checks', () => {
    it('should redirect when user cannot access project data', async () => {
      ;(canAccessProjectData as jest.Mock).mockReturnValue(false)

      const params = Promise.resolve({ id: 'test-project-id' })
      render(<ProjectDataPage params={params} />)

      await waitFor(() => {
        expect(mockRouter.replace).toHaveBeenCalledWith(
          '/projects/test-project-id?error=no-data-access'
        )
      })
    })

    it('should show access denied message when user cannot access', async () => {
      ;(canAccessProjectData as jest.Mock).mockReturnValue(false)

      const params = Promise.resolve({ id: 'test-project-id' })
      render(<ProjectDataPage params={params} />)

      await waitFor(() => {
        expect(
          screen.getByText('projects.data.accessDenied')
        ).toBeInTheDocument()
        expect(
          screen.getByText('projects.data.accessDeniedDescription')
        ).toBeInTheDocument()
      })
    })

    it('should render error icon on access denied page', async () => {
      ;(canAccessProjectData as jest.Mock).mockReturnValue(false)

      const params = Promise.resolve({ id: 'test-project-id' })
      const { container } = render(<ProjectDataPage params={params} />)

      await waitFor(() => {
        const errorIcon = container.querySelector('.text-red-600')
        expect(errorIcon).toBeInTheDocument()
      })
    })

    it('should render back button on access denied page', async () => {
      ;(canAccessProjectData as jest.Mock).mockReturnValue(false)

      const params = Promise.resolve({ id: 'test-project-id' })
      render(<ProjectDataPage params={params} />)

      await waitFor(() => {
        const button = screen.getByText('projects.data.backToOverview')
        expect(button).toBeInTheDocument()
        expect(button).toHaveClass('bg-emerald-600')
      })
    })

    it('should allow access for superadmin users', async () => {
      const superadminUser = { ...mockUser, is_superadmin: true }
      ;(useAuth as jest.Mock).mockReturnValue({
        user: superadminUser,
        isLoading: false,
      })
      ;(canAccessProjectData as jest.Mock).mockReturnValue(true)

      const params = Promise.resolve({ id: 'test-project-id' })
      render(<ProjectDataPage params={params} />)

      await waitFor(() => {
        expect(screen.getByTestId('annotation-tab')).toBeInTheDocument()
      })
    })

    it('should allow access for org_admin users', async () => {
      const orgAdminUser = { ...mockUser, role: 'ORG_ADMIN' }
      ;(useAuth as jest.Mock).mockReturnValue({
        user: orgAdminUser,
        isLoading: false,
      })
      ;(canAccessProjectData as jest.Mock).mockReturnValue(true)

      const params = Promise.resolve({ id: 'test-project-id' })
      render(<ProjectDataPage params={params} />)

      await waitFor(() => {
        expect(screen.getByTestId('annotation-tab')).toBeInTheDocument()
      })
    })

    it('should allow access for contributor users', async () => {
      ;(canAccessProjectData as jest.Mock).mockReturnValue(true)

      const params = Promise.resolve({ id: 'test-project-id' })
      render(<ProjectDataPage params={params} />)

      await waitFor(() => {
        expect(screen.getByTestId('annotation-tab')).toBeInTheDocument()
      })
    })

    it('should deny access for annotator users', async () => {
      const annotatorUser = { ...mockUser, role: 'ANNOTATOR' }
      ;(useAuth as jest.Mock).mockReturnValue({
        user: annotatorUser,
        isLoading: false,
      })
      ;(canAccessProjectData as jest.Mock).mockReturnValue(false)

      const params = Promise.resolve({ id: 'test-project-id' })
      render(<ProjectDataPage params={params} />)

      await waitFor(() => {
        expect(
          screen.getByText('projects.data.accessDenied')
        ).toBeInTheDocument()
      })
    })

    it('should not redirect when user has proper permissions', async () => {
      ;(canAccessProjectData as jest.Mock).mockReturnValue(true)

      const params = Promise.resolve({ id: 'test-project-id' })
      render(<ProjectDataPage params={params} />)

      await waitFor(() => {
        expect(screen.getByTestId('annotation-tab')).toBeInTheDocument()
      })

      expect(mockRouter.replace).not.toHaveBeenCalled()
    })
  })

  describe('Project Loading', () => {
    it('should fetch project if not already loaded', async () => {
      ;(useProjectStore as jest.Mock).mockReturnValue({
        currentProject: null,
        fetchProject: mockFetchProject,
      })

      const params = Promise.resolve({ id: 'test-project-id' })
      render(<ProjectDataPage params={params} />)

      await waitFor(() => {
        expect(mockFetchProject).toHaveBeenCalledWith('test-project-id')
      })
    })

    it('should fetch project if different project is loaded', async () => {
      const differentProject = { ...mockProject, id: 'different-id' }
      ;(useProjectStore as jest.Mock).mockReturnValue({
        currentProject: differentProject,
        fetchProject: mockFetchProject,
      })

      const params = Promise.resolve({ id: 'test-project-id' })
      render(<ProjectDataPage params={params} />)

      await waitFor(() => {
        expect(mockFetchProject).toHaveBeenCalledWith('test-project-id')
      })
    })

    it('should not fetch project if correct project is already loaded', async () => {
      ;(useProjectStore as jest.Mock).mockReturnValue({
        currentProject: mockProject,
        fetchProject: mockFetchProject,
      })

      const params = Promise.resolve({ id: 'test-project-id' })
      render(<ProjectDataPage params={params} />)

      await waitFor(() => {
        expect(screen.getByTestId('annotation-tab')).toBeInTheDocument()
      })

      expect(mockFetchProject).not.toHaveBeenCalled()
    })
  })

  describe('Page Rendering', () => {
    it('should render page content when user has access and project is loaded', async () => {
      const params = Promise.resolve({ id: 'test-project-id' })
      render(<ProjectDataPage params={params} />)

      await waitFor(() => {
        expect(screen.getByTestId('breadcrumb')).toBeInTheDocument()
        expect(screen.getByTestId('annotation-tab')).toBeInTheDocument()
      })
    })

    it('should render breadcrumb with correct navigation items', async () => {
      const params = Promise.resolve({ id: 'test-project-id' })
      render(<ProjectDataPage params={params} />)

      await waitFor(() => {
        const breadcrumb = screen.getByTestId('breadcrumb')
        expect(breadcrumb).toHaveTextContent('navigation.projects')
        expect(breadcrumb).toHaveTextContent(mockProject.title)
        expect(breadcrumb).toHaveTextContent('navigation.projectData')
      })
    })

    it('should render annotation tab with correct project ID', async () => {
      const params = Promise.resolve({ id: 'test-project-id' })
      render(<ProjectDataPage params={params} />)

      await waitFor(() => {
        expect(screen.getByTestId('annotation-tab')).toHaveTextContent(
          'test-project-id'
        )
      })
    })

    it('should render proper layout structure', async () => {
      const params = Promise.resolve({ id: 'test-project-id' })
      const { container } = render(<ProjectDataPage params={params} />)

      await waitFor(() => {
        const layout = container.querySelector('.min-h-screen')
        expect(layout).toBeInTheDocument()
        expect(layout).toHaveClass('bg-zinc-50', 'dark:bg-zinc-900')
      })
    })

    it('should render header with border', async () => {
      const params = Promise.resolve({ id: 'test-project-id' })
      const { container } = render(<ProjectDataPage params={params} />)

      await waitFor(() => {
        const header = container.querySelector('.border-b')
        expect(header).toBeInTheDocument()
        expect(header).toHaveClass('border-zinc-200', 'dark:border-zinc-800')
      })
    })
  })

  describe('Navigation', () => {
    it('should navigate back to project overview from access denied page', async () => {
      ;(canAccessProjectData as jest.Mock).mockReturnValue(false)
      const user = userEvent.setup()

      const params = Promise.resolve({ id: 'test-project-id' })
      render(<ProjectDataPage params={params} />)

      await waitFor(() => {
        const button = screen.getByText('projects.data.backToOverview')
        expect(button).toBeInTheDocument()
      })

      const button = screen.getByText('projects.data.backToOverview')
      await user.click(button)

      expect(mockRouter.push).toHaveBeenCalledWith('/projects/test-project-id')
    })

    it('should handle project ID from params correctly', async () => {
      ;(React.use as jest.Mock).mockReturnValue({ id: 'custom-project-id' })
      ;(useProjectStore as jest.Mock).mockReturnValue({
        currentProject: { ...mockProject, id: 'custom-project-id' },
        fetchProject: mockFetchProject,
      })

      const params = Promise.resolve({ id: 'custom-project-id' })
      render(<ProjectDataPage params={params} />)

      await waitFor(() => {
        expect(screen.getByTestId('annotation-tab')).toHaveTextContent(
          'custom-project-id'
        )
      })
    })
  })

  describe('Translation Keys', () => {
    it('should use correct translation keys for navigation', async () => {
      const params = Promise.resolve({ id: 'test-project-id' })
      render(<ProjectDataPage params={params} />)

      await waitFor(() => {
        expect(mockT).toHaveBeenCalledWith('navigation.projects')
        expect(mockT).toHaveBeenCalledWith('navigation.projectData')
      })
    })

    it('should use correct translation key for loading state', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: mockUser,
        isLoading: true,
      })

      const params = Promise.resolve({ id: 'test-project-id' })
      render(<ProjectDataPage params={params} />)

      await waitFor(() => {
        expect(mockT).toHaveBeenCalledWith('project.loading')
      })
    })

    it('should use correct translation keys for access denied', async () => {
      ;(canAccessProjectData as jest.Mock).mockReturnValue(false)

      const params = Promise.resolve({ id: 'test-project-id' })
      render(<ProjectDataPage params={params} />)

      await waitFor(() => {
        expect(mockT).toHaveBeenCalledWith('projects.data.accessDenied')
        expect(mockT).toHaveBeenCalledWith(
          'projects.data.accessDeniedDescription'
        )
        expect(mockT).toHaveBeenCalledWith('projects.data.backToOverview')
      })
    })
  })

  describe('Effect Hooks', () => {
    it('should check permissions when auth loading completes', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: mockUser,
        isLoading: false,
      })
      ;(canAccessProjectData as jest.Mock).mockReturnValue(true)

      const params = Promise.resolve({ id: 'test-project-id' })
      render(<ProjectDataPage params={params} />)

      await waitFor(() => {
        expect(canAccessProjectData).toHaveBeenCalledWith(
          mockUser,
          expect.objectContaining({ isPrivateMode: false })
        )
      })
    })

    it('should redirect on permission check failure', async () => {
      ;(canAccessProjectData as jest.Mock).mockReturnValue(false)

      const params = Promise.resolve({ id: 'test-project-id' })
      render(<ProjectDataPage params={params} />)

      await waitFor(() => {
        expect(mockRouter.replace).toHaveBeenCalledWith(
          '/projects/test-project-id?error=no-data-access'
        )
      })
    })

    it('should not check permissions while loading', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: null,
        isLoading: true,
      })

      const params = Promise.resolve({ id: 'test-project-id' })
      render(<ProjectDataPage params={params} />)

      await waitFor(() => {
        expect(screen.getByText('project.loading')).toBeInTheDocument()
      })

      expect(mockRouter.replace).not.toHaveBeenCalled()
    })
  })

  describe('Edge Cases', () => {
    it('should handle null user gracefully', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: null,
        isLoading: false,
      })
      ;(canAccessProjectData as jest.Mock).mockReturnValue(false)

      const params = Promise.resolve({ id: 'test-project-id' })
      render(<ProjectDataPage params={params} />)

      await waitFor(() => {
        expect(mockRouter.replace).toHaveBeenCalledWith(
          '/projects/test-project-id?error=no-data-access'
        )
      })
    })

    it('should handle project with special characters in ID', async () => {
      const specialId = 'project-123-abc'
      ;(React.use as jest.Mock).mockReturnValue({ id: specialId })
      ;(useProjectStore as jest.Mock).mockReturnValue({
        currentProject: { ...mockProject, id: specialId },
        fetchProject: mockFetchProject,
      })

      const params = Promise.resolve({ id: specialId })
      render(<ProjectDataPage params={params} />)

      await waitFor(() => {
        expect(screen.getByTestId('annotation-tab')).toHaveTextContent(
          specialId
        )
      })
    })

    it('should handle project title in breadcrumb', async () => {
      const projectWithLongTitle = {
        ...mockProject,
        title: 'Very Long Project Title That Should Still Display Correctly',
      }
      ;(useProjectStore as jest.Mock).mockReturnValue({
        currentProject: projectWithLongTitle,
        fetchProject: mockFetchProject,
      })

      const params = Promise.resolve({ id: 'test-project-id' })
      render(<ProjectDataPage params={params} />)

      await waitFor(() => {
        const breadcrumb = screen.getByTestId('breadcrumb')
        expect(breadcrumb).toHaveTextContent(projectWithLongTitle.title)
      })
    })

    it('should render dark mode styles correctly', async () => {
      const params = Promise.resolve({ id: 'test-project-id' })
      const { container } = render(<ProjectDataPage params={params} />)

      await waitFor(() => {
        const layout = container.querySelector('.dark\\:bg-zinc-900')
        expect(layout).toBeInTheDocument()
      })
    })
  })

  describe('Component Integration', () => {
    it('should pass correct props to AnnotationTab', async () => {
      const params = Promise.resolve({ id: 'test-project-id' })
      render(<ProjectDataPage params={params} />)

      await waitFor(() => {
        const annotationTab = screen.getByTestId('annotation-tab')
        expect(annotationTab).toHaveTextContent(
          'AnnotationTab for test-project-id'
        )
      })
    })

    it('should pass correct items to Breadcrumb', async () => {
      const params = Promise.resolve({ id: 'test-project-id' })
      render(<ProjectDataPage params={params} />)

      await waitFor(() => {
        const breadcrumb = screen.getByTestId('breadcrumb')
        // Breadcrumb includes: Dashboard, Projects, Project Title, Project Data
        expect(breadcrumb.children).toHaveLength(4)
      })
    })
  })

  describe('Multiple Renders', () => {
    it('should handle rerender with same project', async () => {
      const params = Promise.resolve({ id: 'test-project-id' })
      const { rerender } = render(<ProjectDataPage params={params} />)

      await waitFor(() => {
        expect(screen.getByTestId('annotation-tab')).toBeInTheDocument()
      })

      rerender(<ProjectDataPage params={params} />)

      await waitFor(() => {
        expect(screen.getByTestId('annotation-tab')).toBeInTheDocument()
      })
    })

    it('should handle rerender with different project', async () => {
      ;(React.use as jest.Mock).mockReturnValueOnce({ id: 'project-1' })
      const mockFetchProject1 = jest.fn()
      ;(useProjectStore as jest.Mock).mockReturnValue({
        currentProject: { ...mockProject, id: 'project-1' },
        fetchProject: mockFetchProject1,
      })

      const params1 = Promise.resolve({ id: 'project-1' })
      const { rerender } = render(<ProjectDataPage params={params1} />)

      await waitFor(() => {
        expect(screen.getByTestId('annotation-tab')).toBeInTheDocument()
      })

      // Now update the mock to return project-2
      ;(React.use as jest.Mock).mockReturnValueOnce({ id: 'project-2' })
      const mockFetchProject2 = jest.fn()
      ;(useProjectStore as jest.Mock).mockReturnValue({
        currentProject: { ...mockProject, id: 'project-1' }, // Still has project-1, should trigger fetch
        fetchProject: mockFetchProject2,
      })

      const params2 = Promise.resolve({ id: 'project-2' })
      rerender(<ProjectDataPage params={params2} />)

      await waitFor(() => {
        expect(mockFetchProject2).toHaveBeenCalledWith('project-2')
      })
    })
  })

  describe('Access Denied UI Elements', () => {
    it('should render access denied background styling', async () => {
      ;(canAccessProjectData as jest.Mock).mockReturnValue(false)

      const params = Promise.resolve({ id: 'test-project-id' })
      const { container } = render(<ProjectDataPage params={params} />)

      await waitFor(() => {
        const bgElement = container.querySelector('.bg-zinc-50')
        expect(bgElement).toBeInTheDocument()
      })
    })

    it('should render error icon container with correct styles', async () => {
      ;(canAccessProjectData as jest.Mock).mockReturnValue(false)

      const params = Promise.resolve({ id: 'test-project-id' })
      const { container } = render(<ProjectDataPage params={params} />)

      await waitFor(() => {
        const iconContainer = container.querySelector('.bg-red-100')
        expect(iconContainer).toBeInTheDocument()
      })
    })

    it('should render SVG warning icon', async () => {
      ;(canAccessProjectData as jest.Mock).mockReturnValue(false)

      const params = Promise.resolve({ id: 'test-project-id' })
      const { container } = render(<ProjectDataPage params={params} />)

      await waitFor(() => {
        const svg = container.querySelector('svg')
        expect(svg).toBeInTheDocument()
        expect(svg).toHaveAttribute('viewBox', '0 0 24 24')
      })
    })
  })

  describe('Loading State UI Elements', () => {
    it('should render loading container with flex centering', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: null,
        isLoading: true,
      })

      const params = Promise.resolve({ id: 'test-project-id' })
      const { container } = render(<ProjectDataPage params={params} />)

      await waitFor(() => {
        const loadingContainer = container.querySelector(
          '.items-center.justify-center'
        )
        expect(loadingContainer).toBeInTheDocument()
      })
    })

    it('should render spinner with emerald color scheme', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: null,
        isLoading: true,
      })

      const params = Promise.resolve({ id: 'test-project-id' })
      const { container } = render(<ProjectDataPage params={params} />)

      await waitFor(() => {
        const spinner = container.querySelector('.border-emerald-500')
        expect(spinner).toBeInTheDocument()
        expect(spinner).toHaveClass('rounded-full')
      })
    })
  })

  describe('Breadcrumb Navigation', () => {
    it('should render breadcrumb with Projects link', async () => {
      const params = Promise.resolve({ id: 'test-project-id' })
      render(<ProjectDataPage params={params} />)

      await waitFor(() => {
        expect(mockT).toHaveBeenCalledWith('navigation.projects')
        const breadcrumb = screen.getByTestId('breadcrumb')
        expect(breadcrumb).toHaveTextContent('navigation.projects')
      })
    })

    it('should render breadcrumb with project title', async () => {
      const params = Promise.resolve({ id: 'test-project-id' })
      render(<ProjectDataPage params={params} />)

      await waitFor(() => {
        const breadcrumb = screen.getByTestId('breadcrumb')
        expect(breadcrumb).toHaveTextContent(mockProject.title)
      })
    })

    it('should render breadcrumb with Project Data link', async () => {
      const params = Promise.resolve({ id: 'test-project-id' })
      render(<ProjectDataPage params={params} />)

      await waitFor(() => {
        expect(mockT).toHaveBeenCalledWith('navigation.projectData')
        const breadcrumb = screen.getByTestId('breadcrumb')
        expect(breadcrumb).toHaveTextContent('navigation.projectData')
      })
    })
  })
})

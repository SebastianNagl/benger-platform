/**
 * @jest-environment jsdom
 */

import { projectsAPI } from '@/lib/api/projects'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import GenerationPage from '../page'

// Mock API
jest.mock('@/lib/api/projects')

// Mock navigation
const mockPush = jest.fn()
const mockReplace = jest.fn()
const mockSearchParams = new URLSearchParams()

jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mockPush,
    replace: mockReplace,
    prefetch: jest.fn(),
    back: jest.fn(),
    forward: jest.fn(),
    refresh: jest.fn(),
  }),
  usePathname: () => '/generations',
  useSearchParams: () => mockSearchParams,
}))

// Mock Toast context
const mockAddToast = jest.fn()
jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({
    addToast: mockAddToast,
    removeToast: jest.fn(),
  }),
}))

// Mock AuthContext with authenticated user who has access to project data
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: {
      id: 'test-user-id',
      username: 'testuser',
      email: 'test@example.com',
      is_superadmin: false,
      is_active: true,
      role: 'CONTRIBUTOR',
    },
    login: jest.fn(),
    logout: jest.fn(),
    isLoading: false,
    organizations: [],
    currentOrganization: { id: 'org-1', name: 'Test Org' },
    setCurrentOrganization: jest.fn(),
  }),
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
}))

// Mock I18n context
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, vars?: Record<string, any>) => {
      const translations: Record<string, string> = {
        'navigation.dashboard': 'Home',
        'navigation.generation': 'Generation',
        'generation.title': 'LLM Response Generation',
        'generation.project': 'Project',
        'generation.selectProject': 'Select project',
        'common.loading': 'Loading...',
        'dataManagement.accessDenied': 'Access Denied',
        'dataManagement.accessDeniedDescription': 'Only superadmins, organization admins, and contributors can access project data.',
        'common.backToProjects': 'Back to Projects',
      }
      let result = translations[key] || key
      if (vars) {
        Object.entries(vars).forEach(([k, v]) => {
          result = result.replace(`{${k}}`, String(v))
        })
      }
      return result
    },
  }),
}))

jest.mock('@/lib/utils/subdomain', () => ({
  parseSubdomain: () => ({ isPrivateMode: false, slug: null }),
}))

jest.mock('@/components/generation/GenerationTaskList', () => ({
  GenerationTaskList: ({ projectId }: { projectId: string }) => (
    <div data-testid="generation-task-list">
      <div>Project: {projectId}</div>
      <div>Task List Content</div>
    </div>
  ),
}))

jest.mock('@/components/shared/Breadcrumb', () => ({
  Breadcrumb: ({ items }: { items: any[] }) => (
    <div data-testid="breadcrumb">
      {items.map((item, i) => (
        <span key={i}>{item.label}</span>
      ))}
    </div>
  ),
}))

jest.mock('@/components/shared/Button', () => ({
  Button: ({
    children,
    onClick,
    variant,
    className,
    disabled,
  }: {
    children: React.ReactNode
    onClick?: () => void
    variant?: string
    className?: string
    disabled?: boolean
  }) => (
    <button onClick={onClick} data-variant={variant} className={className} disabled={disabled}>
      {children}
    </button>
  ),
}))

jest.mock('@/components/shared/Card', () => ({
  Card: ({
    children,
    className,
  }: {
    children: React.ReactNode
    className?: string
  }) => <div className={className}>{children}</div>,
}))

jest.mock('@/components/shared/ResponsiveContainer', () => ({
  ResponsiveContainer: ({
    children,
    size,
    className,
  }: {
    children: React.ReactNode
    size?: string
    className?: string
  }) => (
    <div data-size={size} className={className}>
      {children}
    </div>
  ),
}))

const mockProjects = [
  {
    id: 'project-1',
    title: 'Test Project',
    task_count: 10,
    generation_config: {
      selected_configuration: {
        models: ['gpt-4', 'claude-3'],
      },
    },
  },
  {
    id: 'project-2',
    title: 'Second Project',
    task_count: 5,
    generation_config: {
      selected_configuration: {
        models: ['gpt-4'],
      },
    },
  },
]

describe('GenerationPage', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockSearchParams.delete('projectId')
    ;(projectsAPI.list as jest.Mock).mockResolvedValue({
      items: mockProjects,
      total: 2,
    })
    // Clear localStorage
    localStorage.removeItem('generations_lastProjectId')
  })

  describe('Page Rendering', () => {
    it('renders the page with correct title and breadcrumb', async () => {
      render(<GenerationPage />)

      expect(screen.getByText('LLM Response Generation')).toBeInTheDocument()
      expect(screen.getByTestId('breadcrumb')).toBeInTheDocument()
      expect(screen.getByText('Home')).toBeInTheDocument()
      expect(screen.getByText('Generation')).toBeInTheDocument()
    })

    it('renders project dropdown with select prompt', async () => {
      render(<GenerationPage />)

      await waitFor(() => {
        expect(screen.getByText('Select project')).toBeInTheDocument()
      })
    })

    it('does not show GenerationTaskList initially', async () => {
      render(<GenerationPage />)

      expect(
        screen.queryByTestId('generation-task-list')
      ).not.toBeInTheDocument()
    })
  })

  describe('Project Selection', () => {
    it('shows project list when dropdown is clicked', async () => {
      const user = userEvent.setup()
      render(<GenerationPage />)

      await waitFor(() => {
        expect(screen.getByText('Select project')).toBeInTheDocument()
      })

      // Click dropdown button
      const dropdownButton = screen.getByText('Select project').closest('button')!
      await user.click(dropdownButton)

      await waitFor(() => {
        expect(screen.getByText('Test Project')).toBeInTheDocument()
        expect(screen.getByText('Second Project')).toBeInTheDocument()
      })
    })

    it('shows GenerationTaskList when project is selected', async () => {
      const user = userEvent.setup()
      render(<GenerationPage />)

      await waitFor(() => {
        expect(screen.getByText('Select project')).toBeInTheDocument()
      })

      // Open dropdown
      const dropdownButton = screen.getByText('Select project').closest('button')!
      await user.click(dropdownButton)

      await waitFor(() => {
        expect(screen.getByText('Test Project')).toBeInTheDocument()
      })

      // Select project
      await user.click(screen.getByText('Test Project'))

      await waitFor(() => {
        expect(screen.getByTestId('generation-task-list')).toBeInTheDocument()
        expect(screen.getByText('Project: project-1')).toBeInTheDocument()
      })
    })

    it('updates URL with projectId when project is selected', async () => {
      const user = userEvent.setup()
      render(<GenerationPage />)

      await waitFor(() => {
        expect(screen.getByText('Select project')).toBeInTheDocument()
      })

      // Open dropdown and select
      const dropdownButton = screen.getByText('Select project').closest('button')!
      await user.click(dropdownButton)

      await waitFor(() => {
        expect(screen.getByText('Test Project')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Test Project'))

      await waitFor(() => {
        expect(mockReplace).toHaveBeenCalledWith(
          expect.stringContaining('projectId=project-1'),
          { scroll: false }
        )
      })
    })

    it('shows task count for each project in dropdown', async () => {
      const user = userEvent.setup()
      render(<GenerationPage />)

      await waitFor(() => {
        expect(screen.getByText('Select project')).toBeInTheDocument()
      })

      const dropdownButton = screen.getByText('Select project').closest('button')!
      await user.click(dropdownButton)

      await waitFor(() => {
        expect(screen.getByText('10 tasks')).toBeInTheDocument()
        expect(screen.getByText('5 tasks')).toBeInTheDocument()
      })
    })
  })

  describe('URL Parameter Handling', () => {
    it('auto-loads project when projectId is in URL', async () => {
      mockSearchParams.set('projectId', 'project-1')

      render(<GenerationPage />)

      await waitFor(() => {
        expect(screen.getByTestId('generation-task-list')).toBeInTheDocument()
        expect(screen.getByText('Project: project-1')).toBeInTheDocument()
      })
    })

    it('does not auto-select when projectId in URL does not match any project', async () => {
      mockSearchParams.set('projectId', 'nonexistent-project')

      render(<GenerationPage />)

      await waitFor(() => {
        // Projects loaded but none matched
        expect(projectsAPI.list).toHaveBeenCalled()
      })

      expect(
        screen.queryByTestId('generation-task-list')
      ).not.toBeInTheDocument()
    })
  })

  describe('Error Handling', () => {
    it('handles project list fetch error gracefully', async () => {
      const consoleSpy = jest.spyOn(console, 'error').mockImplementation()
      ;(projectsAPI.list as jest.Mock).mockRejectedValue(new Error('Fetch failed'))

      render(<GenerationPage />)

      await waitFor(() => {
        expect(consoleSpy).toHaveBeenCalledWith(
          'Failed to load projects:',
          expect.any(Error)
        )
      })

      consoleSpy.mockRestore()
    })
  })

  describe('Project Info Display', () => {
    it('displays selected project title in dropdown', async () => {
      const user = userEvent.setup()
      render(<GenerationPage />)

      await waitFor(() => {
        expect(screen.getByText('Select project')).toBeInTheDocument()
      })

      // Open and select
      const dropdownButton = screen.getByText('Select project').closest('button')!
      await user.click(dropdownButton)

      await waitFor(() => {
        expect(screen.getByText('Test Project')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Test Project'))

      await waitFor(() => {
        // The dropdown button should now show the project title
        expect(screen.getByText('Test Project')).toBeInTheDocument()
      })
    })
  })
})

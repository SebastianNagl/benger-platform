/**
 * @jest-environment jsdom
 *
 * Branch coverage round 9: generations/page.tsx
 * Targets uncovered branches:
 * - isLoading state (loading spinner)
 * - Permission denied state (canAccessProjectData false)
 * - URL projectId auto-select: project found, project not found
 * - localStorage fallback for project selection
 * - Dropdown open/close behavior
 * - selectedProject rendering of GenerationTaskList
 */

import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import '@testing-library/jest-dom'

const mockPush = jest.fn()
const mockReplace = jest.fn()
let mockSearchParamsGet = jest.fn(() => null)

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
  useSearchParams: () => ({
    get: mockSearchParamsGet,
    toString: () => '',
  }),
}))

const mockAddToast = jest.fn()
jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({
    addToast: mockAddToast,
    removeToast: jest.fn(),
  }),
}))

let mockUser: any = {
  id: 'test-user',
  username: 'testuser',
  role: 'CONTRIBUTOR',
  is_superadmin: false,
  is_active: true,
}
let mockIsLoading = false

jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: mockUser,
    isLoading: mockIsLoading,
    organizations: [],
    currentOrganization: { id: 'org-1', name: 'Test Org' },
  }),
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, vars?: any) => {
      if (vars) return `${key}:${JSON.stringify(vars)}`
      return key
    },
    locale: 'en',
  }),
}))

jest.mock('@/lib/utils/subdomain', () => ({
  parseSubdomain: () => ({ isPrivateMode: false, slug: null }),
}))

jest.mock('@/utils/permissions', () => ({
  canAccessProjectData: (user: any, opts: any) => {
    if (!user) return false
    return user.role === 'CONTRIBUTOR' || user.role === 'admin' || user.is_superadmin
  },
}))

const mockProjectsList = jest.fn()
jest.mock('@/lib/api/projects', () => ({
  projectsAPI: {
    list: (...args: any[]) => mockProjectsList(...args),
  },
}))

jest.mock('@/lib/utils/logger', () => ({
  logger: { debug: jest.fn(), info: jest.fn(), warn: jest.fn(), error: jest.fn() },
}))

jest.mock('@/components/shared/Breadcrumb', () => ({
  Breadcrumb: ({ items }: any) => <nav>{items?.map((i: any, k: number) => <span key={k}>{i.label}</span>)}</nav>,
}))

jest.mock('@/components/shared/Button', () => ({
  Button: ({ children, onClick, disabled, ...props }: any) => (
    <button onClick={onClick} disabled={disabled} {...props}>{children}</button>
  ),
}))

jest.mock('@/components/shared/Card', () => ({
  Card: ({ children, className }: any) => <div className={className}>{children}</div>,
}))

jest.mock('@/components/shared/ResponsiveContainer', () => ({
  ResponsiveContainer: ({ children }: any) => <div>{children}</div>,
}))

jest.mock('@/components/generation/GenerationTaskList', () => ({
  GenerationTaskList: ({ projectId }: any) => (
    <div data-testid="generation-task-list">Tasks for {projectId}</div>
  ),
}))

const mockProjects = [
  {
    id: 'p1',
    title: 'Test Project',
    task_count: 10,
  },
  {
    id: 'p2',
    title: 'Second Project',
    task_count: 5,
  },
]

import GenerationPage from '../page'

describe('GenerationPage br9', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockUser = { id: 'test-user', username: 'testuser', role: 'CONTRIBUTOR', is_superadmin: false, is_active: true }
    mockIsLoading = false
    mockSearchParamsGet = jest.fn(() => null)
    mockProjectsList.mockResolvedValue({ items: mockProjects, total: 2 })
    localStorage.removeItem('generations_lastProjectId')
  })

  it('shows loading spinner when isLoading is true', () => {
    mockIsLoading = true
    render(<GenerationPage />)
    expect(screen.getByText('common.loading')).toBeInTheDocument()
  })

  it('shows permission denied when user has no access', () => {
    mockUser = { id: 'u1', username: 'test', role: 'ANNOTATOR', is_superadmin: false }
    render(<GenerationPage />)
    expect(screen.getByText('dataManagement.accessDenied')).toBeInTheDocument()
  })

  it('renders page title when user has access', () => {
    render(<GenerationPage />)
    expect(screen.getByText('generation.title')).toBeInTheDocument()
  })

  it('loads projects on mount', async () => {
    render(<GenerationPage />)

    await waitFor(() => {
      expect(mockProjectsList).toHaveBeenCalledWith(1, 100)
    })
  })

  it('shows project dropdown button', async () => {
    render(<GenerationPage />)

    await waitFor(() => {
      expect(screen.getByText('generation.selectProject')).toBeInTheDocument()
    })
  })

  it('selects project from dropdown and shows task list', async () => {
    render(<GenerationPage />)

    await waitFor(() => {
      expect(screen.getByText('generation.selectProject')).toBeInTheDocument()
    })

    // Click to open dropdown
    const dropdownButton = screen.getByText('generation.selectProject').closest('button')!
    await userEvent.click(dropdownButton)

    await waitFor(() => {
      expect(screen.getByText('Test Project')).toBeInTheDocument()
    })

    // Select a project
    await userEvent.click(screen.getByText('Test Project'))

    await waitFor(() => {
      expect(screen.getByTestId('generation-task-list')).toBeInTheDocument()
    })
  })

  it('auto-selects project from URL searchParam', async () => {
    mockSearchParamsGet = jest.fn((key: string) => key === 'projectId' ? 'p1' : null)

    render(<GenerationPage />)

    await waitFor(() => {
      expect(screen.getByTestId('generation-task-list')).toBeInTheDocument()
      expect(screen.getByText('Tasks for p1')).toBeInTheDocument()
    })
  })

  it('auto-selects project from localStorage', async () => {
    localStorage.setItem('generations_lastProjectId', 'p2')

    render(<GenerationPage />)

    await waitFor(() => {
      expect(screen.getByTestId('generation-task-list')).toBeInTheDocument()
      expect(screen.getByText('Tasks for p2')).toBeInTheDocument()
    })
  })

  it('handles back to projects button in permission denied state', async () => {
    mockUser = { id: 'u1', username: 'test', role: 'ANNOTATOR', is_superadmin: false }
    render(<GenerationPage />)

    const backBtn = screen.getByText('common.backToProjects')
    await userEvent.click(backBtn)

    expect(mockPush).toHaveBeenCalledWith('/projects')
  })

  it('handles project list fetch error gracefully', async () => {
    const consoleSpy = jest.spyOn(console, 'error').mockImplementation()
    mockProjectsList.mockRejectedValue(new Error('Network error'))

    render(<GenerationPage />)

    await waitFor(() => {
      expect(consoleSpy).toHaveBeenCalledWith(
        'Failed to load projects:',
        expect.any(Error)
      )
    })

    consoleSpy.mockRestore()
  })

  it('does not auto-select when URL projectId does not match', async () => {
    mockSearchParamsGet = jest.fn((key: string) => key === 'projectId' ? 'nonexistent' : null)

    render(<GenerationPage />)

    await waitFor(() => {
      expect(mockProjectsList).toHaveBeenCalled()
    })

    expect(screen.queryByTestId('generation-task-list')).not.toBeInTheDocument()
  })
})

/**
 * Additional branch coverage tests for My Tasks Page
 *
 * Focuses on branches not covered by existing page.coverage.test.tsx:
 * - Project ID mismatch triggering fetchProject
 * - Loading state when currentProject is null
 */

/**
 * @jest-environment jsdom
 */

import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { useProjectStore } from '@/stores/projectStore'
import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'
import { useParams, useRouter } from 'next/navigation'
import MyTasksPage from '../page'

jest.mock('next/navigation', () => ({
  useRouter: jest.fn(() => ({
    push: jest.fn(),
    replace: jest.fn(),
    back: jest.fn(),
    forward: jest.fn(),
    refresh: jest.fn(),
    prefetch: jest.fn(),
  })),
  useParams: jest.fn(() => ({ id: 'proj-1' })),
  useSearchParams: jest.fn(() => new URLSearchParams()),
  usePathname: jest.fn(() => '/'),
}))

jest.mock('@/contexts/AuthContext', () => ({
  useAuth: jest.fn(),
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: jest.fn(),
}))

jest.mock('@/stores/projectStore', () => ({
  useProjectStore: jest.fn(),
}))

jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({ addToast: jest.fn() }),
}))

// Prevent actual fetch calls
global.fetch = jest.fn().mockResolvedValue({
  ok: true,
  json: () => Promise.resolve({ tasks: [], total: 0, page: 1, page_size: 20, pages: 1 }),
})

describe('MyTasksPage Branch Coverage', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    ;(useAuth as jest.Mock).mockReturnValue({
      user: { id: 'u1', username: 'tester' },
    })
    ;(useI18n as jest.Mock).mockReturnValue({
      t: (key: string) => key,
    })
  })

  describe('Project loading branches', () => {
    it('shows loading state when projectLoading is true', () => {
      ;(useProjectStore as jest.Mock).mockReturnValue({
        currentProject: null,
        fetchProject: jest.fn(),
        loading: true,
      })
      render(<MyTasksPage />)
      expect(screen.getByText('common.loadingProject')).toBeInTheDocument()
    })

    it('shows loading when currentProject is null even if not projectLoading', () => {
      ;(useProjectStore as jest.Mock).mockReturnValue({
        currentProject: null,
        fetchProject: jest.fn(),
        loading: false,
      })
      render(<MyTasksPage />)
      expect(screen.getByText('common.loadingProject')).toBeInTheDocument()
    })

    it('triggers fetchProject when currentProject ID does not match route param', () => {
      const mockFetch = jest.fn()
      ;(useProjectStore as jest.Mock).mockReturnValue({
        currentProject: { id: 'different-project', title: 'Other Project' },
        fetchProject: mockFetch,
        loading: false,
      })
      render(<MyTasksPage />)
      expect(mockFetch).toHaveBeenCalledWith('proj-1')
    })

    it('does NOT trigger fetchProject when currentProject ID matches', () => {
      const mockFetch = jest.fn()
      ;(useProjectStore as jest.Mock).mockReturnValue({
        currentProject: { id: 'proj-1', title: 'My Project' },
        fetchProject: mockFetch,
        loading: false,
      })
      render(<MyTasksPage />)
      expect(mockFetch).not.toHaveBeenCalled()
    })

    it('renders page content when project is loaded', () => {
      ;(useProjectStore as jest.Mock).mockReturnValue({
        currentProject: { id: 'proj-1', title: 'My Project' },
        fetchProject: jest.fn(),
        loading: false,
      })
      render(<MyTasksPage />)
      expect(screen.getByText('tasks.myTasks.title')).toBeInTheDocument()
    })
  })
})

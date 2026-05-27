/**
 * Tests for the superadmin-only "Show all private projects" toggle on the
 * projects-list filter bar. The toggle defaults OFF (narrow view that hides
 * other users' private projects); flipping it on threads
 * include_all_private=true through to projectStore.fetchProjects and persists
 * the choice in localStorage so it survives refresh.
 *
 * @jest-environment jsdom
 */

import { useProjectStore } from '@/stores/projectStore'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useRouter } from 'next/navigation'
import { ProjectListTable } from '../ProjectListTable'

jest.mock('next/navigation', () => ({
  useRouter: jest.fn(() => ({ push: jest.fn() })),
  useParams: jest.fn(() => ({})),
  useSearchParams: jest.fn(() => new URLSearchParams()),
  usePathname: jest.fn(() => '/'),
  notFound: jest.fn(),
  redirect: jest.fn(),
}))

jest.mock('@/stores/projectStore', () => ({
  useProjectStore: jest.fn(),
}))

jest.mock('@/lib/api/projects', () => ({
  projectsAPI: {
    bulkDeleteProjects: jest.fn(),
    bulkExportProjects: jest.fn(),
    bulkExportFullProjects: jest.fn(),
    bulkArchiveProjects: jest.fn(),
    bulkUnarchiveProjects: jest.fn(),
    importProject: jest.fn(),
  },
}))

jest.mock('@/hooks/useDialogs', () => ({
  useConfirm: () => jest.fn(),
}))

jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({ addToast: jest.fn(), removeToast: jest.fn() }),
}))

// AuthContext is overridden per test via the `mockUser` ref below.
const mockUser = { current: { is_superadmin: false } as { is_superadmin: boolean } }
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: mockUser.current,
    isAuthenticated: true,
    isLoading: false,
    login: jest.fn(),
    logout: jest.fn(),
  }),
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => {
      if (key === 'projects.list.showAllPrivate') return 'Show all private projects'
      return key
    },
    locale: 'en',
  }),
}))

// Pass-through FilterToolbar mock so the toggle slot renders.
jest.mock('@/components/shared/FilterToolbar', () => {
  const FilterToolbar = ({ children }: any) => (
    <div data-testid="filter-toolbar">{children}</div>
  )
  // eslint-disable-next-line react/display-name
  FilterToolbar.Field = ({ label, children }: any) => (
    <div data-testid={`filter-field-${String(label)}`}>{children}</div>
  )
  return { FilterToolbar }
})

// Minimal ToggleSwitch surrogate exposing role="switch" + label, so we can
// assert visibility, default state, and clicks without HeadlessUI plumbing.
jest.mock('@/components/shared/ToggleSwitch', () => ({
  ToggleSwitch: ({
    enabled,
    onChange,
  }: { enabled: boolean; onChange: (next: boolean) => void }) => (
    <button
      role="switch"
      aria-checked={enabled}
      onClick={() => onChange(!enabled)}
      data-testid="superadmin-private-toggle"
    >
      {enabled ? 'on' : 'off'}
    </button>
  ),
}))

const STORAGE_KEY = 'projects-include-all-private'

describe('ProjectListTable — superadmin private-projects toggle', () => {
  const mockFetchProjects = jest.fn()

  const baseStore = {
    projects: [],
    loading: false,
    fetchProjects: mockFetchProjects,
    setSearchQuery: jest.fn(),
    searchQuery: '',
    currentPage: 1,
    pageSize: 25,
    totalProjects: 0,
    totalPages: 0,
    setCurrentPage: jest.fn(),
    setPageSize: jest.fn(),
  }

  beforeEach(() => {
    jest.clearAllMocks()
    window.localStorage.clear()
    ;(useRouter as jest.Mock).mockReturnValue({ push: jest.fn() })
    ;(useProjectStore as unknown as jest.Mock).mockReturnValue(baseStore)
  })

  it('hides the toggle for non-superadmin users', () => {
    mockUser.current = { is_superadmin: false }
    render(<ProjectListTable />)

    expect(screen.queryByTestId('superadmin-private-toggle')).not.toBeInTheDocument()
  })

  it('shows the toggle for superadmins, defaulting to OFF (narrow view)', () => {
    mockUser.current = { is_superadmin: true }
    render(<ProjectListTable />)

    const toggle = screen.getByTestId('superadmin-private-toggle')
    expect(toggle).toBeInTheDocument()
    expect(toggle).toHaveAttribute('aria-checked', 'false')
  })

  it('hydrates the toggle from localStorage', async () => {
    mockUser.current = { is_superadmin: true }
    window.localStorage.setItem(STORAGE_KEY, 'true')

    render(<ProjectListTable />)

    await waitFor(() => {
      expect(screen.getByTestId('superadmin-private-toggle')).toHaveAttribute(
        'aria-checked',
        'true',
      )
    })
  })

  it('flipping the toggle calls fetchProjects(includeAllPrivate=true) and persists the preference', async () => {
    mockUser.current = { is_superadmin: true }
    const user = userEvent.setup()
    render(<ProjectListTable />)

    // Initial mount runs fetchProjects with includeAllPrivate=false.
    expect(mockFetchProjects).toHaveBeenCalledWith(undefined, undefined, false, false)
    mockFetchProjects.mockClear()

    const toggle = screen.getByTestId('superadmin-private-toggle')
    await user.click(toggle)

    await waitFor(() => {
      expect(mockFetchProjects).toHaveBeenCalledWith(undefined, undefined, false, true)
    })
    expect(window.localStorage.getItem(STORAGE_KEY)).toBe('true')
  })
})

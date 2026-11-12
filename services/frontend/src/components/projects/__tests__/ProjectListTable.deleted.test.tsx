/**
 * The deleted-projects mode of the shared project list (soft delete, 093):
 * same table as the active and archived lists, rows open the project, each
 * row offers restore and the permanent delete, and deleted rows never show
 * up in the other two lists.
 *
 * @jest-environment jsdom
 */

import { useProjectStore } from '@/stores/projectStore'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
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
jest.mock('@/stores/projectStore', () => ({ useProjectStore: jest.fn() }))
const mockRestore = jest.fn()
const mockPurge = jest.fn()
jest.mock('@/lib/api/projects', () => ({
  projectsAPI: {
    restoreProject: (...a: any[]) => mockRestore(...a),
    purgeProject: (...a: any[]) => mockPurge(...a),
  },
}))
const mockConfirm = jest.fn()
jest.mock('@/hooks/useDialogs', () => ({ useConfirm: () => mockConfirm }))
const mockAddToast = jest.fn()
jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({ addToast: mockAddToast, removeToast: jest.fn() }),
}))
jest.mock('@/contexts/ProgressContext', () => ({
  useProgress: () => ({
    startProgress: jest.fn(),
    updateProgress: jest.fn(),
    completeProgress: jest.fn(),
  }),
}))
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 'su', is_superadmin: true },
    isAuthenticated: true,
    isLoading: false,
  }),
}))
jest.mock('@/contexts/I18nContext', () =>
  require('@/test-utils/i18nMock').i18nMock('de'),
)

const project = (o: any = {}) => ({
  id: 'p1',
  title: 'Alte Klausur',
  kind: 'exam',
  created_by: 'owner',
  created_at: '2026-08-01T00:00:00Z',
  is_public: false,
  is_archived: false,
  enable_annotation: true,
  task_count: 3,
  annotation_count: 2,
  ...o,
})

const deleted = project({ deleted_at: '2026-09-01T10:00:00Z' })
const alive = project({ id: 'p2', title: 'Aktive Klausur', deleted_at: null })

const mockFetchProjects = jest.fn()
const store = (projects: any[]) => ({
  projects,
  loading: false,
  fetchProjects: mockFetchProjects,
  setSearchQuery: jest.fn(),
  searchQuery: '',
  currentPage: 1,
  pageSize: 25,
  totalProjects: projects.length,
  totalPages: 1,
  setCurrentPage: jest.fn(),
  setPageSize: jest.fn(),
})

describe('ProjectListTable in deleted mode', () => {
  const push = jest.fn()

  beforeEach(() => {
    jest.clearAllMocks()
    ;(useRouter as jest.Mock).mockReturnValue({ push })
    ;(useProjectStore as unknown as jest.Mock).mockReturnValue(
      store([deleted, alive]),
    )
  })

  it('fetches only deleted projects and shows the deleted title', () => {
    render(<ProjectListTable showDeletedOnly />)
    expect(mockFetchProjects).toHaveBeenCalledWith(
      undefined,
      undefined,
      false,
      false,
      true,
    )
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
      'Gelöschte Projekte',
    )
    // The superadmin "all private projects" toggle has no meaning here.
    expect(
      screen.queryByText('Alle privaten Projekte anzeigen'),
    ).not.toBeInTheDocument()
  })

  it('lists only the deleted rows, with the deleted badge, and opens them on click', () => {
    render(<ProjectListTable showDeletedOnly />)
    expect(screen.getByTestId('projects-table-row-p1')).toBeInTheDocument()
    expect(
      screen.queryByTestId('projects-table-row-p2'),
    ).not.toBeInTheDocument()
    expect(screen.getByTestId('project-deleted-badge-p1')).toHaveTextContent(
      'Gelöscht',
    )
    // No bulk selection in this view; restore/purge act per row.
    expect(
      screen.queryByTestId('projects-table-header-checkbox'),
    ).not.toBeInTheDocument()
    fireEvent.click(screen.getByText('Alte Klausur'))
    expect(push).toHaveBeenCalledWith('/projects/p1')
  })

  it('restores a row without opening it, then re-fetches the deleted view', async () => {
    mockRestore.mockResolvedValue(undefined)
    render(<ProjectListTable showDeletedOnly />)
    mockFetchProjects.mockClear()
    fireEvent.click(screen.getByTestId('deleted-restore-p1'))
    await waitFor(() => expect(mockRestore).toHaveBeenCalledWith('p1'))
    expect(push).not.toHaveBeenCalled()
    await waitFor(() =>
      expect(mockFetchProjects).toHaveBeenCalledWith(
        undefined,
        undefined,
        false,
        false,
        true,
      ),
    )
    expect(mockAddToast).toHaveBeenCalledWith(
      'Projekt wiederhergestellt.',
      'success',
    )
  })

  it('purge asks a danger confirm and only proceeds on yes', async () => {
    mockConfirm.mockResolvedValueOnce(false)
    render(<ProjectListTable showDeletedOnly />)
    fireEvent.click(screen.getByTestId('deleted-purge-p1'))
    await waitFor(() => expect(mockConfirm).toHaveBeenCalled())
    expect(mockConfirm.mock.calls[0][0]).toMatchObject({ variant: 'danger' })
    expect(mockConfirm.mock.calls[0][0].message).toContain('Alte Klausur')
    expect(mockPurge).not.toHaveBeenCalled()
    mockConfirm.mockResolvedValueOnce(true)
    mockPurge.mockResolvedValue(undefined)
    fireEvent.click(screen.getByTestId('deleted-purge-p1'))
    await waitFor(() => expect(mockPurge).toHaveBeenCalledWith('p1'))
    expect(push).not.toHaveBeenCalled()
  })

  it('lists a deleted project whatever its archive state, marked archived', () => {
    ;(useProjectStore as unknown as jest.Mock).mockReturnValue(
      store([
        project({ is_archived: true, deleted_at: '2026-09-01T10:00:00Z' }),
      ]),
    )
    render(<ProjectListTable showDeletedOnly />)
    expect(screen.getByTestId('project-archived-badge-p1')).toHaveTextContent(
      'Archiviert',
    )
  })

  it('the archived list says it has no archived projects, without the create link', () => {
    ;(useProjectStore as unknown as jest.Mock).mockReturnValue(store([]))
    render(<ProjectListTable showArchivedOnly />)
    expect(screen.getByTestId('archived-empty')).toHaveTextContent(
      'Keine archivierten Projekte.',
    )
    expect(
      screen.queryByText('Erstelle dein erstes Projekt, um zu beginnen'),
    ).not.toBeInTheDocument()
  })

  it('shows the deleted empty state', () => {
    ;(useProjectStore as unknown as jest.Mock).mockReturnValue(store([alive]))
    render(<ProjectListTable showDeletedOnly />)
    expect(screen.getByTestId('deleted-empty')).toHaveTextContent(
      'Keine gelöschten Projekte.',
    )
  })

  it('while the active list loads over stale deleted rows it shows the spinner, not "no projects"', () => {
    ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
      ...store([deleted]),
      loading: true,
    })
    render(<ProjectListTable />)
    expect(screen.queryByTestId('projects-table')).not.toBeInTheDocument()
    expect(screen.queryByTestId('projects-empty-state')).not.toBeInTheDocument()
    expect(document.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('the active and archived lists never show a deleted row from the shared store', () => {
    // fetchProject puts an opened deleted project into the shared list.
    const archivedDeleted = project({
      id: 'p3',
      is_archived: true,
      deleted_at: '2026-09-02T10:00:00Z',
    })
    ;(useProjectStore as unknown as jest.Mock).mockReturnValue(
      store([deleted, alive, archivedDeleted]),
    )
    const { unmount } = render(<ProjectListTable />)
    expect(mockFetchProjects).toHaveBeenCalledWith(
      undefined,
      undefined,
      false,
      false,
      false,
    )
    expect(screen.getByTestId('projects-table-row-p2')).toBeInTheDocument()
    expect(
      screen.queryByTestId('projects-table-row-p1'),
    ).not.toBeInTheDocument()
    unmount()
    render(<ProjectListTable showArchivedOnly />)
    expect(
      screen.queryByTestId('projects-table-row-p3'),
    ).not.toBeInTheDocument()
  })
})

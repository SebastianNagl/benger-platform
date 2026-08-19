/**
 * ProjectDataTab — dynamic data-column sync (regression).
 * @jest-environment jsdom
 *
 * The column-sync effect used to compare only the PRESENCE of data_/meta_
 * columns, so a task gaining a new `data` key while the tab was mounted
 * (edit-data modal, page change to rows with different keys) never produced
 * its column until a full remount. It now compares the SET of dynamic column
 * ids. This suite runs the REAL useColumnSettings hook and the REAL
 * nested-column extraction against a stateful useProjectData mock, so the
 * whole tasks → dataColumns → updateColumns → header pipeline is exercised.
 */

import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'

import { ProjectDataTab } from '../ProjectDataTab'

// Data-fetching hook → stateful mock: tests swap `mockTasks` and rerender.
let mockTasks: any[] = []
jest.mock('../data/useProjectData', () => ({
  useProjectData: () => ({
    updatePreference: jest.fn(),
    tasks: mockTasks,
    filteredTasks: mockTasks,
    isLoading: false,
    searchQuery: '',
    setSearchQuery: jest.fn(),
    showSearch: false,
    setShowSearch: jest.fn(),
    debouncedSearch: '',
    sortBy: 'id',
    setSortBy: jest.fn(),
    sortOrder: 'desc',
    setSortOrder: jest.fn(),
    serverSortBy: 'id',
    filterStatus: 'all',
    setFilterStatus: jest.fn(),
    filterDateRange: { start: '', end: '' },
    setFilterDateRange: jest.fn(),
    setFilterAnnotator: jest.fn(),
    metadataFilters: {},
    setMetadataFilters: jest.fn(),
    currentPage: 1,
    setCurrentPage: jest.fn(),
    totalTasks: mockTasks.length,
    totalPages: 1,
    reloadCurrentPage: jest.fn(),
  }),
}))

jest.mock('@/contexts/ProgressContext', () => ({
  useProgress: () => ({
    startProgress: jest.fn(),
    updateProgress: jest.fn(),
    completeProgress: jest.fn(),
  }),
}))

jest.mock('@/stores/projectStore', () => ({
  useProjectStore: () => ({
    currentProject: { id: 'project-1', title: 'Exam', num_tasks: 1 },
    loading: false,
  }),
}))

jest.mock('@/hooks/usePermissions', () => ({
  usePermissions: () => ({
    getEffectiveProjectRole: () => 'ADMIN',
    canAccessProjectData: () => true,
  }),
}))

jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({ addToast: jest.fn(), removeToast: jest.fn(), toasts: [] }),
}))

jest.mock('@/lib/api/projects', () => ({
  projectsAPI: {
    getTasksPage: jest.fn(() =>
      Promise.resolve({ items: [], total: 0, page: 1, page_size: 50, pages: 0 })
    ),
    getTaskIds: jest.fn(() =>
      Promise.resolve({ ids: [], total: 0, truncated: false })
    ),
    getMembers: jest.fn(() => Promise.resolve([])),
  },
}))

jest.mock('@/utils/taskTypeAdapter', () => ({
  labelStudioTaskToApi: jest.fn((task) => ({ id: task.id, data: task.data })),
}))

jest.mock('date-fns', () => ({
  formatDistanceToNow: jest.fn(() => '2 days ago'),
}))

// Heavy children → inert markers. The table itself stays REAL so the
// data-column headers render.
jest.mock('@/components/projects/AnnotatorBadges', () => ({
  AnnotatorBadges: () => <div data-testid="annotator-badges" />,
}))
jest.mock('@/components/projects/BulkActions', () => ({
  BulkActions: () => <div data-testid="bulk-actions" />,
}))
jest.mock('@/components/projects/ColumnSelector', () => ({
  ColumnSelector: () => <div data-testid="column-selector" />,
}))
jest.mock('@/components/projects/FilterDropdown', () => ({
  FilterDropdown: () => <div data-testid="filter-dropdown" />,
}))
jest.mock('@/components/projects/ImportDataModal', () => ({
  ImportDataModal: () => null,
}))
jest.mock('@/components/projects/TaskAssignmentModal', () => ({
  TaskAssignmentModal: () => null,
}))
jest.mock('@/components/tasks/TaskAnnotationComparisonModal', () => ({
  TaskAnnotationComparisonModal: () => null,
}))
jest.mock('@/components/tasks/TaskGenerationComparisonModal', () => ({
  TaskGenerationComparisonModal: () => null,
}))
jest.mock('../data/DataRecordModal', () => ({
  DataRecordModal: () => null,
}))
jest.mock('@/components/projects/TableCheckbox', () => ({
  TableCheckbox: (props: any) => (
    <input type="checkbox" readOnly checked={!!props.checked} />
  ),
}))
jest.mock('@/components/projects/UserAvatar', () => ({
  UserAvatar: ({ name }: any) => <div>{name}</div>,
}))
jest.mock('@/components/shared/Button', () => ({
  Button: ({ children, onClick }: any) => (
    <button onClick={onClick}>{children}</button>
  ),
}))
jest.mock('@/components/shared/Input', () => ({
  Input: (props: any) => <input {...props} />,
}))

const examTask = (data: Record<string, string>) => ({
  id: 'task-1',
  data,
  is_labeled: false,
  total_annotations: 0,
  total_generations: 0,
  created_at: '2026-08-01T00:00:00Z',
  assignments: [],
})

describe('ProjectDataTab — dynamic data columns', () => {
  beforeEach(() => {
    localStorage.clear()
    mockTasks = []
  })

  it('derives a column per task.data key on mount', () => {
    mockTasks = [
      examTask({ sachverhalt: 'Der A ...', musterloesung: 'A. Anspruch ...' }),
    ]
    render(<ProjectDataTab projectId="project-1" />)

    expect(screen.getByText('Sachverhalt')).toBeInTheDocument()
    expect(screen.getByText('Musterloesung')).toBeInTheDocument()
    expect(screen.queryByText('Korrekturhinweise')).not.toBeInTheDocument()
  })

  it('adds a column when a task gains a NEW data key while mounted', () => {
    mockTasks = [examTask({ sachverhalt: 'Der A ...' })]
    const { rerender } = render(<ProjectDataTab projectId="project-1" />)
    expect(screen.queryByText('Korrekturhinweise')).not.toBeInTheDocument()

    // Same page, task edited in place (or a page swap to rows with more
    // keys): the sync effect must pick up the changed id SET, not just the
    // presence of data columns.
    mockTasks = [
      examTask({ sachverhalt: 'Der A ...', korrekturhinweise: 'Streng bewerten.' }),
    ]
    rerender(<ProjectDataTab projectId="project-1" />)

    expect(screen.getByText('Korrekturhinweise')).toBeInTheDocument()
    // The pre-existing column survives the update.
    expect(screen.getByText('Sachverhalt')).toBeInTheDocument()
  })
})

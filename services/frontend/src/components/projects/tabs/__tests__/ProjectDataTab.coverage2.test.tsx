/**
 * @jest-environment jsdom
 *
 * Complement coverage tests for ProjectDataTab.
 *
 * Targets branches NOT exercised by the existing ProjectDataTab.* suites:
 * - Server-driven pagination controls (Previous / Next enable+click, page text).
 * - The "select all N matching" banner: visibility gate (page fully selected +
 *   more matching pages) and handleSelectAllMatching (success + truncated warn
 *   + error toast).
 * - handleExportTasks filtered branch: resolves matching ids, surfaces the
 *   truncated warning, and the "no tasks to export" guard.
 * - Generations cell click opening the TaskGenerationComparisonModal (and its
 *   close), only when total_generations > 0.
 * - handleUnassign task-not-found branch.
 *
 * Uses a configurable getTasksPage/getTaskIds so total/pages/truncated can be
 * driven independently of the page items.
 */

import '@testing-library/jest-dom'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ProjectDataTab } from '../ProjectDataTab'

import { useToast } from '@/components/shared/Toast'
import { useAuth } from '@/contexts/AuthContext'
import { useProgress } from '@/contexts/ProgressContext'
import {
  useColumnSettings,
  useTablePreferences,
} from '@/hooks/useColumnSettings'
import { projectsAPI } from '@/lib/api/projects'
import { useProjectStore } from '@/stores/projectStore'

jest.unmock('@/contexts/ProgressContext')
jest.unmock('@/stores/projectStore')
jest.unmock('@/hooks/useColumnSettings')
jest.unmock('@/lib/api/projects')

jest.mock('@/contexts/ProgressContext', () => ({
  useProgress: jest.fn(),
  ProgressProvider: ({ children }: any) => children,
}))

jest.mock('@/stores/projectStore', () => ({
  useProjectStore: jest.fn(),
}))

jest.mock('@/hooks/useColumnSettings', () => ({
  useColumnSettings: jest.fn(),
  useTablePreferences: jest.fn(),
}))

jest.mock('@/lib/api/projects', () => ({
  projectsAPI: {
    runProjectExportJob: jest.fn(() => Promise.resolve({ ok: true })),
    bulkDeleteTasks: jest.fn(),
    bulkArchiveTasks: jest.fn(),
    getMembers: jest.fn(() => Promise.resolve([])),
    removeTaskAssignment: jest.fn(() => Promise.resolve({})),
    getTasksPage: jest.fn(),
    getTaskIds: jest.fn(),
  },
}))

jest.mock('@/utils/dataColumnHelpers', () => ({
  extractMetadataColumns: jest.fn(() => []),
  formatCellValue: jest.fn((value) => ({
    display: value === undefined ? '—' : `meta:${value}`,
    full: String(value ?? '—'),
    truncated: false,
  })),
  hasConsistentMetadataStructure: jest.fn(() => false),
}))

jest.mock('@/utils/nestedDataColumnHelpers', () => ({
  extractNestedDataColumns: jest.fn(() => []),
  formatNestedCellValue: jest.fn((value) => ({
    display: value === undefined ? '—' : `data:${value}`,
    full: String(value ?? '—'),
    truncated: false,
  })),
  getTaskNestedValue: jest.fn((task, key) => task?.data?.[key]),
}))

jest.mock('@/utils/taskTypeAdapter', () => ({
  labelStudioTaskToApi: jest.fn((task) => ({
    id: task.id,
    data: task.data,
    project_id: 'project-1',
  })),
}))

jest.mock('date-fns', () => ({
  formatDistanceToNow: jest.fn(() => '2 days ago'),
}))

jest.mock('@/components/projects/AnnotatorBadges', () => ({
  AnnotatorBadges: ({ assignments, onUnassign }: any) => (
    <div data-testid="annotator-badges">
      {assignments?.map((a: any, i: number) => (
        <div key={i}>
          {a.user_name}
          {onUnassign && (
            <button
              data-testid={`unassign-${a.id}`}
              onClick={() => onUnassign(a.id)}
            >
              Remove
            </button>
          )}
        </div>
      ))}
      {/* Always-present control that unassigns a non-existent id, so the
          handleUnassign "task not found" branch is reachable on demand. */}
      {onUnassign && (
        <button
          data-testid="unassign-ghost"
          onClick={() => onUnassign('ghost-id-not-in-any-task')}
        >
          Remove Ghost
        </button>
      )}
    </div>
  ),
}))

jest.mock('@/components/projects/BulkActions', () => ({
  BulkActions: ({ selectedCount }: any) => (
    <div data-testid="bulk-actions">
      <span data-testid="selected-count">Selected: {selectedCount}</span>
    </div>
  ),
}))

jest.mock('@/components/projects/ColumnSelector', () => ({
  ColumnSelector: () => <div data-testid="column-selector" />,
}))

jest.mock('@/components/projects/FilterDropdown', () => ({
  FilterDropdown: ({ onStatusChange, onDateRangeChange }: any) => (
    <div data-testid="filter-dropdown">
      <button
        data-testid="status-completed"
        onClick={() => onStatusChange('completed')}
      >
        Completed
      </button>
      <button
        data-testid="set-date-range"
        onClick={() => onDateRangeChange?.('2024-01-01', '2024-01-31')}
      >
        Date
      </button>
    </div>
  ),
}))

jest.mock('@/components/projects/ImportDataModal', () => ({
  ImportDataModal: ({ isOpen }: any) =>
    isOpen ? <div data-testid="import-modal" /> : null,
}))

jest.mock('@/components/projects/TaskAssignmentModal', () => ({
  TaskAssignmentModal: ({ isOpen }: any) =>
    isOpen ? <div data-testid="assignment-modal" /> : null,
}))

jest.mock('@/components/tasks/TaskDataViewModal', () => ({
  TaskDataViewModal: ({ isOpen }: any) =>
    isOpen ? <div data-testid="task-data-modal" /> : null,
}))

jest.mock('@/components/tasks/TaskAnnotationComparisonModal', () => ({
  TaskAnnotationComparisonModal: ({ isOpen }: any) =>
    isOpen ? <div data-testid="comparison-modal" /> : null,
}))

jest.mock('@/components/tasks/TaskGenerationComparisonModal', () => ({
  TaskGenerationComparisonModal: ({ isOpen, onClose, task }: any) =>
    isOpen ? (
      <div data-testid="generation-modal">
        <span data-testid="gen-task-id">Task: {task?.id}</span>
        <button data-testid="close-generation" onClick={onClose}>
          Close
        </button>
      </div>
    ) : null,
}))

jest.mock('@/components/projects/TableCheckbox', () => ({
  TableCheckbox: ({
    checked,
    onChange,
    indeterminate,
    'data-testid': testId,
  }: any) => (
    <input
      type="checkbox"
      checked={checked}
      onChange={(e) => onChange(e.target.checked)}
      data-testid={testId || 'checkbox'}
      data-indeterminate={indeterminate}
    />
  ),
}))

jest.mock('@/components/projects/UserAvatar', () => ({
  UserAvatar: ({ name }: any) => <div data-testid="user-avatar">{name}</div>,
}))

jest.mock('@/components/shared/Button', () => ({
  Button: ({
    children,
    onClick,
    variant,
    disabled,
    className,
    title,
    'data-testid': testId,
  }: any) => (
    <button
      onClick={onClick}
      disabled={disabled}
      data-variant={variant}
      className={className}
      title={title}
      data-testid={testId}
    >
      {children}
    </button>
  ),
}))

jest.mock('@/components/shared/Input', () => ({
  Input: (props: any) => <input {...props} />,
}))

const mockUseAuth = useAuth as jest.MockedFunction<typeof useAuth>
const mockUseProgress = useProgress as jest.MockedFunction<typeof useProgress>
const mockUseToast = useToast as jest.MockedFunction<typeof useToast>
const mockUseProjectStore = useProjectStore as jest.MockedFunction<
  typeof useProjectStore
>
const mockUseColumnSettings = useColumnSettings as jest.MockedFunction<
  typeof useColumnSettings
>
const mockUseTablePreferences = useTablePreferences as jest.MockedFunction<
  typeof useTablePreferences
>

const baseTask = (over: any = {}) => ({
  id: '1',
  data: { text: 'Task' },
  is_labeled: false,
  total_annotations: 0,
  total_generations: 0,
  cancelled_annotations: 0,
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
  meta: {},
  assignments: [],
  annotators: [],
  reviewers: [],
  ...over,
})

const defaultColumns = [
  { id: 'select', label: '', visible: true, sortable: false, width: 'w-12', type: 'system' },
  { id: 'id', label: 'ID', visible: true, sortable: true, width: 'w-20', type: 'system' },
  { id: 'completed', label: 'Completed', visible: true, sortable: true, width: 'w-24', type: 'system' },
  { id: 'assigned', label: 'Assigned To', visible: true, sortable: false, width: 'w-32', type: 'system' },
  { id: 'annotations', label: 'Annotations', visible: true, sortable: true, width: 'w-32', type: 'system' },
  { id: 'generations', label: 'Generations', visible: true, sortable: true, width: 'w-32', type: 'system' },
  { id: 'annotators', label: 'Annotators', visible: true, sortable: false, width: 'w-32', type: 'system' },
  { id: 'graders', label: 'Graders', visible: true, sortable: false, width: 'w-32', type: 'system' },
  { id: 'reviewers', label: 'Reviewers', visible: true, sortable: false, width: 'w-32', type: 'system' },
  { id: 'created', label: 'Created', visible: true, sortable: true, width: 'w-36', type: 'system' },
  { id: 'view_data', label: 'View', visible: true, sortable: false, width: 'w-16', type: 'system' },
]

let mockAddToast: jest.Mock
let mockStartProgress: jest.Mock
let mockUpdateProgress: jest.Mock
let mockCompleteProgress: jest.Mock

// Configurable page payloads. Tests override these before render.
let pagePayload: any
let idsPayload: any

beforeEach(() => {
  jest.clearAllMocks()

  mockAddToast = jest.fn()
  mockStartProgress = jest.fn()
  mockUpdateProgress = jest.fn()
  mockCompleteProgress = jest.fn()

  pagePayload = {
    items: [baseTask()],
    total: 1,
    page: 1,
    page_size: 50,
    pages: 1,
  }
  idsPayload = { ids: ['1'], total: 1, truncated: false }

  ;(projectsAPI.getTasksPage as jest.Mock).mockImplementation(async () => pagePayload)
  ;(projectsAPI.getTaskIds as jest.Mock).mockImplementation(async () => idsPayload)
  ;(projectsAPI.removeTaskAssignment as jest.Mock).mockResolvedValue({})
  ;(projectsAPI.getMembers as jest.Mock).mockResolvedValue([])
  ;(projectsAPI.runProjectExportJob as jest.Mock).mockResolvedValue({ ok: true })

  mockUseAuth.mockReturnValue({
    user: {
      id: 'user-1',
      email: 'test@example.com',
      username: 'testuser',
      is_superadmin: true,
      role: 'ADMIN',
      is_active: true,
      name: 'Test User',
    },
    login: jest.fn(),
    signup: jest.fn(),
    logout: jest.fn(),
    updateUser: jest.fn(),
    isLoading: false,
    refreshAuth: jest.fn(),
    organizations: [],
    currentOrganization: null,
    setCurrentOrganization: jest.fn(),
    refreshOrganizations: jest.fn(),
    apiClient: {} as any,
  } as any)

  mockUseProgress.mockReturnValue({
    startProgress: mockStartProgress,
    updateProgress: mockUpdateProgress,
    completeProgress: mockCompleteProgress,
  } as any)

  mockUseToast.mockReturnValue({
    addToast: mockAddToast,
    removeToast: jest.fn(),
    toasts: [],
  } as any)

  mockUseProjectStore.mockReturnValue({
    currentProject: { id: 'project-1', title: 'Test Project', num_tasks: 3 },
    loading: false,
    fetchProjectTasks: jest.fn(),
  } as any)

  mockUseColumnSettings.mockImplementation((_p, _u, cols) => ({
    columns: (cols as any) || defaultColumns,
    toggleColumn: jest.fn(),
    resetColumns: jest.fn(),
    updateColumns: jest.fn(),
    reorderColumns: jest.fn(),
  }))

  mockUseTablePreferences.mockReturnValue({
    preferences: {
      showSearch: false,
      sortBy: 'id',
      sortOrder: 'desc' as const,
      filterStatus: 'all' as const,
    },
    updatePreference: jest.fn(),
  })

  global.confirm = jest.fn(() => true)
})

async function settle() {
  await act(async () => {
    await new Promise((r) => setTimeout(r, 0))
  })
}

describe('ProjectDataTab - pagination controls', () => {
  it('enables Next on page 1 of multiple pages and advances to page 2', async () => {
    pagePayload = {
      items: [baseTask({ id: '1' })],
      total: 120,
      page: 1,
      page_size: 50,
      pages: 3,
    }

    render(<ProjectDataTab projectId="project-1" />)
    await settle()

    expect(screen.getByText('Page 1 of 3')).toBeInTheDocument()

    const prevBtn = screen.getByText('annotationTab.buttons.previous')
    const nextBtn = screen.getByText('annotationTab.buttons.next')
    expect(prevBtn).toBeDisabled()
    expect(nextBtn).not.toBeDisabled()

    // Page 2 returns a different item set.
    pagePayload = {
      items: [baseTask({ id: '51' })],
      total: 120,
      page: 2,
      page_size: 50,
      pages: 3,
    }

    fireEvent.click(nextBtn)
    await settle()

    await waitFor(() => {
      expect(screen.getByText('Page 2 of 3')).toBeInTheDocument()
    })
    expect(
      screen.getByText('annotationTab.buttons.previous')
    ).not.toBeDisabled()
  })

  it('goes back a page with Previous', async () => {
    pagePayload = {
      items: [baseTask({ id: '51' })],
      total: 120,
      page: 1,
      page_size: 50,
      pages: 3,
    }
    render(<ProjectDataTab projectId="project-1" />)
    await settle()

    // Advance first, then come back.
    fireEvent.click(screen.getByText('annotationTab.buttons.next'))
    await settle()
    await waitFor(() =>
      expect(screen.getByText('Page 2 of 3')).toBeInTheDocument()
    )

    fireEvent.click(screen.getByText('annotationTab.buttons.previous'))
    await settle()
    await waitFor(() =>
      expect(screen.getByText('Page 1 of 3')).toBeInTheDocument()
    )
  })
})

describe('ProjectDataTab - select-all-matching banner', () => {
  it('shows the banner when the page is fully selected and more pages match, then selects all matching', async () => {
    pagePayload = {
      items: [baseTask({ id: '1' }), baseTask({ id: '2' })],
      total: 200,
      page: 1,
      page_size: 50,
      pages: 4,
    }
    idsPayload = {
      ids: Array.from({ length: 200 }, (_, i) => String(i + 1)),
      total: 200,
      truncated: false,
    }

    render(<ProjectDataTab projectId="project-1" />)
    await settle()

    // Select the whole current page via the header checkbox.
    const header = screen.getByTestId('header-checkbox')
    fireEvent.click(header)
    await settle()

    await waitFor(() => {
      expect(
        screen.getByText('All 2 tasks on this page are selected.')
      ).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Select all 200 matching tasks'))
    await settle()

    await waitFor(() => {
      expect(projectsAPI.getTaskIds).toHaveBeenCalled()
      // 200 ids now selected -> counter reflects it.
      expect(screen.getByTestId('selected-count')).toHaveTextContent(
        'Selected: 200'
      )
    })
  })

  it('warns when select-all-matching is truncated', async () => {
    pagePayload = {
      items: [baseTask({ id: '1' })],
      total: 9999,
      page: 1,
      page_size: 50,
      pages: 200,
    }
    idsPayload = {
      ids: Array.from({ length: 5000 }, (_, i) => String(i + 1)),
      total: 9999,
      truncated: true,
    }

    render(<ProjectDataTab projectId="project-1" />)
    await settle()

    fireEvent.click(screen.getByTestId('header-checkbox'))
    await settle()
    await waitFor(() =>
      expect(
        screen.getByText(/All 1 tasks on this page are selected\./)
      ).toBeInTheDocument()
    )

    fireEvent.click(screen.getByText(/Select all 9999 matching tasks/))
    await settle()

    await waitFor(() => {
      expect(mockAddToast).toHaveBeenCalledWith(
        expect.stringContaining('capped'),
        'warning'
      )
    })
  })

  it('shows an error toast when select-all-matching fails', async () => {
    pagePayload = {
      items: [baseTask({ id: '1' })],
      total: 500,
      page: 1,
      page_size: 50,
      pages: 10,
    }
    ;(projectsAPI.getTaskIds as jest.Mock).mockRejectedValueOnce(
      new Error('boom')
    )

    render(<ProjectDataTab projectId="project-1" />)
    await settle()

    fireEvent.click(screen.getByTestId('header-checkbox'))
    await settle()
    await waitFor(() =>
      expect(
        screen.getByText(/Select all 500 matching tasks/)
      ).toBeInTheDocument()
    )

    fireEvent.click(screen.getByText(/Select all 500 matching tasks/))
    await settle()

    await waitFor(() => {
      expect(mockAddToast).toHaveBeenCalledWith(
        'annotationTab.messages.selectAllFailed',
        'error'
      )
    })
  })
})

describe('ProjectDataTab - filtered export', () => {
  it('resolves matching ids for a filtered export and warns when truncated', async () => {
    pagePayload = {
      items: [baseTask({ id: '1' })],
      total: 100,
      page: 1,
      page_size: 50,
      pages: 2,
    }
    render(<ProjectDataTab projectId="project-1" />)
    await settle()

    // Apply a status filter so isFullExport is false (filtered path).
    fireEvent.click(screen.getByTestId('status-completed'))
    await settle()

    idsPayload = {
      ids: ['1'],
      total: 100,
      truncated: true,
    }

    fireEvent.click(screen.getByTestId('export-button'))
    await settle()

    await waitFor(() => {
      expect(projectsAPI.getTaskIds).toHaveBeenCalled()
      expect(mockAddToast).toHaveBeenCalledWith(
        expect.stringContaining('Export capped'),
        'warning'
      )
      expect(projectsAPI.runProjectExportJob).toHaveBeenCalled()
    })
  })

  it('warns and does not export when totalTasks is 0 (export button enabled by a stale page)', async () => {
    // filteredTasks has rows (button enabled) but totalTasks resolves to 0,
    // exercising the `if (totalTasks === 0)` guard in handleExportTasks.
    pagePayload = {
      items: [baseTask({ id: '1' })],
      total: 0,
      page: 1,
      page_size: 50,
      pages: 0,
    }
    render(<ProjectDataTab projectId="project-1" />)
    await settle()

    const exportBtn = screen.getByTestId('export-button')
    expect(exportBtn).not.toBeDisabled()
    fireEvent.click(exportBtn)
    await settle()

    await waitFor(() => {
      expect(mockAddToast).toHaveBeenCalledWith(
        'annotationTab.empty.noExport',
        'warning'
      )
    })
    expect(projectsAPI.runProjectExportJob).not.toHaveBeenCalled()
  })

  it('runs a full (unfiltered) export without resolving task ids', async () => {
    pagePayload = {
      items: [baseTask({ id: '1' })],
      total: 1,
      page: 1,
      page_size: 50,
      pages: 1,
    }
    render(<ProjectDataTab projectId="project-1" />)
    await settle()

    fireEvent.click(screen.getByTestId('export-button'))
    await settle()

    await waitFor(() => {
      // Full export omits the id-resolution round trip.
      expect(projectsAPI.getTaskIds).not.toHaveBeenCalled()
      expect(projectsAPI.runProjectExportJob).toHaveBeenCalled()
    })
  })
})

describe('ProjectDataTab - generations modal', () => {
  it('opens the generation comparison modal when a generations cell with count > 0 is clicked', async () => {
    pagePayload = {
      items: [baseTask({ id: '7', total_generations: 3 })],
      total: 1,
      page: 1,
      page_size: 50,
      pages: 1,
    }
    render(<ProjectDataTab projectId="project-1" />)
    await settle()

    // The generations cell renders the count "3" as a clickable span.
    const genCell = screen.getByText('3')
    fireEvent.click(genCell)
    await settle()

    await waitFor(() => {
      expect(screen.getByTestId('generation-modal')).toBeInTheDocument()
      expect(screen.getByTestId('gen-task-id')).toHaveTextContent('Task: 7')
    })

    fireEvent.click(screen.getByTestId('close-generation'))
    await waitFor(() => {
      expect(screen.queryByTestId('generation-modal')).not.toBeInTheDocument()
    })
  })

  it('does not open the modal when total_generations is 0', async () => {
    // annotations=5 so the only "0" in the row is the generations cell.
    pagePayload = {
      items: [
        baseTask({ id: '8', total_generations: 0, total_annotations: 5 }),
      ],
      total: 1,
      page: 1,
      page_size: 50,
      pages: 1,
    }
    render(<ProjectDataTab projectId="project-1" />)
    await settle()

    fireEvent.click(screen.getByText('0'))
    await settle()
    expect(screen.queryByTestId('generation-modal')).not.toBeInTheDocument()
  })
})

describe('ProjectDataTab - unassign edge case', () => {
  it('toasts task-not-found when the assignment id matches no task', async () => {
    pagePayload = {
      items: [
        baseTask({
          id: '9',
          assignments: [
            { id: 'a-1', user_id: 'u1', user_name: 'Jane', target_type: 'task' },
          ],
        }),
      ],
      total: 1,
      page: 1,
      page_size: 50,
      pages: 1,
    }
    render(<ProjectDataTab projectId="project-1" />)
    await settle()

    // The ghost button unassigns an id present in no task's assignment list,
    // so handleUnassign's `if (!task)` not-found branch fires.
    fireEvent.click(screen.getAllByTestId('unassign-ghost')[0])
    await settle()

    await waitFor(() => {
      expect(mockAddToast).toHaveBeenCalledWith('errors.taskNotFound', 'error')
    })
    expect(projectsAPI.removeTaskAssignment).not.toHaveBeenCalled()
  })

  it('shows an error toast when removeTaskAssignment rejects', async () => {
    pagePayload = {
      items: [
        baseTask({
          id: '11',
          assignments: [
            { id: 'a-3', user_id: 'u3', user_name: 'Sue', target_type: 'task' },
          ],
        }),
      ],
      total: 1,
      page: 1,
      page_size: 50,
      pages: 1,
    }
    ;(projectsAPI.removeTaskAssignment as jest.Mock).mockRejectedValueOnce(
      new Error('fail')
    )
    render(<ProjectDataTab projectId="project-1" />)
    await settle()

    fireEvent.click(screen.getByTestId('unassign-a-3'))
    await settle()

    await waitFor(() => {
      expect(mockAddToast).toHaveBeenCalledWith(
        'errors.assignmentRemoveFailed',
        'error'
      )
    })
  })

  it('removes an assignment successfully and refreshes', async () => {
    pagePayload = {
      items: [
        baseTask({
          id: '10',
          assignments: [
            { id: 'a-2', user_id: 'u2', user_name: 'Bob', target_type: 'task' },
          ],
        }),
      ],
      total: 1,
      page: 1,
      page_size: 50,
      pages: 1,
    }
    render(<ProjectDataTab projectId="project-1" />)
    await settle()

    fireEvent.click(screen.getByTestId('unassign-a-2'))
    await settle()

    await waitFor(() => {
      expect(projectsAPI.removeTaskAssignment).toHaveBeenCalledWith(
        'project-1',
        '10',
        'a-2'
      )
    })
  })
})

describe('ProjectDataTab - dynamic data and metadata cells', () => {
  const {
    extractNestedDataColumns,
  } = require('@/utils/nestedDataColumnHelpers')
  const { extractMetadataColumns } = require('@/utils/dataColumnHelpers')

  const columnsWithDynamic = [
    ...defaultColumns.slice(0, 4),
    { id: 'meta_category', label: 'meta.category', visible: true, sortable: false, width: 'w-32', type: 'metadata' },
    { id: 'data_text', label: 'data.text', visible: true, sortable: false, width: 'w-40', type: 'data' },
    ...defaultColumns.slice(4),
  ]

  beforeEach(() => {
    extractNestedDataColumns.mockReturnValue([
      { key: 'text', label: 'data.text', type: 'string' },
    ])
    extractMetadataColumns.mockReturnValue([
      { key: 'category', label: 'meta.category', type: 'string' },
    ])
    mockUseColumnSettings.mockImplementation(() => ({
      columns: columnsWithDynamic as any,
      toggleColumn: jest.fn(),
      resetColumns: jest.fn(),
      updateColumns: jest.fn(),
      reorderColumns: jest.fn(),
    }))
  })

  it('renders dynamic data_ and meta_ cells from the helper formatters', async () => {
    pagePayload = {
      items: [
        baseTask({
          id: '20',
          data: { text: 'hello body' },
          meta: { category: 'legal' },
        }),
      ],
      total: 1,
      page: 1,
      page_size: 50,
      pages: 1,
    }

    render(<ProjectDataTab projectId="project-1" />)
    await settle()

    // The data_ cell uses formatNestedCellValue -> "data:<value>"
    expect(screen.getByText('data:hello body')).toBeInTheDocument()
    // The meta_ cell uses formatCellValue -> "meta:<value>"
    expect(screen.getByText('meta:legal')).toBeInTheDocument()
    // Both dynamic column headers render via t(column.label).
    expect(screen.getByText('data.text')).toBeInTheDocument()
    expect(screen.getByText('meta.category')).toBeInTheDocument()
  })
})

describe('ProjectDataTab - view/edit data modal callbacks', () => {
  it('opens the data view modal from the eye button', async () => {
    pagePayload = {
      items: [baseTask({ id: '30' })],
      total: 1,
      page: 1,
      page_size: 50,
      pages: 1,
    }
    render(<ProjectDataTab projectId="project-1" />)
    await settle()

    // The view_data column renders a button titled via t('annotation.viewTaskData')
    // which the global i18n mock resolves to 'View complete task data'.
    const viewBtn = screen.getByTitle('View complete task data')
    fireEvent.click(viewBtn)
    await settle()

    await waitFor(() => {
      expect(screen.getByTestId('task-data-modal')).toBeInTheDocument()
    })
  })
})

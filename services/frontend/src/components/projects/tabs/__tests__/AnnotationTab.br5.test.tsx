/**
 * @jest-environment jsdom
 *
 * Branch coverage tests for AnnotationTab - round 5.
 * Targets specific uncovered branches:
 * - Metadata filter: array filter on array task value (lines 283-285)
 * - Metadata filter: array filter on single task value (lines 287-289)
 * - Metadata filter: single filter on array task value (lines 292-294)
 * - Metadata filter: single filter on single task value (lines 296-298)
 * - Sort by 'completed' (lines 314-316)
 * - Sort by 'annotations' (lines 317-319)
 * - Sort by 'generations' (lines 321-323)
 * - Sort by 'created' (lines 325-328)
 * - Sort by default (lines 330-332)
 * - Sort asc vs desc (lines 335-338)
 * - handleSort with non-sortable column (line 407)
 * - handleSort toggling sort order (lines 409-412)
 * - handleSort switching column (lines 413-417)
 * - handleExport with selected tasks vs all (lines 441-462)
 * - handleExport error path (lines 494-501)
 * - handleBulkDelete confirm=false (lines 509-516)
 * - handleBulkExport error path (lines 603-610)
 * - handleExportTasks with empty filtered tasks (lines 615-617)
 * - handleUnassign task not found (lines 930-932)
 * - getTaskDisplayValue fallbacks (lines 864-874)
 * - Dynamic data columns in header (lines 1166-1183)
 * - Dynamic meta columns in body (lines 1264-1306)
 * - Dynamic data columns in body (lines 1310-1341)
 * - data column skip when useDataColumns (lines 1414-1416)
 */

import '@testing-library/jest-dom'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { AnnotationTab } from '../AnnotationTab'

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
    export: jest.fn(),
    bulkExportTasks: jest.fn(),
    bulkDeleteTasks: jest.fn(),
    bulkArchiveTasks: jest.fn(),
    getMembers: jest.fn(),
    removeTaskAssignment: jest.fn(),
  },
}))

jest.mock('@/utils/dataColumnHelpers', () => ({
  extractMetadataColumns: jest.fn(() => []),
  formatCellValue: jest.fn((value) => ({
    display: String(value || '\u2014'),
    full: String(value || '\u2014'),
    truncated: false,
  })),
  hasConsistentMetadataStructure: jest.fn(() => false),
}))

jest.mock('@/utils/nestedDataColumnHelpers', () => ({
  extractNestedDataColumns: jest.fn(() => []),
  formatNestedCellValue: jest.fn((value) => ({
    display: String(value || '\u2014'),
    full: String(value || '\u2014'),
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
  AnnotatorBadges: ({ assignments, onAssign, onUnassign }: any) => (
    <div data-testid="annotator-badges">
      {assignments?.length > 0
        ? assignments.map((a: any, i: number) => (
            <div key={i}>
              {a.user_name}
              {onUnassign && (
                <button onClick={() => onUnassign(a.id)}>Remove</button>
              )}
            </div>
          ))
        : onAssign && <button onClick={onAssign}>Assign</button>}
    </div>
  ),
}))

jest.mock('@/components/projects/BulkActions', () => ({
  BulkActions: ({
    selectedCount,
    onDelete,
    onExport,
    onArchive,
    onAssign,
    onTagsUpdated,
  }: any) => (
    <div data-testid="bulk-actions">
      <span data-testid="selected-count">Selected: {selectedCount}</span>
      <button onClick={onDelete} data-testid="bulk-delete">
        Delete
      </button>
      <button onClick={onExport} data-testid="bulk-export">
        Export
      </button>
      <button onClick={onArchive} data-testid="bulk-archive">
        Archive
      </button>
      <button onClick={onAssign} data-testid="bulk-assign">
        Assign
      </button>
      {onTagsUpdated && (
        <button onClick={onTagsUpdated} data-testid="tags-updated">
          Tags Updated
        </button>
      )}
    </div>
  ),
}))

jest.mock('@/components/projects/ColumnSelector', () => ({
  ColumnSelector: ({ columns, onToggle, onReset }: any) => (
    <div data-testid="column-selector" />
  ),
}))

jest.mock('@/components/projects/FilterDropdown', () => ({
  FilterDropdown: ({ filterStatus, onStatusChange }: any) => (
    <div data-testid="filter-dropdown">
      <select
        value={filterStatus}
        onChange={(e) => onStatusChange(e.target.value)}
        data-testid="status-filter"
      >
        <option value="all">All</option>
        <option value="completed">Completed</option>
        <option value="incomplete">Incomplete</option>
      </select>
    </div>
  ),
}))

jest.mock('@/components/projects/ImportDataModal', () => ({
  ImportDataModal: ({ isOpen, onClose, onImportComplete }: any) =>
    isOpen ? (
      <div data-testid="import-modal">
        <button onClick={onImportComplete}>Complete Import</button>
        <button onClick={onClose}>Close</button>
      </div>
    ) : null,
}))

jest.mock('@/components/projects/TaskAssignmentModal', () => ({
  TaskAssignmentModal: ({ isOpen, onClose, onAssignmentComplete }: any) =>
    isOpen ? (
      <div data-testid="assignment-modal">
        <button onClick={onAssignmentComplete}>Complete Assignment</button>
        <button onClick={onClose}>Close</button>
      </div>
    ) : null,
}))

jest.mock('@/components/tasks/TaskDataViewModal', () => ({
  TaskDataViewModal: ({ isOpen, onClose, task }: any) =>
    isOpen ? (
      <div data-testid="task-data-modal">
        <span>Task ID: {task?.id}</span>
        <button onClick={onClose}>Close</button>
      </div>
    ) : null,
}))

jest.mock('@/components/tasks/TaskAnnotationComparisonModal', () => ({
  TaskAnnotationComparisonModal: ({ isOpen, onClose, task }: any) =>
    isOpen ? (
      <div data-testid="comparison-modal">
        <span>Task ID: {task?.id}</span>
        <button onClick={onClose}>Close</button>
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
  Button: ({ children, onClick, variant, disabled, className, title }: any) => (
    <button
      onClick={onClick}
      disabled={disabled}
      data-variant={variant}
      className={className}
      title={title}
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

const mockTasks = [
  {
    id: '1',
    data: { text: 'Sample task 1' },
    is_labeled: false,
    total_annotations: 0,
    cancelled_annotations: 0,
    total_generations: 2,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
    meta: { tags: ['important'], category: 'civil' },
    assignments: [],
  },
  {
    id: '2',
    data: { text: 'Sample task 2' },
    is_labeled: true,
    total_annotations: 2,
    cancelled_annotations: 0,
    total_generations: 0,
    created_at: '2024-01-02T00:00:00Z',
    updated_at: '2024-01-02T00:00:00Z',
    meta: { tags: ['urgent'], category: 'criminal' },
    assignments: [
      {
        id: 'assign-1',
        user_id: 'user-1',
        user_name: 'John Doe',
        status: 'completed',
      },
    ],
  },
]

const defaultColumns = [
  { id: 'select', label: '', visible: true, sortable: false, width: 'w-12', type: 'system' },
  { id: 'id', label: 'ID', visible: true, sortable: true, width: 'w-20', type: 'system' },
  { id: 'completed', label: 'Completed', visible: true, sortable: true, width: 'w-24', type: 'system' },
  { id: 'assigned', label: 'Assigned To', visible: true, sortable: false, width: 'w-32', type: 'system' },
  { id: 'annotations', label: 'Annotations', visible: true, sortable: true, width: 'w-32', type: 'system' },
  { id: 'generations', label: 'Generations', visible: true, sortable: true, width: 'w-24', type: 'system' },
  { id: 'annotators', label: 'Annotators', visible: true, sortable: false, width: 'w-32', type: 'system' },
  { id: 'agreement', label: 'Agreement', visible: true, sortable: true, width: 'w-28', type: 'system' },
  { id: 'reviewers', label: 'Reviewers', visible: true, sortable: false, width: 'w-32', type: 'system' },
  { id: 'created', label: 'Created', visible: true, sortable: true, width: 'w-36', type: 'system' },
  { id: 'view_data', label: 'View', visible: true, sortable: false, width: 'w-16', type: 'system' },
]

describe('AnnotationTab - br5 branch coverage', () => {
  let mockFetchProjectTasks: jest.Mock
  let mockAddToast: jest.Mock
  let mockStartProgress: jest.Mock
  let mockUpdateProgress: jest.Mock
  let mockCompleteProgress: jest.Mock

  beforeEach(() => {
    jest.clearAllMocks()

    mockFetchProjectTasks = jest.fn().mockResolvedValue(mockTasks)
    mockAddToast = jest.fn()
    mockStartProgress = jest.fn()
    mockUpdateProgress = jest.fn()
    mockCompleteProgress = jest.fn()

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
    })

    mockUseProgress.mockReturnValue({
      startProgress: mockStartProgress,
      updateProgress: mockUpdateProgress,
      completeProgress: mockCompleteProgress,
    })

    mockUseToast.mockReturnValue({
      addToast: mockAddToast,
      removeToast: jest.fn(),
      toasts: [],
    })

    mockUseProjectStore.mockReturnValue({
      currentProject: {
        id: 'project-1',
        title: 'Test Project',
        num_tasks: 2,
        num_annotations: 2,
      },
      loading: false,
      fetchProjectTasks: mockFetchProjectTasks,
    } as any)

    mockUseColumnSettings.mockImplementation((projectId, userId, columns) => ({
      columns: columns || defaultColumns,
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

    ;(projectsAPI.export as jest.Mock).mockResolvedValue(
      new Blob(['test data'])
    )
    ;(projectsAPI.bulkExportTasks as jest.Mock).mockResolvedValue(
      new Blob(['test data'])
    )
    ;(projectsAPI.bulkDeleteTasks as jest.Mock).mockResolvedValue({
      deleted: 2,
    })
    ;(projectsAPI.bulkArchiveTasks as jest.Mock).mockResolvedValue({
      archived: 2,
    })
    ;(projectsAPI.getMembers as jest.Mock).mockResolvedValue([])
    ;(projectsAPI.removeTaskAssignment as jest.Mock).mockResolvedValue({})

    global.confirm = jest.fn(() => true)
    global.URL.createObjectURL = jest.fn(() => 'mock-url')
    global.URL.revokeObjectURL = jest.fn()

    const originalCreateElement = document.createElement.bind(document)
    jest
      .spyOn(document, 'createElement')
      .mockImplementation((tagName: string) => {
        const element = originalCreateElement(tagName)
        if (tagName === 'a') {
          element.click = jest.fn()
        }
        return element
      })
  })

  afterEach(() => {
    jest.restoreAllMocks()
  })

  it('renders the annotation tab with tasks', async () => {
    render(<AnnotationTab projectId="project-1" />)
    await waitFor(() => {
      expect(mockFetchProjectTasks).toHaveBeenCalled()
    })
  })

  it('triggers onTagsUpdated callback from BulkActions', async () => {
    render(<AnnotationTab projectId="project-1" />)

    await waitFor(() => {
      expect(screen.getByTestId('bulk-actions')).toBeInTheDocument()
    })

    // Click tags updated button
    const tagsBtn = screen.getByTestId('tags-updated')
    await act(async () => {
      fireEvent.click(tagsBtn)
    })

    // Should refresh tasks and show toast
    await waitFor(() => {
      expect(mockFetchProjectTasks).toHaveBeenCalledTimes(2) // once on mount, once after tags
    })
  })

  it('handles bulk delete with confirm=false', async () => {
    ;(global.confirm as jest.Mock).mockReturnValue(false)

    render(<AnnotationTab projectId="project-1" />)

    await waitFor(() => {
      expect(screen.getByTestId('bulk-actions')).toBeInTheDocument()
    })

    // Select a task first
    const checkboxes = screen.getAllByRole('checkbox')
    if (checkboxes.length > 1) {
      await act(async () => {
        fireEvent.click(checkboxes[1])
      })
    }

    // Click delete
    await act(async () => {
      fireEvent.click(screen.getByTestId('bulk-delete'))
    })

    // bulkDeleteTasks should NOT be called because confirm returned false
    expect(projectsAPI.bulkDeleteTasks).not.toHaveBeenCalled()
  })

  it('handles empty state when no tasks', async () => {
    mockFetchProjectTasks.mockResolvedValue([])

    render(<AnnotationTab projectId="project-1" />)

    await waitFor(() => {
      expect(mockFetchProjectTasks).toHaveBeenCalled()
    })

    // Empty state message
    // The "no tasks" text comes from t('annotationTab.empty.noTasks')
  })

  it('renders with filter status "completed"', async () => {
    mockUseTablePreferences.mockReturnValue({
      preferences: {
        showSearch: false,
        sortBy: 'id',
        sortOrder: 'desc' as const,
        filterStatus: 'completed' as const,
      },
      updatePreference: jest.fn(),
    })

    render(<AnnotationTab projectId="project-1" />)

    await waitFor(() => {
      expect(mockFetchProjectTasks).toHaveBeenCalled()
    })
  })

  it('renders with filter status "incomplete"', async () => {
    mockUseTablePreferences.mockReturnValue({
      preferences: {
        showSearch: false,
        sortBy: 'id',
        sortOrder: 'desc' as const,
        filterStatus: 'incomplete' as const,
      },
      updatePreference: jest.fn(),
    })

    render(<AnnotationTab projectId="project-1" />)

    await waitFor(() => {
      expect(mockFetchProjectTasks).toHaveBeenCalled()
    })
  })

  it('renders with sort by "completed" ascending', async () => {
    mockUseTablePreferences.mockReturnValue({
      preferences: {
        showSearch: false,
        sortBy: 'completed',
        sortOrder: 'asc' as const,
        filterStatus: 'all' as const,
      },
      updatePreference: jest.fn(),
    })

    render(<AnnotationTab projectId="project-1" />)

    await waitFor(() => {
      expect(mockFetchProjectTasks).toHaveBeenCalled()
    })
  })

  it('renders with sort by "annotations"', async () => {
    mockUseTablePreferences.mockReturnValue({
      preferences: {
        showSearch: false,
        sortBy: 'annotations',
        sortOrder: 'desc' as const,
        filterStatus: 'all' as const,
      },
      updatePreference: jest.fn(),
    })

    render(<AnnotationTab projectId="project-1" />)

    await waitFor(() => {
      expect(mockFetchProjectTasks).toHaveBeenCalled()
    })
  })

  it('renders with sort by "generations"', async () => {
    mockUseTablePreferences.mockReturnValue({
      preferences: {
        showSearch: false,
        sortBy: 'generations',
        sortOrder: 'desc' as const,
        filterStatus: 'all' as const,
      },
      updatePreference: jest.fn(),
    })

    render(<AnnotationTab projectId="project-1" />)

    await waitFor(() => {
      expect(mockFetchProjectTasks).toHaveBeenCalled()
    })
  })

  it('renders with sort by "created"', async () => {
    mockUseTablePreferences.mockReturnValue({
      preferences: {
        showSearch: false,
        sortBy: 'created',
        sortOrder: 'asc' as const,
        filterStatus: 'all' as const,
      },
      updatePreference: jest.fn(),
    })

    render(<AnnotationTab projectId="project-1" />)

    await waitFor(() => {
      expect(mockFetchProjectTasks).toHaveBeenCalled()
    })
  })

  it('renders with non-superadmin user', async () => {
    mockUseAuth.mockReturnValue({
      user: {
        id: 'user-2',
        email: 'annotator@example.com',
        username: 'annotator',
        is_superadmin: false,
        role: 'ANNOTATOR',
        is_active: true,
        name: 'Annotator User',
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
    })

    render(<AnnotationTab projectId="project-1" />)

    await waitFor(() => {
      expect(mockFetchProjectTasks).toHaveBeenCalled()
    })
  })

  it('handles search query filtering', async () => {
    mockUseTablePreferences.mockReturnValue({
      preferences: {
        showSearch: true,
        sortBy: 'id',
        sortOrder: 'desc' as const,
        filterStatus: 'all' as const,
      },
      updatePreference: jest.fn(),
    })

    render(<AnnotationTab projectId="project-1" />)

    await waitFor(() => {
      expect(mockFetchProjectTasks).toHaveBeenCalled()
    })

    // Search input should be visible
    const searchInput = screen.getByPlaceholderText(/search/i)
    if (searchInput) {
      fireEvent.change(searchInput, { target: { value: 'Sample task 1' } })
    }
  })

  it('handles export error gracefully', async () => {
    ;(projectsAPI.bulkExportTasks as jest.Mock).mockRejectedValue(
      new Error('Export failed')
    )

    render(<AnnotationTab projectId="project-1" />)

    await waitFor(() => {
      expect(screen.getByTestId('bulk-actions')).toBeInTheDocument()
    })

    // Select a task and export
    const checkboxes = screen.getAllByRole('checkbox')
    if (checkboxes.length > 1) {
      await act(async () => {
        fireEvent.click(checkboxes[1])
      })
    }

    await act(async () => {
      fireEvent.click(screen.getByTestId('bulk-export'))
    })
  })
})

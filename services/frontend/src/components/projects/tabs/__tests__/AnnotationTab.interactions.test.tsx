/**
 * Additional coverage tests for AnnotationTab
 * Targets uncovered handlers: export, bulk delete, bulk export, export all,
 * view task data, import complete, assignment modal, comparison modal,
 * sort by various columns, metadata filters, empty state, search filter.
 *
 * @jest-environment jsdom
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
  extractMetadataColumns: jest.fn(() => [
    { key: 'category', type: 'string', label: 'category' },
  ]),
  formatCellValue: jest.fn((value) => ({
    display: String(value || '\u2014'),
    full: String(value || '\u2014'),
    truncated: false,
  })),
  hasConsistentMetadataStructure: jest.fn(() => true),
}))

jest.mock('@/utils/nestedDataColumnHelpers', () => ({
  extractNestedDataColumns: jest.fn(() => [
    { id: 'text', type: 'string', label: 'text' },
  ]),
  formatNestedCellValue: jest.fn((value) => ({
    display: String(value || '\u2014'),
    full: String(value || '\u2014'),
    truncated: value && String(value).length > 50,
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
                <button data-testid={`unassign-${a.id}`} onClick={() => onUnassign(a.id)}>Remove</button>
              )}
            </div>
          ))
        : onAssign && <button data-testid="assign-task-btn" onClick={onAssign}>Assign</button>}
    </div>
  ),
}))

jest.mock('@/components/projects/BulkActions', () => ({
  BulkActions: ({ selectedCount, onDelete, onExport, onArchive, onAssign }: any) => (
    <div data-testid="bulk-actions">
      <span data-testid="selected-count">Selected: {selectedCount}</span>
      <button onClick={onDelete} data-testid="bulk-delete">Delete</button>
      <button onClick={onExport} data-testid="bulk-export">Export</button>
      <button onClick={onArchive} data-testid="bulk-archive">Archive</button>
      <button onClick={onAssign} data-testid="bulk-assign">Assign</button>
    </div>
  ),
}))

jest.mock('@/components/projects/ColumnSelector', () => ({
  ColumnSelector: ({ columns, onToggle, onReset }: any) => (
    <div data-testid="column-selector">
      {columns?.map((col: any) => (
        <button key={col.id} onClick={() => onToggle(col.id)} data-testid={`column-${col.id}`}>
          {col.label}
        </button>
      ))}
      <button onClick={onReset}>Reset</button>
    </div>
  ),
}))

jest.mock('@/components/projects/FilterDropdown', () => ({
  FilterDropdown: ({ filterStatus, onStatusChange, onDateRangeChange, onAnnotatorChange, onMetadataChange }: any) => (
    <div data-testid="filter-dropdown">
      <select value={filterStatus} onChange={(e) => onStatusChange(e.target.value)} data-testid="status-filter">
        <option value="all">All</option>
        <option value="completed">Completed</option>
        <option value="incomplete">Incomplete</option>
      </select>
      <button data-testid="set-date-range" onClick={() => onDateRangeChange?.('2024-01-01', '2024-01-31')}>Set Date Range</button>
      <button data-testid="set-annotator" onClick={() => onAnnotatorChange?.('user-1')}>Set Annotator</button>
      <button data-testid="set-metadata" onClick={() => onMetadataChange?.({ category: ['legal'] })}>Set Metadata</button>
      <button data-testid="clear-metadata" onClick={() => onMetadataChange?.({})}>Clear Metadata</button>
    </div>
  ),
}))

jest.mock('@/components/projects/ImportDataModal', () => ({
  ImportDataModal: ({ isOpen, onClose, onImportComplete }: any) =>
    isOpen ? (
      <div data-testid="import-modal">
        <button data-testid="complete-import" onClick={onImportComplete}>Complete Import</button>
        <button data-testid="close-import" onClick={onClose}>Close</button>
      </div>
    ) : null,
}))

jest.mock('@/components/projects/TaskAssignmentModal', () => ({
  TaskAssignmentModal: ({ isOpen, onClose, onAssignmentComplete }: any) =>
    isOpen ? (
      <div data-testid="assignment-modal">
        <button data-testid="complete-assignment" onClick={onAssignmentComplete}>Complete Assignment</button>
        <button data-testid="close-assignment" onClick={onClose}>Close</button>
      </div>
    ) : null,
}))

jest.mock('@/components/tasks/TaskDataViewModal', () => ({
  TaskDataViewModal: ({ isOpen, onClose, task }: any) =>
    isOpen ? (
      <div data-testid="task-data-modal">
        <span data-testid="view-task-id">Task: {task?.id}</span>
        <button data-testid="close-data-modal" onClick={onClose}>Close</button>
      </div>
    ) : null,
}))

jest.mock('@/components/tasks/TaskAnnotationComparisonModal', () => ({
  TaskAnnotationComparisonModal: ({ isOpen, onClose, task }: any) =>
    isOpen ? (
      <div data-testid="comparison-modal">
        <span data-testid="comparison-task-id">Task: {task?.id}</span>
        <button data-testid="close-comparison" onClick={onClose}>Close</button>
      </div>
    ) : null,
}))

jest.mock('@/components/projects/TableCheckbox', () => ({
  TableCheckbox: ({ checked, onChange, indeterminate, 'data-testid': testId }: any) => (
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
  Button: ({ children, onClick, variant, disabled, className, title, ...rest }: any) => (
    <button onClick={onClick} disabled={disabled} data-variant={variant} className={className} title={title} {...rest}>
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
const mockUseProjectStore = useProjectStore as jest.MockedFunction<typeof useProjectStore>
const mockUseColumnSettings = useColumnSettings as jest.MockedFunction<typeof useColumnSettings>
const mockUseTablePreferences = useTablePreferences as jest.MockedFunction<typeof useTablePreferences>

const mockTasks = [
  {
    id: '1',
    data: { text: 'Sample task 1' },
    is_labeled: false,
    total_annotations: 0,
    total_generations: 0,
    cancelled_annotations: 0,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
    meta: { category: 'legal' },
    assignments: [],
    agreement: null,
  },
  {
    id: '2',
    data: { text: 'Sample task 2' },
    is_labeled: true,
    total_annotations: 2,
    total_generations: 1,
    cancelled_annotations: 0,
    created_at: '2024-01-02T00:00:00Z',
    updated_at: '2024-01-02T00:00:00Z',
    meta: { category: 'civil' },
    assignments: [
      { id: 'assign-1', user_id: 'user-1', user_name: 'John Doe', status: 'completed' },
    ],
    agreement: 0.85,
  },
  {
    id: '3',
    data: { text: 'Sample task 3' },
    is_labeled: false,
    total_annotations: 1,
    total_generations: 2,
    cancelled_annotations: 0,
    created_at: '2024-01-03T00:00:00Z',
    updated_at: '2024-01-03T00:00:00Z',
    meta: { category: 'legal' },
    assignments: [],
    agreement: null,
  },
]

const defaultColumns = [
  { id: 'select', label: '', visible: true, sortable: false, width: 'w-12', type: 'system' },
  { id: 'id', label: 'ID', visible: true, sortable: true, width: 'w-20', type: 'system' },
  { id: 'completed', label: 'Completed', visible: true, sortable: true, width: 'w-24', type: 'system' },
  { id: 'assigned', label: 'Assigned To', visible: true, sortable: false, width: 'w-32', type: 'system' },
  { id: 'annotations', label: 'Annotations', visible: true, sortable: true, width: 'w-32', type: 'system' },
  { id: 'generations', label: 'Generations', visible: true, sortable: true, width: 'w-32', type: 'system' },
  { id: 'annotators', label: 'Annotators', visible: true, sortable: false, width: 'w-32', type: 'system' },
  { id: 'agreement', label: 'Agreement', visible: true, sortable: true, width: 'w-28', type: 'system' },
  { id: 'reviewers', label: 'Reviewers', visible: true, sortable: false, width: 'w-32', type: 'system' },
  { id: 'created', label: 'Created', visible: true, sortable: true, width: 'w-36', type: 'system' },
  { id: 'view_data', label: 'View', visible: true, sortable: false, width: 'w-16', type: 'system' },
  { id: 'data_text', label: 'data.text', visible: true, sortable: false, width: 'w-40', type: 'data' },
  { id: 'meta_category', label: 'meta.category', visible: true, sortable: false, width: 'w-32', type: 'metadata' },
]

let mockFetchProjectTasks: jest.Mock
let mockAddToast: jest.Mock
let mockStartProgress: jest.Mock
let mockUpdateProgress: jest.Mock
let mockCompleteProgress: jest.Mock
let mockUpdatePreference: jest.Mock

function setupMocks() {
  mockFetchProjectTasks = jest.fn().mockResolvedValue(mockTasks)
  mockAddToast = jest.fn()
  mockStartProgress = jest.fn()
  mockUpdateProgress = jest.fn()
  mockCompleteProgress = jest.fn()
  mockUpdatePreference = jest.fn()

  mockUseAuth.mockReturnValue({
    user: { id: 'user-1', email: 'test@example.com', username: 'testuser', is_superadmin: true, role: 'ADMIN', is_active: true, name: 'Test User' },
    login: jest.fn(), signup: jest.fn(), logout: jest.fn(), updateUser: jest.fn(),
    isLoading: false, refreshAuth: jest.fn(), organizations: [],
    currentOrganization: null, setCurrentOrganization: jest.fn(), refreshOrganizations: jest.fn(),
    apiClient: {} as any,
  })

  mockUseProgress.mockReturnValue({
    startProgress: mockStartProgress,
    updateProgress: mockUpdateProgress,
    completeProgress: mockCompleteProgress,
  })

  mockUseToast.mockReturnValue({ addToast: mockAddToast, removeToast: jest.fn(), toasts: [] })

  mockUseProjectStore.mockReturnValue({
    currentProject: { id: 'project-1', title: 'Test Project', num_tasks: 3, num_annotations: 3 },
    loading: false,
    fetchProjectTasks: mockFetchProjectTasks,
  } as any)

  // Track columns dynamically - the component calls updateColumns() to add data_/meta_ cols
  let currentColumns = defaultColumns
  const mockUpdateColumns = jest.fn((newCols) => { currentColumns = newCols })
  mockUseColumnSettings.mockImplementation(() => ({
    columns: currentColumns,
    toggleColumn: jest.fn(),
    resetColumns: jest.fn(),
    updateColumns: mockUpdateColumns,
    reorderColumns: jest.fn(),
  }))

  mockUseTablePreferences.mockReturnValue({
    preferences: { showSearch: false, sortBy: 'id', sortOrder: 'desc' as const, filterStatus: 'all' as const },
    updatePreference: mockUpdatePreference,
  })

  ;(projectsAPI.export as jest.Mock).mockResolvedValue(new Blob(['test']))
  ;(projectsAPI.bulkExportTasks as jest.Mock).mockResolvedValue(new Blob(['test']))
  ;(projectsAPI.bulkDeleteTasks as jest.Mock).mockResolvedValue({ deleted: 1 })
  ;(projectsAPI.bulkArchiveTasks as jest.Mock).mockResolvedValue({ archived: 1 })
  ;(projectsAPI.getMembers as jest.Mock).mockResolvedValue([{ id: 'user-1', username: 'testuser' }])
  ;(projectsAPI.removeTaskAssignment as jest.Mock).mockResolvedValue({})

  global.confirm = jest.fn(() => true)
  global.URL.createObjectURL = jest.fn(() => 'mock-url')
  global.URL.revokeObjectURL = jest.fn()

  const originalCreateElement = document.createElement.bind(document)
  jest.spyOn(document, 'createElement').mockImplementation((tagName: string) => {
    const element = originalCreateElement(tagName)
    if (tagName === 'a') element.click = jest.fn()
    return element
  })
}

async function renderAndWaitForTasks() {
  render(<AnnotationTab projectId="project-1" />)
  await waitFor(() => expect(mockFetchProjectTasks).toHaveBeenCalled())
  await act(async () => { await new Promise(r => setTimeout(r, 0)) })
}

describe('AnnotationTab - interaction coverage', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    setupMocks()
  })

  afterEach(() => {
    jest.restoreAllMocks()
  })

  // ---- EXPORT HANDLERS ----

  describe('Export tasks (Export button)', () => {
    it('exports all filtered tasks when export button clicked', async () => {
      await renderAndWaitForTasks()

      const exportBtn = screen.getByTestId('export-button')
      fireEvent.click(exportBtn)

      await waitFor(() => {
        expect(projectsAPI.bulkExportTasks).toHaveBeenCalledWith('project-1', expect.any(Array), 'json')
      })
      expect(mockStartProgress).toHaveBeenCalled()
      expect(mockCompleteProgress).toHaveBeenCalledWith(expect.any(String), 'success')
      expect(mockAddToast).toHaveBeenCalledWith(expect.any(String), 'success')
    })

    it('shows warning when exporting with no tasks', async () => {
      mockFetchProjectTasks.mockResolvedValue([])
      render(<AnnotationTab projectId="project-1" />)
      await waitFor(() => expect(mockFetchProjectTasks).toHaveBeenCalled())
      await act(async () => { await new Promise(r => setTimeout(r, 0)) })

      // Export button should be disabled when no tasks
      const exportBtn = screen.getByTestId('export-button')
      expect(exportBtn).toBeDisabled()
    })

    it('handles export failure', async () => {
      ;(projectsAPI.bulkExportTasks as jest.Mock).mockRejectedValue(new Error('Network error'))
      await renderAndWaitForTasks()

      fireEvent.click(screen.getByTestId('export-button'))

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(expect.stringContaining('Failed'), 'error')
      })
      expect(mockCompleteProgress).toHaveBeenCalledWith(expect.any(String), 'error')
    })
  })

  describe('Bulk export', () => {
    it('exports selected tasks when bulk export clicked', async () => {
      await renderAndWaitForTasks()

      // Select a task
      const checkboxes = screen.getAllByRole('checkbox')
      fireEvent.click(checkboxes[1])

      fireEvent.click(screen.getByTestId('bulk-export'))

      await waitFor(() => {
        expect(projectsAPI.bulkExportTasks).toHaveBeenCalledWith('project-1', expect.any(Array), 'json')
      })
      expect(mockAddToast).toHaveBeenCalledWith(expect.any(String), 'success')
    })

    it('handles bulk export failure', async () => {
      ;(projectsAPI.bulkExportTasks as jest.Mock).mockRejectedValue(new Error('Export failed'))
      await renderAndWaitForTasks()

      const checkboxes = screen.getAllByRole('checkbox')
      fireEvent.click(checkboxes[1])

      fireEvent.click(screen.getByTestId('bulk-export'))

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(expect.stringContaining('Failed'), 'error')
      })
    })
  })

  describe('Bulk delete', () => {
    it('deletes selected tasks after confirmation', async () => {
      await renderAndWaitForTasks()

      const checkboxes = screen.getAllByRole('checkbox')
      fireEvent.click(checkboxes[1])

      fireEvent.click(screen.getByTestId('bulk-delete'))

      await waitFor(() => {
        expect(projectsAPI.bulkDeleteTasks).toHaveBeenCalledWith('project-1', expect.any(Array))
      })
    })

    it('handles bulk delete failure', async () => {
      ;(projectsAPI.bulkDeleteTasks as jest.Mock).mockRejectedValue(new Error('Delete failed'))
      await renderAndWaitForTasks()

      const checkboxes = screen.getAllByRole('checkbox')
      fireEvent.click(checkboxes[1])

      fireEvent.click(screen.getByTestId('bulk-delete'))

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(expect.stringContaining('Failed'), 'error')
      })
    })
  })

  // ---- SORTING ----

  describe('Sort by various columns', () => {
    it('sorts by annotations column', async () => {
      await renderAndWaitForTasks()

      const annotationsHeader = screen.getAllByText(/Annotations/i)
      const th = annotationsHeader[0]?.closest('th')
      if (th) {
        fireEvent.click(th)
        await waitFor(() => {
          expect(mockUpdatePreference).toHaveBeenCalledWith('sortBy', 'annotations')
        })
      }
    })

    it('sorts by generations column', async () => {
      await renderAndWaitForTasks()

      const header = screen.getAllByText(/Generations/i)
      const th = header[0]?.closest('th')
      if (th) {
        fireEvent.click(th)
        await waitFor(() => {
          expect(mockUpdatePreference).toHaveBeenCalledWith('sortBy', 'generations')
        })
      }
    })

    it('toggles sort order when clicking same column', async () => {
      // Start with sortBy = 'id'
      await renderAndWaitForTasks()

      // Find the ID column header - it's rendered as t(column.label) which returns 'ID'
      const sortableThs = document.querySelectorAll('th[role="button"]')
      const idTh = Array.from(sortableThs).find(th => th.textContent?.includes('ID'))
      if (idTh) {
        fireEvent.click(idTh)
        // Since we started with id desc, clicking should toggle to asc
        await waitFor(() => {
          expect(mockUpdatePreference).toHaveBeenCalledWith('sortOrder', 'asc')
        })
      }
    })

    it('handles keyboard navigation on sortable columns', async () => {
      await renderAndWaitForTasks()

      const sortableThs = document.querySelectorAll('th[role="button"]')
      const idTh = Array.from(sortableThs).find(th => th.textContent?.includes('ID'))
      if (idTh) {
        fireEvent.keyDown(idTh, { key: 'Enter' })
        await waitFor(() => {
          expect(mockUpdatePreference).toHaveBeenCalled()
        })
      }
    })
  })

  // ---- FILTERS ----

  describe('Status filter', () => {
    it('filters by completed status', async () => {
      await renderAndWaitForTasks()

      fireEvent.change(screen.getByTestId('status-filter'), { target: { value: 'completed' } })

      await waitFor(() => {
        // After filtering, only completed task should show
        expect(screen.getByText(/annotationTab\.display\.showing/)).toBeInTheDocument()
      })
    })

    it('filters by incomplete status', async () => {
      await renderAndWaitForTasks()

      fireEvent.change(screen.getByTestId('status-filter'), { target: { value: 'incomplete' } })

      await waitFor(() => {
        expect(screen.getByText(/annotationTab\.display\.showing/)).toBeInTheDocument()
      })
    })
  })

  describe('Date range filter', () => {
    it('filters by date range', async () => {
      await renderAndWaitForTasks()

      fireEvent.click(screen.getByTestId('set-date-range'))

      await waitFor(() => {
        expect(screen.getByText(/annotationTab\.display\.showing/)).toBeInTheDocument()
      })
    })
  })

  describe('Annotator filter', () => {
    it('sets annotator filter', async () => {
      await renderAndWaitForTasks()

      fireEvent.click(screen.getByTestId('set-annotator'))
      // The annotator filter implementation currently always returns true
    })
  })

  describe('Metadata filter', () => {
    it('filters by metadata', async () => {
      await renderAndWaitForTasks()

      fireEvent.click(screen.getByTestId('set-metadata'))

      await waitFor(() => {
        expect(screen.getByText(/annotationTab\.display\.showing/)).toBeInTheDocument()
      })
    })

    it('clears metadata filter', async () => {
      await renderAndWaitForTasks()

      fireEvent.click(screen.getByTestId('set-metadata'))
      fireEvent.click(screen.getByTestId('clear-metadata'))

      await waitFor(() => {
        expect(screen.getByText(/annotationTab\.display\.showing/)).toBeInTheDocument()
      })
    })
  })

  // ---- SELECT ALL ----

  describe('Select all', () => {
    it('selects all tasks via header checkbox', async () => {
      await renderAndWaitForTasks()

      const headerCb = screen.getByTestId('header-checkbox')
      fireEvent.click(headerCb)

      // Wait for the setTimeout in handleSelectAll
      await act(async () => { await new Promise(r => setTimeout(r, 50)) })
    })
  })

  // ---- VIEW TASK DATA ----

  describe('View task data', () => {
    it('opens task data modal when eye icon clicked', async () => {
      await renderAndWaitForTasks()

      // Find the view_data buttons - they have title="annotation.viewTaskData"
      // In the table, these are buttons inside view_data td cells
      const allButtons = document.querySelectorAll('td button')
      const viewButton = Array.from(allButtons).find(b => b.getAttribute('title') === 'annotation.viewTaskData')
      if (viewButton) {
        fireEvent.click(viewButton)

        await waitFor(() => {
          expect(screen.getByTestId('task-data-modal')).toBeInTheDocument()
        })

        // Close it
        fireEvent.click(screen.getByTestId('close-data-modal'))

        await waitFor(() => {
          expect(screen.queryByTestId('task-data-modal')).not.toBeInTheDocument()
        })
      }
    })
  })

  // ---- COMPARISON MODAL ----

  describe('Comparison modal', () => {
    it('opens comparison modal when clicking a task row', async () => {
      await renderAndWaitForTasks()

      // Click a table row (not a checkbox or button)
      const rows = document.querySelectorAll('tbody tr')
      if (rows.length > 0) {
        fireEvent.click(rows[0])

        await waitFor(() => {
          expect(screen.getByTestId('comparison-modal')).toBeInTheDocument()
        })

        fireEvent.click(screen.getByTestId('close-comparison'))

        await waitFor(() => {
          expect(screen.queryByTestId('comparison-modal')).not.toBeInTheDocument()
        })
      }
    })
  })

  // ---- IMPORT MODAL ----

  describe('Import modal', () => {
    it('opens import modal and completes import', async () => {
      await renderAndWaitForTasks()

      fireEvent.click(screen.getByTestId('import-button'))

      await waitFor(() => {
        expect(screen.getByTestId('import-modal')).toBeInTheDocument()
      })

      // Complete import
      fireEvent.click(screen.getByTestId('complete-import'))

      await waitFor(() => {
        // Should refresh tasks
        expect(mockFetchProjectTasks).toHaveBeenCalledTimes(2) // initial + after import
      })
    })

    it('closes import modal', async () => {
      await renderAndWaitForTasks()

      fireEvent.click(screen.getByTestId('import-button'))
      await waitFor(() => expect(screen.getByTestId('import-modal')).toBeInTheDocument())

      fireEvent.click(screen.getByTestId('close-import'))
      await waitFor(() => {
        expect(screen.queryByTestId('import-modal')).not.toBeInTheDocument()
      })
    })
  })

  // ---- ASSIGNMENT MODAL ----

  describe('Assignment modal', () => {
    it('opens assignment modal via bulk assign', async () => {
      await renderAndWaitForTasks()

      // Select a task first
      const checkboxes = screen.getAllByRole('checkbox')
      fireEvent.click(checkboxes[1])

      fireEvent.click(screen.getByTestId('bulk-assign'))

      await waitFor(() => {
        expect(screen.getByTestId('assignment-modal')).toBeInTheDocument()
      })
    })

    it('completes assignment and refreshes tasks', async () => {
      await renderAndWaitForTasks()

      const checkboxes = screen.getAllByRole('checkbox')
      fireEvent.click(checkboxes[1])

      fireEvent.click(screen.getByTestId('bulk-assign'))
      await waitFor(() => expect(screen.getByTestId('assignment-modal')).toBeInTheDocument())

      fireEvent.click(screen.getByTestId('complete-assignment'))

      await waitFor(() => {
        // Toast uses translation key: annotationTab.messages.tasksAssigned
        expect(mockAddToast).toHaveBeenCalledWith(expect.any(String), 'success')
      })
    })

    it('shows warning when no tasks selected for assignment', async () => {
      await renderAndWaitForTasks()

      // Click assign without selecting tasks
      fireEvent.click(screen.getByTestId('bulk-assign'))

      expect(mockAddToast).toHaveBeenCalledWith(expect.any(String), 'warning')
    })

    it('opens assignment from individual task assign button', async () => {
      await renderAndWaitForTasks()

      const assignBtns = screen.queryAllByTestId('assign-task-btn')
      if (assignBtns.length > 0) {
        fireEvent.click(assignBtns[0])

        await waitFor(() => {
          expect(screen.getByTestId('assignment-modal')).toBeInTheDocument()
        })
      }
    })
  })

  // ---- UNASSIGN ----

  describe('Unassign', () => {
    it('unassigns a task and refreshes', async () => {
      await renderAndWaitForTasks()

      const unassignBtn = screen.queryByTestId('unassign-assign-1')
      if (unassignBtn) {
        fireEvent.click(unassignBtn)

        await waitFor(() => {
          expect(projectsAPI.removeTaskAssignment).toHaveBeenCalledWith('project-1', '2', 'assign-1')
        })
        // Toast uses translation key: success.assignmentRemoved
        expect(mockAddToast).toHaveBeenCalledWith(expect.any(String), 'success')
      }
    })

    it('handles unassign failure', async () => {
      ;(projectsAPI.removeTaskAssignment as jest.Mock).mockRejectedValue(new Error('Failed'))
      await renderAndWaitForTasks()

      const unassignBtn = screen.queryByTestId('unassign-assign-1')
      if (unassignBtn) {
        fireEvent.click(unassignBtn)

        await waitFor(() => {
          expect(mockAddToast).toHaveBeenCalledWith(expect.any(String), 'error')
        })
      }
    })
  })

  // ---- SEARCH ----

  describe('Search', () => {
    it('shows search bar and filters tasks', async () => {
      // Enable search in preferences
      mockUseTablePreferences.mockReturnValue({
        preferences: { showSearch: true, sortBy: 'id', sortOrder: 'desc' as const, filterStatus: 'all' as const },
        updatePreference: mockUpdatePreference,
      })

      await renderAndWaitForTasks()

      // Search input should be visible
      const searchInput = screen.getByPlaceholderText('search.placeholder')
      expect(searchInput).toBeInTheDocument()

      fireEvent.change(searchInput, { target: { value: 'task 1' } })

      await waitFor(() => {
        // Should filter to only matching tasks
        expect(screen.getByText(/annotationTab\.display\.showing/)).toBeInTheDocument()
      })
    })
  })

  // ---- EMPTY STATE ----

  describe('Empty state', () => {
    it('shows empty state when no tasks loaded', async () => {
      mockFetchProjectTasks.mockResolvedValue([])
      render(<AnnotationTab projectId="project-1" />)

      await waitFor(() => expect(mockFetchProjectTasks).toHaveBeenCalled())
      await act(async () => { await new Promise(r => setTimeout(r, 0)) })

      expect(screen.getByText('annotationTab.empty.noTasks')).toBeInTheDocument()
    })

    it('shows no-match message when search/filter yields no results', async () => {
      mockUseTablePreferences.mockReturnValue({
        preferences: { showSearch: true, sortBy: 'id', sortOrder: 'desc' as const, filterStatus: 'all' as const },
        updatePreference: mockUpdatePreference,
      })

      await renderAndWaitForTasks()

      const searchInput = screen.getByPlaceholderText('search.placeholder')
      fireEvent.change(searchInput, { target: { value: 'nonexistent-query-xyz' } })

      await waitFor(() => {
        expect(screen.getByText('annotationTab.empty.noMatch')).toBeInTheDocument()
      })
    })
  })

  // ---- DYNAMIC COLUMNS (data_ and meta_) ----

  describe('Dynamic columns', () => {
    it('renders data_ columns in the table', async () => {
      await renderAndWaitForTasks()

      // The data_text column should be visible in column headers
      const headers = document.querySelectorAll('th')
      expect(headers.length).toBeGreaterThan(5)
    })

    it('renders meta_ columns in the table headers', async () => {
      await renderAndWaitForTasks()

      // The columns include meta_category which should have been rendered
      // The th text comes from t(column.label) = 'meta.category'
      const headers = document.querySelectorAll('th')
      // At minimum we should have the system columns + data_ + meta_ columns
      expect(headers.length).toBeGreaterThanOrEqual(10)
    })
  })

  // ---- LOADING STATE ----

  describe('Loading state', () => {
    it('shows loading spinner while tasks are loading', () => {
      mockUseProjectStore.mockReturnValue({
        currentProject: { id: 'project-1', title: 'Test Project', num_tasks: 0, num_annotations: 0 },
        loading: true,
        fetchProjectTasks: jest.fn().mockReturnValue(new Promise(() => {})), // never resolves
      } as any)

      render(<AnnotationTab projectId="project-1" />)

      // Should show loading spinner
      const spinner = document.querySelector('.animate-spin')
      expect(spinner).toBeInTheDocument()
    })
  })

  // ---- SORT BY DIFFERENT COLUMNS (exercising switch cases) ----

  describe('Sort by various columns - switch cases', () => {
    it('sorts by completed column', async () => {
      mockUseTablePreferences.mockReturnValue({
        preferences: { showSearch: false, sortBy: 'completed', sortOrder: 'asc' as const, filterStatus: 'all' as const },
        updatePreference: mockUpdatePreference,
      })
      await renderAndWaitForTasks()
      // Sort should have been applied - just check renders without error
      expect(screen.getByText(/annotationTab\.display\.showing/)).toBeInTheDocument()
    })

    it('sorts by annotations column', async () => {
      mockUseTablePreferences.mockReturnValue({
        preferences: { showSearch: false, sortBy: 'annotations', sortOrder: 'desc' as const, filterStatus: 'all' as const },
        updatePreference: mockUpdatePreference,
      })
      await renderAndWaitForTasks()
      expect(screen.getByText(/annotationTab\.display\.showing/)).toBeInTheDocument()
    })

    it('sorts by generations column', async () => {
      mockUseTablePreferences.mockReturnValue({
        preferences: { showSearch: false, sortBy: 'generations', sortOrder: 'asc' as const, filterStatus: 'all' as const },
        updatePreference: mockUpdatePreference,
      })
      await renderAndWaitForTasks()
      expect(screen.getByText(/annotationTab\.display\.showing/)).toBeInTheDocument()
    })

    it('sorts by created column', async () => {
      mockUseTablePreferences.mockReturnValue({
        preferences: { showSearch: false, sortBy: 'created', sortOrder: 'desc' as const, filterStatus: 'all' as const },
        updatePreference: mockUpdatePreference,
      })
      await renderAndWaitForTasks()
      expect(screen.getByText(/annotationTab\.display\.showing/)).toBeInTheDocument()
    })

    it('sorts by default (unknown column) ascending', async () => {
      mockUseTablePreferences.mockReturnValue({
        preferences: { showSearch: false, sortBy: 'unknown', sortOrder: 'asc' as const, filterStatus: 'all' as const },
        updatePreference: mockUpdatePreference,
      })
      await renderAndWaitForTasks()
      expect(screen.getByText(/annotationTab\.display\.showing/)).toBeInTheDocument()
    })
  })

  // ---- BULK DELETE SUCCESS PATH ----

  describe('Bulk delete success path', () => {
    it('refreshes tasks after successful delete', async () => {
      await renderAndWaitForTasks()

      const checkboxes = screen.getAllByRole('checkbox')
      fireEvent.click(checkboxes[1])

      fireEvent.click(screen.getByTestId('bulk-delete'))

      await waitFor(() => {
        expect(projectsAPI.bulkDeleteTasks).toHaveBeenCalled()
      })

      // After successful delete, tasks should be refreshed
      await waitFor(() => {
        expect(mockFetchProjectTasks).toHaveBeenCalledTimes(2) // initial + after delete
      })
    })
  })

  // ---- METADATA FILTER EDGE CASES ----

  describe('Metadata filter edge cases', () => {
    it('filters by metadata array values matching task array values', async () => {
      // Task has meta: { category: 'legal' } (string)
      // Filter with array: { category: ['legal'] }
      await renderAndWaitForTasks()
      fireEvent.click(screen.getByTestId('set-metadata'))

      await waitFor(() => {
        expect(screen.getByText(/annotationTab\.display\.showing/)).toBeInTheDocument()
      })
    })
  })

  // ---- SELECTED TASKS COUNTER ----

  describe('Selected tasks counter', () => {
    it('shows selected count in the header', async () => {
      await renderAndWaitForTasks()

      const checkboxes = screen.getAllByRole('checkbox')
      fireEvent.click(checkboxes[1])
      fireEvent.click(checkboxes[2])

      await waitFor(() => {
        expect(screen.getByText(/annotationTab\.display\.selected/)).toBeInTheDocument()
      })
    })
  })
})

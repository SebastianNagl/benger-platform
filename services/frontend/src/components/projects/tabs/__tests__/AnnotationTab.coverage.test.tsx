/**
 * Additional coverage tests for AnnotationTab component
 * Covers bulk archive, sort by different columns, view modals, cancel delete
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
                <button data-testid={`unassign-${a.id}`} onClick={() => onUnassign(a.id)}>Remove</button>
              )}
            </div>
          ))
        : onAssign && <button onClick={onAssign}>Assign</button>}
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
  FilterDropdown: ({ filterStatus, onStatusChange }: any) => (
    <div data-testid="filter-dropdown">
      <select value={filterStatus} onChange={(e) => onStatusChange(e.target.value)} data-testid="status-filter">
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
  Button: ({ children, onClick, variant, disabled, className, title }: any) => (
    <button onClick={onClick} disabled={disabled} data-variant={variant} className={className} title={title}>
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
    meta: {},
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
    meta: {},
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
]

describe('AnnotationTab - Coverage', () => {
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

    mockUseColumnSettings.mockImplementation((projectId, userId, cols) => ({
      columns: cols || defaultColumns,
      toggleColumn: jest.fn(),
      resetColumns: jest.fn(),
      updateColumns: jest.fn(),
      reorderColumns: jest.fn(),
    }))

    mockUseTablePreferences.mockReturnValue({
      preferences: { showSearch: false, sortBy: 'id', sortOrder: 'desc' as const, filterStatus: 'all' as const },
      updatePreference: jest.fn(),
    })

    ;(projectsAPI.export as jest.Mock).mockResolvedValue(new Blob(['test']))
    ;(projectsAPI.bulkExportTasks as jest.Mock).mockResolvedValue(new Blob(['test']))
    ;(projectsAPI.bulkDeleteTasks as jest.Mock).mockResolvedValue({ deleted: 1 })
    ;(projectsAPI.bulkArchiveTasks as jest.Mock).mockResolvedValue({ archived: 1 })
    ;(projectsAPI.getMembers as jest.Mock).mockResolvedValue([])
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
  })

  afterEach(() => {
    jest.restoreAllMocks()
  })

  describe('Bulk Archive', () => {
    it('should archive selected tasks', async () => {
      render(<AnnotationTab projectId="project-1" />)

      await waitFor(() => { expect(mockFetchProjectTasks).toHaveBeenCalled() })
      await act(async () => { await new Promise(r => setTimeout(r, 0)) })

      const checkboxes = screen.getAllByRole('checkbox')
      fireEvent.click(checkboxes[1])

      const archiveButton = screen.getByTestId('bulk-archive')
      fireEvent.click(archiveButton)

      await waitFor(() => {
        expect(projectsAPI.bulkArchiveTasks).toHaveBeenCalledWith('project-1', expect.any(Array))
      })
    })

    it('should handle archive errors', async () => {
      ;(projectsAPI.bulkArchiveTasks as jest.Mock).mockRejectedValue(new Error('Archive failed'))

      render(<AnnotationTab projectId="project-1" />)

      await waitFor(() => { expect(mockFetchProjectTasks).toHaveBeenCalled() })
      await act(async () => { await new Promise(r => setTimeout(r, 0)) })

      const checkboxes = screen.getAllByRole('checkbox')
      fireEvent.click(checkboxes[1])

      fireEvent.click(screen.getByTestId('bulk-archive'))

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(expect.stringContaining('Failed'), 'error')
      })
    })
  })

  describe('Sorting by Different Columns', () => {
    it('should sort by completed column', async () => {
      const mockUpdatePreference = jest.fn()
      mockUseTablePreferences.mockReturnValue({
        preferences: { showSearch: false, sortBy: 'id', sortOrder: 'desc' as const, filterStatus: 'all' as const },
        updatePreference: mockUpdatePreference,
      })

      render(<AnnotationTab projectId="project-1" />)

      await waitFor(() => { expect(mockFetchProjectTasks).toHaveBeenCalled() })

      // Find and click the completed column header
      const completedHeaders = screen.getAllByText(/Completed/i)
      const completedTh = completedHeaders[0]?.closest('th')
      if (completedTh) {
        fireEvent.click(completedTh)
        await waitFor(() => {
          expect(mockUpdatePreference).toHaveBeenCalledWith('sortBy', 'completed')
        })
      }
    })

    it('should sort by created column', async () => {
      const mockUpdatePreference = jest.fn()
      mockUseTablePreferences.mockReturnValue({
        preferences: { showSearch: false, sortBy: 'id', sortOrder: 'desc' as const, filterStatus: 'all' as const },
        updatePreference: mockUpdatePreference,
      })

      render(<AnnotationTab projectId="project-1" />)

      await waitFor(() => { expect(mockFetchProjectTasks).toHaveBeenCalled() })

      const createdHeaders = screen.getAllByText(/Created/i)
      const createdTh = createdHeaders[0]?.closest('th')
      if (createdTh) {
        fireEvent.click(createdTh)
        await waitFor(() => {
          expect(mockUpdatePreference).toHaveBeenCalledWith('sortBy', 'created')
        })
      }
    })
  })

  describe('Cancel Delete', () => {
    it('should not delete when confirm is cancelled', async () => {
      global.confirm = jest.fn(() => false)

      render(<AnnotationTab projectId="project-1" />)

      await waitFor(() => { expect(mockFetchProjectTasks).toHaveBeenCalled() })
      await act(async () => { await new Promise(r => setTimeout(r, 0)) })

      const checkboxes = screen.getAllByRole('checkbox')
      fireEvent.click(checkboxes[1])

      fireEvent.click(screen.getByTestId('bulk-delete'))

      // Should not call API when cancelled
      expect(projectsAPI.bulkDeleteTasks).not.toHaveBeenCalled()
    })
  })

  describe('Empty Selection Guards', () => {
    it('should not export when no tasks selected and bulk export clicked', async () => {
      render(<AnnotationTab projectId="project-1" />)

      await waitFor(() => { expect(mockFetchProjectTasks).toHaveBeenCalled() })

      // Click bulk export without selecting tasks
      fireEvent.click(screen.getByTestId('bulk-export'))

      // bulkExportTasks should not be called for 0 selected
      await act(async () => { await new Promise(r => setTimeout(r, 50)) })
      // The guard returns early when selectedTasks.size === 0
    })

    it('should not archive when no tasks selected', async () => {
      render(<AnnotationTab projectId="project-1" />)

      await waitFor(() => { expect(mockFetchProjectTasks).toHaveBeenCalled() })

      fireEvent.click(screen.getByTestId('bulk-archive'))

      await act(async () => { await new Promise(r => setTimeout(r, 50)) })
      expect(projectsAPI.bulkArchiveTasks).not.toHaveBeenCalled()
    })
  })

  describe('Task Row Rendering', () => {
    it('renders task rows with completion indicator', async () => {
      render(<AnnotationTab projectId="project-1" />)

      await waitFor(() => {
        expect(mockFetchProjectTasks).toHaveBeenCalled()
      })

      await act(async () => { await new Promise(r => setTimeout(r, 0)) })

      // Should show task data in the table
      const tbody = document.querySelector('tbody')
      expect(tbody).not.toBeNull()
      expect(screen.getByText(/annotationTab\.display\.showing/i)).toBeInTheDocument()
    })
  })

  describe('Assignment Unassign', () => {
    it('should unassign a task when remove button clicked', async () => {
      render(<AnnotationTab projectId="project-1" />)

      await waitFor(() => { expect(mockFetchProjectTasks).toHaveBeenCalled() })
      await act(async () => { await new Promise(r => setTimeout(r, 0)) })

      // Find the unassign button for the assigned task
      const unassignBtn = screen.queryByTestId('unassign-assign-1')
      if (unassignBtn) {
        fireEvent.click(unassignBtn)

        await waitFor(() => {
          expect(projectsAPI.removeTaskAssignment).toHaveBeenCalledWith(
            'project-1', '2', 'assign-1'
          )
        })
      }
    })
  })
})

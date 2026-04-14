/**
 * Surgical coverage tests for TaskAnnotationComparisonModal
 *
 * Targets previously uncovered functions:
 * - renderAnnotationValue for boolean, array, object, number, long string types
 * - onClose button click in header and footer
 * - retry button click on error state
 * - "Add My Annotation" button click
 * - "Edit My Annotation" button click
 * - "Load More" annotations button
 * - onCancel callback from AnnotationCreator
 *
 * @jest-environment jsdom
 */

import { projectsAPI } from '@/lib/api/projects'
import { UsersClient } from '@/lib/api/users'
import '@testing-library/jest-dom'
import { fireEvent, render, screen, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { TaskAnnotationComparisonModal } from '../TaskAnnotationComparisonModal'

jest.mock('@/lib/api/projects')
jest.mock('@/lib/api/users')

const mockUser = {
  id: 'user-123',
  username: 'testuser',
  email: 'test@example.com',
}

jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: mockUser,
  }),
}))

const translations: Record<string, string> = {
  'annotation.comparison.modal.title': 'Annotations',
  'annotation.comparison.modal.taskId': 'Task {{taskId}}',
  'annotation.comparison.description': 'Compare annotations from different annotators',
  'annotation.comparison.modal.close': 'Close',
  'annotation.comparison.modal.retry': 'Retry',
  'annotation.comparison.tabs.createNew': 'Create New Annotation',
  'annotation.comparison.tabs.addYourAnnotation': 'Add Your Annotation',
  'annotation.comparison.tabs.editYourAnnotation': 'Edit Your Annotation',
  'annotation.comparison.tabs.updateExisting': 'Update your existing annotation',
  'annotation.comparison.tabs.addNew': 'Add a new annotation to this task',
  'annotation.comparison.empty.noAnnotationsYet': 'This task has no annotations yet.',
  'annotation.comparison.empty.noAnnotationsAvailable': 'No annotations available',
  'annotation.comparison.messages.projectLoadFailed': 'Failed to load project',
  'annotation.comparison.messages.loadFailed': 'Failed to load annotations',
  'annotation.comparison.messages.annotationSubmitted': 'Annotation submitted!',
  'annotation.comparison.messages.annotationUpdated': 'Annotation updated!',
  'annotation.comparison.messages.loadingUserAnnotation': 'Loading your annotation...',
  'annotation.comparison.messages.waitingForAnnotation': 'Please wait',
  'annotation.comparison.messages.noData': 'No annotation data',
  'annotation.comparison.result.notAnswered': 'Not answered',
  'annotation.comparison.result.yes': 'Yes',
  'annotation.comparison.result.no': 'No',
  'annotation.comparison.result.showFullText': 'Show full text',
  'annotation.comparison.status.draft': 'Draft',
  'annotation.comparison.status.submitted': 'Submitted',
  'annotation.comparison.status.approved': 'Approved',
  'annotation.comparison.status.rejected': 'Rejected',
  'annotation.comparison.info.lastUpdated': 'Last updated: {{date}}',
  'annotation.comparison.info.timeSpent': 'Time spent: {{seconds}}s',
  'annotation.comparison.info.confidence': 'Confidence: {{percent}}%',
  'annotation.comparison.info.showingVersions': 'Showing {{count}} versions',
  'annotation.comparison.info.versionLabel': 'Version {{version}} - {{date}}',
  'annotation.comparison.info.annotatorNotes': 'Annotator Notes',
  'annotation.comparison.info.annotatorCount': '{{count}} annotator{{plural}}',
  'annotation.comparison.info.totalAnnotations': '{{count}} total annotation{{plural}}',
  'annotation.comparison.buttons.addMyAnnotation': 'Add My Annotation',
  'annotation.comparison.buttons.editMyAnnotation': 'Edit My Annotation',
  'annotation.comparison.buttons.loadMore': 'Load {{count}} more',
}

const mockT = (key: string, vars?: Record<string, any>) => {
  let result = translations[key] || key
  if (vars) {
    Object.keys(vars).forEach((varKey) => {
      result = result.replace(`{{${varKey}}}`, String(vars[varKey]))
    })
  }
  return result
}

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: mockT,
  }),
}))

let mockOnSubmit: jest.Mock
let mockOnCancel: jest.Mock

jest.mock('@/components/labeling/AnnotationCreator', () => ({
  AnnotationCreator: ({ onSubmit, onCancel, task, projectId, labelConfig }: any) => {
    mockOnSubmit = onSubmit
    mockOnCancel = onCancel
    return (
      <div data-testid="annotation-creator">
        <button data-testid="creator-submit" onClick={() => onSubmit({ result: [] })}>Submit</button>
        <button data-testid="creator-cancel" onClick={() => onCancel()}>Cancel</button>
      </div>
    )
  },
}))

jest.mock('@/lib/utils/logger', () => ({
  logger: { debug: jest.fn(), info: jest.fn(), warn: jest.fn(), error: jest.fn() },
}))

const makeAnnotation = (overrides: any = {}) => ({
  id: `ann-${Math.random().toString(36).slice(2, 8)}`,
  completed_by: 'other-user-456',
  result: [
    { from_name: 'field1', type: 'choices', value: { choices: ['A'] } },
  ],
  was_cancelled: false,
  ground_truth: false,
  created_at: '2025-06-01T10:00:00Z',
  updated_at: '2025-06-01T10:00:00Z',
  metadata: {},
  ...overrides,
})

const mockTask = {
  id: 'task-1',
  data: { text: 'Hello world' },
  annotations: [],
  predictions: [],
  meta: {},
  created_at: '2025-01-01',
  updated_at: '2025-01-01',
}

const mockProject = {
  id: 'proj-1',
  title: 'Test Project',
  label_config: '<View><Choices name="field1"><Choice value="A"/></Choices></View>',
}

describe('TaskAnnotationComparisonModal - Surgical Coverage', () => {
  const user = userEvent.setup()

  beforeEach(() => {
    jest.clearAllMocks()
    ;(UsersClient as jest.Mock).mockImplementation(() => ({
      getAllUsers: jest.fn().mockResolvedValue([
        { id: 'other-user-456', username: 'other', email: 'other@test.com' },
        { id: 'user-123', username: 'testuser', email: 'test@example.com' },
      ]),
    }))
  })

  it('renders various annotation value types (boolean, array, object, number)', async () => {
    const annotations = [
      makeAnnotation({
        id: 'ann-1',
        completed_by: 'other-user-456',
        result: [
          { from_name: 'bool_field', type: 'choices', value: true },
          { from_name: 'array_field', type: 'labels', value: ['item1', 'item2'] },
          { from_name: 'object_field', type: 'rating', value: { score: 5, label: 'good' } },
          { from_name: 'number_field', type: 'number', value: 42 },
          { from_name: 'long_text', type: 'textarea', value: 'x'.repeat(250) },
          { from_name: 'null_field', type: 'text', value: null },
        ],
      }),
    ]
    ;(projectsAPI.get as jest.Mock).mockResolvedValue(mockProject)
    ;(projectsAPI.getTaskAnnotations as jest.Mock).mockResolvedValue(annotations)

    render(
      <TaskAnnotationComparisonModal
        task={mockTask as any}
        isOpen={true}
        onClose={jest.fn()}
        projectId="proj-1"
      />
    )

    await waitFor(() => {
      // Boolean renders Yes/No
      expect(screen.getByText('Yes')).toBeInTheDocument()
      // Array renders items
      expect(screen.getByText('item1')).toBeInTheDocument()
      expect(screen.getByText('item2')).toBeInTheDocument()
      // Number renders with font-mono
      expect(screen.getByText('42')).toBeInTheDocument()
      // Null renders "Not answered"
      expect(screen.getByText('Not answered')).toBeInTheDocument()
    })

    // Long text shows "Show full text" details
    expect(screen.getByText('Show full text')).toBeInTheDocument()
  })

  it('clicking close button in header calls onClose', async () => {
    const onClose = jest.fn()
    ;(projectsAPI.get as jest.Mock).mockResolvedValue(mockProject)
    ;(projectsAPI.getTaskAnnotations as jest.Mock).mockResolvedValue([
      makeAnnotation({ completed_by: 'other-user-456' }),
    ])

    render(
      <TaskAnnotationComparisonModal
        task={mockTask as any}
        isOpen={true}
        onClose={onClose}
        projectId="proj-1"
      />
    )

    await waitFor(() => {
      expect(screen.getByText('Annotations')).toBeInTheDocument()
    })

    // Click the close button in footer
    const closeButtons = screen.getAllByText('Close')
    await user.click(closeButtons[0])
    expect(onClose).toHaveBeenCalled()
  })

  it('clicks "Add My Annotation" button when user has not annotated', async () => {
    ;(projectsAPI.get as jest.Mock).mockResolvedValue(mockProject)
    ;(projectsAPI.getTaskAnnotations as jest.Mock).mockResolvedValue([
      makeAnnotation({ completed_by: 'other-user-456' }),
    ])

    render(
      <TaskAnnotationComparisonModal
        task={mockTask as any}
        isOpen={true}
        onClose={jest.fn()}
        projectId="proj-1"
      />
    )

    await waitFor(() => {
      expect(screen.getByText('Add My Annotation')).toBeInTheDocument()
    })

    await user.click(screen.getByText('Add My Annotation'))

    // Should show the AnnotationCreator
    await waitFor(() => {
      expect(screen.getByTestId('annotation-creator')).toBeInTheDocument()
    })
  })

  it('clicks "Edit My Annotation" button when user already has annotations', async () => {
    ;(projectsAPI.get as jest.Mock).mockResolvedValue(mockProject)
    ;(projectsAPI.getTaskAnnotations as jest.Mock).mockResolvedValue([
      makeAnnotation({ completed_by: 'user-123', id: 'my-ann-1' }),
    ])

    render(
      <TaskAnnotationComparisonModal
        task={mockTask as any}
        isOpen={true}
        onClose={jest.fn()}
        projectId="proj-1"
      />
    )

    await waitFor(() => {
      expect(screen.getByText('Edit My Annotation')).toBeInTheDocument()
    })

    await user.click(screen.getByText('Edit My Annotation'))

    // Should show the AnnotationCreator in edit mode
    await waitFor(() => {
      expect(screen.getByTestId('annotation-creator')).toBeInTheDocument()
    })
  })

  it('clicks retry button on error state', async () => {
    ;(projectsAPI.get as jest.Mock).mockResolvedValue(mockProject)
    ;(projectsAPI.getTaskAnnotations as jest.Mock)
      .mockRejectedValueOnce(new Error('Network error'))
      .mockResolvedValueOnce([])

    render(
      <TaskAnnotationComparisonModal
        task={mockTask as any}
        isOpen={true}
        onClose={jest.fn()}
        projectId="proj-1"
      />
    )

    await waitFor(() => {
      expect(screen.getByText('Retry')).toBeInTheDocument()
    })

    await user.click(screen.getByText('Retry'))

    await waitFor(() => {
      expect(projectsAPI.getTaskAnnotations).toHaveBeenCalledTimes(2)
    })
  })

  it('cancels annotation creation via AnnotationCreator onCancel in add mode', async () => {
    ;(projectsAPI.get as jest.Mock).mockResolvedValue(mockProject)
    ;(projectsAPI.getTaskAnnotations as jest.Mock).mockResolvedValue([
      makeAnnotation({ completed_by: 'other-user-456' }),
    ])

    render(
      <TaskAnnotationComparisonModal
        task={mockTask as any}
        isOpen={true}
        onClose={jest.fn()}
        projectId="proj-1"
      />
    )

    await waitFor(() => {
      expect(screen.getByText('Add My Annotation')).toBeInTheDocument()
    })

    // Enter add mode
    await user.click(screen.getByText('Add My Annotation'))

    await waitFor(() => {
      expect(screen.getByTestId('annotation-creator')).toBeInTheDocument()
    })

    // Click cancel
    await user.click(screen.getByTestId('creator-cancel'))

    // Should go back to view mode
    await waitFor(() => {
      expect(screen.getByText('Add My Annotation')).toBeInTheDocument()
    })
  })

  it('shows "Load More" button for annotator with many versions and clicks it', async () => {
    // Create 8 annotations for the same user to trigger lazy loading (default shows 5)
    const manyAnnotations = Array.from({ length: 8 }, (_, i) =>
      makeAnnotation({
        id: `ann-${i}`,
        completed_by: 'other-user-456',
        created_at: `2025-06-0${i + 1}T10:00:00Z`,
        updated_at: `2025-06-0${i + 1}T10:00:00Z`,
      })
    )
    ;(projectsAPI.get as jest.Mock).mockResolvedValue(mockProject)
    ;(projectsAPI.getTaskAnnotations as jest.Mock).mockResolvedValue(manyAnnotations)

    render(
      <TaskAnnotationComparisonModal
        task={mockTask as any}
        isOpen={true}
        onClose={jest.fn()}
        projectId="proj-1"
      />
    )

    await waitFor(() => {
      expect(screen.getByText(/Load \d+ more/)).toBeInTheDocument()
    })

    // Click "Load more"
    await user.click(screen.getByText(/Load \d+ more/))

    // After loading more, the button should be gone (8 - 5 = 3, then +5 = 10 > 8)
    await waitFor(() => {
      expect(screen.queryByText(/Load \d+ more/)).not.toBeInTheDocument()
    })
  })

  it('shows empty state with create mode for task with no annotations', async () => {
    ;(projectsAPI.get as jest.Mock).mockResolvedValue(mockProject)
    ;(projectsAPI.getTaskAnnotations as jest.Mock).mockResolvedValue([])

    render(
      <TaskAnnotationComparisonModal
        task={mockTask as any}
        isOpen={true}
        onClose={jest.fn()}
        projectId="proj-1"
      />
    )

    await waitFor(() => {
      expect(screen.getByTestId('annotation-creator')).toBeInTheDocument()
      expect(screen.getByText('Create New Annotation')).toBeInTheDocument()
    })
  })
})

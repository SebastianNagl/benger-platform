/**
 * @jest-environment jsdom
 *
 * Branch coverage tests for LabelingInterface.
 * Uses the same mock pattern as the existing LabelingInterface.test.tsx.
 */

import { useProjectStore } from '@/stores/projectStore'
import '@testing-library/jest-dom'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useRouter, useSearchParams } from 'next/navigation'
import { LabelingInterface } from '../LabelingInterface'

// Mock next/navigation
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
  useSearchParams: jest.fn(),
}))

// Mock react-hot-toast
jest.mock('react-hot-toast', () => {
  const mockToastFn = jest.fn()
  return {
    toast: Object.assign(mockToastFn, {
      success: jest.fn(),
      error: jest.fn(),
    }),
  }
})

// Mock projectsAPI
jest.mock('@/lib/api/projects', () => ({
  projectsAPI: {
    getTaskAnnotations: jest.fn().mockResolvedValue([]),
    saveDraft: jest.fn().mockResolvedValue(undefined),
    getTimerStatus: jest.fn().mockResolvedValue({
      server_time: new Date().toISOString(),
      session: null,
    }),
    startTimer: jest.fn().mockResolvedValue({
      session_id: 'session-1',
      server_time: new Date().toISOString(),
      started_at: new Date().toISOString(),
      time_limit_seconds: 600,
      is_strict: true,
    }),
    submitQuestionnaireResponse: jest.fn().mockResolvedValue({}),
  },
}))

import { toast } from 'react-hot-toast'
import { projectsAPI } from '@/lib/api/projects'
import { useAuth } from '@/contexts/AuthContext'

// Mock the DynamicAnnotationInterface
jest.mock('../DynamicAnnotationInterface', () => ({
  DynamicAnnotationInterface: function MockDynamicAnnotationInterface({
    onSubmit,
    onSkip,
    onChange,
    showSubmitButton,
    requireConfirmBeforeSubmit,
  }: any) {
    return (
      <div data-testid="dynamic-annotation">
        <span data-testid="show-submit-prop">{String(showSubmitButton)}</span>
        <span data-testid="require-confirm-prop">{String(requireConfirmBeforeSubmit)}</span>
        {onSkip && <button data-testid="mock-skip" onClick={onSkip}>Skip</button>}
        <button data-testid="mock-submit" onClick={() => {
          const results = [{from_name:'a',to_name:'t',type:'textarea',value:{text:['test']}}]
          onChange?.(results)
          onSubmit?.(results)
        }}>Submit</button>
      </div>
    )
  },
}))

// Mock AnnotationTimer
jest.mock('../AnnotationTimer', () => ({
  AnnotationTimer: ({ onTimeExpired }: any) => (
    <div data-testid="mock-timer">
      <button data-testid="expire-timer" onClick={onTimeExpired}>Expire</button>
    </div>
  ),
}))

// Mock PostAnnotationQuestionnaireModal
jest.mock('@/components/labeling/PostAnnotationQuestionnaireModal', () => ({
  PostAnnotationQuestionnaireModal: () => null,
}))

// Mock useActivityTracker
jest.mock('@/hooks/useActivityTracker', () => ({
  useActivityTracker: () => ({
    start: jest.fn(),
    getData: jest.fn().mockReturnValue({ activeMs: 1000, focusedMs: 900, tabSwitches: 0 }),
  }),
}))

jest.mock('@/lib/utils/variantHash', () => ({
  selectVariant: jest.fn().mockReturnValue(null),
}))

jest.mock('@/lib/utils/logger', () => ({
  logger: { debug: jest.fn(), warn: jest.fn(), error: jest.fn() },
}))

// Mock auth context
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: jest.fn(),
}))

// Mock I18n context
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, params?: any) => params?.defaultValue || key,
    locale: 'en',
  }),
}))

// Mock date-fns
jest.mock('date-fns', () => ({
  formatDistanceToNow: () => '2 minutes',
}))

// Mock the project store
jest.mock('@/stores/projectStore', () => ({
  useProjectStore: jest.fn(),
}))

const mockPush = jest.fn()

function setupMocks(storeOverrides: any = {}) {
  ;(useRouter as jest.Mock).mockReturnValue({ push: mockPush })
  ;(useSearchParams as jest.Mock).mockReturnValue({ get: jest.fn() })
  ;(useAuth as jest.Mock).mockReturnValue({
    user: { id: 'user-1', name: 'Test User' },
  })

  const defaults = {
    currentProject: null,
    currentTask: null,
    currentTaskPosition: null,
    currentTaskTotal: null,
    loading: false,
    getNextTask: jest.fn().mockResolvedValue(null),
    createAnnotation: jest.fn().mockResolvedValue(undefined),
    createAnnotationInternal: jest.fn().mockResolvedValue({ id: 'ann-1' }),
    skipTask: jest.fn().mockResolvedValue(undefined),
    fetchProject: jest.fn().mockResolvedValue(undefined),
    fetchProjectTasks: jest.fn().mockResolvedValue([]),
    taskCycle: [],
    currentTaskIndex: 0,
    setTaskByIndex: jest.fn(),
    advanceToNextTask: jest.fn(),
    completeCurrentTask: jest.fn(),
    labelConfigVersion: 0,
    allTasksCompleted: false,
    resetAnnotationCompletion: jest.fn(),
  }

  ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
    ...defaults,
    ...storeOverrides,
  })
}

describe('LabelingInterface - branch2 coverage', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    Storage.prototype.getItem = jest.fn().mockReturnValue(null)
    Storage.prototype.setItem = jest.fn()
    Storage.prototype.removeItem = jest.fn()
  })

  it('shows loading spinner when loading and no task', () => {
    setupMocks({ loading: true })
    const { container } = render(<LabelingInterface projectId="proj-1" />)
    expect(container.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('renders all-tasks-completed screen when no task and not loading', () => {
    setupMocks({ loading: false })
    render(<LabelingInterface projectId="proj-1" />)
    expect(screen.getByText('All tasks completed!')).toBeInTheDocument()
    expect(screen.getByText('Back to Project')).toBeInTheDocument()
  })

  it('navigates back when clicking Back to Project on completed screen', () => {
    setupMocks({ loading: false })
    render(<LabelingInterface projectId="proj-1" />)
    fireEvent.click(screen.getByText('Back to Project'))
    expect(mockPush).toHaveBeenCalledWith('/projects/proj-1')
  })

  it('renders no label config message when label_config is null', () => {
    setupMocks({
      currentProject: {
        id: 'proj-1',
        title: 'Test',
        label_config: null,
        annotation_time_limit_enabled: false,
      },
      currentTask: { id: 'task-1', data: {} },
      currentTaskPosition: 1,
      currentTaskTotal: 5,
    })

    render(<LabelingInterface projectId="proj-1" />)
    expect(screen.getByText('No label configuration found')).toBeInTheDocument()
  })

  it('renders LLM responses when present on task', () => {
    setupMocks({
      currentProject: {
        id: 'proj-1',
        title: 'Test',
        label_config: '<View/>',
        annotation_time_limit_enabled: false,
      },
      currentTask: {
        id: 'task-1',
        data: {},
        llm_responses: { 'gpt-4': 'LLM answer here' },
      },
      currentTaskPosition: 1,
      currentTaskTotal: 5,
    })

    render(<LabelingInterface projectId="proj-1" />)
    expect(screen.getByText('LLM Responses')).toBeInTheDocument()
    expect(screen.getByText('gpt-4')).toBeInTheDocument()
    expect(screen.getByText('LLM answer here')).toBeInTheDocument()
  })

  it('hides skip button when show_skip_button is false', () => {
    setupMocks({
      currentProject: {
        id: 'proj-1',
        title: 'Test',
        label_config: '<View/>',
        show_skip_button: false,
        annotation_time_limit_enabled: false,
      },
      currentTask: { id: 'task-1', data: {} },
      currentTaskPosition: 1,
      currentTaskTotal: 5,
    })

    render(<LabelingInterface projectId="proj-1" />)
    expect(screen.queryByTestId('mock-skip')).not.toBeInTheDocument()
  })

  it('shows skip button when show_skip_button is not false', () => {
    setupMocks({
      currentProject: {
        id: 'proj-1',
        title: 'Test',
        label_config: '<View/>',
        show_skip_button: true,
        annotation_time_limit_enabled: false,
      },
      currentTask: { id: 'task-1', data: {} },
      currentTaskPosition: 1,
      currentTaskTotal: 5,
    })

    render(<LabelingInterface projectId="proj-1" />)
    expect(screen.getByTestId('mock-skip')).toBeInTheDocument()
  })

  it('passes showSubmitButton=false when project disables it', () => {
    setupMocks({
      currentProject: {
        id: 'proj-1',
        title: 'Test',
        label_config: '<View/>',
        show_submit_button: false,
        annotation_time_limit_enabled: false,
      },
      currentTask: { id: 'task-1', data: {} },
      currentTaskPosition: 1,
      currentTaskTotal: 5,
    })

    render(<LabelingInterface projectId="proj-1" />)
    expect(screen.getByTestId('show-submit-prop')).toHaveTextContent('false')
  })

  it('passes requireConfirmBeforeSubmit=true', () => {
    setupMocks({
      currentProject: {
        id: 'proj-1',
        title: 'Test',
        label_config: '<View/>',
        require_confirm_before_submit: true,
        annotation_time_limit_enabled: false,
      },
      currentTask: { id: 'task-1', data: {} },
      currentTaskPosition: 1,
      currentTaskTotal: 5,
    })

    render(<LabelingInterface projectId="proj-1" />)
    expect(screen.getByTestId('require-confirm-prop')).toHaveTextContent('true')
  })

  it('renders AnnotationTimer when time limit enabled', () => {
    setupMocks({
      currentProject: {
        id: 'proj-1',
        title: 'Test',
        label_config: '<View/>',
        annotation_time_limit_enabled: true,
        annotation_time_limit_seconds: 300,
      },
      currentTask: { id: 'task-1', data: {} },
      currentTaskPosition: 1,
      currentTaskTotal: 5,
    })

    render(<LabelingInterface projectId="proj-1" />)
    expect(screen.getByTestId('mock-timer')).toBeInTheDocument()
  })

  it('renders elapsed time when no time limit', () => {
    setupMocks({
      currentProject: {
        id: 'proj-1',
        title: 'Test',
        label_config: '<View/>',
        annotation_time_limit_enabled: false,
      },
      currentTask: { id: 'task-1', data: {} },
      currentTaskPosition: 1,
      currentTaskTotal: 5,
    })

    render(<LabelingInterface projectId="proj-1" />)
    expect(screen.getByText('2 minutes')).toBeInTheDocument()
  })

  it('shows task position fallback with ? when null', () => {
    setupMocks({
      currentProject: {
        id: 'proj-1',
        title: 'Test Project',
        label_config: '<View/>',
        annotation_time_limit_enabled: false,
      },
      currentTask: { id: 'task-1', data: {} },
      currentTaskPosition: null,
      currentTaskTotal: null,
    })

    render(<LabelingInterface projectId="proj-1" />)
    expect(screen.getByText(/Task \? of/)).toBeInTheDocument()
  })

  it('shows instructions button when project has instructions', () => {
    setupMocks({
      currentProject: {
        id: 'proj-1',
        title: 'Test',
        label_config: '<View/>',
        instructions: 'Read these instructions',
        show_instruction: true,
        annotation_time_limit_enabled: false,
      },
      currentTask: { id: 'task-1', data: {} },
      currentTaskPosition: 1,
      currentTaskTotal: 5,
    })

    render(<LabelingInterface projectId="proj-1" />)
    expect(screen.getByText('Instructions')).toBeInTheDocument()
  })

  it('hides instructions button when no instructions', () => {
    setupMocks({
      currentProject: {
        id: 'proj-1',
        title: 'Test',
        label_config: '<View/>',
        instructions: null,
        conditional_instructions: null,
        annotation_time_limit_enabled: false,
      },
      currentTask: { id: 'task-1', data: {} },
      currentTaskPosition: 1,
      currentTaskTotal: 5,
    })

    render(<LabelingInterface projectId="proj-1" />)
    expect(screen.queryByText('Instructions')).not.toBeInTheDocument()
  })

  it('renders skip comment modal when require_comment_on_skip is true', async () => {
    const mockSkipTask = jest.fn().mockResolvedValue(undefined)
    setupMocks({
      currentProject: {
        id: 'proj-1',
        title: 'Test',
        label_config: '<View/>',
        require_comment_on_skip: true,
        annotation_time_limit_enabled: false,
      },
      currentTask: { id: 'task-1', data: {} },
      currentTaskPosition: 1,
      currentTaskTotal: 5,
      skipTask: mockSkipTask,
    })

    render(<LabelingInterface projectId="proj-1" />)

    // Click skip should show the comment modal
    fireEvent.click(screen.getByTestId('mock-skip'))

    await waitFor(() => {
      // Should show the skip comment dialog
      expect(screen.getByText('annotation.interface.skipCommentTitle')).toBeInTheDocument()
    })
  })
})

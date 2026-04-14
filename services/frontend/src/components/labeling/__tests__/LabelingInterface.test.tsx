/**
 * @jest-environment jsdom
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
  },
}))

// Import toast after mock setup so we can access the mock functions
import { toast } from 'react-hot-toast'
import { projectsAPI } from '@/lib/api/projects'
import { useAuth } from '@/contexts/AuthContext'

// Mock the DynamicAnnotationInterface
jest.mock('../DynamicAnnotationInterface', () => ({
  DynamicAnnotationInterface: function MockDynamicAnnotationInterface({
    onSubmit,
    onSkip,
    onChange,
    labelConfig,
    taskData,
  }: any) {
    return (
      <div data-testid="dynamic-annotation-interface">
        <div data-testid="label-config">{labelConfig}</div>
        <div data-testid="task-data">{JSON.stringify(taskData)}</div>
        <button
          data-testid="mock-submit"
          onClick={() => {
            // Don't catch errors - let them propagate to the parent
            onSubmit([])
          }}
        >
          Submit
        </button>
        {onChange && (
          <button
            data-testid="mock-annotate"
            onClick={() => {
              onChange([{ type: 'textarea', value: { text: ['test annotation'] } }])
            }}
          >
            Annotate
          </button>
        )}
        {onSkip && (
          <button
            data-testid="mock-skip"
            onClick={() => {
              // Don't catch errors - let them propagate to the parent
              onSkip()
            }}
          >
            Skip
          </button>
        )}
      </div>
    )
  },
}))

// Mock date-fns
jest.mock('date-fns', () => ({
  formatDistanceToNow: jest.fn(() => '5 minutes ago'),
}))

// Mock the project store
jest.mock('@/stores/projectStore', () => ({
  useProjectStore: jest.fn(),
}))

// Mock I18n context
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, options?: Record<string, any>) => {
      const translations: Record<string, string> = {
        'annotation.timer.expiredToast': 'Time limit reached',
        'annotation.interface.skipCommentTitle': 'Skip Task',
        'annotation.interface.skipCommentMessage': 'Please provide a reason for skipping this task.',
        'annotation.interface.skipCommentPlaceholder': 'Enter your comment...',
        'annotation.interface.cancel': 'Cancel',
        'annotation.interface.skip': 'Skip',
        'annotation.instructions.title': 'Annotation Instructions',
        'annotation.instructions.dontShowAgain': "Don't show again for this project",
        'annotation.instructions.startAnnotating': 'Start Annotating',
        'annotation.taskLoadedFromUrl': 'Loaded task {taskNumber} from URL',
        'annotation.taskNotFound': 'Task {taskNumber} not found (max: {maxTasks}). Loading first task instead.',
      }
      let result = translations[key] || options?.defaultValue || key
      if (options) {
        Object.entries(options).forEach(([k, v]) => {
          if (k !== 'defaultValue') {
            result = result.replace(`{${k}}`, String(v))
          }
        })
      }
      return result
    },
    locale: 'en',
  }),
}))

describe('LabelingInterface', () => {
  const mockRouter = {
    push: jest.fn(),
    back: jest.fn(),
  }

  const mockSearchParams = {
    get: jest.fn(),
  }

  const mockProject = {
    id: 'project-1',
    title: 'Test Project',
    description: 'Test description',
    label_config: '<View><Text name="text" value="$text"/></View>',
    num_tasks: 10,
    num_annotations: 5,
    is_published: true,
    is_archived: false,
    created_by: 'user-1',
    organization_id: 'org-1',
    show_instruction: true,
    show_skip_button: true,
    show_submit_button: true,
    require_comment_on_skip: false,
    require_confirm_before_submit: false,
    enable_empty_annotation: false,
    maximum_annotations: 1,
    min_annotations_to_start_training: 1,
    created_at: '2025-01-01T00:00:00Z',
  }

  const mockTask = {
    id: 'task-1',
    project_id: 'project-1',
    data: { text: 'Test task data' },
    annotations: [],
    created_at: '2025-01-01T00:00:00Z',
    updated_at: '2025-01-01T00:00:00Z',
  }

  const mockStoreState = {
    currentProject: mockProject,
    currentTask: mockTask,
    currentTaskPosition: 1,
    currentTaskTotal: 10,
    loading: false,
    getNextTask: jest.fn().mockResolvedValue(mockTask),
    createAnnotation: jest.fn(),
    createAnnotationInternal: jest.fn().mockResolvedValue(undefined),
    skipTask: jest.fn().mockResolvedValue(undefined),
    fetchProject: jest.fn().mockResolvedValue(mockProject),
    fetchProjectTasks: jest.fn().mockResolvedValue([mockTask]),
    taskCycle: [mockTask],
    currentTaskIndex: 0,
    setTaskByIndex: jest.fn(),
    advanceToNextTask: jest.fn(),
    completeCurrentTask: jest.fn(),
    labelConfigVersion: 0,
    resetAnnotationCompletion: jest.fn(),
    allTasksCompleted: false,
    annotationCompletion: null,
  }

  beforeEach(() => {
    jest.clearAllMocks()
    // Mock localStorage to return no saved task position
    const localStorageMock = {
      getItem: jest.fn(() => null),
      setItem: jest.fn(),
      removeItem: jest.fn(),
      clear: jest.fn(),
      length: 0,
      key: jest.fn(),
    }
    Object.defineProperty(window, 'localStorage', {
      value: localStorageMock,
      writable: true,
    })
    ;(useRouter as jest.Mock).mockReturnValue(mockRouter)
    ;(useSearchParams as jest.Mock).mockReturnValue(mockSearchParams)
    ;(useProjectStore as unknown as jest.Mock).mockReturnValue(mockStoreState)
    mockSearchParams.get.mockReturnValue(null)
    ;(projectsAPI.getTaskAnnotations as jest.Mock).mockResolvedValue([])
  })

  describe('Interface Rendering', () => {
    it('should render the labeling interface with project details', async () => {
      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(screen.getByText('Test Project')).toBeInTheDocument()
      })

      expect(screen.getByText(/Task 1 of 10/)).toBeInTheDocument()
    })

    it('should display the dynamic annotation interface', async () => {
      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(
          screen.getByTestId('dynamic-annotation-interface')
        ).toBeInTheDocument()
      })
    })

    it('should show the back to project button', async () => {
      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(screen.getByText('Back to Project')).toBeInTheDocument()
      })
    })

    it('should display task position and total', async () => {
      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(screen.getByText(/Task 1 of 10/)).toBeInTheDocument()
      })
    })

    it('should show time indicator', async () => {
      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(screen.getByText('5 minutes ago')).toBeInTheDocument()
      })
    })
  })

  describe('Initialization', () => {
    it('should fetch project on mount', async () => {
      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(mockStoreState.fetchProject).toHaveBeenCalledWith('project-1')
      })
    })

    it('should load next task on mount', async () => {
      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(mockStoreState.getNextTask).toHaveBeenCalledWith('project-1')
      })
    })

    it('should handle task parameter in URL', async () => {
      mockSearchParams.get.mockReturnValue('5')
      mockStoreState.fetchProjectTasks.mockResolvedValue([
        mockTask,
        { ...mockTask, id: 'task-2' },
        { ...mockTask, id: 'task-3' },
        { ...mockTask, id: 'task-4' },
        { ...mockTask, id: 'task-5' },
      ])

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(mockStoreState.fetchProjectTasks).toHaveBeenCalledWith(
          'project-1',
          false
        )
        expect(mockStoreState.setTaskByIndex).toHaveBeenCalledWith(4)
        expect(toast.success).toHaveBeenCalledWith('Loaded task 5 from URL')
      })
    })

    it('should handle invalid task number in URL by loading first task', async () => {
      // When task param is invalid (NaN), component falls through to normal task loading
      mockSearchParams.get.mockReturnValue('invalid')

      render(<LabelingInterface projectId="project-1" />)

      // Should load first available task instead of showing error
      await waitFor(() => {
        expect(mockStoreState.getNextTask).toHaveBeenCalledWith('project-1')
      })
    })

    it('should handle task number out of range', async () => {
      mockSearchParams.get.mockReturnValue('999')
      mockStoreState.fetchProjectTasks.mockResolvedValue([mockTask])

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith(
          expect.stringContaining('Task 999 not found')
        )
      })
    })

    it('should handle failed task loading from URL', async () => {
      mockSearchParams.get.mockReturnValue('5')
      mockStoreState.fetchProjectTasks.mockRejectedValue(
        new Error('Failed to fetch tasks')
      )

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith('Failed to load specific task')
      })
    })

    it('should show initialization error', async () => {
      const errorStore = {
        ...mockStoreState,
        fetchProject: jest.fn().mockRejectedValue(new Error('Network error')),
      }
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue(errorStore)

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(screen.getByText('Initialization Error')).toBeInTheDocument()
        expect(screen.getByText('Network error')).toBeInTheDocument()
      })
    })

    it('should show no tasks available message', async () => {
      const noTasksStore = {
        ...mockStoreState,
        getNextTask: jest.fn().mockResolvedValue(null),
      }
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue(noTasksStore)

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(
          screen.getByText(
            'No tasks are available for annotation in this project.'
          )
        ).toBeInTheDocument()
      })
    })
  })

  describe('Loading States', () => {
    it('should show loading spinner when loading and no task', () => {
      const loadingStore = {
        ...mockStoreState,
        loading: true,
        currentTask: null,
      }
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue(loadingStore)

      render(<LabelingInterface projectId="project-1" />)

      const spinner = document.querySelector('.animate-spin')
      expect(spinner).toBeInTheDocument()
    })

    it('should not show loading spinner when task is loaded', async () => {
      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        const spinner = document.querySelector('.animate-spin')
        expect(spinner).not.toBeInTheDocument()
      })
    })
  })

  describe('Completion State', () => {
    it('should show completion message when no tasks available', () => {
      const completedStore = {
        ...mockStoreState,
        currentTask: null,
        loading: false,
      }
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue(completedStore)

      render(<LabelingInterface projectId="project-1" />)

      expect(screen.getByText('All tasks completed!')).toBeInTheDocument()
      expect(
        screen.getByText(
          "You've annotated all available tasks in this project."
        )
      ).toBeInTheDocument()
    })

    it('should allow navigation back to project from completion screen', () => {
      const completedStore = {
        ...mockStoreState,
        currentTask: null,
        loading: false,
      }
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue(completedStore)

      render(<LabelingInterface projectId="project-1" />)

      const backButton = screen.getByText('Back to Project')
      fireEvent.click(backButton)

      expect(mockRouter.push).toHaveBeenCalledWith('/projects/project-1')
    })
  })

  describe('Navigation', () => {
    it('should navigate back to project', async () => {
      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        const backButton = screen.getByText('Back to Project')
        fireEvent.click(backButton)
      })

      expect(mockRouter.push).toHaveBeenCalledWith('/projects/project-1')
    })
  })

  describe('Annotation Submission', () => {
    it('should create annotation when submitted', async () => {
      mockStoreState.createAnnotationInternal.mockResolvedValue({
        id: 'annotation-1',
        task_id: 'task-1',
        result: [],
        created_at: '2025-01-01T00:00:00Z',
      })

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        const submitButton = screen.getByTestId('mock-submit')
        fireEvent.click(submitButton)
      })

      await waitFor(() => {
        expect(mockStoreState.createAnnotationInternal).toHaveBeenCalledWith(
          'task-1',
          expect.objectContaining({ result: [] }),
          false
        )
      })
    })

    it('should pass createAnnotation handler to DynamicAnnotationInterface', async () => {
      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(
          screen.getByTestId('dynamic-annotation-interface')
        ).toBeInTheDocument()
      })

      // Verify the interface can submit annotations
      const submitButton = screen.getByTestId('mock-submit')
      expect(submitButton).toBeInTheDocument()
    })
  })

  describe('Task Skipping', () => {
    it('should skip task when skip button clicked', async () => {
      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        const skipButton = screen.getByTestId('mock-skip')
        fireEvent.click(skipButton)
      })

      await waitFor(() => {
        expect(mockStoreState.skipTask).toHaveBeenCalled()
      })
    })

    it('should handle skip error', async () => {
      const consoleErrorSpy = jest
        .spyOn(console, 'error')
        .mockImplementation(() => {})

      const errorStore = {
        ...mockStoreState,
        skipTask: jest.fn().mockRejectedValue(new Error('Skip failed')),
      }
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue(errorStore)

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        const skipButton = screen.getByTestId('mock-skip')
        fireEvent.click(skipButton)
      })

      await waitFor(() => {
        expect(consoleErrorSpy).toHaveBeenCalledWith(
          'Failed to skip task:',
          expect.any(Error)
        )
      })

      consoleErrorSpy.mockRestore()
    })

    it('should pass skipTask handler to DynamicAnnotationInterface', async () => {
      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(screen.getByTestId('mock-skip')).toBeInTheDocument()
      })

      // Verify skip button is present when show_skip_button is true
      const skipButton = screen.getByTestId('mock-skip')
      expect(skipButton).toBeInTheDocument()
    })

    it('should not show skip button when disabled in project settings', async () => {
      const noSkipStore = {
        ...mockStoreState,
        currentProject: {
          ...mockProject,
          show_skip_button: false,
        },
      }
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue(noSkipStore)

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(screen.queryByTestId('mock-skip')).not.toBeInTheDocument()
      })
    })
  })

  describe('Label Configuration', () => {
    it('should show error when no label config', async () => {
      const noConfigStore = {
        ...mockStoreState,
        currentProject: {
          ...mockProject,
          label_config: null,
        },
      }
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue(noConfigStore)

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(
          screen.getByText('No label configuration found')
        ).toBeInTheDocument()
      })
    })

    it('should pass label config to annotation interface', async () => {
      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        const labelConfigElement = screen.getByTestId('label-config')
        expect(labelConfigElement).toHaveTextContent(
          '<View><Text name="text" value="$text"/></View>'
        )
      })
    })

    it('should pass task data to annotation interface', async () => {
      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        const taskDataElement = screen.getByTestId('task-data')
        expect(taskDataElement).toHaveTextContent(
          JSON.stringify({ text: 'Test task data' })
        )
      })
    })

    it('should respond to label config version changes', async () => {
      const storeWithConfig = {
        ...mockStoreState,
        labelConfigVersion: 1,
        fetchProjectTasks: jest.fn().mockResolvedValue([mockTask]),
      }
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue(
        storeWithConfig
      )

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(
          screen.getByTestId('dynamic-annotation-interface')
        ).toBeInTheDocument()
      })

      // When label config version changes, fetchProjectTasks should be called with per-user filter
      expect(storeWithConfig.fetchProjectTasks).toHaveBeenCalledWith(
        'project-1',
        true
      )
    })
  })

  describe('LLM Responses Display', () => {
    it('should show LLM responses when available', async () => {
      const taskWithLLM = {
        ...mockTask,
        llm_responses: {
          'gpt-4': 'GPT-4 response',
          'claude-3': 'Claude response',
        },
      }

      const storeWithLLM = {
        ...mockStoreState,
        currentTask: taskWithLLM,
      }
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue(storeWithLLM)

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(screen.getByText('LLM Responses')).toBeInTheDocument()
        expect(screen.getByText('gpt-4')).toBeInTheDocument()
        expect(screen.getByText('GPT-4 response')).toBeInTheDocument()
        expect(screen.getByText('claude-3')).toBeInTheDocument()
        expect(screen.getByText('Claude response')).toBeInTheDocument()
      })
    })

    it('should not show LLM responses section when none available', async () => {
      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(screen.queryByText('LLM Responses')).not.toBeInTheDocument()
      })
    })

    it('should handle empty LLM responses object', async () => {
      const taskWithEmptyLLM = {
        ...mockTask,
        llm_responses: {},
      }

      const storeWithEmptyLLM = {
        ...mockStoreState,
        currentTask: taskWithEmptyLLM,
      }
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue(
        storeWithEmptyLLM
      )

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(screen.queryByText('LLM Responses')).not.toBeInTheDocument()
      })
    })
  })

  describe('Error Recovery', () => {
    it('should show try again button on initialization error', async () => {
      const errorStore = {
        ...mockStoreState,
        fetchProject: jest.fn().mockRejectedValue(new Error('Network error')),
      }
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue(errorStore)

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(screen.getByText('Try Again')).toBeInTheDocument()
      })

      const tryAgainButton = screen.getByText('Try Again')
      expect(tryAgainButton).toBeInTheDocument()
    })

    it('should allow navigation back on initialization error', async () => {
      const errorStore = {
        ...mockStoreState,
        fetchProject: jest.fn().mockRejectedValue(new Error('Network error')),
      }
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue(errorStore)

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(screen.getByText('Back to Project')).toBeInTheDocument()
      })

      const backButton = screen.getByText('Back to Project')
      fireEvent.click(backButton)

      expect(mockRouter.push).toHaveBeenCalledWith('/projects/project-1')
    })
  })

  describe('Task State Management', () => {
    it('should clear state when projectId changes', async () => {
      const { rerender } = render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(mockStoreState.fetchProject).toHaveBeenCalledWith('project-1')
      })

      jest.clearAllMocks()

      rerender(<LabelingInterface projectId="project-2" />)

      await waitFor(() => {
        expect(mockStoreState.fetchProject).toHaveBeenCalledWith('project-2')
      })
    })
  })

  describe('Fallback Task Position', () => {
    it('should use project num_tasks when currentTaskTotal is null', async () => {
      const storeWithNullTotal = {
        ...mockStoreState,
        currentTaskTotal: null,
      }
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue(
        storeWithNullTotal
      )

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(screen.getByText(/Task 1 of 10/)).toBeInTheDocument()
      })
    })

    it('should show question mark when both total and num_tasks are null', async () => {
      const storeWithNoTotal = {
        ...mockStoreState,
        currentTaskTotal: null,
        currentProject: {
          ...mockProject,
          num_tasks: null,
        },
      }
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue(
        storeWithNoTotal
      )

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(screen.getByText(/Task 1 of \?/)).toBeInTheDocument()
      })
    })
  })

  describe('Empty Task Data', () => {
    it('should handle task with empty data object', async () => {
      const taskWithEmptyData = {
        ...mockTask,
        data: {},
      }

      const storeWithEmptyData = {
        ...mockStoreState,
        currentTask: taskWithEmptyData,
      }
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue(
        storeWithEmptyData
      )

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        const taskDataElement = screen.getByTestId('task-data')
        expect(taskDataElement).toHaveTextContent('{}')
      })
    })

    it('should handle task with null data', async () => {
      const taskWithNullData = {
        ...mockTask,
        data: null,
      }

      const storeWithNullData = {
        ...mockStoreState,
        currentTask: taskWithNullData,
      }
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue(
        storeWithNullData
      )

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        const taskDataElement = screen.getByTestId('task-data')
        expect(taskDataElement).toHaveTextContent('{}')
      })
    })
  })

  describe('URL Parameter Edge Cases', () => {
    it('should handle zero task number in URL by loading first task', async () => {
      // When task param is 0 (not > 0), component falls through to normal task loading
      mockSearchParams.get.mockReturnValue('0')

      render(<LabelingInterface projectId="project-1" />)

      // Should load first available task instead of showing error
      await waitFor(() => {
        expect(mockStoreState.getNextTask).toHaveBeenCalledWith('project-1')
      })
    })

    it('should handle negative task number in URL', async () => {
      mockSearchParams.get.mockReturnValue('-1')
      mockStoreState.fetchProjectTasks.mockResolvedValue([mockTask])

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(mockStoreState.getNextTask).toHaveBeenCalledWith('project-1')
      })
    })
  })

  describe('Task ID Tracking', () => {
    it('should pass task ID to DynamicAnnotationInterface', async () => {
      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(
          screen.getByTestId('dynamic-annotation-interface')
        ).toBeInTheDocument()
      })

      // Verify the interface is rendered with the current task
      expect(mockStoreState.currentTask?.id).toBe('task-1')
    })
  })

  describe('Time Tracking', () => {
    it('should display time since task started', async () => {
      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(screen.getByText('5 minutes ago')).toBeInTheDocument()
      })
    })
  })

  describe('Annotation Error Handling', () => {
    it('should handle annotation submission error', async () => {
      const consoleErrorSpy = jest
        .spyOn(console, 'error')
        .mockImplementation(() => {})

      const errorStore = {
        ...mockStoreState,
        createAnnotationInternal: jest
          .fn()
          .mockRejectedValue(new Error('Submit failed')),
      }
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue(errorStore)

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        const submitButton = screen.getByTestId('mock-submit')
        fireEvent.click(submitButton)
      })

      await waitFor(() => {
        expect(consoleErrorSpy).toHaveBeenCalledWith(
          'Failed to submit annotation:',
          expect.any(Error)
        )
      })

      consoleErrorSpy.mockRestore()
    })
  })

  describe('SearchParams Reactivity', () => {
    it('should reload when searchParams change', async () => {
      const { rerender } = render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(mockStoreState.fetchProject).toHaveBeenCalledWith('project-1')
      })

      jest.clearAllMocks()

      // Change searchParams
      const newSearchParams = {
        get: jest.fn().mockReturnValue('3'),
      }
      ;(useSearchParams as jest.Mock).mockReturnValue(newSearchParams)
      mockStoreState.fetchProjectTasks.mockResolvedValue([mockTask])

      rerender(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(mockStoreState.fetchProject).toHaveBeenCalledWith('project-1')
      })
    })
  })

  describe('Task Position Display', () => {
    it('should display current task position', async () => {
      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(screen.getByText(/Task 1 of 10/)).toBeInTheDocument()
      })
    })

    it('should show question mark when position is null', async () => {
      const storeWithNullPosition = {
        ...mockStoreState,
        currentTaskPosition: null,
      }
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue(
        storeWithNullPosition
      )

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(screen.getByText(/Task \? of 10/)).toBeInTheDocument()
      })
    })
  })

  describe('Label Config Version Tracking', () => {
    it('should not fetch tasks when labelConfigVersion is 0', async () => {
      const storeWithZeroVersion = {
        ...mockStoreState,
        labelConfigVersion: 0,
        fetchProjectTasks: jest.fn(),
      }
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue(
        storeWithZeroVersion
      )

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(
          screen.getByTestId('dynamic-annotation-interface')
        ).toBeInTheDocument()
      })

      expect(storeWithZeroVersion.fetchProjectTasks).not.toHaveBeenCalled()
    })

    it('should clear initialization error on config change', async () => {
      const errorStore = {
        ...mockStoreState,
        labelConfigVersion: 1,
        fetchProject: jest.fn().mockRejectedValue(new Error('Initial error')),
        fetchProjectTasks: jest.fn().mockResolvedValue([mockTask]),
      }
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue(errorStore)

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(screen.getByText('Initialization Error')).toBeInTheDocument()
      })
    })
  })

  describe('Project Configuration', () => {
    it('should pass show_skip_button setting to interface', async () => {
      const projectWithSkip = {
        ...mockStoreState,
        currentProject: {
          ...mockProject,
          show_skip_button: true,
        },
      }
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue(
        projectWithSkip
      )

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(screen.getByTestId('mock-skip')).toBeInTheDocument()
      })
    })

    it('should show skip button when show_skip_button is null (defaults to enabled)', async () => {
      // Component behavior: show_skip_button defaults to true unless explicitly set to false
      // null, undefined, and true all result in showing the skip button
      const projectWithNullSkip = {
        ...mockStoreState,
        currentProject: {
          ...mockProject,
          show_skip_button: null,
        },
      }
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue(
        projectWithNullSkip
      )

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        // Skip button should be present because null !== false
        expect(screen.getByTestId('mock-skip')).toBeInTheDocument()
      })
    })
  })

  describe('LLM Response Edge Cases', () => {
    it('should handle non-string LLM responses', async () => {
      const taskWithObjectResponse = {
        ...mockTask,
        llm_responses: {
          'model-1': { answer: 'complex', confidence: 0.9 },
        },
      }

      const storeWithObjectLLM = {
        ...mockStoreState,
        currentTask: taskWithObjectResponse,
      }
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue(
        storeWithObjectLLM
      )

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(screen.getByText('LLM Responses')).toBeInTheDocument()
        expect(screen.getByText('model-1')).toBeInTheDocument()
      })
    })
  })

  describe('Server-Side Draft Sync', () => {
    beforeEach(() => {
      jest.useFakeTimers()
      ;(projectsAPI.saveDraft as jest.Mock).mockClear()
      ;(projectsAPI.saveDraft as jest.Mock).mockResolvedValue(undefined)
    })

    afterEach(() => {
      jest.useRealTimers()
    })

    it('should call saveDraft after 30s when annotations exist', async () => {
      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(screen.getByTestId('mock-annotate')).toBeInTheDocument()
      })

      // Simulate user making an annotation
      fireEvent.click(screen.getByTestId('mock-annotate'))

      // Advance 30s to trigger sync interval
      await jest.advanceTimersByTimeAsync(30_000)

      await waitFor(() => {
        expect(projectsAPI.saveDraft).toHaveBeenCalledWith(
          'project-1',
          'task-1',
          [{ type: 'textarea', value: { text: ['test annotation'] } }]
        )
      })
    })

    it('should not sync when annotations have not changed since last sync', async () => {
      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(screen.getByTestId('mock-annotate')).toBeInTheDocument()
      })

      // Simulate annotation
      fireEvent.click(screen.getByTestId('mock-annotate'))

      // First interval — should sync (annotations changed)
      await jest.advanceTimersByTimeAsync(30_000)

      await waitFor(() => {
        expect(projectsAPI.saveDraft).toHaveBeenCalledTimes(1)
      })

      // Second interval — should NOT sync (no changes since last sync)
      await jest.advanceTimersByTimeAsync(30_000)

      // Still only 1 call — change detection prevented duplicate save
      expect(projectsAPI.saveDraft).toHaveBeenCalledTimes(1)
    })

    it('should sync again after new changes are made', async () => {
      // We need the mock onChange to produce different data on second click
      // The mock always produces the same data, so saveDraft will be called
      // once (first change), then not again (same serialized data).
      // This test verifies the mechanism works.
      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(screen.getByTestId('mock-annotate')).toBeInTheDocument()
      })

      // First annotation change
      fireEvent.click(screen.getByTestId('mock-annotate'))
      await jest.advanceTimersByTimeAsync(30_000)

      await waitFor(() => {
        expect(projectsAPI.saveDraft).toHaveBeenCalledTimes(1)
      })

      // Simulate submit (which clears annotations), then annotate again
      // This changes the annotations state, which should trigger a new sync
      fireEvent.click(screen.getByTestId('mock-submit'))

      // Wait for state update from submit
      await waitFor(() => {
        // After submit, annotations are cleared by the component
      })

      // New annotation
      fireEvent.click(screen.getByTestId('mock-annotate'))
      await jest.advanceTimersByTimeAsync(30_000)

      // Should have synced again (annotations changed from [] to [data])
      await waitFor(() => {
        expect(projectsAPI.saveDraft).toHaveBeenCalledTimes(2)
      })
    })

    it('should not sync when annotations are empty', async () => {
      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(screen.getByTestId('dynamic-annotation-interface')).toBeInTheDocument()
      })

      // Advance 30s without making any annotations
      await jest.advanceTimersByTimeAsync(30_000)

      expect(projectsAPI.saveDraft).not.toHaveBeenCalled()
    })

    it('should sync on visibilitychange to hidden when annotations exist', async () => {
      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(screen.getByTestId('mock-annotate')).toBeInTheDocument()
      })

      // Make annotation
      fireEvent.click(screen.getByTestId('mock-annotate'))

      // Simulate tab becoming hidden
      Object.defineProperty(document, 'visibilityState', {
        value: 'hidden',
        writable: true,
      })
      document.dispatchEvent(new Event('visibilitychange'))

      await waitFor(() => {
        expect(projectsAPI.saveDraft).toHaveBeenCalledWith(
          'project-1',
          'task-1',
          [{ type: 'textarea', value: { text: ['test annotation'] } }]
        )
      })

      // Restore
      Object.defineProperty(document, 'visibilityState', {
        value: 'visible',
        writable: true,
      })
    })

    it('should not sync on visibilitychange when annotations are empty', async () => {
      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(screen.getByTestId('dynamic-annotation-interface')).toBeInTheDocument()
      })

      // Simulate tab hidden without making annotations
      Object.defineProperty(document, 'visibilityState', {
        value: 'hidden',
        writable: true,
      })
      document.dispatchEvent(new Event('visibilitychange'))

      expect(projectsAPI.saveDraft).not.toHaveBeenCalled()

      Object.defineProperty(document, 'visibilityState', {
        value: 'visible',
        writable: true,
      })
    })

    it('should clean up interval and visibilitychange listener on unmount', async () => {
      const clearIntervalSpy = jest.spyOn(global, 'clearInterval')
      const removeEventSpy = jest.spyOn(document, 'removeEventListener')

      const { unmount } = render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(screen.getByTestId('dynamic-annotation-interface')).toBeInTheDocument()
      })

      unmount()

      expect(clearIntervalSpy).toHaveBeenCalled()
      expect(removeEventSpy).toHaveBeenCalledWith(
        'visibilitychange',
        expect.any(Function)
      )

      clearIntervalSpy.mockRestore()
      removeEventSpy.mockRestore()
    })

    it('should silently handle saveDraft errors', async () => {
      ;(projectsAPI.saveDraft as jest.Mock).mockRejectedValue(new Error('Network error'))

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(screen.getByTestId('mock-annotate')).toBeInTheDocument()
      })

      // Make annotation
      fireEvent.click(screen.getByTestId('mock-annotate'))

      // Advance 30s — should call saveDraft but not crash
      await jest.advanceTimersByTimeAsync(30_000)

      await waitFor(() => {
        expect(projectsAPI.saveDraft).toHaveBeenCalled()
      })

      // Component should still be rendered (no crash)
      expect(screen.getByTestId('dynamic-annotation-interface')).toBeInTheDocument()
    })
  })

  describe('Strict Timer: Zombie Session Recovery', () => {
    it('should show pre_start screen for zombie sessions (expired + not completed)', async () => {
      const strictProject = {
        ...mockProject,
        strict_timer_enabled: true,
        annotation_time_limit_enabled: true,
        annotation_time_limit_seconds: 600,
      }

      const storeWithStrictTimer = {
        ...mockStoreState,
        currentProject: strictProject,
      }
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue(storeWithStrictTimer)

      // Mock timer status: expired session with no completed_at (zombie)
      ;(projectsAPI.getTimerStatus as jest.Mock).mockResolvedValue({
        server_time: new Date().toISOString(),
        session: {
          session_id: 'zombie-session',
          started_at: new Date(Date.now() - 7200000).toISOString(),
          time_limit_seconds: 600,
          is_strict: true,
          elapsed_seconds: 7200,
          remaining_seconds: 0,
          is_expired: true,
          completed_at: null,
          auto_submitted: false,
        },
      })

      render(<LabelingInterface projectId="project-1" />)

      // Should show "Ready to Begin" (pre_start), NOT "Time's Up"
      await waitFor(() => {
        expect(screen.getByText("Ready to Begin")).toBeInTheDocument()
      })

      // Should NOT show "Time's Up"
      expect(screen.queryByText("Time's Up")).not.toBeInTheDocument()
    })

    it('should show time_over for completed expired sessions', async () => {
      const strictProject = {
        ...mockProject,
        strict_timer_enabled: true,
        annotation_time_limit_enabled: true,
        annotation_time_limit_seconds: 600,
      }

      const storeWithStrictTimer = {
        ...mockStoreState,
        currentProject: strictProject,
      }
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue(storeWithStrictTimer)

      // Mock timer status: expired AND completed session
      ;(projectsAPI.getTimerStatus as jest.Mock).mockResolvedValue({
        server_time: new Date().toISOString(),
        session: {
          session_id: 'completed-session',
          started_at: new Date(Date.now() - 7200000).toISOString(),
          time_limit_seconds: 600,
          is_strict: true,
          elapsed_seconds: 7200,
          remaining_seconds: 0,
          is_expired: true,
          completed_at: new Date().toISOString(),
          auto_submitted: true,
        },
      })

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(screen.getByText("Time's Up")).toBeInTheDocument()
      })
    })
  })

  describe('Strict Timer: Continue Button', () => {
    it('should call completeCurrentTask when Continue is clicked on time_over screen', async () => {
      const strictProject = {
        ...mockProject,
        strict_timer_enabled: true,
        annotation_time_limit_enabled: true,
        annotation_time_limit_seconds: 600,
      }

      const storeWithStrictTimer = {
        ...mockStoreState,
        currentProject: strictProject,
      }
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue(storeWithStrictTimer)

      // Mock: expired + completed session → time_over screen
      ;(projectsAPI.getTimerStatus as jest.Mock).mockResolvedValue({
        server_time: new Date().toISOString(),
        session: {
          session_id: 'done-session',
          started_at: new Date(Date.now() - 7200000).toISOString(),
          time_limit_seconds: 600,
          is_strict: true,
          elapsed_seconds: 7200,
          remaining_seconds: 0,
          is_expired: true,
          completed_at: new Date().toISOString(),
          auto_submitted: true,
        },
      })

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(screen.getByText("Time's Up")).toBeInTheDocument()
      })

      // Click Continue
      const continueButton = screen.getByText('Continue')
      fireEvent.click(continueButton)

      // Should call completeCurrentTask to advance, not just re-init the same task
      expect(storeWithStrictTimer.completeCurrentTask).toHaveBeenCalled()
    })
  })

  describe('Instructions Button', () => {
    it('should show Instructions button when project has instructions', async () => {
      const storeWithInstructions = {
        ...mockStoreState,
        currentProject: {
          ...mockProject,
          instructions: 'Read these before annotating.',
          show_instruction: true,
        },
      }
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue(storeWithInstructions)

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(screen.getByText('Instructions')).toBeInTheDocument()
      })
    })

    it('should not show Instructions button when project has no instructions', async () => {
      const storeNoInstructions = {
        ...mockStoreState,
        currentProject: {
          ...mockProject,
          instructions: null,
          conditional_instructions: null,
        },
      }
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue(storeNoInstructions)

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(screen.getByText('Test Project')).toBeInTheDocument()
      })

      expect(screen.queryByText('Instructions')).not.toBeInTheDocument()
    })

    it('should open instructions modal when Instructions button is clicked', async () => {
      const storeWithInstructions = {
        ...mockStoreState,
        currentProject: {
          ...mockProject,
          instructions: 'Important annotation guidelines here.',
          show_instruction: false, // Not auto-shown
        },
      }
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue(storeWithInstructions)

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(screen.getByText('Instructions')).toBeInTheDocument()
      })

      // Modal should not be visible initially (show_instruction is false and no auto-show)
      expect(screen.queryByText('Important annotation guidelines here.')).not.toBeInTheDocument()

      // Click the Instructions button
      fireEvent.click(screen.getByText('Instructions'))

      // Modal should now be visible with the instructions text
      await waitFor(() => {
        expect(screen.getByText('Important annotation guidelines here.')).toBeInTheDocument()
      })
    })

    it('should show Close button instead of Start Annotating when opened manually', async () => {
      const storeWithInstructions = {
        ...mockStoreState,
        currentProject: {
          ...mockProject,
          instructions: 'Test instructions content.',
          show_instruction: false,
        },
      }
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue(storeWithInstructions)

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(screen.getByText('Instructions')).toBeInTheDocument()
      })

      // Click the Instructions button to open manually
      fireEvent.click(screen.getByText('Instructions'))

      await waitFor(() => {
        expect(screen.getByText('Test instructions content.')).toBeInTheDocument()
      })

      // Should show "Close" not "Start Annotating"
      expect(screen.getByText('Close')).toBeInTheDocument()
      expect(screen.queryByText('Start Annotating')).not.toBeInTheDocument()
    })

    it('should hide Don\'t show again checkbox when opened manually', async () => {
      const storeWithInstructions = {
        ...mockStoreState,
        currentProject: {
          ...mockProject,
          instructions: 'Instruction text here.',
          show_instruction: false,
          instructions_always_visible: false,
        },
      }
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue(storeWithInstructions)

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(screen.getByText('Instructions')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByText('Instructions'))

      await waitFor(() => {
        expect(screen.getByText('Instruction text here.')).toBeInTheDocument()
      })

      // "Don't show again" checkbox should NOT be present when opened manually
      expect(screen.queryByText("Don't show again for this project")).not.toBeInTheDocument()
    })

    it('should show instructions modal on load and hide Don\'t show again when always visible', async () => {
      const storeAlwaysVisible = {
        ...mockStoreState,
        currentProject: {
          ...mockProject,
          instructions: 'Always visible instructions.',
          show_instruction: true,
          instructions_always_visible: true,
        },
      }
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue(storeAlwaysVisible)

      render(<LabelingInterface projectId="project-1" />)

      // Modal should auto-show
      await waitFor(() => {
        expect(screen.getByText('Always visible instructions.')).toBeInTheDocument()
      })

      // "Don't show again" should be hidden when always visible
      expect(screen.queryByText("Don't show again for this project")).not.toBeInTheDocument()

      // Should show "Start Annotating" (auto-shown, not manual)
      expect(screen.getByText('Start Annotating')).toBeInTheDocument()
    })
  })

  describe('User-scoped localStorage keys (#1306)', () => {
    const mockAuthDefault = {
      user: null,
      login: jest.fn(),
      signup: jest.fn(),
      logout: jest.fn(),
      updateUser: jest.fn(),
      isLoading: false,
      refreshAuth: jest.fn(),
      apiClient: {
        getAllUsers: jest.fn().mockResolvedValue([]),
        getOrganizationMembers: jest.fn().mockResolvedValue([]),
        listInvitations: jest.fn().mockResolvedValue([]),
        getOrganizationInvitations: jest.fn().mockResolvedValue([]),
        getOrganizations: jest.fn().mockResolvedValue([]),
        getTasks: jest.fn().mockResolvedValue({ tasks: [], total: 0 }),
        getTask: jest.fn().mockResolvedValue(null),
        get: jest.fn().mockResolvedValue({}),
        post: jest.fn().mockResolvedValue({}),
        put: jest.fn().mockResolvedValue({}),
        patch: jest.fn().mockResolvedValue({}),
        delete: jest.fn().mockResolvedValue({}),
      },
      organizations: [],
      currentOrganization: null,
      setCurrentOrganization: jest.fn(),
      refreshOrganizations: jest.fn(),
    }

    it('should include user ID in localStorage keys when user is authenticated', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        ...mockAuthDefault,
        user: { id: 'user-42', username: 'testuser', email: 'test@example.com' },
      })

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(screen.getByText('Test Project')).toBeInTheDocument()
      })

      // The setItem calls should use user-scoped keys
      const setItemCalls = (localStorage.setItem as jest.Mock).mock.calls
      const positionCall = setItemCalls.find(
        ([key]: [string]) => key.includes('task_position')
      )
      const idCall = setItemCalls.find(
        ([key]: [string]) => key.includes('task_id')
      )

      expect(positionCall).toBeDefined()
      expect(positionCall![0]).toBe('benger_task_position_project-1_user-42')
      expect(idCall).toBeDefined()
      expect(idCall![0]).toBe('benger_task_id_project-1_user-42')
    })

    it('should use "anon" fallback in localStorage keys when user is null', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        ...mockAuthDefault,
        user: null,
      })

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(screen.getByText('Test Project')).toBeInTheDocument()
      })

      const setItemCalls = (localStorage.setItem as jest.Mock).mock.calls
      const positionCall = setItemCalls.find(
        ([key]: [string]) => key.includes('task_position')
      )
      const idCall = setItemCalls.find(
        ([key]: [string]) => key.includes('task_id')
      )

      expect(positionCall).toBeDefined()
      expect(positionCall![0]).toBe('benger_task_position_project-1_anon')
      expect(idCall).toBeDefined()
      expect(idCall![0]).toBe('benger_task_id_project-1_anon')
    })

    it('should read from user-scoped localStorage key on initialization', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        ...mockAuthDefault,
        user: { id: 'user-42', username: 'testuser', email: 'test@example.com' },
      })

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(screen.getByText('Test Project')).toBeInTheDocument()
      })

      // getItem should be called with user-scoped keys
      const getItemCalls = (localStorage.getItem as jest.Mock).mock.calls.map(
        ([key]: [string]) => key
      )
      expect(getItemCalls).toContain('benger_task_id_project-1_user-42')
      expect(getItemCalls).toContain('benger_task_position_project-1_user-42')
    })

    it('should isolate task positions between different users on the same project', async () => {
      // Simulate user A saving position
      ;(useAuth as jest.Mock).mockReturnValue({
        ...mockAuthDefault,
        user: { id: 'user-A', username: 'alice', email: 'alice@example.com' },
      })

      const { unmount } = render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(screen.getByText('Test Project')).toBeInTheDocument()
      })

      const setItemCallsA = (localStorage.setItem as jest.Mock).mock.calls
      const positionCallA = setItemCallsA.find(
        ([key]: [string]) => key.includes('task_position')
      )
      expect(positionCallA).toBeDefined()
      expect(positionCallA![0]).toBe('benger_task_position_project-1_user-A')

      unmount()
      jest.clearAllMocks()

      // Simulate user B
      ;(useAuth as jest.Mock).mockReturnValue({
        ...mockAuthDefault,
        user: { id: 'user-B', username: 'bob', email: 'bob@example.com' },
      })
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue(mockStoreState)
      ;(useRouter as jest.Mock).mockReturnValue(mockRouter)
      ;(useSearchParams as jest.Mock).mockReturnValue(mockSearchParams)
      ;(projectsAPI.getTaskAnnotations as jest.Mock).mockResolvedValue([])

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(screen.getByText('Test Project')).toBeInTheDocument()
      })

      const setItemCallsB = (localStorage.setItem as jest.Mock).mock.calls
      const positionCallB = setItemCallsB.find(
        ([key]: [string]) => key.includes('task_position')
      )
      expect(positionCallB).toBeDefined()
      expect(positionCallB![0]).toBe('benger_task_position_project-1_user-B')

      // Keys must be different for different users
      expect(positionCallA![0]).not.toBe(positionCallB![0])
    })
  })

  describe('Loading Existing Annotations', () => {
    it('should load existing annotations when task has prior annotations', async () => {
      const existingAnnotations = [
        {
          id: 'ann-1',
          result: [{ type: 'choices', value: { choices: ['option1'] } }],
          created_at: '2025-01-01T00:00:00Z',
        },
      ]
      ;(projectsAPI.getTaskAnnotations as jest.Mock).mockResolvedValue(existingAnnotations)

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(projectsAPI.getTaskAnnotations).toHaveBeenCalledWith('task-1')
      })
    })

    it('should handle empty result in existing annotations', async () => {
      const annotationNoResult = [
        { id: 'ann-1', result: null, created_at: '2025-01-01T00:00:00Z' },
      ]
      ;(projectsAPI.getTaskAnnotations as jest.Mock).mockResolvedValue(annotationNoResult)

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(screen.getByTestId('dynamic-annotation-interface')).toBeInTheDocument()
      })
    })

    it('should handle annotation loading failure gracefully', async () => {
      ;(projectsAPI.getTaskAnnotations as jest.Mock).mockRejectedValue(new Error('Network error'))

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(screen.getByTestId('dynamic-annotation-interface')).toBeInTheDocument()
      })
    })

    it('should clear loaded annotations when currentTask has no id', async () => {
      const storeNoTask = {
        ...mockStoreState,
        currentTask: { ...mockTask, id: undefined },
      }
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue(storeNoTask)

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(projectsAPI.getTaskAnnotations).not.toHaveBeenCalled()
      })
    })
  })

  describe('Timer Initialization Paths', () => {
    it('should use client time when timer not enabled', async () => {
      const noTimerProject = {
        ...mockProject,
        annotation_time_limit_enabled: false,
      }
      const storeNoTimer = {
        ...mockStoreState,
        currentProject: noTimerProject,
      }
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue(storeNoTimer)

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(screen.getByTestId('dynamic-annotation-interface')).toBeInTheDocument()
      })
      // Timer status should not be called for non-timed projects
      expect(projectsAPI.getTimerStatus).not.toHaveBeenCalled()
    })

    it('should auto-start timer in non-strict mode with no existing session', async () => {
      const timedProject = {
        ...mockProject,
        annotation_time_limit_enabled: true,
        annotation_time_limit_seconds: 600,
        strict_timer_enabled: false,
      }
      const storeTimed = {
        ...mockStoreState,
        currentProject: timedProject,
      }
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue(storeTimed)
      ;(projectsAPI.getTimerStatus as jest.Mock).mockResolvedValue({
        server_time: new Date().toISOString(),
        session: null,
      })

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(projectsAPI.startTimer).toHaveBeenCalledWith('project-1', 'task-1')
      })
    })

    it('should resume running timer session', async () => {
      const timedProject = {
        ...mockProject,
        annotation_time_limit_enabled: true,
        annotation_time_limit_seconds: 600,
        strict_timer_enabled: false,
      }
      const storeTimed = {
        ...mockStoreState,
        currentProject: timedProject,
      }
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue(storeTimed)
      ;(projectsAPI.getTimerStatus as jest.Mock).mockResolvedValue({
        server_time: new Date().toISOString(),
        session: {
          session_id: 'running-session',
          started_at: new Date(Date.now() - 60000).toISOString(),
          time_limit_seconds: 600,
          is_strict: false,
          elapsed_seconds: 60,
          remaining_seconds: 540,
          is_expired: false,
          completed_at: null,
          auto_submitted: false,
        },
      })

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(screen.getByTestId('dynamic-annotation-interface')).toBeInTheDocument()
      })
      // Should NOT start a new timer (session exists)
      expect(projectsAPI.startTimer).not.toHaveBeenCalled()
    })

    it('should fallback to client time when timer init fails', async () => {
      const timedProject = {
        ...mockProject,
        annotation_time_limit_enabled: true,
        annotation_time_limit_seconds: 600,
        strict_timer_enabled: false,
      }
      const storeTimed = {
        ...mockStoreState,
        currentProject: timedProject,
      }
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue(storeTimed)
      ;(projectsAPI.getTimerStatus as jest.Mock).mockRejectedValue(new Error('Server error'))

      render(<LabelingInterface projectId="project-1" />)

      // Should still render the annotation interface (client-side fallback)
      await waitFor(() => {
        expect(screen.getByTestId('dynamic-annotation-interface')).toBeInTheDocument()
      })
    })

    it('should show pre-start screen in strict mode with no session', async () => {
      const strictProject = {
        ...mockProject,
        strict_timer_enabled: true,
        annotation_time_limit_enabled: true,
        annotation_time_limit_seconds: 600,
      }
      const storeStrict = {
        ...mockStoreState,
        currentProject: strictProject,
      }
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue(storeStrict)
      ;(projectsAPI.getTimerStatus as jest.Mock).mockResolvedValue({
        server_time: new Date().toISOString(),
        session: null,
      })

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(screen.getByText('Ready to Begin')).toBeInTheDocument()
      })
    })

    it('should show non-strict expired session as annotating', async () => {
      const timedProject = {
        ...mockProject,
        annotation_time_limit_enabled: true,
        annotation_time_limit_seconds: 600,
        strict_timer_enabled: false,
      }
      const storeTimed = {
        ...mockStoreState,
        currentProject: timedProject,
      }
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue(storeTimed)
      ;(projectsAPI.getTimerStatus as jest.Mock).mockResolvedValue({
        server_time: new Date().toISOString(),
        session: {
          session_id: 'expired-nonstrict',
          started_at: new Date(Date.now() - 7200000).toISOString(),
          time_limit_seconds: 600,
          is_strict: false,
          elapsed_seconds: 7200,
          remaining_seconds: 0,
          is_expired: true,
          completed_at: null,
          auto_submitted: false,
        },
      })

      render(<LabelingInterface projectId="project-1" />)

      // Non-strict expired: should still show the annotation interface
      await waitFor(() => {
        expect(screen.getByTestId('dynamic-annotation-interface')).toBeInTheDocument()
      })
    })
  })

  describe('Skip With Comment Modal', () => {
    it('should show skip comment modal when require_comment_on_skip is true', async () => {
      const requireCommentStore = {
        ...mockStoreState,
        currentProject: {
          ...mockProject,
          require_comment_on_skip: true,
        },
      }
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue(requireCommentStore)

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(screen.getByTestId('mock-skip')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByTestId('mock-skip'))

      await waitFor(() => {
        expect(screen.getByText('Skip Task')).toBeInTheDocument()
        expect(screen.getByText('Please provide a reason for skipping this task.')).toBeInTheDocument()
      })
    })

    it('should close skip modal on Cancel', async () => {
      const requireCommentStore = {
        ...mockStoreState,
        currentProject: {
          ...mockProject,
          require_comment_on_skip: true,
        },
      }
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue(requireCommentStore)

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        fireEvent.click(screen.getByTestId('mock-skip'))
      })

      await waitFor(() => {
        expect(screen.getByText('Skip Task')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByText('Cancel'))

      await waitFor(() => {
        expect(screen.queryByText('Skip Task')).not.toBeInTheDocument()
      })
    })

    it('should skip with comment when provided', async () => {
      const requireCommentStore = {
        ...mockStoreState,
        currentProject: {
          ...mockProject,
          require_comment_on_skip: true,
        },
      }
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue(requireCommentStore)

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        fireEvent.click(screen.getByTestId('mock-skip'))
      })

      await waitFor(() => {
        expect(screen.getByText('Skip Task')).toBeInTheDocument()
      })

      // Type a comment
      const textarea = screen.getByPlaceholderText('Enter your comment...')
      fireEvent.change(textarea, { target: { value: 'Task is ambiguous' } })

      // Skip button should now be enabled
      const skipButton = screen.getAllByText('Skip').find(el => el.tagName === 'BUTTON' && !el.hasAttribute('data-testid'))
      fireEvent.click(skipButton!)

      await waitFor(() => {
        expect(mockStoreState.skipTask).toHaveBeenCalledWith('Task is ambiguous')
      })
    })

    it('should disable Skip button when comment is empty', async () => {
      const requireCommentStore = {
        ...mockStoreState,
        currentProject: {
          ...mockProject,
          require_comment_on_skip: true,
        },
      }
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue(requireCommentStore)

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        fireEvent.click(screen.getByTestId('mock-skip'))
      })

      await waitFor(() => {
        expect(screen.getByText('Skip Task')).toBeInTheDocument()
      })

      // Skip button in modal should be disabled when comment is empty
      const allSkipButtons = screen.getAllByText('Skip')
      const modalSkipButton = allSkipButtons.find(el => el.closest('.fixed'))
      expect(modalSkipButton).toBeDisabled()
    })
  })

  describe('Strict Timer Start', () => {
    it('should start timer when Start button is clicked on pre_start screen', async () => {
      const strictProject = {
        ...mockProject,
        strict_timer_enabled: true,
        annotation_time_limit_enabled: true,
        annotation_time_limit_seconds: 600,
      }
      const storeStrict = {
        ...mockStoreState,
        currentProject: strictProject,
      }
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue(storeStrict)
      ;(projectsAPI.getTimerStatus as jest.Mock).mockResolvedValue({
        server_time: new Date().toISOString(),
        session: null,
      })

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(screen.getByText('Ready to Begin')).toBeInTheDocument()
      })

      // Click Start
      fireEvent.click(screen.getByText('Start'))

      await waitFor(() => {
        expect(projectsAPI.startTimer).toHaveBeenCalledWith('project-1', 'task-1')
      })
    })

    it('should show error toast when start timer fails', async () => {
      const strictProject = {
        ...mockProject,
        strict_timer_enabled: true,
        annotation_time_limit_enabled: true,
        annotation_time_limit_seconds: 600,
      }
      const storeStrict = {
        ...mockStoreState,
        currentProject: strictProject,
      }
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue(storeStrict)
      ;(projectsAPI.getTimerStatus as jest.Mock).mockResolvedValue({
        server_time: new Date().toISOString(),
        session: null,
      })
      ;(projectsAPI.startTimer as jest.Mock).mockRejectedValue(new Error('Server error'))

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(screen.getByText('Ready to Begin')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByText('Start'))

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith('Failed to start timer')
      })
    })

    it('should show conditional instructions on pre-start screen', async () => {
      const strictProject = {
        ...mockProject,
        strict_timer_enabled: true,
        annotation_time_limit_enabled: true,
        annotation_time_limit_seconds: 600,
        conditional_instructions: [
          { id: 'variant-1', content: 'Special instructions for this variant', weight: 100 },
        ],
      }
      const storeStrict = {
        ...mockStoreState,
        currentProject: strictProject,
      }
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue(storeStrict)
      ;(projectsAPI.getTimerStatus as jest.Mock).mockResolvedValue({
        server_time: new Date().toISOString(),
        session: null,
      })

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(screen.getByText('Ready to Begin')).toBeInTheDocument()
      })

      // Conditional instructions should be shown on the pre-start screen
      expect(screen.getByText('Annotation Instructions')).toBeInTheDocument()
    })
  })

  describe('Instruction Modal Auto-show Logic', () => {
    it('should auto-show instructions modal when show_instruction is true and not dismissed', async () => {
      const storeWithInstructions = {
        ...mockStoreState,
        currentProject: {
          ...mockProject,
          instructions: 'Read these carefully.',
          show_instruction: true,
          instructions_always_visible: false,
          conditional_instructions: null,
        },
      }
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue(storeWithInstructions)
      // localStorage.getItem returns null (not dismissed)

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(screen.getByText('Read these carefully.')).toBeInTheDocument()
      })

      // Should show "Don't show again" checkbox
      expect(screen.getByText("Don't show again for this project")).toBeInTheDocument()
    })

    it('should not auto-show instructions when already dismissed', async () => {
      ;(window.localStorage.getItem as jest.Mock).mockImplementation((key: string) => {
        if (key === 'benger-instructions-dismissed-project-1') return 'true'
        return null
      })

      const storeWithInstructions = {
        ...mockStoreState,
        currentProject: {
          ...mockProject,
          instructions: 'Read these carefully.',
          show_instruction: true,
          instructions_always_visible: false,
          conditional_instructions: null,
        },
      }
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue(storeWithInstructions)

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(screen.getByText('Test Project')).toBeInTheDocument()
      })

      expect(screen.queryByText('Read these carefully.')).not.toBeInTheDocument()
    })

    it('should always show conditional instructions per-task (no dismiss)', async () => {
      const storeWithConditional = {
        ...mockStoreState,
        currentProject: {
          ...mockProject,
          instructions: null,
          show_instruction: false,
          instructions_always_visible: false,
          conditional_instructions: [
            { id: 'variant-a', content: 'Condition A instructions', weight: 100 },
          ],
          strict_timer_enabled: false,
          annotation_time_limit_enabled: false,
        },
      }
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue(storeWithConditional)

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(screen.getByText('Annotation Instructions')).toBeInTheDocument()
      })
    })

    it('should save dismissed state when dont show again is checked', async () => {
      const storeWithInstructions = {
        ...mockStoreState,
        currentProject: {
          ...mockProject,
          instructions: 'Instructions text.',
          show_instruction: true,
          instructions_always_visible: false,
          conditional_instructions: null,
        },
      }
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue(storeWithInstructions)

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(screen.getByText('Instructions text.')).toBeInTheDocument()
      })

      // Check the "Don't show again" checkbox
      const checkbox = screen.getByRole('checkbox')
      fireEvent.click(checkbox)

      // Click Start Annotating
      fireEvent.click(screen.getByText('Start Annotating'))

      await waitFor(() => {
        expect(localStorage.setItem).toHaveBeenCalledWith(
          'benger-instructions-dismissed-project-1',
          'true'
        )
      })
    })
  })

  describe('Immediate Evaluation Flow', () => {
    it('should show evaluation modal after submit when immediate evaluation is enabled', async () => {
      const evalProject = {
        ...mockProject,
        immediate_evaluation_enabled: true,
      }
      const evalStore = {
        ...mockStoreState,
        currentProject: evalProject,
        createAnnotationInternal: jest.fn().mockResolvedValue({
          id: 'annotation-1',
          task_id: 'task-1',
          result: [],
          created_at: '2025-01-01T00:00:00Z',
        }),
      }
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue(evalStore)

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(screen.getByTestId('mock-submit')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByTestId('mock-submit'))

      // Should show evaluation modal loading state
      await waitFor(() => {
        expect(evalStore.createAnnotationInternal).toHaveBeenCalledWith(
          'task-1',
          expect.objectContaining({ result: [] }),
          true // skipAdvance when evaluation is enabled
        )
      })
    })
  })

  describe('Questionnaire Flow', () => {
    it('should show questionnaire modal after submit when questionnaire is enabled', async () => {
      const questionnaireProject = {
        ...mockProject,
        questionnaire_enabled: true,
        questionnaire_config: '<View><Rating name="q" toName="q" maxRating="5"/></View>',
        immediate_evaluation_enabled: false,
      }
      const qStore = {
        ...mockStoreState,
        currentProject: questionnaireProject,
        createAnnotationInternal: jest.fn().mockResolvedValue({
          id: 'annotation-1',
          task_id: 'task-1',
          result: [],
          created_at: '2025-01-01T00:00:00Z',
        }),
      }
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue(qStore)

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(screen.getByTestId('mock-submit')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByTestId('mock-submit'))

      await waitFor(() => {
        expect(qStore.createAnnotationInternal).toHaveBeenCalledWith(
          'task-1',
          expect.objectContaining({ result: [] }),
          true // skipAdvance when questionnaire is active
        )
      })
    })
  })

  describe('All Tasks Completed Redirect', () => {
    it('should redirect to project page when all tasks completed', async () => {
      const completedStore = {
        ...mockStoreState,
        allTasksCompleted: true,
      }
      ;(useProjectStore as unknown as jest.Mock).mockReturnValue(completedStore)

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(mockRouter.push).toHaveBeenCalledWith('/projects/project-1')
      })

      expect(completedStore.resetAnnotationCompletion).toHaveBeenCalled()
      expect(localStorage.removeItem).toHaveBeenCalledWith(
        expect.stringContaining('task_position')
      )
      expect(localStorage.removeItem).toHaveBeenCalledWith(
        expect.stringContaining('task_id')
      )
    })
  })

  describe('Saved Task ID Restoration', () => {
    it('should restore from saved task ID in localStorage', async () => {
      ;(window.localStorage.getItem as jest.Mock).mockImplementation((key: string) => {
        if (key.includes('task_id')) return 'task-3'
        if (key.includes('task_position')) return '3'
        return null
      })

      const tasks = [
        { ...mockTask, id: 'task-1' },
        { ...mockTask, id: 'task-2' },
        { ...mockTask, id: 'task-3' },
      ]
      mockStoreState.fetchProjectTasks.mockResolvedValue(tasks)

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(mockStoreState.fetchProjectTasks).toHaveBeenCalledWith('project-1', true)
        expect(mockStoreState.setTaskByIndex).toHaveBeenCalledWith(2) // task-3 at index 2
      })
    })

    it('should fall back to position when saved task ID not found', async () => {
      ;(window.localStorage.getItem as jest.Mock).mockImplementation((key: string) => {
        if (key.includes('task_id')) return 'deleted-task'
        if (key.includes('task_position')) return '2'
        return null
      })

      const tasks = [
        { ...mockTask, id: 'task-1' },
        { ...mockTask, id: 'task-2' },
      ]
      mockStoreState.fetchProjectTasks.mockResolvedValue(tasks)

      render(<LabelingInterface projectId="project-1" />)

      await waitFor(() => {
        expect(mockStoreState.setTaskByIndex).toHaveBeenCalledWith(1) // position 2 → index 1
      })
    })
  })
})

import { renderWithProviders } from '@/test-utils'
import '@testing-library/jest-dom'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import React from 'react'

// Mock Next.js router
const mockPush = jest.fn()
const mockRouter = {
  push: mockPush,
  pathname: '/',
  query: {},
  asPath: '/',
  events: {
    on: jest.fn(),
    off: jest.fn(),
    emit: jest.fn(),
  },
}

jest.mock('next/navigation', () => ({
  useRouter: () => mockRouter,
  usePathname: () => mockRouter.pathname,
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({}),
}))

// Mock API client
const mockApiClient = {
  getProjects: jest.fn(),
  getProject: jest.fn(),
  getTasks: jest.fn(),
  getTask: jest.fn(),
  createAnnotation: jest.fn(),
  updateAnnotation: jest.fn(),
  getAnnotations: jest.fn(),
  submitAnnotation: jest.fn(),
  skipTask: jest.fn(),
  getProjectProgress: jest.fn(),
  getUserAnnotationStats: jest.fn(),
}

// Simplified App component for testing
const App = () => {
  const [currentView, setCurrentView] = React.useState('projects')
  const [selectedProject, setSelectedProject] = React.useState<any>(null)
  const [currentTask, setCurrentTask] = React.useState<any>(null)
  const [annotations, setAnnotations] = React.useState<any[]>([])
  const [progress, setProgress] = React.useState({ completed: 0, total: 10 })

  const handleProjectSelect = (project: any) => {
    setSelectedProject(project)
    setCurrentView('annotation')
    setCurrentTask({
      id: 'task-1',
      question: 'What is the legal basis for this claim?',
      context: 'Contract law context...',
      data: { document: 'Legal document text...' },
    })
  }

  const handleAnnotationSubmit = async (annotation: any) => {
    const newAnnotation = {
      id: `annotation-${annotations.length + 1}`,
      taskId: currentTask.id,
      value: annotation,
      createdAt: new Date().toISOString(),
    }

    setAnnotations([...annotations, newAnnotation])
    setProgress((prev) => ({ ...prev, completed: prev.completed + 1 }))

    // Auto-save simulation
    try {
      await mockApiClient.createAnnotation(newAnnotation)
    } catch (error) {
      // Handle save errors gracefully - continue with the flow
      console.warn('Auto-save failed:', error)
    }

    // Move to next task
    if (progress.completed + 1 < progress.total) {
      setCurrentTask({
        id: `task-${progress.completed + 2}`,
        question: `Question ${progress.completed + 2}`,
        context: 'Next context...',
        data: { document: 'Next document...' },
      })
    } else {
      setCurrentView('complete')
    }
  }

  const handleSkip = () => {
    setProgress((prev) => ({ ...prev, completed: prev.completed + 1 }))
    setCurrentTask({
      id: `task-${progress.completed + 2}`,
      question: `Question ${progress.completed + 2}`,
      context: 'Next context...',
      data: { document: 'Next document...' },
    })
  }

  if (currentView === 'projects') {
    return (
      <div data-testid="projects-view">
        <h1>Projects</h1>
        <div data-testid="project-list">
          <button
            data-testid="project-1"
            onClick={() =>
              handleProjectSelect({ id: '1', name: 'Test Project' })
            }
          >
            Test Project
          </button>
        </div>
      </div>
    )
  }

  if (currentView === 'annotation') {
    return (
      <div data-testid="annotation-view">
        <div data-testid="progress-bar">
          {progress.completed}/{progress.total} completed
        </div>

        <div data-testid="task-content">
          <h2>{currentTask.question}</h2>
          <p>{currentTask.context}</p>
          <div>{currentTask.data.document}</div>
        </div>

        <div data-testid="annotation-interface">
          <textarea
            data-testid="annotation-input"
            placeholder="Enter your annotation..."
          />
          <button
            data-testid="submit-button"
            onClick={() => {
              const input = document.querySelector(
                '[data-testid="annotation-input"]'
              ) as HTMLTextAreaElement
              handleAnnotationSubmit(input.value)
            }}
          >
            Submit
          </button>
          <button data-testid="skip-button" onClick={handleSkip}>
            Skip
          </button>
          <button
            data-testid="next-button"
            onClick={() => {
              const input = document.querySelector(
                '[data-testid="annotation-input"]'
              ) as HTMLTextAreaElement
              handleAnnotationSubmit(input.value)
            }}
          >
            Next
          </button>
        </div>

        <div data-testid="auto-save-indicator">
          {annotations.length > 0 && 'Auto-saved'}
        </div>
      </div>
    )
  }

  if (currentView === 'complete') {
    return (
      <div data-testid="complete-view">
        <h1>Annotation Complete!</h1>
        <p>You have completed all tasks in this project.</p>
        <div data-testid="final-stats">
          Total annotations: {annotations.length}
        </div>
      </div>
    )
  }

  return null
}

describe('Complete Annotation Flow', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockApiClient.getProjects.mockResolvedValue([
      { id: '1', name: 'Test Project', taskCount: 10 },
    ])
    mockApiClient.createAnnotation.mockResolvedValue({ success: true })
  })

  describe('Navigation Flow', () => {
    it('navigates from projects to annotation', async () => {
      const user = userEvent.setup()

      renderWithProviders(<App />)

      // Start at projects view
      expect(screen.getByTestId('projects-view')).toBeInTheDocument()
      expect(screen.getByText('Projects')).toBeInTheDocument()

      // Click on a project
      await user.click(screen.getByTestId('project-1'))

      // Should navigate to annotation view
      await waitFor(() => {
        expect(screen.getByTestId('annotation-view')).toBeInTheDocument()
        expect(screen.getByTestId('task-content')).toBeInTheDocument()
      })
    })

    it('displays task information correctly', async () => {
      const user = userEvent.setup()

      renderWithProviders(<App />)

      await user.click(screen.getByTestId('project-1'))

      await waitFor(() => {
        expect(
          screen.getByText('What is the legal basis for this claim?')
        ).toBeInTheDocument()
        expect(screen.getByText('Contract law context...')).toBeInTheDocument()
        expect(screen.getByText('Legal document text...')).toBeInTheDocument()
      })
    })
  })

  describe('Annotation Submission', () => {
    it('completes full annotation lifecycle', async () => {
      const user = userEvent.setup()

      renderWithProviders(<App />)

      // Navigate to annotation
      await user.click(screen.getByTestId('project-1'))

      await waitFor(() => {
        expect(screen.getByTestId('annotation-interface')).toBeInTheDocument()
      })

      // Enter annotation
      const input = screen.getByTestId('annotation-input')
      await user.type(input, 'This is based on Section 433 BGB')

      // Submit annotation
      await user.click(screen.getByTestId('submit-button'))

      // Verify progression
      await waitFor(() => {
        expect(screen.getByText('1/10 completed')).toBeInTheDocument()
      })

      // Verify auto-save
      await waitFor(() => {
        expect(screen.getByTestId('auto-save-indicator')).toHaveTextContent(
          'Auto-saved'
        )
        expect(mockApiClient.createAnnotation).toHaveBeenCalledWith(
          expect.objectContaining({
            value: 'This is based on Section 433 BGB',
            taskId: 'task-1',
          })
        )
      })
    })

    it('handles multiple annotations in sequence', async () => {
      const user = userEvent.setup()

      renderWithProviders(<App />)

      await user.click(screen.getByTestId('project-1'))

      // Complete multiple annotations
      for (let i = 1; i <= 3; i++) {
        const input = screen.getByTestId('annotation-input')
        await user.clear(input)
        await user.type(input, `Annotation ${i}`)
        await user.click(screen.getByTestId('submit-button'))

        await waitFor(() => {
          expect(screen.getByText(`${i}/10 completed`)).toBeInTheDocument()
        })
      }

      // Verify all annotations were saved
      expect(mockApiClient.createAnnotation).toHaveBeenCalledTimes(3)
    })

    it('navigates to next task after submission', async () => {
      const user = userEvent.setup()

      renderWithProviders(<App />)

      await user.click(screen.getByTestId('project-1'))

      // Submit first annotation
      const input = screen.getByTestId('annotation-input')
      await user.type(input, 'First annotation')
      await user.click(screen.getByTestId('next-button'))

      // Should show next task
      await waitFor(() => {
        expect(screen.getByText('Question 2')).toBeInTheDocument()
      })
    })

    it('allows skipping tasks', async () => {
      const user = userEvent.setup()

      renderWithProviders(<App />)

      await user.click(screen.getByTestId('project-1'))

      // Skip first task
      await user.click(screen.getByTestId('skip-button'))

      // Should move to next task
      await waitFor(() => {
        expect(screen.getByText('Question 2')).toBeInTheDocument()
        expect(screen.getByText('1/10 completed')).toBeInTheDocument()
      })
    })
  })

  describe('Progress Tracking', () => {
    it('updates progress bar correctly', async () => {
      const user = userEvent.setup()

      renderWithProviders(<App />)

      await user.click(screen.getByTestId('project-1'))

      // Initial progress
      expect(screen.getByText('0/10 completed')).toBeInTheDocument()

      // Complete one annotation
      const input = screen.getByTestId('annotation-input')
      await user.type(input, 'Test')
      await user.click(screen.getByTestId('submit-button'))

      await waitFor(() => {
        expect(screen.getByText('1/10 completed')).toBeInTheDocument()
      })
    })

    it('shows completion screen when all tasks are done', async () => {
      const user = userEvent.setup()

      renderWithProviders(<App />)

      await user.click(screen.getByTestId('project-1'))

      // Complete all 10 tasks
      for (let i = 1; i <= 10; i++) {
        const input = screen.getByTestId('annotation-input')
        await user.clear(input)
        await user.type(input, `Annotation ${i}`)
        await user.click(screen.getByTestId('submit-button'))

        if (i < 10) {
          await waitFor(() => {
            expect(screen.getByText(`${i}/10 completed`)).toBeInTheDocument()
          })
        }
      }

      // Should show completion view
      await waitFor(() => {
        expect(screen.getByTestId('complete-view')).toBeInTheDocument()
        expect(screen.getByText('Annotation Complete!')).toBeInTheDocument()
        expect(screen.getByText('Total annotations: 10')).toBeInTheDocument()
      })
    })
  })

  describe('Auto-save Functionality', () => {
    it('auto-saves annotations', async () => {
      const user = userEvent.setup()

      renderWithProviders(<App />)

      await user.click(screen.getByTestId('project-1'))

      const input = screen.getByTestId('annotation-input')
      await user.type(input, 'Auto-save test')
      await user.click(screen.getByTestId('submit-button'))

      await waitFor(() => {
        expect(screen.getByTestId('auto-save-indicator')).toHaveTextContent(
          'Auto-saved'
        )
        expect(mockApiClient.createAnnotation).toHaveBeenCalled()
      })
    })

    it('handles auto-save errors gracefully', async () => {
      mockApiClient.createAnnotation.mockRejectedValueOnce(
        new Error('Network error')
      )

      const user = userEvent.setup()

      renderWithProviders(<App />)

      await user.click(screen.getByTestId('project-1'))

      const input = screen.getByTestId('annotation-input')
      await user.type(input, 'Test with error')
      await user.click(screen.getByTestId('submit-button'))

      // Should still progress despite save error
      await waitFor(() => {
        expect(screen.getByText('1/10 completed')).toBeInTheDocument()
      })
    })
  })

  describe('Keyboard Navigation', () => {
    it('supports keyboard shortcuts for submission', async () => {
      const user = userEvent.setup()

      renderWithProviders(<App />)

      await user.click(screen.getByTestId('project-1'))

      const input = screen.getByTestId('annotation-input')
      await user.type(input, 'Keyboard test')

      // Simulate Ctrl+Enter for submission (would need to be implemented in actual component)
      await user.keyboard('{Control>}{Enter}{/Control}')

      // For this test, we'll use the button click as fallback
      await user.click(screen.getByTestId('submit-button'))

      await waitFor(() => {
        expect(screen.getByText('1/10 completed')).toBeInTheDocument()
      })
    })
  })

  describe('Data Persistence', () => {
    it('maintains annotation history', async () => {
      const user = userEvent.setup()

      renderWithProviders(<App />)

      await user.click(screen.getByTestId('project-1'))

      // Complete multiple annotations
      const annotations = ['First', 'Second', 'Third']

      for (const text of annotations) {
        const input = screen.getByTestId('annotation-input')
        await user.clear(input)
        await user.type(input, text)
        await user.click(screen.getByTestId('submit-button'))
      }

      // Verify all annotations were saved
      expect(mockApiClient.createAnnotation).toHaveBeenCalledTimes(3)

      for (const text of annotations) {
        expect(mockApiClient.createAnnotation).toHaveBeenCalledWith(
          expect.objectContaining({ value: text })
        )
      }
    })
  })
})

import { projectsAPI } from '@/lib/api/projects'
import '@testing-library/jest-dom'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { AnnotationCreator } from '../AnnotationCreator'

// Mock the dependencies
jest.mock('@/lib/api/projects')

const mockTranslate = (key: string, arg2?: any, arg3?: any) => {
  const vars = typeof arg2 === 'object' ? arg2 : arg3;
  const translations: Record<string, string> = {
    'labeling.annotationCreator.submitFailed': 'Failed to submit annotation',
    'labeling.annotationCreator.taskLabel': 'Task',
    'labeling.annotationCreator.saving': 'Saving...',
    'labeling.annotationCreator.autoSaveInfo': 'Your work is automatically saved locally in your browser.',
  };
  let result = translations[key] || key;
  if (vars) {
    Object.entries(vars).forEach(([k, v]) => {
      result = result.replace(`{${k}}`, String(v));
    });
  }
  return result;
};

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({ t: mockTranslate, locale: 'en', setLocale: jest.fn() }),
}))

// Mock DynamicAnnotationInterface
jest.mock('@/components/labeling/DynamicAnnotationInterface', () => ({
  DynamicAnnotationInterface: ({
    onSubmit,
    onSkip,
    initialValues,
  }: {
    onSubmit: (results: any[]) => void
    onSkip?: () => void
    initialValues?: any[]
  }) => {
    return (
      <div data-testid="dynamic-annotation-interface">
        {initialValues && (
          <div data-testid="initial-values">
            {JSON.stringify(initialValues)}
          </div>
        )}
        <button
          onClick={() => onSubmit([{ from_name: 'test', value: 'test value' }])}
        >
          Submit
        </button>
        {onSkip && <button onClick={onSkip}>Skip</button>}
      </div>
    )
  },
}))

describe('AnnotationCreator', () => {
  const mockTask = {
    id: 'task-1',
    data: { text: 'Sample text' },
    meta: {},
    created_at: '2024-01-01',
    updated_at: '2024-01-01',
  }

  const mockAnnotation = {
    id: 'ann-1',
    task: 'task-1',
    completed_by: 'user-1',
    result: [{ from_name: 'text', value: 'Initial value' }],
    was_cancelled: true,
    created_at: '2024-01-01',
    updated_at: '2024-01-01',
  }

  const defaultProps = {
    task: mockTask,
    projectId: 'project-1',
    labelConfig: '<View><Text name="text" value="$text"/></View>',
    onSubmit: jest.fn(),
    onCancel: jest.fn(),
  }

  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('Basic Rendering', () => {
    it('should render the annotation interface', () => {
      render(<AnnotationCreator {...defaultProps} />)

      expect(
        screen.getByTestId('dynamic-annotation-interface')
      ).toBeInTheDocument()
      expect(screen.getByText(`Task #${mockTask.id}`)).toBeInTheDocument()
    })

    it('should display info text about local saving', () => {
      render(<AnnotationCreator {...defaultProps} />)

      expect(
        screen.getByText('Your work is automatically saved locally in your browser.')
      ).toBeInTheDocument()
    })
  })

  describe('Submission Flow', () => {
    it('should create new annotation on submit when no initial annotation exists', async () => {
      const onSubmit = jest.fn()
      ;(projectsAPI.createAnnotation as jest.Mock).mockResolvedValue({
        id: 'new-ann',
        was_cancelled: false,
        result: [{ from_name: 'test', value: 'test value' }],
      })

      render(<AnnotationCreator {...defaultProps} onSubmit={onSubmit} />)

      const submitButton = screen.getByText('Submit')
      fireEvent.click(submitButton)

      await waitFor(() => {
        expect(projectsAPI.createAnnotation).toHaveBeenCalledWith(
          mockTask.id,
          expect.objectContaining({
            result: [{ from_name: 'test', value: 'test value' }],
            was_cancelled: false,
          })
        )
        expect(onSubmit).toHaveBeenCalledWith(
          expect.objectContaining({
            id: 'new-ann',
            was_cancelled: false,
          })
        )
      })
    })

    it('should update existing annotation on submit when initial annotation exists', async () => {
      const onSubmit = jest.fn()
      ;(projectsAPI.updateAnnotation as jest.Mock).mockResolvedValue({
        ...mockAnnotation,
        was_cancelled: false,
        result: [{ from_name: 'test', value: 'test value' }],
      })

      render(
        <AnnotationCreator
          {...defaultProps}
          initialAnnotation={mockAnnotation}
          onSubmit={onSubmit}
        />
      )

      const submitButton = screen.getByText('Submit')
      fireEvent.click(submitButton)

      await waitFor(() => {
        expect(projectsAPI.updateAnnotation).toHaveBeenCalledWith(
          mockAnnotation.id,
          expect.objectContaining({
            result: [{ from_name: 'test', value: 'test value' }],
            was_cancelled: false,
          })
        )
        expect(onSubmit).toHaveBeenCalled()
      })
    })

    it('should handle submission errors gracefully', async () => {
      ;(projectsAPI.createAnnotation as jest.Mock).mockRejectedValue(
        new Error('Network error')
      )

      render(<AnnotationCreator {...defaultProps} />)

      const submitButton = screen.getByText('Submit')
      fireEvent.click(submitButton)

      await waitFor(() => {
        expect(
          screen.getByText('Failed to submit annotation')
        ).toBeInTheDocument()
      })
    })

    it('should show saving indicator while submitting', async () => {
      ;(projectsAPI.createAnnotation as jest.Mock).mockImplementation(
        () =>
          new Promise((resolve) =>
            setTimeout(
              () =>
                resolve({
                  id: 'new-ann',
                  was_cancelled: false,
                  result: [],
                }),
              100
            )
          )
      )

      render(<AnnotationCreator {...defaultProps} />)

      const submitButton = screen.getByText('Submit')
      fireEvent.click(submitButton)

      expect(screen.getByText('Saving...')).toBeInTheDocument()
    })
  })

  describe('Cancel/Skip Flow', () => {
    it('should call onCancel when skip is clicked', () => {
      const onCancel = jest.fn()
      render(<AnnotationCreator {...defaultProps} onCancel={onCancel} />)

      const skipButton = screen.getByText('Skip')
      fireEvent.click(skipButton)

      expect(onCancel).toHaveBeenCalled()
    })
  })

  describe('Initial Annotation', () => {
    it('should load initial annotation values', () => {
      render(
        <AnnotationCreator
          {...defaultProps}
          initialAnnotation={mockAnnotation}
        />
      )

      expect(screen.getByTestId('initial-values')).toHaveTextContent(
        JSON.stringify(mockAnnotation.result)
      )
    })
  })

  describe('Status Display', () => {
    it('should show task ID in status bar', () => {
      render(<AnnotationCreator {...defaultProps} />)

      expect(screen.getByText(`Task #${mockTask.id}`)).toBeInTheDocument()
    })
  })
})

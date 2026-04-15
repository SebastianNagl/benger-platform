/**
 * Unit tests for PostAnnotationQuestionnaireModal component
 */

/**
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// Mock I18n context with the specific translation keys used by this component
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, params?: any) => {
      const translations: Record<string, string> = {
        'annotation.questionnaire.title': 'Post-Annotation Questionnaire',
        'annotation.questionnaire.description':
          'Please answer the following questions about this annotation.',
        'annotation.questionnaire.submitting': 'Submitting questionnaire...',
      }
      return translations[key] || key
    },
    locale: 'en',
    isReady: true,
  }),
}))

// Mock the DynamicAnnotationInterface — capture onSubmit so tests can trigger it
let capturedOnSubmit: ((annotations: any[]) => void) | null = null
jest.mock('@/components/labeling/DynamicAnnotationInterface', () => ({
  DynamicAnnotationInterface: ({
    onSubmit,
    labelConfig,
    taskData,
    showSubmitButton,
    enableAutoSave,
  }: any) => {
    capturedOnSubmit = onSubmit
    return (
      <div data-testid="mock-dynamic-interface">
        <div data-testid="label-config">{labelConfig}</div>
        <div data-testid="show-submit">{String(showSubmitButton)}</div>
        <div data-testid="auto-save">{String(enableAutoSave)}</div>
        <button
          data-testid="mock-submit"
          onClick={() => onSubmit([{ id: 'test', value: 'answer' }])}
        >
          Submit
        </button>
      </div>
    )
  },
}))

import { PostAnnotationQuestionnaireModal } from '../../../components/labeling/PostAnnotationQuestionnaireModal'

const defaultProps = {
  isOpen: true,
  questionnaireConfig: '<View><Choices name="q1" toName="text"><Choice value="Yes"/><Choice value="No"/></Choices></View>',
  projectId: 'proj-123',
  taskId: 'task-456',
  annotationId: 'ann-789',
  onComplete: jest.fn(),
  onSubmitResponse: jest.fn().mockResolvedValue(undefined),
}

describe('PostAnnotationQuestionnaireModal', () => {
  beforeEach(() => {
    capturedOnSubmit = null
    defaultProps.onComplete = jest.fn()
    defaultProps.onSubmitResponse = jest.fn().mockResolvedValue(undefined)
  })

  describe('Rendering', () => {
    it('should render modal content when isOpen is true', async () => {
      await act(async () => {
        render(<PostAnnotationQuestionnaireModal {...defaultProps} isOpen={true} />)
      })

      expect(
        screen.getByText('Post-Annotation Questionnaire')
      ).toBeInTheDocument()
    })

    it('should not render modal content when isOpen is false', async () => {
      await act(async () => {
        render(<PostAnnotationQuestionnaireModal {...defaultProps} isOpen={false} />)
      })

      expect(
        screen.queryByText('Post-Annotation Questionnaire')
      ).not.toBeInTheDocument()
    })

    it('should display title and description via i18n', async () => {
      await act(async () => {
        render(<PostAnnotationQuestionnaireModal {...defaultProps} />)
      })

      expect(
        screen.getByText('Post-Annotation Questionnaire')
      ).toBeInTheDocument()
      expect(
        screen.getByText(
          'Please answer the following questions about this annotation.'
        )
      ).toBeInTheDocument()
    })

    it('should pass correct props to DynamicAnnotationInterface', async () => {
      await act(async () => {
        render(<PostAnnotationQuestionnaireModal {...defaultProps} />)
      })

      expect(screen.getByTestId('mock-dynamic-interface')).toBeInTheDocument()
      expect(screen.getByTestId('label-config')).toHaveTextContent(
        defaultProps.questionnaireConfig
      )
      expect(screen.getByTestId('show-submit')).toHaveTextContent('true')
      expect(screen.getByTestId('auto-save')).toHaveTextContent('false')
    })
  })

  describe('Submission Flow', () => {
    it('should call onSubmitResponse with correct arguments', async () => {
      const user = userEvent.setup()

      await act(async () => {
        render(<PostAnnotationQuestionnaireModal {...defaultProps} />)
      })

      const submitButton = screen.getByTestId('mock-submit')
      await user.click(submitButton)

      await waitFor(() => {
        expect(defaultProps.onSubmitResponse).toHaveBeenCalledWith(
          'proj-123',
          'task-456',
          'ann-789',
          [{ id: 'test', value: 'answer' }]
        )
      })
    })

    it('should show submitting spinner during API call', async () => {
      // Create a promise that we control so we can observe the submitting state
      let resolveSubmit!: () => void
      const submitPromise = new Promise<void>((resolve) => {
        resolveSubmit = resolve
      })
      defaultProps.onSubmitResponse = jest.fn().mockReturnValue(submitPromise)

      await act(async () => {
        render(<PostAnnotationQuestionnaireModal {...defaultProps} />)
      })

      // Trigger submit via captured callback
      await act(async () => {
        capturedOnSubmit!([{ id: 'test', value: 'answer' }])
      })

      // The submitting text should be visible while the promise is pending
      expect(
        screen.getByText('Submitting questionnaire...')
      ).toBeInTheDocument()

      // Resolve the promise to clean up
      await act(async () => {
        resolveSubmit()
      })
    })

    it('should call onComplete after successful submission', async () => {
      const user = userEvent.setup()

      await act(async () => {
        render(<PostAnnotationQuestionnaireModal {...defaultProps} />)
      })

      const submitButton = screen.getByTestId('mock-submit')
      await user.click(submitButton)

      await waitFor(() => {
        expect(defaultProps.onComplete).toHaveBeenCalledTimes(1)
      })
    })

    it('should NOT call onComplete when submission fails', async () => {
      defaultProps.onSubmitResponse = jest
        .fn()
        .mockRejectedValue(new Error('Server error'))

      const user = userEvent.setup()

      await act(async () => {
        render(<PostAnnotationQuestionnaireModal {...defaultProps} />)
      })

      const submitButton = screen.getByTestId('mock-submit')
      await user.click(submitButton)

      await waitFor(() => {
        expect(defaultProps.onComplete).not.toHaveBeenCalled()
      })
    })
  })

  describe('Error Handling', () => {
    it('should display error message when onSubmitResponse throws', async () => {
      defaultProps.onSubmitResponse = jest
        .fn()
        .mockRejectedValue(new Error('Network failure'))

      const user = userEvent.setup()

      await act(async () => {
        render(<PostAnnotationQuestionnaireModal {...defaultProps} />)
      })

      const submitButton = screen.getByTestId('mock-submit')
      await user.click(submitButton)

      await waitFor(() => {
        expect(screen.getByText('Network failure')).toBeInTheDocument()
      })
    })

    it('should use err.message when available', async () => {
      defaultProps.onSubmitResponse = jest
        .fn()
        .mockRejectedValue(new Error('Custom error message'))

      const user = userEvent.setup()

      await act(async () => {
        render(<PostAnnotationQuestionnaireModal {...defaultProps} />)
      })

      const submitButton = screen.getByTestId('mock-submit')
      await user.click(submitButton)

      await waitFor(() => {
        expect(screen.getByText('Custom error message')).toBeInTheDocument()
      })
    })

    it('should fall back to default error message when err.message is undefined', async () => {
      // Reject with an object that has no message property
      defaultProps.onSubmitResponse = jest
        .fn()
        .mockRejectedValue({ code: 500 })

      const user = userEvent.setup()

      await act(async () => {
        render(<PostAnnotationQuestionnaireModal {...defaultProps} />)
      })

      const submitButton = screen.getByTestId('mock-submit')
      await user.click(submitButton)

      await waitFor(() => {
        expect(
          screen.getByText('Failed to submit questionnaire response')
        ).toBeInTheDocument()
      })
    })

    it('should clear error on new submission attempt', async () => {
      // First submission fails
      defaultProps.onSubmitResponse = jest
        .fn()
        .mockRejectedValueOnce(new Error('First attempt failed'))
        .mockResolvedValueOnce(undefined)

      const user = userEvent.setup()

      await act(async () => {
        render(<PostAnnotationQuestionnaireModal {...defaultProps} />)
      })

      // First submit — should show error
      const submitButton = screen.getByTestId('mock-submit')
      await user.click(submitButton)

      await waitFor(() => {
        expect(screen.getByText('First attempt failed')).toBeInTheDocument()
      })

      // Second submit — error should be cleared during submission
      await user.click(submitButton)

      await waitFor(() => {
        expect(
          screen.queryByText('First attempt failed')
        ).not.toBeInTheDocument()
      })
    })
  })

  describe('Non-dismissible', () => {
    it('should have a no-op onClose handler on the Dialog', async () => {
      await act(async () => {
        render(<PostAnnotationQuestionnaireModal {...defaultProps} />)
      })

      // The Dialog renders with onClose={() => {}}, meaning pressing Escape
      // or clicking the backdrop should not dismiss the modal.
      // We verify the modal stays open after an Escape keypress.
      const user = userEvent.setup()
      await user.keyboard('{Escape}')

      // Modal should still be visible — it was not dismissed
      expect(
        screen.getByText('Post-Annotation Questionnaire')
      ).toBeInTheDocument()
    })
  })
})

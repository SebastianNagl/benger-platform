/**
 * Tests for QuestionAddModal component
 * Target: 85%+ coverage
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QuestionAddModal } from '../QuestionAddModal'

// Mock the Button component
jest.mock('@/components/shared/Button', () => ({
  Button: ({ children, onClick, className, disabled, ...props }: any) => (
    <button
      onClick={onClick}
      className={className}
      disabled={disabled}
      {...props}
    >
      {children}
    </button>
  ),
}))

describe('QuestionAddModal', () => {
  const mockOnSave = jest.fn()
  const mockOnCancel = jest.fn()

  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('Rendering', () => {
    it('renders modal when isOpen is true', () => {
      render(
        <QuestionAddModal
          isOpen={true}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      expect(screen.getByTestId('question-add-modal')).toBeInTheDocument()
      expect(screen.getByText('Add Questions')).toBeInTheDocument()
    })

    it('does not render modal when isOpen is false', () => {
      render(
        <QuestionAddModal
          isOpen={false}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      expect(screen.queryByTestId('question-add-modal')).not.toBeInTheDocument()
    })

    it('renders with initial empty question', () => {
      render(
        <QuestionAddModal
          isOpen={true}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      expect(screen.getByText('Question #1')).toBeInTheDocument()
      expect(screen.getByTestId('add-question-0')).toBeInTheDocument()
      expect(screen.getByTestId('add-case-0')).toBeInTheDocument()
      expect(screen.getByTestId('add-answer-0-0')).toBeInTheDocument()
    })

    it('does not render reasoning field for non-QAR tasks', () => {
      render(
        <QuestionAddModal
          isOpen={true}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
          taskType="qa"
        />
      )

      expect(screen.queryByTestId('add-reasoning-0')).not.toBeInTheDocument()
    })

    it('renders reasoning field for QAR tasks', () => {
      render(
        <QuestionAddModal
          isOpen={true}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
          taskType="QAR"
        />
      )

      expect(screen.getByTestId('add-reasoning-0')).toBeInTheDocument()
    })
  })

  describe('Question Management', () => {
    it('allows adding multiple questions', async () => {
      const user = userEvent.setup()
      render(
        <QuestionAddModal
          isOpen={true}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      expect(screen.getByText('Question #1')).toBeInTheDocument()

      const addButton = screen.getByText('Add Another Question')
      await user.click(addButton)

      expect(screen.getByText('Question #2')).toBeInTheDocument()
      expect(screen.getByTestId('add-question-1')).toBeInTheDocument()
    })

    it('allows removing questions when more than one exists', async () => {
      const user = userEvent.setup()
      render(
        <QuestionAddModal
          isOpen={true}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      // Add a second question
      const addButton = screen.getByText('Add Another Question')
      await user.click(addButton)

      expect(screen.getByText('Question #2')).toBeInTheDocument()

      // Remove the second question
      const removeButtons = screen.getAllByTitle('Remove question')
      await user.click(removeButtons[1])

      expect(screen.queryByText('Question #2')).not.toBeInTheDocument()
      expect(screen.getByText('Question #1')).toBeInTheDocument()
    })

    it('does not show remove button when only one question exists', () => {
      render(
        <QuestionAddModal
          isOpen={true}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      const removeButton = screen.queryByTitle('Remove question')
      expect(removeButton).not.toBeInTheDocument()
    })

    it('updates question text correctly', async () => {
      const user = userEvent.setup()
      render(
        <QuestionAddModal
          isOpen={true}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      const questionInput = screen.getByTestId('add-question-0')
      await user.type(questionInput, 'What is the law?')

      expect(questionInput).toHaveValue('What is the law?')
    })

    it('updates case text correctly', async () => {
      const user = userEvent.setup()
      render(
        <QuestionAddModal
          isOpen={true}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      const caseInput = screen.getByTestId('add-case-0')
      await user.type(caseInput, 'Case background information')

      expect(caseInput).toHaveValue('Case background information')
    })

    it('updates reasoning text correctly for QAR tasks', async () => {
      const user = userEvent.setup()
      render(
        <QuestionAddModal
          isOpen={true}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
          taskType="QAR"
        />
      )

      const reasoningInput = screen.getByTestId('add-reasoning-0')
      await user.type(reasoningInput, 'Legal reasoning explanation')

      expect(reasoningInput).toHaveValue('Legal reasoning explanation')
    })
  })

  describe('Answer Management', () => {
    it('starts with one empty answer field', () => {
      render(
        <QuestionAddModal
          isOpen={true}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      expect(screen.getByTestId('add-answer-0-0')).toBeInTheDocument()
      expect(screen.getByPlaceholderText('Answer 1...')).toBeInTheDocument()
    })

    it('allows adding multiple answers', async () => {
      const user = userEvent.setup()
      render(
        <QuestionAddModal
          isOpen={true}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      const addAnswerButton = screen.getByText('Add Answer')
      await user.click(addAnswerButton)

      expect(screen.getByTestId('add-answer-0-1')).toBeInTheDocument()
      expect(screen.getByPlaceholderText('Answer 2...')).toBeInTheDocument()
    })

    it('allows removing answers when more than one exists', async () => {
      const user = userEvent.setup()
      render(
        <QuestionAddModal
          isOpen={true}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      // Add a second answer
      const addAnswerButton = screen.getByText('Add Answer')
      await user.click(addAnswerButton)

      expect(screen.getByTestId('add-answer-0-1')).toBeInTheDocument()

      // Remove the second answer
      const removeButtons = screen.getAllByTitle('Remove answer')
      await user.click(removeButtons[1])

      expect(screen.queryByTestId('add-answer-0-1')).not.toBeInTheDocument()
      expect(screen.getByTestId('add-answer-0-0')).toBeInTheDocument()
    })

    it('does not show remove button when only one answer exists', () => {
      render(
        <QuestionAddModal
          isOpen={true}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      const removeButton = screen.queryByTitle('Remove answer')
      expect(removeButton).not.toBeInTheDocument()
    })

    it('updates answer text correctly', async () => {
      const user = userEvent.setup()
      render(
        <QuestionAddModal
          isOpen={true}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      const answerInput = screen.getByTestId('add-answer-0-0')
      await user.type(answerInput, 'This is the answer')

      expect(answerInput).toHaveValue('This is the answer')
    })
  })

  describe('Validation', () => {
    it('shows error when question is empty', async () => {
      const user = userEvent.setup()
      render(
        <QuestionAddModal
          isOpen={true}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      const saveButton = screen.getByTestId('add-questions-button')
      await user.click(saveButton)

      await waitFor(() => {
        expect(screen.getByText('Question is required')).toBeInTheDocument()
      })

      expect(mockOnSave).not.toHaveBeenCalled()
    })

    it('shows error when all answers are empty', async () => {
      const user = userEvent.setup()
      render(
        <QuestionAddModal
          isOpen={true}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      // Fill question but leave answer empty
      const questionInput = screen.getByTestId('add-question-0')
      await user.type(questionInput, 'What is the law?')

      const saveButton = screen.getByTestId('add-questions-button')
      await user.click(saveButton)

      await waitFor(() => {
        expect(
          screen.getByText('At least one answer is required')
        ).toBeInTheDocument()
      })

      expect(mockOnSave).not.toHaveBeenCalled()
    })

    it('validates multiple questions independently', async () => {
      const user = userEvent.setup()
      render(
        <QuestionAddModal
          isOpen={true}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      // Add a second question
      const addButton = screen.getByText('Add Another Question')
      await user.click(addButton)

      // Fill only the first question
      const firstQuestion = screen.getByTestId('add-question-0')
      await user.type(firstQuestion, 'First question')

      const firstAnswer = screen.getByTestId('add-answer-0-0')
      await user.type(firstAnswer, 'First answer')

      // Try to save with second question empty
      const saveButton = screen.getByTestId('add-questions-button')
      await user.click(saveButton)

      await waitFor(() => {
        const errors = screen.getAllByText('Question is required')
        expect(errors.length).toBeGreaterThan(0)
      })

      expect(mockOnSave).not.toHaveBeenCalled()
    })

    it('allows saving when all required fields are filled', async () => {
      const user = userEvent.setup()
      render(
        <QuestionAddModal
          isOpen={true}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      const questionInput = screen.getByTestId('add-question-0')
      await user.type(questionInput, 'What is the law?')

      const answerInput = screen.getByTestId('add-answer-0-0')
      await user.type(answerInput, 'The law is a system of rules')

      const saveButton = screen.getByTestId('add-questions-button')
      await user.click(saveButton)

      expect(mockOnSave).toHaveBeenCalledWith([
        {
          question: 'What is the law?',
          answer: ['The law is a system of rules'],
          case: undefined,
          reasoning: undefined,
        },
      ])
    })

    it('filters out empty answers when saving', async () => {
      const user = userEvent.setup()
      render(
        <QuestionAddModal
          isOpen={true}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      const questionInput = screen.getByTestId('add-question-0')
      await user.type(questionInput, 'What is the law?')

      const answerInput = screen.getByTestId('add-answer-0-0')
      await user.type(answerInput, 'Valid answer')

      // Add second answer but leave it empty
      const addAnswerButton = screen.getByText('Add Answer')
      await user.click(addAnswerButton)

      const saveButton = screen.getByTestId('add-questions-button')
      await user.click(saveButton)

      expect(mockOnSave).toHaveBeenCalledWith([
        {
          question: 'What is the law?',
          answer: ['Valid answer'],
          case: undefined,
          reasoning: undefined,
        },
      ])
    })

    it('trims whitespace from question and case when saving', async () => {
      const user = userEvent.setup()
      render(
        <QuestionAddModal
          isOpen={true}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      const questionInput = screen.getByTestId('add-question-0')
      await user.type(questionInput, '  What is the law?  ')

      const caseInput = screen.getByTestId('add-case-0')
      await user.type(caseInput, '  Case info  ')

      const answerInput = screen.getByTestId('add-answer-0-0')
      await user.type(answerInput, 'Answer text')

      const saveButton = screen.getByTestId('add-questions-button')
      await user.click(saveButton)

      expect(mockOnSave).toHaveBeenCalledWith([
        {
          question: 'What is the law?',
          answer: ['Answer text'],
          case: 'Case info',
          reasoning: undefined,
        },
      ])
    })

    it('omits case field when empty', async () => {
      const user = userEvent.setup()
      render(
        <QuestionAddModal
          isOpen={true}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      const questionInput = screen.getByTestId('add-question-0')
      await user.type(questionInput, 'Question text')

      const answerInput = screen.getByTestId('add-answer-0-0')
      await user.type(answerInput, 'Answer text')

      const saveButton = screen.getByTestId('add-questions-button')
      await user.click(saveButton)

      expect(mockOnSave).toHaveBeenCalledWith([
        {
          question: 'Question text',
          answer: ['Answer text'],
          case: undefined,
          reasoning: undefined,
        },
      ])
    })
  })

  describe('Modal Actions', () => {
    it('calls onCancel when cancel button is clicked', async () => {
      const user = userEvent.setup()
      render(
        <QuestionAddModal
          isOpen={true}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      const cancelButton = screen.getByText('Cancel')
      await user.click(cancelButton)

      expect(mockOnCancel).toHaveBeenCalled()
    })

    it('calls onCancel when close icon is clicked', async () => {
      const user = userEvent.setup()
      render(
        <QuestionAddModal
          isOpen={true}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      const closeButton = screen.getByRole('button', { name: '' })
      await user.click(closeButton)

      expect(mockOnCancel).toHaveBeenCalled()
    })

    it('resets form state when modal closes', async () => {
      const user = userEvent.setup()
      const { rerender } = render(
        <QuestionAddModal
          isOpen={true}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      // Fill in some data
      const questionInput = screen.getByTestId('add-question-0')
      await user.type(questionInput, 'Test question')

      // Close modal
      const closeButton = screen.getByRole('button', { name: '' })
      await user.click(closeButton)

      // Reopen modal
      rerender(
        <QuestionAddModal
          isOpen={true}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      // Check that form is reset
      const newQuestionInput = screen.getByTestId('add-question-0')
      expect(newQuestionInput).toHaveValue('')
    })

    it('displays correct button text for single question', () => {
      render(
        <QuestionAddModal
          isOpen={true}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      expect(screen.getByText('Add 1 Question(s)')).toBeInTheDocument()
    })

    it('displays correct button text for multiple questions', async () => {
      const user = userEvent.setup()
      render(
        <QuestionAddModal
          isOpen={true}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      const addButton = screen.getByText('Add Another Question')
      await user.click(addButton)
      await user.click(addButton)

      expect(screen.getByText('Add 3 Question(s)')).toBeInTheDocument()
    })
  })

  describe('Multi-Question Scenarios', () => {
    it('saves multiple questions correctly', async () => {
      const user = userEvent.setup()
      render(
        <QuestionAddModal
          isOpen={true}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      // Add second question
      const addButton = screen.getByText('Add Another Question')
      await user.click(addButton)

      // Fill first question
      const firstQuestion = screen.getByTestId('add-question-0')
      await user.type(firstQuestion, 'Question 1')
      const firstAnswer = screen.getByTestId('add-answer-0-0')
      await user.type(firstAnswer, 'Answer 1')

      // Fill second question
      const secondQuestion = screen.getByTestId('add-question-1')
      await user.type(secondQuestion, 'Question 2')
      const secondAnswer = screen.getByTestId('add-answer-1-0')
      await user.type(secondAnswer, 'Answer 2')

      const saveButton = screen.getByTestId('add-questions-button')
      await user.click(saveButton)

      expect(mockOnSave).toHaveBeenCalledWith([
        {
          question: 'Question 1',
          answer: ['Answer 1'],
          case: undefined,
          reasoning: undefined,
        },
        {
          question: 'Question 2',
          answer: ['Answer 2'],
          case: undefined,
          reasoning: undefined,
        },
      ])
    })

    it('saves questions with multiple answers', async () => {
      const user = userEvent.setup()
      render(
        <QuestionAddModal
          isOpen={true}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      const questionInput = screen.getByTestId('add-question-0')
      await user.type(questionInput, 'Question with multiple answers')

      // Add multiple answers
      const firstAnswer = screen.getByTestId('add-answer-0-0')
      await user.type(firstAnswer, 'Answer 1')

      const addAnswerButton = screen.getByText('Add Answer')
      await user.click(addAnswerButton)

      const secondAnswer = screen.getByTestId('add-answer-0-1')
      await user.type(secondAnswer, 'Answer 2')

      await user.click(addAnswerButton)

      const thirdAnswer = screen.getByTestId('add-answer-0-2')
      await user.type(thirdAnswer, 'Answer 3')

      const saveButton = screen.getByTestId('add-questions-button')
      await user.click(saveButton)

      expect(mockOnSave).toHaveBeenCalledWith([
        {
          question: 'Question with multiple answers',
          answer: ['Answer 1', 'Answer 2', 'Answer 3'],
          case: undefined,
          reasoning: undefined,
        },
      ])
    })

    it('clears errors when question is removed', async () => {
      const user = userEvent.setup()
      render(
        <QuestionAddModal
          isOpen={true}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      // Add second question
      const addButton = screen.getByText('Add Another Question')
      await user.click(addButton)

      // Try to save with empty questions
      const saveButton = screen.getByTestId('add-questions-button')
      await user.click(saveButton)

      await waitFor(() => {
        const errors = screen.getAllByText('Question is required')
        expect(errors.length).toBe(2)
      })

      // Remove second question
      const removeButtons = screen.getAllByTitle('Remove question')
      await user.click(removeButtons[1])

      // Only one error should remain
      await waitFor(() => {
        const errors = screen.getAllByText('Question is required')
        expect(errors.length).toBe(1)
      })
    })
  })

  describe('QAR Task Type', () => {
    it('includes reasoning in saved data for QAR tasks', async () => {
      const user = userEvent.setup()
      render(
        <QuestionAddModal
          isOpen={true}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
          taskType="QAR"
        />
      )

      const questionInput = screen.getByTestId('add-question-0')
      await user.type(questionInput, 'Legal question')

      const answerInput = screen.getByTestId('add-answer-0-0')
      await user.type(answerInput, 'Legal answer')

      const reasoningInput = screen.getByTestId('add-reasoning-0')
      await user.type(reasoningInput, 'Legal reasoning')

      const saveButton = screen.getByTestId('add-questions-button')
      await user.click(saveButton)

      expect(mockOnSave).toHaveBeenCalledWith([
        {
          question: 'Legal question',
          answer: ['Legal answer'],
          case: undefined,
          reasoning: 'Legal reasoning',
        },
      ])
    })

    it('omits reasoning when empty for QAR tasks', async () => {
      const user = userEvent.setup()
      render(
        <QuestionAddModal
          isOpen={true}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
          taskType="QAR"
        />
      )

      const questionInput = screen.getByTestId('add-question-0')
      await user.type(questionInput, 'Legal question')

      const answerInput = screen.getByTestId('add-answer-0-0')
      await user.type(answerInput, 'Legal answer')

      const saveButton = screen.getByTestId('add-questions-button')
      await user.click(saveButton)

      expect(mockOnSave).toHaveBeenCalledWith([
        {
          question: 'Legal question',
          answer: ['Legal answer'],
          case: undefined,
          reasoning: undefined,
        },
      ])
    })
  })
})

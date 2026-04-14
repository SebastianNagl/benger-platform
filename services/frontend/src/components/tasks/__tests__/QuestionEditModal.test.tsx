/**
 * Tests for QuestionEditModal component
 * Target: 85%+ coverage
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QuestionEditModal } from '../QuestionEditModal'

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

describe('QuestionEditModal', () => {
  const mockOnSave = jest.fn()
  const mockOnCancel = jest.fn()

  const mockQuestion = {
    id: 1,
    question: 'What is the law?',
    reference_answers: ['The law is a system of rules', 'Laws govern society'],
    context: 'Legal system basics',
  }

  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('Rendering', () => {
    it('renders modal when isOpen is true', () => {
      render(
        <QuestionEditModal
          isOpen={true}
          question={mockQuestion}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      expect(screen.getByTestId('question-edit-modal')).toBeInTheDocument()
      expect(screen.getByText('Edit Question #1')).toBeInTheDocument()
    })

    it('does not render modal when isOpen is false', () => {
      render(
        <QuestionEditModal
          isOpen={false}
          question={mockQuestion}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      expect(
        screen.queryByTestId('question-edit-modal')
      ).not.toBeInTheDocument()
    })

    it('populates form with question data', () => {
      render(
        <QuestionEditModal
          isOpen={true}
          question={mockQuestion}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      expect(screen.getByDisplayValue('What is the law?')).toBeInTheDocument()
      expect(
        screen.getByDisplayValue('The law is a system of rules')
      ).toBeInTheDocument()
      expect(
        screen.getByDisplayValue('Laws govern society')
      ).toBeInTheDocument()
      expect(
        screen.getByDisplayValue('Legal system basics')
      ).toBeInTheDocument()
    })

    it('handles question without context', () => {
      const questionWithoutContext = {
        ...mockQuestion,
        context: undefined,
      }

      render(
        <QuestionEditModal
          isOpen={true}
          question={questionWithoutContext}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      const contextInput = screen.getByPlaceholderText(
        'Enter additional context...'
      )
      expect(contextInput).toHaveValue('')
    })

    it('handles question with empty reference answers array', () => {
      const questionWithoutAnswers = {
        ...mockQuestion,
        reference_answers: [],
      }

      render(
        <QuestionEditModal
          isOpen={true}
          question={questionWithoutAnswers}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      // Should have at least one empty answer field
      expect(
        screen.getByPlaceholderText('Reference answer 1...')
      ).toBeInTheDocument()
    })

    it('updates form when question prop changes', () => {
      const { rerender } = render(
        <QuestionEditModal
          isOpen={true}
          question={mockQuestion}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      expect(screen.getByDisplayValue('What is the law?')).toBeInTheDocument()

      const newQuestion = {
        ...mockQuestion,
        question: 'What is justice?',
      }

      rerender(
        <QuestionEditModal
          isOpen={true}
          question={newQuestion}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      expect(screen.getByDisplayValue('What is justice?')).toBeInTheDocument()
    })
  })

  describe('Question Editing', () => {
    it('allows editing question text', async () => {
      const user = userEvent.setup()
      render(
        <QuestionEditModal
          isOpen={true}
          question={mockQuestion}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      const questionInput = screen.getByTestId('question-input')
      await user.clear(questionInput)
      await user.type(questionInput, 'Updated question text')

      expect(questionInput).toHaveValue('Updated question text')
    })

    it('allows editing context', async () => {
      const user = userEvent.setup()
      render(
        <QuestionEditModal
          isOpen={true}
          question={mockQuestion}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      const contextInput = screen.getByDisplayValue('Legal system basics')
      await user.clear(contextInput)
      await user.type(contextInput, 'Updated context')

      expect(contextInput).toHaveValue('Updated context')
    })

    it('allows editing reference answers', async () => {
      const user = userEvent.setup()
      render(
        <QuestionEditModal
          isOpen={true}
          question={mockQuestion}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      const firstAnswer = screen.getByTestId('reference-answer-0')
      await user.clear(firstAnswer)
      await user.type(firstAnswer, 'Updated answer')

      expect(firstAnswer).toHaveValue('Updated answer')
    })
  })

  describe('Reference Answer Management', () => {
    it('allows adding new reference answers', async () => {
      const user = userEvent.setup()
      render(
        <QuestionEditModal
          isOpen={true}
          question={mockQuestion}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      expect(screen.getAllByPlaceholderText(/Reference answer/)).toHaveLength(2)

      const addButton = screen.getByText('Add Answer')
      await user.click(addButton)

      expect(screen.getAllByPlaceholderText(/Reference answer/)).toHaveLength(3)
      expect(
        screen.getByPlaceholderText('Reference answer 3...')
      ).toBeInTheDocument()
    })

    it('allows removing reference answers when more than one exists', async () => {
      const user = userEvent.setup()
      render(
        <QuestionEditModal
          isOpen={true}
          question={mockQuestion}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      expect(screen.getAllByPlaceholderText(/Reference answer/)).toHaveLength(2)

      const removeButtons = screen.getAllByTitle('Remove answer')
      await user.click(removeButtons[1])

      expect(screen.getAllByPlaceholderText(/Reference answer/)).toHaveLength(1)
    })

    it('does not show remove button when only one answer exists', async () => {
      const user = userEvent.setup()
      const questionWithOneAnswer = {
        ...mockQuestion,
        reference_answers: ['Single answer'],
      }

      render(
        <QuestionEditModal
          isOpen={true}
          question={questionWithOneAnswer}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      const removeButton = screen.queryByTitle('Remove answer')
      expect(removeButton).not.toBeInTheDocument()
    })

    it('prevents removing the last answer', async () => {
      const user = userEvent.setup()
      render(
        <QuestionEditModal
          isOpen={true}
          question={mockQuestion}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      // Remove first answer
      const removeButtons = screen.getAllByTitle('Remove answer')
      await user.click(removeButtons[0])

      expect(screen.getAllByPlaceholderText(/Reference answer/)).toHaveLength(1)

      // Try to remove the last answer - button should not be present
      const remainingRemoveButton = screen.queryByTitle('Remove answer')
      expect(remainingRemoveButton).not.toBeInTheDocument()
    })
  })

  describe('Validation', () => {
    it('shows error when question is empty', async () => {
      const user = userEvent.setup()
      render(
        <QuestionEditModal
          isOpen={true}
          question={mockQuestion}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      const questionInput = screen.getByTestId('question-input')
      await user.clear(questionInput)

      const saveButton = screen.getByTestId('save-question-button')
      await user.click(saveButton)

      await waitFor(() => {
        expect(screen.getByText('Question is required')).toBeInTheDocument()
      })

      expect(mockOnSave).not.toHaveBeenCalled()
    })

    it('shows error when all reference answers are empty', async () => {
      const user = userEvent.setup()
      render(
        <QuestionEditModal
          isOpen={true}
          question={mockQuestion}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      const answers = screen.getAllByTestId(/reference-answer-/)
      for (const answer of answers) {
        await user.clear(answer)
      }

      const saveButton = screen.getByTestId('save-question-button')
      await user.click(saveButton)

      await waitFor(() => {
        expect(
          screen.getByText('At least one reference answer is required')
        ).toBeInTheDocument()
      })

      expect(mockOnSave).not.toHaveBeenCalled()
    })

    it('allows saving when validation passes', async () => {
      const user = userEvent.setup()
      render(
        <QuestionEditModal
          isOpen={true}
          question={mockQuestion}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      const saveButton = screen.getByTestId('save-question-button')
      await user.click(saveButton)

      expect(mockOnSave).toHaveBeenCalledWith({
        question: 'What is the law?',
        reference_answers: [
          'The law is a system of rules',
          'Laws govern society',
        ],
        context: 'Legal system basics',
      })
    })

    it('filters out empty answers when saving', async () => {
      const user = userEvent.setup()
      render(
        <QuestionEditModal
          isOpen={true}
          question={mockQuestion}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      // Add a new empty answer
      const addButton = screen.getByText('Add Answer')
      await user.click(addButton)

      const saveButton = screen.getByTestId('save-question-button')
      await user.click(saveButton)

      expect(mockOnSave).toHaveBeenCalledWith({
        question: 'What is the law?',
        reference_answers: [
          'The law is a system of rules',
          'Laws govern society',
        ],
        context: 'Legal system basics',
      })
    })

    it('trims whitespace from fields when saving', async () => {
      const user = userEvent.setup()
      render(
        <QuestionEditModal
          isOpen={true}
          question={mockQuestion}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      const questionInput = screen.getByTestId('question-input')
      await user.clear(questionInput)
      await user.type(questionInput, '  Trimmed question  ')

      const contextInput = screen.getByDisplayValue('Legal system basics')
      await user.clear(contextInput)
      await user.type(contextInput, '  Trimmed context  ')

      const saveButton = screen.getByTestId('save-question-button')
      await user.click(saveButton)

      expect(mockOnSave).toHaveBeenCalledWith({
        question: 'Trimmed question',
        reference_answers: [
          'The law is a system of rules',
          'Laws govern society',
        ],
        context: 'Trimmed context',
      })
    })

    it('omits context when empty', async () => {
      const user = userEvent.setup()
      render(
        <QuestionEditModal
          isOpen={true}
          question={mockQuestion}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      const contextInput = screen.getByDisplayValue('Legal system basics')
      await user.clear(contextInput)

      const saveButton = screen.getByTestId('save-question-button')
      await user.click(saveButton)

      expect(mockOnSave).toHaveBeenCalledWith({
        question: 'What is the law?',
        reference_answers: [
          'The law is a system of rules',
          'Laws govern society',
        ],
        context: undefined,
      })
    })

    it('accepts whitespace-only answers as empty', async () => {
      const user = userEvent.setup()
      render(
        <QuestionEditModal
          isOpen={true}
          question={mockQuestion}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      const firstAnswer = screen.getByTestId('reference-answer-0')
      await user.clear(firstAnswer)
      await user.type(firstAnswer, '   ')

      const saveButton = screen.getByTestId('save-question-button')
      await user.click(saveButton)

      expect(mockOnSave).toHaveBeenCalledWith({
        question: 'What is the law?',
        reference_answers: ['Laws govern society'],
        context: 'Legal system basics',
      })
    })
  })

  describe('Modal Actions', () => {
    it('calls onCancel when cancel button is clicked', async () => {
      const user = userEvent.setup()
      render(
        <QuestionEditModal
          isOpen={true}
          question={mockQuestion}
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
        <QuestionEditModal
          isOpen={true}
          question={mockQuestion}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      const closeButton = screen.getByRole('button', { name: '' })
      await user.click(closeButton)

      expect(mockOnCancel).toHaveBeenCalled()
    })

    it('displays correct button text', () => {
      render(
        <QuestionEditModal
          isOpen={true}
          question={mockQuestion}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      expect(screen.getByText('Save Changes')).toBeInTheDocument()
      expect(screen.getByText('Cancel')).toBeInTheDocument()
    })
  })

  describe('Edge Cases', () => {
    it('handles null question gracefully', () => {
      render(
        <QuestionEditModal
          isOpen={true}
          question={null}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      expect(screen.getByTestId('question-edit-modal')).toBeInTheDocument()
    })

    it('resets form when modal is reopened', () => {
      const { rerender } = render(
        <QuestionEditModal
          isOpen={true}
          question={mockQuestion}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      expect(screen.getByDisplayValue('What is the law?')).toBeInTheDocument()

      // Close modal
      rerender(
        <QuestionEditModal
          isOpen={false}
          question={mockQuestion}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      // Reopen with new question
      const newQuestion = {
        id: 2,
        question: 'New question',
        reference_answers: ['New answer'],
      }

      rerender(
        <QuestionEditModal
          isOpen={true}
          question={newQuestion}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      expect(screen.getByDisplayValue('New question')).toBeInTheDocument()
      expect(screen.getByDisplayValue('New answer')).toBeInTheDocument()
    })

    it('clears errors when modal is reopened', async () => {
      const user = userEvent.setup()
      const { rerender } = render(
        <QuestionEditModal
          isOpen={true}
          question={mockQuestion}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      // Create validation error
      const questionInput = screen.getByTestId('question-input')
      await user.clear(questionInput)

      const saveButton = screen.getByTestId('save-question-button')
      await user.click(saveButton)

      await waitFor(() => {
        expect(screen.getByText('Question is required')).toBeInTheDocument()
      })

      // Close and reopen modal
      rerender(
        <QuestionEditModal
          isOpen={false}
          question={mockQuestion}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      rerender(
        <QuestionEditModal
          isOpen={true}
          question={mockQuestion}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      expect(screen.queryByText('Question is required')).not.toBeInTheDocument()
    })

    it('handles question without id', () => {
      const questionWithoutId = {
        ...mockQuestion,
        id: undefined,
      } as any

      render(
        <QuestionEditModal
          isOpen={true}
          question={questionWithoutId}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      // Should still render, title without id
      expect(screen.getByText(/Edit Question/)).toBeInTheDocument()
    })
  })

  describe('Form State Management', () => {
    it('maintains separate state for each answer', async () => {
      const user = userEvent.setup()
      render(
        <QuestionEditModal
          isOpen={true}
          question={mockQuestion}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      const firstAnswer = screen.getByTestId('reference-answer-0')
      const secondAnswer = screen.getByTestId('reference-answer-1')

      await user.clear(firstAnswer)
      await user.type(firstAnswer, 'Updated first answer')

      await user.clear(secondAnswer)
      await user.type(secondAnswer, 'Updated second answer')

      expect(firstAnswer).toHaveValue('Updated first answer')
      expect(secondAnswer).toHaveValue('Updated second answer')
    })

    it('updates answer indices correctly after removal', async () => {
      const user = userEvent.setup()
      render(
        <QuestionEditModal
          isOpen={true}
          question={mockQuestion}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      // Add third answer
      const addButton = screen.getByText('Add Answer')
      await user.click(addButton)

      const thirdAnswer = screen.getByTestId('reference-answer-2')
      await user.type(thirdAnswer, 'Third answer')

      // Remove middle answer
      const removeButtons = screen.getAllByTitle('Remove answer')
      await user.click(removeButtons[1])

      // Check that indices are correct
      expect(screen.getByTestId('reference-answer-0')).toBeInTheDocument()
      expect(screen.getByTestId('reference-answer-1')).toBeInTheDocument()
      expect(screen.queryByTestId('reference-answer-2')).not.toBeInTheDocument()
    })
  })
})

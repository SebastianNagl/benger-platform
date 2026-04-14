/**
 * @jest-environment jsdom
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QuestionCard } from '../tasks/QuestionCard'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, params?: any) => {
      const translations: Record<string, string> = {
        'tasks.questionCard.questionId': `Question ${params?.id || ''}`,
        'tasks.questionCard.mcqId': `MCQ ${params?.id || ''}`,
        'tasks.questionCard.edit': 'Edit',
        'tasks.questionCard.delete': 'Delete',
        'tasks.questionCard.save': 'Save',
        'tasks.questionCard.cancel': 'Cancel',
        'tasks.questionCard.collapse': 'Collapse',
        'tasks.questionCard.expand': 'Expand',
        'tasks.questionCard.caseOptional': 'Case (Optional)',
        'tasks.questionCard.question': 'Question',
        'tasks.questionCard.referenceAnswer': 'Reference Answer',
        'tasks.questionCard.answer': 'Answer',
        'tasks.questionCard.reasoning': 'Reasoning',
        'tasks.questionCard.contextOptional': 'Context (Optional)',
        'tasks.questionCard.answerOptions': 'Answer Options',
        'tasks.questionCard.placeholderCase': 'Case background, case, or relevant details...',
        'tasks.questionCard.placeholderQuestion': 'Enter your question here...',
        'tasks.questionCard.placeholderExpectedAnswer': 'Enter the expected answer...',
        'tasks.questionCard.placeholderMcq': 'Enter your multiple choice question here...',
        'tasks.questionCard.placeholderContext': 'Additional case or background information (optional)...',
        'tasks.questionCard.placeholderLegalCase': 'Case background, relevant precedents, or case...',
        'tasks.questionCard.placeholderLegalQuestion': 'Enter the legal question to be analyzed...',
        'tasks.questionCard.placeholderLegalAnswer': 'Provide the expected answer to the legal question...',
        'tasks.questionCard.placeholderReasoning': 'Provide detailed reasoning for the decision...',
        'tasks.questionCard.selectCorrectTooltip': 'Select the radio button for the correct reference answer',
        'tasks.questionCard.optionPlaceholder': `Option ${params?.option || ''}`,
        'tasks.questionCard.answerConfiguration': 'Answer Configuration:',
        'tasks.questionCard.answerConfigHelp': 'QAR tasks always use free text input for detailed reasoning',
        'tasks.questionCard.caseLabel': 'Case:',
        'tasks.questionCard.questionLabel': 'Question:',
        'tasks.questionCard.referenceAnswerLabel': 'Reference Answer:',
        'tasks.questionCard.contextLabel': 'Context:',
        'tasks.questionCard.optionsLabel': 'Options:',
        'tasks.questionCard.answerLabel': 'Answer:',
        'tasks.questionCard.reasoningLabel': 'Reasoning:',
        'tasks.questionCard.questionPreview': 'Question (preview):',
        'tasks.questionCard.answerPreview': 'Answer (preview):',
        'tasks.questionCard.reasoningPreview': 'Reasoning (preview):',
        'tasks.questionCard.noQuestionText': 'No question text',
        'tasks.questionCard.noReferenceAnswer': 'No reference answer',
        'tasks.questionCard.noAnswerProvided': 'No answer provided',
        'tasks.questionCard.noReasoningProvided': 'No reasoning provided',
        'tasks.questionCard.noOption': `No option ${params?.option || ''}`,
        'tasks.questionCard.correct': 'Correct',
      }
      return translations[key] || key
    },
    locale: 'en',
    setLocale: jest.fn(),
  }),
}))

const mockQAQuestion = {
  id: 'test-question-1',
  question: 'What is the capital of Germany?',
  reference_answer: 'Berlin',
}

const mockQARQuestion = {
  id: 'test-question-2',
  question: 'Analyze this legal case.',
  reference_answer: 'The defendant is liable under §823 BGB.',
  reasoning: 'The reasoning is based on tort law principles.',
  case_name: 'Test Legal Case',
  fall: 'Case Study 1',
  binary_solution: 'Yes',
}

const mockOnUpdate = jest.fn()
const mockOnDelete = jest.fn()
const mockOnToggleExpanded = jest.fn()

describe('QuestionCard', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('QA Task Type', () => {
    it('renders QA question and answer correctly', async () => {
      render(
        <QuestionCard
          question={mockQAQuestion}
          taskType="qa"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
        />
      )

      expect(
        screen.getByText('What is the capital of Germany?')
      ).toBeInTheDocument()
      expect(screen.getByText('Berlin')).toBeInTheDocument()
      expect(screen.getByText('Question test-question-1')).toBeInTheDocument()
    })

    it('shows delete, cancel, and save buttons in edit mode', async () => {
      render(
        <QuestionCard
          question={mockQAQuestion}
          taskType="qa"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
        />
      )

      // Component starts in edit mode, so Edit button is not visible
      expect(
        screen.queryByRole('button', { name: /edit/i })
      ).not.toBeInTheDocument()
      expect(
        screen.getByRole('button', { name: /delete/i })
      ).toBeInTheDocument()
      expect(
        screen.getByRole('button', { name: /cancel/i })
      ).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /save/i })).toBeInTheDocument()
    })

    it('handles delete action', async () => {
      const user = userEvent.setup()
      render(
        <QuestionCard
          question={mockQAQuestion}
          taskType="qa"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
        />
      )

      const deleteButton = screen.getByRole('button', { name: /delete/i })
      await user.click(deleteButton)

      expect(mockOnDelete).toHaveBeenCalledWith('test-question-1')
    })

    it('starts in edit mode with form inputs visible', async () => {
      render(
        <QuestionCard
          question={mockQAQuestion}
          taskType="qa"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
        />
      )

      // Component starts in edit mode, so form inputs should be visible
      expect(
        screen.getByDisplayValue('What is the capital of Germany?')
      ).toBeInTheDocument()
      expect(screen.getByDisplayValue('Berlin')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /save/i })).toBeInTheDocument()
      expect(
        screen.getByRole('button', { name: /cancel/i })
      ).toBeInTheDocument()
    })

    it('allows editing question text', async () => {
      const user = userEvent.setup()
      render(
        <QuestionCard
          question={mockQAQuestion}
          taskType="qa"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
        />
      )

      // Component starts in edit mode, so we can directly edit
      const questionInput = screen.getByDisplayValue(
        'What is the capital of Germany?'
      )
      await user.clear(questionInput)
      await user.type(questionInput, 'What is the largest city in Germany?')

      expect(questionInput).toHaveValue('What is the largest city in Germany?')
    })

    it('saves changes on form submission', async () => {
      const user = userEvent.setup()
      render(
        <QuestionCard
          question={mockQAQuestion}
          taskType="qa"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
        />
      )

      // Component starts in edit mode already

      const questionInput = screen.getByDisplayValue(
        'What is the capital of Germany?'
      )
      const answerInput = screen.getByDisplayValue('Berlin')

      await user.clear(questionInput)
      await user.type(questionInput, 'Updated question?')
      await user.clear(answerInput)
      await user.type(answerInput, 'Updated answer')

      const saveButton = screen.getByRole('button', { name: /save/i })
      await user.click(saveButton)

      expect(mockOnUpdate).toHaveBeenCalledWith({
        ...mockQAQuestion,
        question: 'Updated question?',
        reference_answer: 'Updated answer',
      })
    })

    it('cancels editing and resets to original values', async () => {
      const user = userEvent.setup()
      render(
        <QuestionCard
          question={mockQAQuestion}
          taskType="qa"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
        />
      )

      // Component starts in edit mode already
      const questionInput = screen.getByDisplayValue(
        'What is the capital of Germany?'
      )
      await user.clear(questionInput)
      await user.type(questionInput, 'This should not be saved')

      const cancelButton = screen.getByRole('button', { name: /cancel/i })
      await user.click(cancelButton)

      // Component has auto-save, so onUpdate will be called during typing
      expect(mockOnUpdate).toHaveBeenCalled()
      // After cancel, should exit edit mode and show original text as read-only
      expect(
        screen.getByText('What is the capital of Germany?')
      ).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /edit/i })).toBeInTheDocument()
    })
  })

  describe('QA Reasoning Task Type', () => {
    it('renders QAR question correctly in edit mode', async () => {
      render(
        <QuestionCard
          question={mockQARQuestion}
          taskType="qa_reasoning"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
          isExpanded={false}
          onToggleExpanded={mockOnToggleExpanded}
        />
      )

      // Component starts in edit mode, so form fields should be visible
      expect(
        screen.getByDisplayValue('Analyze this legal case.')
      ).toBeInTheDocument()
      expect(
        screen.getByDisplayValue('The defendant is liable under §823 BGB.')
      ).toBeInTheDocument()
      expect(
        screen.getByRole('button', { name: /delete/i })
      ).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /save/i })).toBeInTheDocument()
    })

    it('hides expand/collapse buttons in edit mode', async () => {
      render(
        <QuestionCard
          question={mockQARQuestion}
          taskType="qa_reasoning"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
          isExpanded={false}
          onToggleExpanded={mockOnToggleExpanded}
        />
      )

      // Component starts in edit mode, so expand/collapse buttons should not be visible
      expect(
        screen.queryByRole('button', { name: /expand/i })
      ).not.toBeInTheDocument()
      expect(
        screen.queryByRole('button', { name: /collapse/i })
      ).not.toBeInTheDocument()
    })

    it('shows form fields in edit mode regardless of expanded state', async () => {
      render(
        <QuestionCard
          question={mockQARQuestion}
          taskType="qa_reasoning"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
          isExpanded={true}
          onToggleExpanded={mockOnToggleExpanded}
        />
      )

      // In edit mode, form fields should be visible regardless of expanded state
      expect(
        screen.getByDisplayValue('Analyze this legal case.')
      ).toBeInTheDocument()
      expect(
        screen.getByDisplayValue('The defendant is liable under §823 BGB.')
      ).toBeInTheDocument()
    })
  })

  describe('Form Labels and Accessibility', () => {
    it('has proper form labels in edit mode', async () => {
      const user = userEvent.setup()
      render(
        <QuestionCard
          question={mockQAQuestion}
          taskType="qa"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
        />
      )

      // Component starts in edit mode already

      // Check for proper labels - be more specific
      expect(screen.getByText('Question')).toBeInTheDocument()
      expect(screen.getByText('Reference Answer')).toBeInTheDocument()
    })

    it('supports keyboard navigation in forms', async () => {
      const user = userEvent.setup()
      render(
        <QuestionCard
          question={mockQAQuestion}
          taskType="qa"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
        />
      )

      // Component starts in edit mode already

      const questionInput = screen.getByDisplayValue(
        'What is the capital of Germany?'
      )
      await user.click(questionInput)
      await user.keyboard('{Tab}')

      const answerInput = screen.getByDisplayValue('Berlin')
      expect(answerInput).toHaveFocus()
    })
  })

  describe('Edge Cases', () => {
    it('handles empty question data gracefully', () => {
      const emptyQuestion = {
        id: 'empty-question',
        question: '',
        reference_answer: '',
      }

      render(
        <QuestionCard
          question={emptyQuestion}
          taskType="qa"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
        />
      )

      // In edit mode, empty values show as empty input fields, not placeholder text
      const questionInput = screen.getByPlaceholderText(
        'Enter your question here...'
      )
      const answerInput = screen.getByPlaceholderText(
        'Enter the expected answer...'
      )

      expect(questionInput).toHaveValue('')
      expect(answerInput).toHaveValue('')
      expect(questionInput).toBeInTheDocument()
      expect(answerInput).toBeInTheDocument()
    })

    it('handles missing optional props for QAR', () => {
      const minimalQARQuestion = {
        id: 'minimal-qar',
        question: 'Basic question',
      }

      render(
        <QuestionCard
          question={minimalQARQuestion}
          taskType="qa_reasoning"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
        />
      )

      expect(screen.getByText('Question minimal-qar')).toBeInTheDocument()
    })
  })
})

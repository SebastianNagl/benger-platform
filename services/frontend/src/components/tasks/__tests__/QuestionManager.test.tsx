/**
 * Tests for QuestionManager component
 * Target: 90%+ coverage (currently at 16%)
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QuestionData } from '../QuestionCard'
import { QuestionManager, questionsToJson } from '../QuestionManager'

// Mock the Button component
jest.mock('@/components/shared/Button', () => ({
  Button: ({ children, onClick, className, disabled, type, ...props }: any) => (
    <button
      onClick={onClick}
      className={className}
      disabled={disabled}
      type={type}
      {...props}
    >
      {children}
    </button>
  ),
}))

// Mock QuestionCard component
jest.mock('../QuestionCard', () => ({
  QuestionCard: ({
    question,
    onUpdate,
    onDelete,
    onToggleExpanded,
    isExpanded,
  }: any) => (
    <div data-testid={`question-card-${question.id}`}>
      <span>{question.question || 'Empty question'}</span>
      <button onClick={() => onUpdate({ ...question, question: 'Updated' })}>
        Update
      </button>
      <button onClick={() => onDelete(question.id)}>Delete</button>
      {onToggleExpanded && (
        <button onClick={() => onToggleExpanded(question.id)}>
          {isExpanded ? 'Collapse' : 'Expand'}
        </button>
      )}
    </div>
  ),
}))

describe('QuestionManager', () => {
  const mockOnQuestionsChange = jest.fn()

  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('Rendering - QA Task Type', () => {
    it('renders empty state for QA tasks', () => {
      render(
        <QuestionManager
          taskType="qa"
          questions={[]}
          onQuestionsChange={mockOnQuestionsChange}
        />
      )

      expect(screen.getByText('Questions (0)')).toBeInTheDocument()
      expect(
        screen.getByText('Add simple question-answer pairs')
      ).toBeInTheDocument()
      expect(screen.getByText('No questions yet')).toBeInTheDocument()
      expect(
        screen.getByText('Add your first question-answer pair to get started.')
      ).toBeInTheDocument()
    })

    it('renders questions for QA task type', () => {
      const questions: QuestionData[] = [
        {
          id: '1',
          question: 'What is the law?',
          reference_answer: 'A system of rules',
          case: 'Legal basics',
        },
      ]

      render(
        <QuestionManager
          taskType="qa"
          questions={questions}
          onQuestionsChange={mockOnQuestionsChange}
        />
      )

      expect(screen.getByText('Questions (1)')).toBeInTheDocument()
      expect(screen.getByTestId('question-card-1')).toBeInTheDocument()
    })

    it('does not show expand/collapse controls for QA tasks', () => {
      const questions: QuestionData[] = [
        { id: '1', question: 'Test', reference_answer: 'Answer', case: '' },
      ]

      render(
        <QuestionManager
          taskType="qa"
          questions={questions}
          onQuestionsChange={mockOnQuestionsChange}
        />
      )

      expect(screen.queryByText('Expand All')).not.toBeInTheDocument()
      expect(screen.queryByText('Collapse All')).not.toBeInTheDocument()
    })
  })

  describe('Rendering - QAR Task Type', () => {
    it('renders empty state for QAR tasks', () => {
      render(
        <QuestionManager
          taskType="qa_reasoning"
          questions={[]}
          onQuestionsChange={mockOnQuestionsChange}
        />
      )

      expect(
        screen.getByText('Add questions with reasoning')
      ).toBeInTheDocument()
    })

    it('renders questions for QAR task type', () => {
      const questions: QuestionData[] = [
        {
          id: '1',
          question: 'Legal question',
          reference_answer: 'Legal answer',
          reasoning: 'Legal reasoning',
          case: 'Case info',
        },
      ]

      render(
        <QuestionManager
          taskType="qa_reasoning"
          questions={questions}
          onQuestionsChange={mockOnQuestionsChange}
        />
      )

      expect(screen.getByTestId('question-card-1')).toBeInTheDocument()
    })

    it('shows expand/collapse controls for QAR tasks with questions', () => {
      const questions: QuestionData[] = [
        {
          id: '1',
          question: 'Test',
          reference_answer: 'Answer',
          reasoning: 'Reasoning',
          case: '',
        },
      ]

      render(
        <QuestionManager
          taskType="qa_reasoning"
          questions={questions}
          onQuestionsChange={mockOnQuestionsChange}
        />
      )

      expect(screen.getByText('Expand All')).toBeInTheDocument()
      expect(screen.getByText('Collapse All')).toBeInTheDocument()
    })

    it('does not show expand/collapse controls when no questions exist', () => {
      render(
        <QuestionManager
          taskType="qa_reasoning"
          questions={[]}
          onQuestionsChange={mockOnQuestionsChange}
        />
      )

      expect(screen.queryByText('Expand All')).not.toBeInTheDocument()
      expect(screen.queryByText('Collapse All')).not.toBeInTheDocument()
    })
  })

  describe('Rendering - Multiple Choice Task Type', () => {
    it('renders empty state for multiple choice tasks', () => {
      render(
        <QuestionManager
          taskType="multiple_choice"
          questions={[]}
          onQuestionsChange={mockOnQuestionsChange}
        />
      )

      expect(
        screen.getByText('Add multiple choice questions with 4 options')
      ).toBeInTheDocument()
    })

    it('renders questions for multiple choice task type', () => {
      const questions: QuestionData[] = [
        {
          id: '1',
          question: 'Which is correct?',
          choice_a: 'Option A',
          choice_b: 'Option B',
          choice_c: 'Option C',
          choice_d: 'Option D',
          correct_answer: 'a',
          case: '',
        },
      ]

      render(
        <QuestionManager
          taskType="multiple_choice"
          questions={questions}
          onQuestionsChange={mockOnQuestionsChange}
        />
      )

      expect(screen.getByTestId('question-card-1')).toBeInTheDocument()
    })
  })

  describe('Adding Questions', () => {
    it('adds new QA question with correct structure', async () => {
      const user = userEvent.setup()
      render(
        <QuestionManager
          taskType="qa"
          questions={[]}
          onQuestionsChange={mockOnQuestionsChange}
        />
      )

      const addButton = screen.getByText('+ Add Question')
      await user.click(addButton)

      expect(mockOnQuestionsChange).toHaveBeenCalledWith([
        expect.objectContaining({
          id: expect.any(String),
          question: '',
          case: '',
          reference_answer: '',
        }),
      ])
    })

    it('adds new QAR question with correct structure', async () => {
      const user = userEvent.setup()
      render(
        <QuestionManager
          taskType="qa_reasoning"
          questions={[]}
          onQuestionsChange={mockOnQuestionsChange}
        />
      )

      const addButton = screen.getByText('+ Add Question')
      await user.click(addButton)

      expect(mockOnQuestionsChange).toHaveBeenCalledWith([
        expect.objectContaining({
          id: expect.any(String),
          question: '',
          case: '',
          reference_answer: '',
          reasoning: '',
          answer_config: {
            type: 'text',
            default_type: 'text',
          },
        }),
      ])
    })

    it('adds new multiple choice question with correct structure', async () => {
      const user = userEvent.setup()
      render(
        <QuestionManager
          taskType="multiple_choice"
          questions={[]}
          onQuestionsChange={mockOnQuestionsChange}
        />
      )

      const addButton = screen.getByText('+ Add Question')
      await user.click(addButton)

      expect(mockOnQuestionsChange).toHaveBeenCalledWith([
        expect.objectContaining({
          id: expect.any(String),
          question: '',
          case: '',
          choice_a: '',
          choice_b: '',
          choice_c: '',
          choice_d: '',
          correct_answer: 'a',
        }),
      ])
    })

    it('generates unique IDs for each question', async () => {
      const user = userEvent.setup()
      render(
        <QuestionManager
          taskType="qa"
          questions={[]}
          onQuestionsChange={mockOnQuestionsChange}
        />
      )

      const addButton = screen.getByText('+ Add Question')
      await user.click(addButton)
      await user.click(addButton)

      const calls = mockOnQuestionsChange.mock.calls
      // First click adds first question
      const firstId = calls[0][0][0].id
      // Second click adds second question to the list
      const secondCallQuestions = calls[1][0]
      const secondId = secondCallQuestions[secondCallQuestions.length - 1].id

      expect(firstId).not.toBe(secondId)
    })

    it('adds question from empty state button', async () => {
      const user = userEvent.setup()
      render(
        <QuestionManager
          taskType="qa"
          questions={[]}
          onQuestionsChange={mockOnQuestionsChange}
        />
      )

      const addButton = screen.getByText('Add Question')
      await user.click(addButton)

      expect(mockOnQuestionsChange).toHaveBeenCalled()
    })
  })

  describe('Updating Questions', () => {
    it('updates question when QuestionCard triggers update', async () => {
      const questions: QuestionData[] = [
        {
          id: '1',
          question: 'Original',
          reference_answer: 'Answer',
          case: '',
        },
      ]

      const user = userEvent.setup()
      render(
        <QuestionManager
          taskType="qa"
          questions={questions}
          onQuestionsChange={mockOnQuestionsChange}
        />
      )

      const updateButton = screen.getByText('Update')
      await user.click(updateButton)

      expect(mockOnQuestionsChange).toHaveBeenCalledWith([
        expect.objectContaining({
          id: '1',
          question: 'Updated',
        }),
      ])
    })

    it('only updates the specific question, not others', async () => {
      const questions: QuestionData[] = [
        {
          id: '1',
          question: 'First',
          reference_answer: 'Answer 1',
          case: '',
        },
        {
          id: '2',
          question: 'Second',
          reference_answer: 'Answer 2',
          case: '',
        },
      ]

      const user = userEvent.setup()
      render(
        <QuestionManager
          taskType="qa"
          questions={questions}
          onQuestionsChange={mockOnQuestionsChange}
        />
      )

      const updateButtons = screen.getAllByText('Update')
      await user.click(updateButtons[0])

      expect(mockOnQuestionsChange).toHaveBeenCalledWith([
        expect.objectContaining({ id: '1', question: 'Updated' }),
        expect.objectContaining({ id: '2', question: 'Second' }),
      ])
    })
  })

  describe('Deleting Questions', () => {
    it('deletes question when QuestionCard triggers delete', async () => {
      const questions: QuestionData[] = [
        {
          id: '1',
          question: 'To be deleted',
          reference_answer: 'Answer',
          case: '',
        },
      ]

      const user = userEvent.setup()
      render(
        <QuestionManager
          taskType="qa"
          questions={questions}
          onQuestionsChange={mockOnQuestionsChange}
        />
      )

      const deleteButton = screen.getByText('Delete')
      await user.click(deleteButton)

      expect(mockOnQuestionsChange).toHaveBeenCalledWith([])
    })

    it('deletes correct question when multiple exist', async () => {
      const questions: QuestionData[] = [
        {
          id: '1',
          question: 'First',
          reference_answer: 'Answer 1',
          case: '',
        },
        {
          id: '2',
          question: 'Second',
          reference_answer: 'Answer 2',
          case: '',
        },
        {
          id: '3',
          question: 'Third',
          reference_answer: 'Answer 3',
          case: '',
        },
      ]

      const user = userEvent.setup()
      render(
        <QuestionManager
          taskType="qa"
          questions={questions}
          onQuestionsChange={mockOnQuestionsChange}
        />
      )

      const deleteButtons = screen.getAllByText('Delete')
      await user.click(deleteButtons[1]) // Delete second question

      expect(mockOnQuestionsChange).toHaveBeenCalledWith([
        expect.objectContaining({ id: '1' }),
        expect.objectContaining({ id: '3' }),
      ])
    })

    it('removes question from expanded set when deleted', async () => {
      const questions: QuestionData[] = [
        {
          id: '1',
          question: 'Test',
          reference_answer: 'Answer',
          reasoning: 'Reasoning',
          case: '',
        },
      ]

      const user = userEvent.setup()
      render(
        <QuestionManager
          taskType="qa_reasoning"
          questions={questions}
          onQuestionsChange={mockOnQuestionsChange}
        />
      )

      // Expand the question
      const expandButton = screen.getByText('Expand')
      await user.click(expandButton)

      // Delete the question
      const deleteButton = screen.getByText('Delete')
      await user.click(deleteButton)

      expect(mockOnQuestionsChange).toHaveBeenCalledWith([])
    })
  })

  describe('Expand/Collapse Functionality', () => {
    it('expands all questions for QAR tasks', async () => {
      const questions: QuestionData[] = [
        {
          id: '1',
          question: 'First',
          reference_answer: 'Answer 1',
          reasoning: 'Reasoning 1',
          case: '',
        },
        {
          id: '2',
          question: 'Second',
          reference_answer: 'Answer 2',
          reasoning: 'Reasoning 2',
          case: '',
        },
      ]

      const user = userEvent.setup()
      render(
        <QuestionManager
          taskType="qa_reasoning"
          questions={questions}
          onQuestionsChange={mockOnQuestionsChange}
        />
      )

      const expandAllButton = screen.getByText('Expand All')
      await user.click(expandAllButton)

      // Both questions should show collapse button
      const collapseButtons = screen.getAllByText('Collapse')
      expect(collapseButtons).toHaveLength(2)
    })

    it('collapses all questions for QAR tasks', async () => {
      const questions: QuestionData[] = [
        {
          id: '1',
          question: 'First',
          reference_answer: 'Answer 1',
          reasoning: 'Reasoning 1',
          case: '',
        },
        {
          id: '2',
          question: 'Second',
          reference_answer: 'Answer 2',
          reasoning: 'Reasoning 2',
          case: '',
        },
      ]

      const user = userEvent.setup()
      render(
        <QuestionManager
          taskType="qa_reasoning"
          questions={questions}
          onQuestionsChange={mockOnQuestionsChange}
        />
      )

      // Expand all first
      const expandAllButton = screen.getByText('Expand All')
      await user.click(expandAllButton)

      // Then collapse all
      const collapseAllButton = screen.getByText('Collapse All')
      await user.click(collapseAllButton)

      // Both questions should show expand button
      const expandButtons = screen.getAllByText('Expand')
      expect(expandButtons).toHaveLength(2)
    })

    it('toggles individual question expansion', async () => {
      const questions: QuestionData[] = [
        {
          id: '1',
          question: 'Test',
          reference_answer: 'Answer',
          reasoning: 'Reasoning',
          case: '',
        },
      ]

      const user = userEvent.setup()
      render(
        <QuestionManager
          taskType="qa_reasoning"
          questions={questions}
          onQuestionsChange={mockOnQuestionsChange}
        />
      )

      const expandButton = screen.getByText('Expand')
      await user.click(expandButton)

      expect(screen.getByText('Collapse')).toBeInTheDocument()

      await user.click(screen.getByText('Collapse'))

      expect(screen.getByText('Expand')).toBeInTheDocument()
    })
  })

  describe('Question Count Display', () => {
    it('shows correct count with no questions', () => {
      render(
        <QuestionManager
          taskType="qa"
          questions={[]}
          onQuestionsChange={mockOnQuestionsChange}
        />
      )

      expect(screen.getByText('Questions (0)')).toBeInTheDocument()
    })

    it('shows correct count with one question', () => {
      const questions: QuestionData[] = [
        { id: '1', question: 'Test', reference_answer: 'Answer', case: '' },
      ]

      render(
        <QuestionManager
          taskType="qa"
          questions={questions}
          onQuestionsChange={mockOnQuestionsChange}
        />
      )

      expect(screen.getByText('Questions (1)')).toBeInTheDocument()
    })

    it('shows correct count with multiple questions', () => {
      const questions: QuestionData[] = [
        { id: '1', question: 'Test 1', reference_answer: 'Answer 1', case: '' },
        { id: '2', question: 'Test 2', reference_answer: 'Answer 2', case: '' },
        { id: '3', question: 'Test 3', reference_answer: 'Answer 3', case: '' },
      ]

      render(
        <QuestionManager
          taskType="qa"
          questions={questions}
          onQuestionsChange={mockOnQuestionsChange}
        />
      )

      expect(screen.getByText('Questions (3)')).toBeInTheDocument()
    })
  })

  describe('questionsToJson Helper Function', () => {
    it('converts QA questions to JSON format', () => {
      const questions: QuestionData[] = [
        {
          id: '1',
          question: 'Test question',
          reference_answer: 'Test answer',
          case: '',
        },
      ]

      const result = JSON.parse(questionsToJson(questions, 'qa'))

      expect(result).toEqual([
        {
          id: '1',
          question_data: {
            Frage: 'Test question',
            Antwort: 'Test answer',
          },
        },
      ])
    })

    it('converts QAR questions to JSON format', () => {
      const questions: QuestionData[] = [
        {
          id: '1',
          question: 'Test question',
          reference_answer: 'Test answer',
          reasoning: 'Test reasoning',
          case: '',
        },
      ]

      const result = JSON.parse(questionsToJson(questions, 'qa_reasoning'))

      expect(result).toEqual([
        {
          id: '1',
          question_data: {
            question: 'Test question',
            answer: 'Test answer',
            reasoning: 'Test reasoning',
          },
        },
      ])
    })

    it('converts multiple choice questions to JSON format', () => {
      const questions: QuestionData[] = [
        {
          id: '1',
          question: 'Test question',
          choice_a: 'Option A',
          choice_b: 'Option B',
          choice_c: 'Option C',
          choice_d: 'Option D',
          correct_answer: 'a',
          case: '',
        },
      ]

      const result = JSON.parse(questionsToJson(questions, 'multiple_choice'))

      expect(result).toEqual([
        {
          id: '1',
          question_data: {
            question: 'Test question',
            context: '',
            choice_a: 'Option A',
            choice_b: 'Option B',
            choice_c: 'Option C',
            choice_d: 'Option D',
            correct_answer: 'a',
          },
        },
      ])
    })

    it('includes context field for multiple choice questions', () => {
      const questions: QuestionData[] = [
        {
          id: '1',
          question: 'Test question',
          context: 'Test context',
          choice_a: 'A',
          choice_b: 'B',
          choice_c: 'C',
          choice_d: 'D',
          correct_answer: 'a',
          case: '',
        },
      ]

      const result = JSON.parse(questionsToJson(questions, 'multiple_choice'))

      expect(result[0].question_data.context).toBe('Test context')
    })

    it('uses empty string for missing context in multiple choice', () => {
      const questions: QuestionData[] = [
        {
          id: '1',
          question: 'Test',
          choice_a: 'A',
          choice_b: 'B',
          choice_c: 'C',
          choice_d: 'D',
          correct_answer: 'a',
          case: '',
        },
      ]

      const result = JSON.parse(questionsToJson(questions, 'multiple_choice'))

      expect(result[0].question_data.context).toBe('')
    })

    it('converts multiple questions correctly', () => {
      const questions: QuestionData[] = [
        { id: '1', question: 'Q1', reference_answer: 'A1', case: '' },
        { id: '2', question: 'Q2', reference_answer: 'A2', case: '' },
      ]

      const result = JSON.parse(questionsToJson(questions, 'qa'))

      expect(result).toHaveLength(2)
      expect(result[0].id).toBe('1')
      expect(result[1].id).toBe('2')
    })

    it('formats JSON with proper indentation', () => {
      const questions: QuestionData[] = [
        { id: '1', question: 'Test', reference_answer: 'Answer', case: '' },
      ]

      const result = questionsToJson(questions, 'qa')

      expect(result).toContain('\n')
      expect(result).toContain('  ')
    })
  })

  describe('Answer Configuration', () => {
    it('applies answer configuration to QAR questions', async () => {
      const user = userEvent.setup()
      const answerConfig = {
        answerType: 'radio' as const,
        answerChoices: ['Yes', 'No'],
        isApplied: true,
      }

      render(
        <QuestionManager
          taskType="qa_reasoning"
          questions={[]}
          onQuestionsChange={mockOnQuestionsChange}
          answerConfig={answerConfig}
        />
      )

      const addButton = screen.getByText('+ Add Question')
      await user.click(addButton)

      // QAR tasks should always use text type regardless of config
      expect(mockOnQuestionsChange).toHaveBeenCalledWith([
        expect.objectContaining({
          answer_config: {
            type: 'text',
            default_type: 'text',
          },
        }),
      ])
    })
  })
})

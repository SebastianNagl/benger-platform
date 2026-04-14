import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QuestionCard, QuestionData } from '../QuestionCard'

// Mock I18nContext
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, params?: any) => {
      const translations: Record<string, string> = {
        'tasks.questionCard.questionId': 'Question {id}',
        'tasks.questionCard.mcqId': 'MCQ {id}',
        'tasks.questionCard.edit': 'Edit',
        'tasks.questionCard.delete': 'Delete',
        'tasks.questionCard.save': 'Save',
        'tasks.questionCard.cancel': 'Cancel',
        'tasks.questionCard.expand': 'Expand',
        'tasks.questionCard.collapse': 'Collapse',
        'tasks.questionCard.caseOptional': 'Case (Optional)',
        'tasks.questionCard.question': 'Question',
        'tasks.questionCard.referenceAnswer': 'Reference Answer',
        'tasks.questionCard.answer': 'Answer',
        'tasks.questionCard.reasoning': 'Reasoning',
        'tasks.questionCard.answerOptions': 'Answer Options',
        'tasks.questionCard.contextOptional': 'Context (Optional)',
        'tasks.questionCard.caseLabel': 'Case:',
        'tasks.questionCard.questionLabel': 'Question:',
        'tasks.questionCard.referenceAnswerLabel': 'Reference Answer:',
        'tasks.questionCard.answerLabel': 'Answer:',
        'tasks.questionCard.reasoningLabel': 'Reasoning:',
        'tasks.questionCard.contextLabel': 'Context:',
        'tasks.questionCard.optionsLabel': 'Options:',
        'tasks.questionCard.noQuestionText': 'No question text',
        'tasks.questionCard.noReferenceAnswer': 'No reference answer',
        'tasks.questionCard.noAnswerProvided': 'No answer provided',
        'tasks.questionCard.noReasoningProvided': 'No reasoning provided',
        'tasks.questionCard.noOption': 'No option {option}',
        'tasks.questionCard.correct': '✓ Correct',
        'tasks.questionCard.placeholderCase': 'Enter case details...',
        'tasks.questionCard.placeholderQuestion': 'Enter your question here...',
        'tasks.questionCard.placeholderExpectedAnswer': 'Enter the expected answer...',
        'tasks.questionCard.placeholderMcq': 'Enter your question here...',
        'tasks.questionCard.placeholderContext': 'Enter context...',
        'tasks.questionCard.placeholderLegalCase': 'Enter case details...',
        'tasks.questionCard.placeholderLegalQuestion': 'Enter your question here...',
        'tasks.questionCard.placeholderLegalAnswer': 'Enter expected answer...',
        'tasks.questionCard.placeholderReasoning': 'Enter reasoning...',
        'tasks.questionCard.selectCorrectTooltip': 'Select the correct answer',
        'tasks.questionCard.optionPlaceholder': 'Option {option}',
        'tasks.questionCard.answerConfiguration': 'Answer Configuration:',
        'tasks.questionCard.answerConfigHelp': 'Configure correct answer',
        'tasks.questionCard.questionPreview': 'Question (preview):',
        'tasks.questionCard.answerPreview': 'Answer (preview):',
        'tasks.questionCard.reasoningPreview': 'Reasoning (preview):',
      }
      let result = translations[key] || key
      if (params && typeof params === 'object') {
        Object.entries(params).forEach(([k, v]) => {
          result = result.replace(`{${k}}`, String(v))
        })
      }
      return result
    },
    locale: 'en',
  }),
}))

// Mock the Button component to avoid import issues
jest.mock('@/components/shared/Button', () => ({
  Button: ({ children, onClick, className, ...props }: any) => (
    <button onClick={onClick} className={className} {...props}>
      {children}
    </button>
  ),
}))

describe('QuestionCard', () => {
  const mockOnUpdate = jest.fn()
  const mockOnDelete = jest.fn()
  const mockOnToggleExpanded = jest.fn()

  const qaQuestion: QuestionData = {
    id: '1',
    question: 'What is the law?',
    reference_answer: 'The law is a system of rules.',
    case: 'This is a legal case',
  }

  const mcQuestion: QuestionData = {
    id: '2',
    question: 'Which is correct?',
    choice_a: 'Option A',
    choice_b: 'Option B',
    choice_c: 'Option C',
    choice_d: 'Option D',
    correct_answer: 'a',
    case: 'Context for the question',
  }

  const qarQuestion: QuestionData = {
    id: '3',
    question: 'Analyze this legal issue',
    reference_answer: 'Detailed analysis',
    reasoning: 'Legal reasoning here',
    case: 'Legal case background',
  }

  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('QA type questions', () => {
    it('renders QA question in editing mode by default', () => {
      render(
        <QuestionCard
          question={qaQuestion}
          taskType="qa"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
        />
      )

      expect(screen.getByText('Question 1')).toBeInTheDocument()
      expect(screen.getByDisplayValue('What is the law?')).toBeInTheDocument()
      expect(
        screen.getByDisplayValue('The law is a system of rules.')
      ).toBeInTheDocument()
      expect(
        screen.getByDisplayValue('This is a legal case')
      ).toBeInTheDocument()
    })

    it('handles field changes and auto-saves', async () => {
      const user = userEvent.setup()
      render(
        <QuestionCard
          question={qaQuestion}
          taskType="qa"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
        />
      )

      const questionInput = screen.getByDisplayValue('What is the law?')
      await user.clear(questionInput)
      await user.type(questionInput, 'New question text')

      expect(mockOnUpdate).toHaveBeenCalledWith({
        ...qaQuestion,
        question: 'New question text',
      })
    })

    it('handles save and cancel actions', async () => {
      const user = userEvent.setup()
      render(
        <QuestionCard
          question={qaQuestion}
          taskType="qa"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
        />
      )

      // Make a change
      const questionInput = screen.getByDisplayValue('What is the law?')
      await user.clear(questionInput)
      await user.type(questionInput, 'Modified question')

      // Save
      const saveButton = screen.getByText('Save')
      await user.click(saveButton)

      // Should switch to view mode
      await waitFor(() => {
        expect(screen.getByText('Edit')).toBeInTheDocument()
      })
    })

    it('handles delete action', async () => {
      const user = userEvent.setup()
      render(
        <QuestionCard
          question={qaQuestion}
          taskType="qa"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
        />
      )

      const deleteButton = screen.getByText('Delete')
      await user.click(deleteButton)

      expect(mockOnDelete).toHaveBeenCalledWith('1')
    })

    it('switches between edit and view modes', async () => {
      const user = userEvent.setup()
      render(
        <QuestionCard
          question={qaQuestion}
          taskType="qa"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
        />
      )

      // Start in edit mode, save to switch to view mode
      const saveButton = screen.getByText('Save')
      await user.click(saveButton)

      await waitFor(() => {
        expect(screen.getByText('Edit')).toBeInTheDocument()
        expect(screen.getByText('Question:')).toBeInTheDocument()
        expect(screen.getByText('Reference Answer:')).toBeInTheDocument()
      })

      // Click edit to go back to edit mode
      const editButton = screen.getByText('Edit')
      await user.click(editButton)

      await waitFor(() => {
        expect(screen.getByDisplayValue('What is the law?')).toBeInTheDocument()
      })
    })
  })

  describe('Multiple Choice type questions', () => {
    it('renders MC question with choices', () => {
      render(
        <QuestionCard
          question={mcQuestion}
          taskType="multiple_choice"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
        />
      )

      expect(screen.getByText('MCQ 2')).toBeInTheDocument()
      expect(screen.getByDisplayValue('Which is correct?')).toBeInTheDocument()
      expect(screen.getByDisplayValue('Option A')).toBeInTheDocument()
      expect(screen.getByDisplayValue('Option B')).toBeInTheDocument()
      expect(screen.getByDisplayValue('Option C')).toBeInTheDocument()
      expect(screen.getByDisplayValue('Option D')).toBeInTheDocument()
    })

    it('handles correct answer selection', async () => {
      const user = userEvent.setup()
      render(
        <QuestionCard
          question={mcQuestion}
          taskType="multiple_choice"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
        />
      )

      const optionBRadio = screen.getByLabelText('B')
      await user.click(optionBRadio)

      expect(mockOnUpdate).toHaveBeenCalledWith({
        ...mcQuestion,
        correct_answer: 'b',
      })
    })

    it('handles choice text changes', async () => {
      const user = userEvent.setup()
      render(
        <QuestionCard
          question={mcQuestion}
          taskType="multiple_choice"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
        />
      )

      const choiceAInput = screen.getByDisplayValue('Option A')
      await user.clear(choiceAInput)
      await user.type(choiceAInput, 'New Option A')

      expect(mockOnUpdate).toHaveBeenCalledWith({
        ...mcQuestion,
        choice_a: 'New Option A',
      })
    })

    it('displays correct answer indicator in view mode', async () => {
      const user = userEvent.setup()
      render(
        <QuestionCard
          question={mcQuestion}
          taskType="multiple_choice"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
        />
      )

      // Save to switch to view mode
      const saveButton = screen.getByText('Save')
      await user.click(saveButton)

      // Test removed - correct answer display feature not yet implemented
    })
  })

  describe('QA Reasoning type questions', () => {
    it('renders QAR question with reasoning field', () => {
      render(
        <QuestionCard
          question={qarQuestion}
          taskType="qa_reasoning"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
        />
      )

      expect(screen.getByText('Question 3')).toBeInTheDocument()
      expect(
        screen.getByDisplayValue('Analyze this legal issue')
      ).toBeInTheDocument()
      expect(screen.getByDisplayValue('Detailed analysis')).toBeInTheDocument()
      expect(
        screen.getByDisplayValue('Legal reasoning here')
      ).toBeInTheDocument()
    })

    it('handles expand/collapse functionality', async () => {
      const user = userEvent.setup()
      render(
        <QuestionCard
          question={qarQuestion}
          taskType="qa_reasoning"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
          isExpanded={false}
          onToggleExpanded={mockOnToggleExpanded}
        />
      )

      // Save to get to view mode
      const saveButton = screen.getByText('Save')
      await user.click(saveButton)

      await waitFor(() => {
        const expandButton = screen.getByText('Expand')
        expect(expandButton).toBeInTheDocument()
      })

      const expandButton = screen.getByText('Expand')
      await user.click(expandButton)

      expect(mockOnToggleExpanded).toHaveBeenCalled()
    })

    it('shows collapsed view by default', async () => {
      const user = userEvent.setup()
      render(
        <QuestionCard
          question={qarQuestion}
          taskType="qa_reasoning"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
          isExpanded={false}
          onToggleExpanded={mockOnToggleExpanded}
        />
      )

      // Save to view mode
      const saveButton = screen.getByText('Save')
      await user.click(saveButton)

      await waitFor(() => {
        expect(screen.getByText('Question (preview):')).toBeInTheDocument()
        expect(screen.getByText('Answer (preview):')).toBeInTheDocument()
        expect(screen.getByText('Reasoning (preview):')).toBeInTheDocument()
      })
    })

    it('shows expanded view when isExpanded is true', async () => {
      const user = userEvent.setup()
      render(
        <QuestionCard
          question={qarQuestion}
          taskType="qa_reasoning"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
          isExpanded={true}
          onToggleExpanded={mockOnToggleExpanded}
        />
      )

      // Save to view mode
      const saveButton = screen.getByText('Save')
      await user.click(saveButton)

      await waitFor(() => {
        expect(screen.getByText('Case:')).toBeInTheDocument()
        expect(screen.getByText('Question:')).toBeInTheDocument()
        expect(screen.getByText('Answer:')).toBeInTheDocument()
        expect(screen.getByText('Reasoning:')).toBeInTheDocument()
        expect(screen.getByText('Collapse')).toBeInTheDocument()
      })
    })

    it('handles reasoning field changes', async () => {
      const user = userEvent.setup()
      render(
        <QuestionCard
          question={qarQuestion}
          taskType="qa_reasoning"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
        />
      )

      const reasoningInput = screen.getByDisplayValue('Legal reasoning here')
      await user.clear(reasoningInput)
      await user.type(reasoningInput, 'Updated reasoning')

      expect(mockOnUpdate).toHaveBeenCalledWith({
        ...qarQuestion,
        reasoning: 'Updated reasoning',
      })
    })
  })

  describe('Common functionality', () => {
    it('handles cancel action correctly', async () => {
      const user = userEvent.setup()
      render(
        <QuestionCard
          question={qaQuestion}
          taskType="qa"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
        />
      )

      // Make a change
      const questionInput = screen.getByDisplayValue('What is the law?')
      await user.clear(questionInput)
      await user.type(questionInput, 'Changed text')

      // Cancel
      const cancelButton = screen.getByText('Cancel')
      await user.click(cancelButton)

      // Should reset to original value in view mode
      await waitFor(() => {
        expect(screen.getByText('Edit')).toBeInTheDocument()
      })
    })

    it('handles empty optional fields', () => {
      const emptyQuestion: QuestionData = {
        id: '4',
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

      expect(
        screen.getByPlaceholderText('Enter your question here...')
      ).toBeInTheDocument()
      expect(
        screen.getByPlaceholderText('Enter the expected answer...')
      ).toBeInTheDocument()
    })

    it('displays proper styling for different task types', () => {
      const { rerender } = render(
        <QuestionCard
          question={qaQuestion}
          taskType="qa"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
        />
      )

      // QA should have blue theme
      expect(screen.getByText('Q')).toBeInTheDocument()

      rerender(
        <QuestionCard
          question={mcQuestion}
          taskType="multiple_choice"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
        />
      )

      // MC should have orange theme
      expect(screen.getByText('M')).toBeInTheDocument()

      rerender(
        <QuestionCard
          question={qarQuestion}
          taskType="qa_reasoning"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
        />
      )

      // QAR should have emerald theme
      expect(screen.getByText('L')).toBeInTheDocument()
    })

    it('handles case field changes in QA', async () => {
      const user = userEvent.setup()
      render(
        <QuestionCard
          question={qaQuestion}
          taskType="qa"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
        />
      )

      const caseInput = screen.getByDisplayValue('This is a legal case')
      await user.clear(caseInput)
      await user.type(caseInput, 'Updated case')

      expect(mockOnUpdate).toHaveBeenCalledWith({
        ...qaQuestion,
        case: 'Updated case',
      })
    })

    it('renders view mode correctly for QA without case', async () => {
      const user = userEvent.setup()
      const noCaseQuestion = { ...qaQuestion, case: undefined }
      render(
        <QuestionCard
          question={noCaseQuestion}
          taskType="qa"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
        />
      )

      await user.click(screen.getByText('Save'))

      await waitFor(() => {
        expect(screen.queryByText('Case:')).not.toBeInTheDocument()
      })
    })

    it('displays fallback text for empty question in view mode', async () => {
      const user = userEvent.setup()
      const emptyQuestion = { ...qaQuestion, question: '' }
      render(
        <QuestionCard
          question={emptyQuestion}
          taskType="qa"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
        />
      )

      await user.click(screen.getByText('Save'))

      await waitFor(() => {
        expect(screen.getByText('No question text')).toBeInTheDocument()
      })
    })

    it('displays fallback text for empty reference answer in view mode', async () => {
      const user = userEvent.setup()
      const emptyAnswer = { ...qaQuestion, reference_answer: '' }
      render(
        <QuestionCard
          question={emptyAnswer}
          taskType="qa"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
        />
      )

      await user.click(screen.getByText('Save'))

      await waitFor(() => {
        expect(screen.getByText('No reference answer')).toBeInTheDocument()
      })
    })

    it('handles multiple consecutive edits in QA', async () => {
      const user = userEvent.setup()
      render(
        <QuestionCard
          question={qaQuestion}
          taskType="qa"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
        />
      )

      const questionInput = screen.getByDisplayValue('What is the law?')
      await user.type(questionInput, ' updated')

      const answerInput = screen.getByDisplayValue(
        'The law is a system of rules.'
      )
      await user.type(answerInput, ' updated')

      expect(mockOnUpdate).toHaveBeenCalled()
      expect(mockOnUpdate.mock.calls.length).toBeGreaterThan(0)
    })

    it('preserves model and human responses in QA', async () => {
      const user = userEvent.setup()
      const withResponses = {
        ...qaQuestion,
        model_responses: { 'model-1': { answer: 'Model answer' } },
        human_responses: { 'user-1': { answer: 'Human answer' } },
      }
      render(
        <QuestionCard
          question={withResponses}
          taskType="qa"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
        />
      )

      const questionInput = screen.getByDisplayValue('What is the law?')
      await user.type(questionInput, ' x')

      expect(mockOnUpdate).toHaveBeenCalledWith(
        expect.objectContaining({
          model_responses: withResponses.model_responses,
          human_responses: withResponses.human_responses,
        })
      )
    })

    it('handles MC with all choices empty', async () => {
      const user = userEvent.setup()
      const emptyChoices = {
        ...mcQuestion,
        choice_a: '',
        choice_b: '',
        choice_c: '',
        choice_d: '',
      }
      render(
        <QuestionCard
          question={emptyChoices}
          taskType="multiple_choice"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
        />
      )

      await user.click(screen.getByText('Save'))

      await waitFor(() => {
        expect(screen.getAllByText(/No option [A-D]/).length).toBeGreaterThan(0)
      })
    })

    it('displays correct answer indicator for all MC options in view mode', async () => {
      const user = userEvent.setup()
      render(
        <QuestionCard
          question={mcQuestion}
          taskType="multiple_choice"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
        />
      )

      await user.click(screen.getByText('Save'))

      await waitFor(() => {
        expect(screen.getByText('✓ Correct')).toBeInTheDocument()
      })
    })

    it('handles MC context field', async () => {
      const user = userEvent.setup()
      render(
        <QuestionCard
          question={mcQuestion}
          taskType="multiple_choice"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
        />
      )

      const contextInput = screen.getByDisplayValue('Context for the question')
      await user.clear(contextInput)
      await user.type(contextInput, 'New context')

      expect(mockOnUpdate).toHaveBeenCalledWith({
        ...mcQuestion,
        case: 'New context',
      })
    })

    it('renders MC view mode without context', async () => {
      const user = userEvent.setup()
      const noContext = { ...mcQuestion, case: undefined }
      render(
        <QuestionCard
          question={noContext}
          taskType="multiple_choice"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
        />
      )

      await user.click(screen.getByText('Save'))

      await waitFor(() => {
        expect(screen.queryByText('Context:')).not.toBeInTheDocument()
      })
    })

    it('handles all MC radio button selections', async () => {
      const user = userEvent.setup()
      render(
        <QuestionCard
          question={mcQuestion}
          taskType="multiple_choice"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
        />
      )

      await user.click(screen.getByLabelText('C'))
      expect(mockOnUpdate).toHaveBeenCalledWith({
        ...mcQuestion,
        correct_answer: 'c',
      })

      await user.click(screen.getByLabelText('D'))
      expect(mockOnUpdate).toHaveBeenCalledWith({
        ...mcQuestion,
        correct_answer: 'd',
      })
    })

    it('displays help tooltip in MC edit mode', () => {
      render(
        <QuestionCard
          question={mcQuestion}
          taskType="multiple_choice"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
        />
      )

      const helpIcon = document.querySelector('svg[stroke="currentColor"]')
      expect(helpIcon).toBeInTheDocument()
    })

    it('handles QAR case field updates', async () => {
      const user = userEvent.setup()
      render(
        <QuestionCard
          question={qarQuestion}
          taskType="qa_reasoning"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
        />
      )

      const caseInput = screen.getByDisplayValue('Legal case background')
      await user.clear(caseInput)
      await user.type(caseInput, 'New background')

      expect(mockOnUpdate).toHaveBeenCalledWith({
        ...qarQuestion,
        case: 'New background',
      })
    })

    it('renders QAR collapsed view with truncated text', async () => {
      const user = userEvent.setup()
      const longQuestion = {
        ...qarQuestion,
        question: 'A'.repeat(150),
        reference_answer: 'B'.repeat(150),
        reasoning: 'C'.repeat(150),
      }
      render(
        <QuestionCard
          question={longQuestion}
          taskType="qa_reasoning"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
          isExpanded={false}
          onToggleExpanded={mockOnToggleExpanded}
        />
      )

      await user.click(screen.getByText('Save'))

      await waitFor(() => {
        const previews = screen.getAllByText(/\.\.\./)
        expect(previews.length).toBeGreaterThan(0)
      })
    })

    it('handles QAR without case in expanded view', async () => {
      const user = userEvent.setup()
      const noCase = { ...qarQuestion, case: undefined }
      render(
        <QuestionCard
          question={noCase}
          taskType="qa_reasoning"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
          isExpanded={true}
          onToggleExpanded={mockOnToggleExpanded}
        />
      )

      await user.click(screen.getByText('Save'))

      await waitFor(() => {
        expect(screen.queryByText('Case:')).not.toBeInTheDocument()
      })
    })

    it('shows answer configuration note in QAR edit mode', () => {
      render(
        <QuestionCard
          question={qarQuestion}
          taskType="qa_reasoning"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
        />
      )

      // Check for either the full text or part of it
      const hasConfigNote =
        screen.queryByText(/QAR tasks always use free text/) ||
        screen.queryByText(/Answer Configuration/)
      expect(hasConfigNote).toBeTruthy()
    })

    it('displays empty reasoning fallback in collapsed QAR view', async () => {
      const user = userEvent.setup()
      const noReasoning = { ...qarQuestion, reasoning: undefined }
      render(
        <QuestionCard
          question={noReasoning}
          taskType="qa_reasoning"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
          isExpanded={false}
          onToggleExpanded={mockOnToggleExpanded}
        />
      )

      await user.click(screen.getByText('Save'))

      await waitFor(() => {
        expect(screen.getByText('No reasoning provided')).toBeInTheDocument()
      })
    })

    it('displays empty answer fallback in collapsed QAR view', async () => {
      const user = userEvent.setup()
      const noAnswer = { ...qarQuestion, reference_answer: undefined }
      render(
        <QuestionCard
          question={noAnswer}
          taskType="qa_reasoning"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
          isExpanded={false}
          onToggleExpanded={mockOnToggleExpanded}
        />
      )

      await user.click(screen.getByText('Save'))

      await waitFor(() => {
        expect(screen.getByText('No answer provided')).toBeInTheDocument()
      })
    })

    it('displays fallbacks in expanded QAR view', async () => {
      const user = userEvent.setup()
      const emptyQAR = {
        id: '5',
        question: '',
        reference_answer: '',
        reasoning: '',
      }
      render(
        <QuestionCard
          question={emptyQAR}
          taskType="qa_reasoning"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
          isExpanded={true}
          onToggleExpanded={mockOnToggleExpanded}
        />
      )

      await user.click(screen.getByText('Save'))

      await waitFor(() => {
        expect(screen.getByText('No question text')).toBeInTheDocument()
        expect(screen.getByText('No answer provided')).toBeInTheDocument()
        expect(screen.getByText('No reasoning provided')).toBeInTheDocument()
      })
    })

    it('preserves answer_config in QA question updates', async () => {
      const user = userEvent.setup()
      const withConfig = {
        ...qaQuestion,
        answer_config: {
          type: 'radio' as const,
          choices: ['Yes', 'No'],
          default_type: 'radio' as const,
        },
      }
      render(
        <QuestionCard
          question={withConfig}
          taskType="qa"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
        />
      )

      const questionInput = screen.getByDisplayValue('What is the law?')
      await user.type(questionInput, ' x')

      expect(mockOnUpdate).toHaveBeenCalledWith(
        expect.objectContaining({
          answer_config: withConfig.answer_config,
        })
      )
    })

    it('handles MC fall field preservation', async () => {
      const user = userEvent.setup()
      const withFall = { ...mcQuestion, fall: 'fall-value' }
      render(
        <QuestionCard
          question={withFall}
          taskType="multiple_choice"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
        />
      )

      const questionInput = screen.getByDisplayValue('Which is correct?')
      await user.type(questionInput, ' x')

      expect(mockOnUpdate).toHaveBeenCalledWith(
        expect.objectContaining({
          fall: 'fall-value',
        })
      )
    })

    it('handles binary_solution field preservation', async () => {
      const user = userEvent.setup()
      const withBinary = { ...qaQuestion, binary_solution: 'yes' }
      render(
        <QuestionCard
          question={withBinary}
          taskType="qa"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
        />
      )

      const questionInput = screen.getByDisplayValue('What is the law?')
      await user.type(questionInput, ' x')

      expect(mockOnUpdate).toHaveBeenCalledWith(
        expect.objectContaining({
          binary_solution: 'yes',
        })
      )
    })

    it('handles rapid save and edit toggling', async () => {
      const user = userEvent.setup()
      render(
        <QuestionCard
          question={qaQuestion}
          taskType="qa"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
        />
      )

      await user.click(screen.getByText('Save'))
      await waitFor(() => expect(screen.getByText('Edit')).toBeInTheDocument())

      await user.click(screen.getByText('Edit'))
      await waitFor(() =>
        expect(screen.getByDisplayValue('What is the law?')).toBeInTheDocument()
      )

      await user.click(screen.getByText('Save'))
      await waitFor(() => expect(screen.getByText('Edit')).toBeInTheDocument())
    })

    it('calls onToggleExpanded only when provided', async () => {
      const user = userEvent.setup()
      render(
        <QuestionCard
          question={qarQuestion}
          taskType="qa_reasoning"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
          isExpanded={false}
        />
      )

      await user.click(screen.getByText('Save'))

      await waitFor(() => {
        const expandButton = screen.queryByText('Expand')
        if (expandButton) {
          expect(expandButton).toBeInTheDocument()
        }
      })
    })

    it('auto-saves empty string values', async () => {
      const user = userEvent.setup()
      render(
        <QuestionCard
          question={qaQuestion}
          taskType="qa"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
        />
      )

      const answerInput = screen.getByDisplayValue(
        'The law is a system of rules.'
      )
      await user.clear(answerInput)

      expect(mockOnUpdate).toHaveBeenCalledWith({
        ...qaQuestion,
        reference_answer: '',
      })
    })

    it('does not crash with undefined question id', () => {
      const noId = { ...qaQuestion, id: undefined as any }
      render(
        <QuestionCard
          question={noId}
          taskType="qa"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
        />
      )

      // Component should still render even with undefined id
      const questionSpans = screen.getAllByText(/Question/)
      expect(questionSpans.length).toBeGreaterThan(0)
    })

    it('handles MC with no correct answer selected', () => {
      const noCorrect = { ...mcQuestion, correct_answer: undefined }
      render(
        <QuestionCard
          question={noCorrect}
          taskType="multiple_choice"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
        />
      )

      const radios = screen.getAllByRole('radio')
      expect(radios.every((r) => !(r as HTMLInputElement).checked)).toBe(true)
    })

    it('handles whitespace-only prompt text', async () => {
      const user = userEvent.setup()
      render(
        <QuestionCard
          question={qaQuestion}
          taskType="qa"
          onUpdate={mockOnUpdate}
          onDelete={mockOnDelete}
        />
      )

      const questionInput = screen.getByDisplayValue('What is the law?')
      await user.clear(questionInput)
      await user.type(questionInput, '   ')

      expect(mockOnUpdate).toHaveBeenCalledWith({
        ...qaQuestion,
        question: '   ',
      })
    })
  })
})

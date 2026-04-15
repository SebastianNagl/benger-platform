import { Button } from '@/components/shared/Button'
import { QuestionCard, QuestionData } from '@/components/tasks/QuestionCard'
import { useCallback, useState } from 'react'

interface QuestionManagerProps {
  taskType: 'qa' | 'qa_reasoning' | 'multiple_choice'
  questions: QuestionData[]
  onQuestionsChange: (questions: QuestionData[]) => void
  answerConfig?: {
    answerType: 'radio' | 'text'
    answerChoices: string[]
    isApplied: boolean
  }
}

export function QuestionManager({
  taskType,
  questions,
  onQuestionsChange,
  answerConfig,
}: QuestionManagerProps) {
  const [expandedCards, setExpandedCards] = useState<Set<string>>(new Set())

  // Generate unique ID for new questions
  const generateId = useCallback(() => {
    return Date.now().toString() + Math.random().toString(36).substr(2, 9)
  }, [])

  // Create empty question based on task type
  const createEmptyQuestion = useCallback((): QuestionData => {
    const id = generateId()

    if (taskType === 'qa') {
      return {
        id,
        question: '',
        case: '',
        reference_answer: '',
      }
    } else if (taskType === 'qa_reasoning') {
      // QAR tasks always use text input for answers (no radio buttons)
      // This ensures consistent annotation experience for reasoning tasks
      return {
        id,
        question: '',
        case: '',
        reference_answer: '',
        reasoning: '',
        answer_config: {
          type: 'text',
          default_type: 'text',
        },
      }
    } else if (taskType === 'multiple_choice') {
      return {
        id,
        question: '',
        case: '',
        choice_a: '',
        choice_b: '',
        choice_c: '',
        choice_d: '',
        correct_answer: 'a',
      }
    } else {
      return {
        id,
        question: '',
        fall: '',
        binary_solution: '',
        reasoning: '',
      }
    }
  }, [taskType, generateId])

  const handleAddQuestion = () => {
    const newQuestion = createEmptyQuestion()
    onQuestionsChange([...questions, newQuestion])
  }

  const handleUpdateQuestion = (updatedQuestion: QuestionData) => {
    const updatedQuestions = questions.map((q) =>
      q.id === updatedQuestion.id ? updatedQuestion : q
    )
    onQuestionsChange(updatedQuestions)
  }

  const handleDeleteQuestion = (id: string) => {
    const updatedQuestions = questions.filter((q) => q.id !== id)
    onQuestionsChange(updatedQuestions)

    // Remove from expanded set if it was expanded
    setExpandedCards((prev) => {
      const newSet = new Set(prev)
      newSet.delete(id)
      return newSet
    })
  }

  const handleToggleExpanded = (id: string) => {
    setExpandedCards((prev) => {
      const newSet = new Set(prev)
      if (newSet.has(id)) {
        newSet.delete(id)
      } else {
        newSet.add(id)
      }
      return newSet
    })
  }

  const handleExpandAll = () => {
    setExpandedCards(new Set(questions.map((q) => q.id)))
  }

  const handleCollapseAll = () => {
    setExpandedCards(new Set())
  }

  return (
    <div className="space-y-6">
      {/* Header with controls */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
            Questions ({questions.length})
          </h3>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            {taskType === 'qa'
              ? 'Add simple question-answer pairs'
              : taskType === 'multiple_choice'
                ? 'Add multiple choice questions with 4 options'
                : 'Add questions with reasoning'}
          </p>
        </div>

        <div className="flex items-center space-x-2">
          {questions.length > 0 && taskType === 'qa_reasoning' && (
            <>
              <Button
                type="button"
                onClick={handleExpandAll}
                variant="outline"
                className="px-3 py-1 text-sm"
              >
                Expand All
              </Button>
              <Button
                type="button"
                onClick={handleCollapseAll}
                variant="outline"
                className="px-3 py-1 text-sm"
              >
                Collapse All
              </Button>
            </>
          )}

          <Button
            type="button"
            onClick={handleAddQuestion}
            className="bg-blue-600 px-3 py-1 text-sm text-white hover:bg-blue-700"
          >
            + Add Question
          </Button>
        </div>
      </div>

      {/* Questions List */}
      {questions.length === 0 ? (
        <div className="rounded-lg border-2 border-dashed border-gray-300 py-12 text-center dark:border-gray-600">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-gray-100 dark:bg-gray-700">
            <svg
              className="h-6 w-6 text-gray-500 dark:text-gray-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
          </div>
          <h3 className="mb-2 text-lg font-medium text-gray-900 dark:text-gray-100">
            No questions yet
          </h3>
          <p className="mb-4 text-gray-600 dark:text-gray-400">
            {taskType === 'qa'
              ? 'Add your first question-answer pair to get started.'
              : 'Add your first question to get started.'}
          </p>
          <Button
            type="button"
            onClick={handleAddQuestion}
            className="bg-blue-600 text-white hover:bg-blue-700"
          >
            Add Question
          </Button>
        </div>
      ) : (
        <div className="space-y-4">
          {questions.map((question) => (
            <QuestionCard
              key={question.id}
              question={question}
              taskType={taskType}
              onUpdate={handleUpdateQuestion}
              onDelete={handleDeleteQuestion}
              isExpanded={expandedCards.has(question.id)}
              onToggleExpanded={() => handleToggleExpanded(question.id)}
            />
          ))}
        </div>
      )}
    </div>
  )
}

// Helper function to convert questions to JSON format for the backend
export function questionsToJson(
  questions: QuestionData[],
  taskType: 'qa' | 'qa_reasoning' | 'multiple_choice'
): string {
  const convertedQuestions = questions.map((q) => {
    if (taskType === 'qa') {
      // For QA tasks, use German field names and wrap in question_data
      return {
        id: q.id,
        question_data: {
          Frage: q.question,
          Antwort: q.reference_answer,
        },
      }
    } else if (taskType === 'qa_reasoning') {
      // For QAR tasks, use English field names and wrap in question_data
      return {
        id: q.id,
        question_data: {
          question: q.question,
          answer: q.reference_answer,
          reasoning: q.reasoning,
        },
      }
    } else if (taskType === 'multiple_choice') {
      // For MCQ tasks, wrap in question_data with id at root level
      return {
        id: q.id,
        question_data: {
          question: q.question,
          context: (q as any).context || '', // Include context field with default empty string
          choice_a: q.choice_a,
          choice_b: q.choice_b,
          choice_c: q.choice_c,
          choice_d: q.choice_d,
          correct_answer: q.correct_answer,
        },
      }
    } else {
      return {
        id: q.id,
        question_data: {
          fall: q.fall,
          binary_solution: q.binary_solution,
          reasoning: q.reasoning,
        },
      }
    }
  })

  return JSON.stringify(convertedQuestions, null, 2)
}

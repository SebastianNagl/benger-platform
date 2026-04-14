/**
 * QuestionAddModal Component
 *
 * Modal for adding new questions to a task for superadmin users.
 *
 * Issue #164: Add question management functionality for superadmin users
 */

import { Button } from '@/components/shared/Button'
import { useI18n } from '@/contexts/I18nContext'
import { Dialog, Transition } from '@headlessui/react'
import { PlusIcon, TrashIcon, XMarkIcon } from '@heroicons/react/24/outline'
import { Fragment, useState } from 'react'

interface QuestionAddModalProps {
  isOpen: boolean
  onSave: (
    questions: Array<{
      question: string
      answer: string[]
      case?: string
      reasoning?: string
    }>
  ) => void
  onCancel: () => void
  taskType?: string
}

export function QuestionAddModal({
  isOpen,
  onSave,
  onCancel,
  taskType,
}: QuestionAddModalProps) {
  const { t } = useI18n()
  const [questions, setQuestions] = useState([
    {
      question: '',
      answer: [''],
      case: '',
      reasoning: '',
    },
  ])
  const [errors, setErrors] = useState<{
    [key: number]: {
      question?: string
      reference_answers?: string
      answer?: string
    }
  }>({})

  const validateForm = () => {
    const newErrors: typeof errors = {}
    let isValid = true

    questions.forEach((q, index) => {
      const itemErrors: {
        question?: string
        reference_answers?: string
        answer?: string
      } = {}

      if (!q.question.trim()) {
        itemErrors.question = t('tasks.questions.validation.questionRequired')
        isValid = false
      }

      const validAnswers = q.answer.filter((answer) => answer.trim())
      if (validAnswers.length === 0) {
        itemErrors.answer = t('tasks.questions.validation.answerRequired')
        isValid = false
      }

      if (Object.keys(itemErrors).length > 0) {
        newErrors[index] = itemErrors
      }
    })

    setErrors(newErrors)
    return isValid
  }

  const handleSave = () => {
    if (validateForm()) {
      // Clean up questions before saving
      const cleanedQuestions = questions.map((q) => ({
        question: q.question.trim(),
        answer: q.answer.filter((answer) => answer.trim()),
        case: q.case.trim() || undefined,
        reasoning: q.reasoning?.trim() || undefined,
      }))

      onSave(cleanedQuestions)
    }
  }

  const addQuestion = () => {
    setQuestions((prev) => [
      ...prev,
      {
        question: '',
        answer: [''],
        case: '',
        reasoning: '',
      },
    ])
  }

  const removeQuestion = (index: number) => {
    if (questions.length > 1) {
      setQuestions((prev) => prev.filter((_, i) => i !== index))
      setErrors((prev) => {
        const newErrors = { ...prev }
        delete newErrors[index]
        return newErrors
      })
    }
  }

  const updateQuestion = (index: number, field: string, value: string) => {
    setQuestions((prev) =>
      prev.map((q, i) => (i === index ? { ...q, [field]: value } : q))
    )
  }

  const addReferenceAnswer = (questionIndex: number) => {
    setQuestions((prev) =>
      prev.map((q, i) =>
        i === questionIndex ? { ...q, answer: [...q.answer, ''] } : q
      )
    )
  }

  const removeReferenceAnswer = (
    questionIndex: number,
    answerIndex: number
  ) => {
    setQuestions((prev) =>
      prev.map((q, i) =>
        i === questionIndex && q.answer.length > 1
          ? { ...q, answer: q.answer.filter((_, j) => j !== answerIndex) }
          : q
      )
    )
  }

  const updateReferenceAnswer = (
    questionIndex: number,
    answerIndex: number,
    value: string
  ) => {
    setQuestions((prev) =>
      prev.map((q, i) =>
        i === questionIndex
          ? {
              ...q,
              answer: q.answer.map((answer, j) =>
                j === answerIndex ? value : answer
              ),
            }
          : q
      )
    )
  }

  const handleClose = () => {
    // Reset state when closing
    setQuestions([
      {
        question: '',
        answer: [''],
        case: '',
        reasoning: '',
      },
    ])
    setErrors({})
    onCancel()
  }

  return (
    <Transition appear show={isOpen} as={Fragment}>
      <Dialog as="div" className="relative z-50" onClose={handleClose}>
        <Transition.Child
          as={Fragment}
          enter="ease-out duration-300"
          enterFrom="opacity-0"
          enterTo="opacity-100"
          leave="ease-in duration-200"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-black bg-opacity-25" />
        </Transition.Child>

        <div className="fixed inset-0 overflow-y-auto">
          <div className="flex min-h-full items-center justify-center p-4 text-center">
            <Transition.Child
              as={Fragment}
              enter="ease-out duration-300"
              enterFrom="opacity-0 scale-95"
              enterTo="opacity-100 scale-100"
              leave="ease-in duration-200"
              leaveFrom="opacity-100 scale-100"
              leaveTo="opacity-0 scale-95"
            >
              <Dialog.Panel
                className="w-full max-w-4xl transform overflow-hidden rounded-2xl bg-white p-6 text-left align-middle shadow-xl transition-all dark:bg-zinc-900"
                data-testid="question-add-modal"
              >
                <div className="mb-4 flex items-center justify-between">
                  <Dialog.Title
                    as="h3"
                    className="text-lg font-medium leading-6 text-zinc-900 dark:text-zinc-100"
                  >
                    {t('tasks.questions.addTitle')}
                  </Dialog.Title>
                  <button
                    onClick={handleClose}
                    className="text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300"
                  >
                    <XMarkIcon className="h-6 w-6" />
                  </button>
                </div>

                <div className="max-h-[70vh] space-y-6 overflow-y-auto">
                  {questions.map((question, qIndex) => (
                    <div
                      key={qIndex}
                      className="space-y-4 rounded-lg border border-zinc-200 p-4 dark:border-zinc-700"
                    >
                      <div className="flex items-start justify-between">
                        <h4 className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                          {t('tasks.questions.questionNumber', { number: qIndex + 1 })}
                        </h4>
                        {questions.length > 1 && (
                          <button
                            onClick={() => removeQuestion(qIndex)}
                            className="text-red-600 hover:text-red-800 dark:text-red-400 dark:hover:text-red-300"
                            title={t('tasks.questions.removeQuestion')}
                          >
                            <TrashIcon className="h-4 w-4" />
                          </button>
                        )}
                      </div>

                      {/* Question Field */}
                      <div>
                        <label
                          htmlFor={`question-${qIndex}`}
                          className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300"
                        >
                          {t('tasks.questions.questionLabel')}
                        </label>
                        <textarea
                          id={`question-${qIndex}`}
                          name={`questions.${qIndex}.question`}
                          rows={2}
                          value={question.question}
                          onChange={(e) =>
                            updateQuestion(qIndex, 'question', e.target.value)
                          }
                          className="w-full rounded-md border border-zinc-300 px-3 py-2 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-blue-500 dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100"
                          placeholder={t('tasks.questions.questionPlaceholder')}
                          data-testid={`add-question-${qIndex}`}
                        />
                        {errors[qIndex]?.question && (
                          <p className="mt-1 text-sm text-red-600 dark:text-red-400">
                            {errors[qIndex].question}
                          </p>
                        )}
                      </div>

                      {/* Context Field */}
                      <div>
                        <label
                          htmlFor={`case-${qIndex}`}
                          className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300"
                        >
                          {t('tasks.questions.caseLabel')}
                        </label>
                        <textarea
                          id={`case-${qIndex}`}
                          name={`questions.${qIndex}.case`}
                          rows={2}
                          value={question.case}
                          onChange={(e) =>
                            updateQuestion(qIndex, 'case', e.target.value)
                          }
                          className="w-full rounded-md border border-zinc-300 px-3 py-2 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-blue-500 dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100"
                          placeholder={t('tasks.questions.casePlaceholder')}
                          data-testid={`add-case-${qIndex}`}
                        />
                      </div>

                      {/* Reference Answers */}
                      <div>
                        <div className="mb-2 flex items-center justify-between">
                          <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300">
                            {t('tasks.questions.answerLabel')}
                          </label>
                          <button
                            onClick={() => addReferenceAnswer(qIndex)}
                            className="flex items-center gap-1 text-sm text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300"
                          >
                            <PlusIcon className="h-4 w-4" />
                            {t('tasks.questions.addAnswer')}
                          </button>
                        </div>

                        <div className="space-y-2">
                          {question.answer.map((answer, aIndex) => (
                            <div key={aIndex} className="flex gap-2">
                              <input
                                type="text"
                                name={`questions.${qIndex}.answer.${aIndex}`}
                                value={answer}
                                onChange={(e) =>
                                  updateReferenceAnswer(
                                    qIndex,
                                    aIndex,
                                    e.target.value
                                  )
                                }
                                className="flex-1 rounded-md border border-zinc-300 px-3 py-2 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-blue-500 dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100"
                                placeholder={t('tasks.questions.answerPlaceholder', { number: aIndex + 1 })}
                                data-testid={`add-answer-${qIndex}-${aIndex}`}
                              />
                              {question.answer.length > 1 && (
                                <button
                                  onClick={() =>
                                    removeReferenceAnswer(qIndex, aIndex)
                                  }
                                  className="p-2 text-red-600 hover:text-red-800 dark:text-red-400 dark:hover:text-red-300"
                                  title={t('tasks.questions.removeAnswer')}
                                >
                                  <TrashIcon className="h-4 w-4" />
                                </button>
                              )}
                            </div>
                          ))}
                        </div>

                        {errors[qIndex]?.answer && (
                          <p className="mt-1 text-sm text-red-600 dark:text-red-400">
                            {errors[qIndex].answer}
                          </p>
                        )}
                      </div>

                      {/* Reasoning Field - Only show for QAR tasks */}
                      {taskType === 'QAR' && (
                        <div>
                          <label
                            htmlFor={`reasoning-${qIndex}`}
                            className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300"
                          >
                            {t('tasks.questions.reasoningLabel')}
                          </label>
                          <textarea
                            id={`reasoning-${qIndex}`}
                            name={`questions.${qIndex}.reasoning`}
                            rows={3}
                            value={question.reasoning}
                            onChange={(e) =>
                              updateQuestion(
                                qIndex,
                                'reasoning',
                                e.target.value
                              )
                            }
                            className="w-full rounded-md border border-zinc-300 px-3 py-2 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-blue-500 dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100"
                            placeholder={t('tasks.questions.reasoningPlaceholder')}
                            data-testid={`add-reasoning-${qIndex}`}
                          />
                        </div>
                      )}
                    </div>
                  ))}
                </div>

                {/* Add Another Question Button */}
                <div className="mt-4">
                  <button
                    onClick={addQuestion}
                    className="flex w-full items-center justify-center gap-2 rounded-lg border-2 border-dashed border-zinc-300 py-2 text-zinc-600 transition-colors hover:border-zinc-400 hover:text-zinc-700 dark:border-zinc-600 dark:text-zinc-400 dark:hover:border-zinc-500 dark:hover:text-zinc-300"
                  >
                    <PlusIcon className="h-5 w-5" />
                    {t('tasks.questions.addAnother')}
                  </button>
                </div>

                {/* Action Buttons */}
                <div className="mt-6 flex justify-end gap-3">
                  <Button type="button" variant="outline" onClick={handleClose}>
                    {t('common.cancel')}
                  </Button>
                  <Button
                    type="button"
                    onClick={handleSave}
                    className="bg-blue-600 text-white hover:bg-blue-700"
                    data-testid="add-questions-button"
                  >
                    {t('tasks.questions.addCount', { count: questions.length })}
                  </Button>
                </div>
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition>
  )
}

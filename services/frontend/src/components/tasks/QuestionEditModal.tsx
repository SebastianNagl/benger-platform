/**
 * QuestionEditModal Component
 *
 * Modal for editing questions, reference answers, and context for superadmin users.
 *
 * Issue #164: Add question editing functionality for superadmin users
 */

import { Button } from '@/components/shared/Button'
import { useI18n } from '@/contexts/I18nContext'
import { logger } from '@/lib/utils/logger'
import { Dialog, Transition } from '@headlessui/react'
import { PlusIcon, TrashIcon, XMarkIcon } from '@heroicons/react/24/outline'
import { Fragment, useEffect, useState } from 'react'

interface QuestionEditModalProps {
  isOpen: boolean
  question: {
    id: number
    question: string
    reference_answers: string[]
    context?: string
  } | null
  onSave: (data: {
    question: string
    reference_answers: string[]
    context?: string
  }) => void
  onCancel: () => void
}

export function QuestionEditModal({
  isOpen,
  question,
  onSave,
  onCancel,
}: QuestionEditModalProps) {
  const { t } = useI18n()
  const [formData, setFormData] = useState({
    question: '',
    reference_answers: [''],
    context: '',
  })
  const [errors, setErrors] = useState<{
    question?: string
    reference_answers?: string
  }>({})

  // Initialize form data when modal opens with a new question
  useEffect(() => {
    if (isOpen && question) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- Prop sync for modal form state
      setFormData({
        question: question.question || '',
        reference_answers:
          question.reference_answers.length > 0
            ? question.reference_answers
            : [''],
        context: question.context || '',
      })
       
      setErrors({})
    }
  }, [isOpen, question])

  const validateForm = () => {
    const newErrors: typeof errors = {}

    if (!formData.question.trim()) {
      newErrors.question = t('tasks.questions.validation.questionRequired')
    }

    const validAnswers = formData.reference_answers.filter((answer) =>
      answer.trim()
    )
    if (validAnswers.length === 0) {
      newErrors.reference_answers = t('tasks.questions.validation.referenceAnswerRequired')
    }

    setErrors(newErrors)
    return Object.keys(newErrors).length === 0
  }

  const handleSave = () => {
    if (validateForm()) {
      // Filter out empty reference answers
      const cleanedAnswers = formData.reference_answers.filter((answer) =>
        answer.trim()
      )

      const saveData = {
        question: formData.question.trim(),
        reference_answers: cleanedAnswers,
        context: formData.context.trim() || undefined,
      }

      logger.debug('Calling onSave with:', saveData)
      onSave(saveData)
    } else {
      logger.debug('Form validation failed')
    }
  }

  const addReferenceAnswer = () => {
    setFormData((prev) => ({
      ...prev,
      reference_answers: [...prev.reference_answers, ''],
    }))
  }

  const removeReferenceAnswer = (index: number) => {
    if (formData.reference_answers.length > 1) {
      setFormData((prev) => ({
        ...prev,
        reference_answers: prev.reference_answers.filter((_, i) => i !== index),
      }))
    }
  }

  const updateReferenceAnswer = (index: number, value: string) => {
    setFormData((prev) => ({
      ...prev,
      reference_answers: prev.reference_answers.map((answer, i) =>
        i === index ? value : answer
      ),
    }))
  }

  return (
    <Transition appear show={isOpen} as={Fragment}>
      <Dialog as="div" className="relative z-50" onClose={onCancel}>
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
                className="w-full max-w-2xl transform overflow-hidden rounded-2xl bg-white p-6 text-left align-middle shadow-xl transition-all dark:bg-zinc-900"
                data-testid="question-edit-modal"
              >
                <div className="mb-4 flex items-center justify-between">
                  <Dialog.Title
                    as="h3"
                    className="text-lg font-medium leading-6 text-zinc-900 dark:text-zinc-100"
                  >
                    {t('tasks.questions.editTitle')}{' '}
                    {question?.id !== undefined ? `#${question.id}` : ''}
                  </Dialog.Title>
                  <button
                    onClick={onCancel}
                    className="text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300"
                  >
                    <XMarkIcon className="h-6 w-6" />
                  </button>
                </div>

                <div className="space-y-4">
                  {/* Question Field */}
                  <div>
                    <label
                      htmlFor="question"
                      className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300"
                    >
                      {t('tasks.questions.questionLabel')}
                    </label>
                    <textarea
                      id="question"
                      name="question"
                      rows={3}
                      value={formData.question}
                      onChange={(e) =>
                        setFormData((prev) => ({
                          ...prev,
                          question: e.target.value,
                        }))
                      }
                      className="w-full rounded-md border border-zinc-300 px-3 py-2 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-blue-500 dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100"
                      placeholder={t('tasks.questions.questionPlaceholder')}
                      data-testid="question-input"
                    />
                    {errors.question && (
                      <p className="mt-1 text-sm text-red-600 dark:text-red-400">
                        {errors.question}
                      </p>
                    )}
                  </div>

                  {/* Context Field */}
                  <div>
                    <label
                      htmlFor="context"
                      className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300"
                    >
                      {t('tasks.questions.contextLabel')}
                    </label>
                    <textarea
                      id="context"
                      rows={2}
                      value={formData.context}
                      onChange={(e) =>
                        setFormData((prev) => ({
                          ...prev,
                          context: e.target.value,
                        }))
                      }
                      className="w-full rounded-md border border-zinc-300 px-3 py-2 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-blue-500 dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100"
                      placeholder={t('tasks.questions.contextPlaceholder')}
                    />
                  </div>

                  {/* Reference Answers */}
                  <div>
                    <div className="mb-2 flex items-center justify-between">
                      <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300">
                        {t('tasks.questions.referenceAnswersLabel')}
                      </label>
                      <button
                        onClick={addReferenceAnswer}
                        className="flex items-center gap-1 text-sm text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300"
                      >
                        <PlusIcon className="h-4 w-4" />
                        {t('tasks.questions.addAnswer')}
                      </button>
                    </div>

                    <div className="space-y-2">
                      {formData.reference_answers.map((answer, index) => (
                        <div key={index} className="flex gap-2">
                          <input
                            type="text"
                            name={`reference_answers.${index}`}
                            value={answer}
                            onChange={(e) =>
                              updateReferenceAnswer(index, e.target.value)
                            }
                            className="flex-1 rounded-md border border-zinc-300 px-3 py-2 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-blue-500 dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100"
                            placeholder={t('tasks.questions.referenceAnswerPlaceholder', { number: index + 1 })}
                            data-testid={`reference-answer-${index}`}
                          />
                          {formData.reference_answers.length > 1 && (
                            <button
                              onClick={() => removeReferenceAnswer(index)}
                              className="p-2 text-red-600 hover:text-red-800 dark:text-red-400 dark:hover:text-red-300"
                              title={t('tasks.questions.removeAnswer')}
                            >
                              <TrashIcon className="h-4 w-4" />
                            </button>
                          )}
                        </div>
                      ))}
                    </div>

                    {errors.reference_answers && (
                      <p className="mt-1 text-sm text-red-600 dark:text-red-400">
                        {errors.reference_answers}
                      </p>
                    )}
                  </div>
                </div>

                {/* Action Buttons */}
                <div className="mt-6 flex justify-end gap-3">
                  <Button type="button" variant="outline" onClick={onCancel}>
                    {t('common.cancel')}
                  </Button>
                  <Button
                    type="button"
                    onClick={() => {
                      logger.debug('Button onClick triggered')
                      handleSave()
                    }}
                    className="bg-blue-600 text-white hover:bg-blue-700"
                    data-testid="save-question-button"
                  >
                    {t('common.saveChanges')}
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

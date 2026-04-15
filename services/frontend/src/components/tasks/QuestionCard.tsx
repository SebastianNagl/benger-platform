import { Button } from '@/components/shared/Button'
import { useI18n } from '@/contexts/I18nContext'
import { useState } from 'react'

interface QuestionData {
  id: string
  question?: string
  reference_answer?: string
  reasoning?: string
  fall?: string
  binary_solution?: string
  // MCQ-specific fields
  case?: string
  choice_a?: string
  choice_b?: string
  choice_c?: string
  choice_d?: string
  correct_answer?: 'a' | 'b' | 'c' | 'd'
  // For preserving imported model and human responses
  model_responses?: Record<string, { answer: string; reasoning?: string }>
  human_responses?: Record<string, { answer: string; reasoning?: string }>
  // Answer configuration for QAR tasks
  answer_config?: {
    type: 'radio' | 'text'
    choices?: string[]
    default_type: 'radio' | 'text'
  }
}

interface QuestionCardProps {
  question: QuestionData
  taskType: 'qa' | 'qa_reasoning' | 'multiple_choice'
  onUpdate: (question: QuestionData) => void
  onDelete: (id: string) => void
  isExpanded?: boolean
  onToggleExpanded?: () => void
}

export function QuestionCard({
  question,
  taskType,
  onUpdate,
  onDelete,
  isExpanded = false,
  onToggleExpanded,
}: QuestionCardProps) {
  const { t } = useI18n()
  const [isEditing, setIsEditing] = useState(true) // Start in edit mode
  const [localQuestion, setLocalQuestion] = useState(question)

  const handleSave = () => {
    onUpdate(localQuestion)
    setIsEditing(false)
  }

  const handleCancel = () => {
    setLocalQuestion(question)
    setIsEditing(false)
  }

  const handleFieldChange = (field: keyof QuestionData, value: string) => {
    const updatedQuestion = { ...localQuestion, [field]: value }
    setLocalQuestion(updatedQuestion)
    // Auto-save changes immediately
    onUpdate(updatedQuestion)
  }

  if (taskType === 'qa') {
    return (
      <div className="rounded-lg border border-gray-200 bg-white shadow-sm dark:border-gray-700 dark:bg-gray-800">
        <div className="p-4">
          <div className="mb-3 flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <div className="flex h-6 w-6 items-center justify-center rounded-full bg-blue-600">
                <span className="text-xs font-bold text-white">Q</span>
              </div>
              <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                {t('tasks.questionCard.questionId', { id: question.id })}
              </span>
            </div>
            <div className="flex items-center space-x-2">
              {!isEditing && (
                <Button
                  type="button"
                  onClick={() => setIsEditing(true)}
                  variant="outline"
                  className="px-2 py-1 text-xs"
                >
                  {t('tasks.questionCard.edit')}
                </Button>
              )}
              <Button
                type="button"
                onClick={() => onDelete(question.id)}
                variant="outline"
                className="border-red-300 px-2 py-1 text-xs text-red-600 hover:bg-red-50"
              >
                {t('tasks.questionCard.delete')}
              </Button>
            </div>
          </div>

          {isEditing ? (
            <div className="space-y-4">
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
                  {t('tasks.questionCard.caseOptional')}
                </label>
                <textarea
                  value={localQuestion.case || ''}
                  onChange={(e) => handleFieldChange('case', e.target.value)}
                  rows={3}
                  className="block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 transition-colors focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
                  placeholder={t('tasks.questionCard.placeholderCase')}
                />
              </div>

              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
                  {t('tasks.questionCard.question')} <span className="text-red-500">*</span>
                </label>
                <textarea
                  value={localQuestion.question}
                  onChange={(e) =>
                    handleFieldChange('question', e.target.value)
                  }
                  rows={3}
                  className="block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 transition-colors focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
                  placeholder={t('tasks.questionCard.placeholderQuestion')}
                />
              </div>

              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
                  {t('tasks.questionCard.referenceAnswer')} <span className="text-red-500">*</span>
                </label>
                <textarea
                  value={localQuestion.reference_answer || ''}
                  onChange={(e) =>
                    handleFieldChange('reference_answer', e.target.value)
                  }
                  rows={4}
                  className="block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 transition-colors focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
                  placeholder={t('tasks.questionCard.placeholderExpectedAnswer')}
                />
              </div>

              <div className="flex justify-end space-x-2">
                <Button
                  type="button"
                  onClick={handleCancel}
                  variant="outline"
                  className="px-3 py-1 text-sm"
                >
                  {t('tasks.questionCard.cancel')}
                </Button>
                <Button
                  type="button"
                  onClick={handleSave}
                  className="bg-blue-600 px-3 py-1 text-sm text-white hover:bg-blue-700"
                >
                  {t('tasks.questionCard.save')}
                </Button>
              </div>
            </div>
          ) : (
            <div className="space-y-3">
              {question.case && (
                <div>
                  <p className="mb-1 text-sm font-medium text-gray-700 dark:text-gray-300">
                    {t('tasks.questionCard.caseLabel')}
                  </p>
                  <p className="rounded bg-gray-50 p-2 text-sm italic text-gray-600 dark:bg-gray-700 dark:text-gray-400">
                    {question.case}
                  </p>
                </div>
              )}

              <div>
                <p className="mb-1 text-sm font-medium text-gray-700 dark:text-gray-300">
                  {t('tasks.questionCard.questionLabel')}
                </p>
                <p className="rounded bg-gray-50 p-2 text-sm text-gray-900 dark:bg-gray-700 dark:text-gray-100">
                  {question.question || t('tasks.questionCard.noQuestionText')}
                </p>
              </div>

              <div>
                <p className="mb-1 text-sm font-medium text-gray-700 dark:text-gray-300">
                  {t('tasks.questionCard.referenceAnswerLabel')}
                </p>
                <p className="rounded bg-gray-50 p-2 text-sm text-gray-900 dark:bg-gray-700 dark:text-gray-100">
                  {question.reference_answer || t('tasks.questionCard.noReferenceAnswer')}
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    )
  }

  // Multiple Choice type
  if (taskType === 'multiple_choice') {
    return (
      <div className="rounded-lg border border-orange-200 bg-white shadow-sm dark:border-orange-700 dark:bg-orange-800/20">
        <div className="p-4">
          <div className="mb-3 flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <div className="flex h-6 w-6 items-center justify-center rounded-full bg-orange-600">
                <span className="text-xs font-bold text-white">M</span>
              </div>
              <span className="text-sm font-medium text-orange-900 dark:text-orange-100">
                {t('tasks.questionCard.mcqId', { id: question.id })}
              </span>
            </div>
            <div className="flex items-center space-x-2">
              {!isEditing && (
                <Button
                  type="button"
                  onClick={() => setIsEditing(true)}
                  variant="outline"
                  className="border-orange-300 px-2 py-1 text-xs text-orange-700 hover:bg-orange-100"
                >
                  {t('tasks.questionCard.edit')}
                </Button>
              )}
              <Button
                type="button"
                onClick={() => onDelete(question.id)}
                variant="outline"
                className="border-red-300 px-2 py-1 text-xs text-red-600 hover:bg-red-50"
              >
                {t('tasks.questionCard.delete')}
              </Button>
            </div>
          </div>

          {isEditing ? (
            <div className="space-y-4">
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
                  {t('tasks.questionCard.question')} <span className="text-red-500">*</span>
                </label>
                <textarea
                  value={localQuestion.question || ''}
                  onChange={(e) =>
                    handleFieldChange('question', e.target.value)
                  }
                  rows={3}
                  className="block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 transition-colors focus:border-orange-500 focus:ring-2 focus:ring-orange-500/20 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
                  placeholder={t('tasks.questionCard.placeholderMcq')}
                />
              </div>

              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
                  {t('tasks.questionCard.contextOptional')}
                </label>
                <textarea
                  value={localQuestion.case || ''}
                  onChange={(e) => handleFieldChange('case', e.target.value)}
                  rows={2}
                  className="block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 transition-colors focus:border-orange-500 focus:ring-2 focus:ring-orange-500/20 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
                  placeholder={t('tasks.questionCard.placeholderContext')}
                />
              </div>

              <div className="space-y-3">
                <div className="flex items-center space-x-2">
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                    {t('tasks.questionCard.answerOptions')} <span className="text-red-500">*</span>
                  </label>
                  <div className="group relative">
                    <svg
                      className="h-4 w-4 cursor-help text-gray-400 hover:text-gray-600"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                      />
                    </svg>
                    <div className="absolute bottom-full left-1/2 z-10 mb-2 hidden -translate-x-1/2 transform group-hover:block">
                      <div className="whitespace-nowrap rounded bg-gray-900 px-3 py-2 text-xs text-white">
                        {t('tasks.questionCard.selectCorrectTooltip')}
                      </div>
                      <div className="absolute left-1/2 top-full -translate-x-1/2 transform border-4 border-transparent border-t-gray-900"></div>
                    </div>
                  </div>
                </div>

                {(['a', 'b', 'c', 'd'] as const).map((option) => (
                  <div
                    key={option}
                    className="flex items-center space-x-3 rounded-md border border-gray-200 p-3 dark:border-gray-600"
                  >
                    <div className="flex items-center">
                      <input
                        type="radio"
                        id={`correct-${question.id}-${option}`}
                        name={`correct-${question.id}`}
                        checked={localQuestion.correct_answer === option}
                        onChange={() =>
                          handleFieldChange('correct_answer', option)
                        }
                        className="h-4 w-4 border-gray-300 text-orange-600 focus:ring-orange-500"
                      />
                      <label
                        htmlFor={`correct-${question.id}-${option}`}
                        className="ml-2 text-sm font-medium text-gray-700 dark:text-gray-300"
                      >
                        {option.toUpperCase()}
                      </label>
                    </div>
                    <div className="flex-1">
                      <input
                        type="text"
                        value={String(
                          localQuestion[
                            `choice_${option}` as keyof QuestionData
                          ] || ''
                        )}
                        onChange={(e) =>
                          handleFieldChange(`choice_${option}`, e.target.value)
                        }
                        className="block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 transition-colors focus:border-orange-500 focus:ring-2 focus:ring-orange-500/20 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
                        placeholder={t('tasks.questionCard.optionPlaceholder', { option: option.toUpperCase() })}
                      />
                    </div>
                  </div>
                ))}
              </div>

              <div className="flex justify-end space-x-2">
                <Button
                  type="button"
                  onClick={handleCancel}
                  variant="outline"
                  className="px-3 py-1 text-sm"
                >
                  {t('tasks.questionCard.cancel')}
                </Button>
                <Button
                  type="button"
                  onClick={handleSave}
                  className="bg-orange-600 px-3 py-1 text-sm text-white hover:bg-orange-700"
                >
                  {t('tasks.questionCard.save')}
                </Button>
              </div>
            </div>
          ) : (
            <div className="space-y-3">
              <div>
                <p className="mb-1 text-sm font-medium text-gray-700 dark:text-gray-300">
                  {t('tasks.questionCard.questionLabel')}
                </p>
                <p className="rounded bg-gray-50 p-2 text-sm text-gray-900 dark:bg-gray-700 dark:text-gray-100">
                  {question.question || t('tasks.questionCard.noQuestionText')}
                </p>
              </div>

              {localQuestion.case && (
                <div>
                  <p className="mb-1 text-sm font-medium text-gray-700 dark:text-gray-300">
                    {t('tasks.questionCard.contextLabel')}
                  </p>
                  <p className="rounded bg-gray-50 p-2 text-sm italic text-gray-600 dark:bg-gray-700 dark:text-gray-400">
                    {localQuestion.case}
                  </p>
                </div>
              )}

              <div>
                <p className="mb-2 text-sm font-medium text-gray-700 dark:text-gray-300">
                  {t('tasks.questionCard.optionsLabel')}
                </p>
                <div className="space-y-2">
                  {(['a', 'b', 'c', 'd'] as const).map((option) => (
                    <div
                      key={option}
                      className={`flex items-center space-x-2 rounded p-2 text-sm ${
                        localQuestion.correct_answer === option
                          ? 'border border-green-200 bg-green-50 dark:border-green-700 dark:bg-green-900/20'
                          : 'bg-gray-50 dark:bg-gray-700'
                      }`}
                    >
                      <span className="font-medium">
                        {option.toUpperCase()}:
                      </span>
                      <span className="text-gray-900 dark:text-gray-100">
                        {String(
                          localQuestion[
                            `choice_${option}` as keyof QuestionData
                          ] || t('tasks.questionCard.noOption', { option: option.toUpperCase() })
                        )}
                      </span>
                      {localQuestion.correct_answer === option && (
                        <span className="text-xs font-medium text-green-600 dark:text-green-400">
                          {t('tasks.questionCard.correct')}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    )
  }

  // QA Reasoning type
  return (
    <div className="rounded-lg border border-emerald-200 bg-white shadow-sm dark:border-emerald-700 dark:bg-emerald-800/20">
      <div className="p-4">
        <div className="mb-3 flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <div className="flex h-6 w-6 items-center justify-center rounded-full bg-emerald-600">
              <span className="text-xs font-bold text-white">L</span>
            </div>
            <span className="text-sm font-medium text-emerald-900 dark:text-emerald-100">
              {t('tasks.questionCard.questionId', { id: question.id })}
            </span>
          </div>
          <div className="flex items-center space-x-2">
            {!isEditing && (
              <>
                <Button
                  type="button"
                  onClick={onToggleExpanded}
                  variant="outline"
                  className="border-emerald-300 px-2 py-1 text-xs text-emerald-700 hover:bg-emerald-100"
                >
                  {isExpanded ? t('tasks.questionCard.collapse') : t('tasks.questionCard.expand')}
                </Button>
                <Button
                  type="button"
                  onClick={() => setIsEditing(true)}
                  variant="outline"
                  className="border-emerald-300 px-2 py-1 text-xs text-emerald-700 hover:bg-emerald-100"
                >
                  {t('tasks.questionCard.edit')}
                </Button>
              </>
            )}
            <Button
              type="button"
              onClick={() => onDelete(question.id)}
              variant="outline"
              className="border-red-300 px-2 py-1 text-xs text-red-600 hover:bg-red-50"
            >
              {t('tasks.questionCard.delete')}
            </Button>
          </div>
        </div>

        {isEditing ? (
          <div className="space-y-4">
            <div>
              <label className="mb-1 block text-sm font-medium text-emerald-700 dark:text-emerald-300">
                {t('tasks.questionCard.caseOptional')}
              </label>
              <textarea
                value={localQuestion.case || ''}
                onChange={(e) => handleFieldChange('case', e.target.value)}
                rows={3}
                className="block w-full rounded-md border border-emerald-300 bg-white px-3 py-2 text-sm text-emerald-900 transition-colors focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/20 dark:border-emerald-600 dark:bg-emerald-900/50 dark:text-emerald-100"
                placeholder={t('tasks.questionCard.placeholderLegalCase')}
              />
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium text-emerald-700 dark:text-emerald-300">
                {t('tasks.questionCard.question')} <span className="text-red-500">*</span>
              </label>
              <textarea
                value={localQuestion.question || ''}
                onChange={(e) => handleFieldChange('question', e.target.value)}
                rows={3}
                className="block w-full rounded-md border border-emerald-300 bg-white px-3 py-2 text-sm text-emerald-900 transition-colors focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/20 dark:border-emerald-600 dark:bg-emerald-900/50 dark:text-emerald-100"
                placeholder={t('tasks.questionCard.placeholderLegalQuestion')}
              />
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium text-emerald-700 dark:text-emerald-300">
                {t('tasks.questionCard.answer')} <span className="text-red-500">*</span>
              </label>

              {/* QAR tasks always use text input (no radio buttons) */}
              <textarea
                value={localQuestion.reference_answer || ''}
                onChange={(e) =>
                  handleFieldChange('reference_answer', e.target.value)
                }
                rows={3}
                className="block w-full rounded-md border border-emerald-300 bg-white px-3 py-2 text-sm text-emerald-900 transition-colors focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/20 dark:border-emerald-600 dark:bg-emerald-900/50 dark:text-emerald-100"
                placeholder={t('tasks.questionCard.placeholderLegalAnswer')}
              />

              <div className="mt-2 rounded bg-emerald-50 p-2 text-xs text-emerald-600 dark:bg-emerald-900/20 dark:text-emerald-400">
                <strong>{t('tasks.questionCard.answerConfiguration')}</strong> {t('tasks.questionCard.answerConfigHelp')}
              </div>
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium text-emerald-700 dark:text-emerald-300">
                {t('tasks.questionCard.reasoning')} <span className="text-red-500">*</span>
              </label>
              <textarea
                value={localQuestion.reasoning || ''}
                onChange={(e) => handleFieldChange('reasoning', e.target.value)}
                rows={8}
                className="block w-full rounded-md border border-emerald-300 bg-white px-3 py-2 text-sm text-emerald-900 transition-colors focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/20 dark:border-emerald-600 dark:bg-emerald-900/50 dark:text-emerald-100"
                placeholder={t('tasks.questionCard.placeholderReasoning')}
              />
            </div>

            <div className="flex justify-end space-x-2">
              <Button
                type="button"
                onClick={handleCancel}
                variant="outline"
                className="border-emerald-300 px-3 py-1 text-sm text-emerald-700 hover:bg-emerald-100"
              >
                {t('tasks.questionCard.cancel')}
              </Button>
              <Button
                type="button"
                onClick={handleSave}
                className="bg-emerald-600 px-3 py-1 text-sm text-white hover:bg-emerald-700"
              >
                {t('tasks.questionCard.save')}
              </Button>
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            {/* Collapsed view */}
            {!isExpanded ? (
              <div className="space-y-2">
                <div>
                  <p className="text-sm font-medium text-emerald-700 dark:text-emerald-300">
                    {t('tasks.questionCard.questionPreview')}
                  </p>
                  <p className="truncate text-sm text-emerald-900 dark:text-emerald-100">
                    {question.question
                      ? question.question.substring(0, 100) + '...'
                      : t('tasks.questionCard.noQuestionText')}
                  </p>
                </div>
                <div>
                  <p className="text-sm font-medium text-emerald-700 dark:text-emerald-300">
                    {t('tasks.questionCard.answerPreview')}
                  </p>
                  <p className="truncate text-sm text-emerald-900 dark:text-emerald-100">
                    {question.reference_answer
                      ? question.reference_answer.substring(0, 100) + '...'
                      : t('tasks.questionCard.noAnswerProvided')}
                  </p>
                </div>
                <div>
                  <p className="text-sm font-medium text-emerald-700 dark:text-emerald-300">
                    {t('tasks.questionCard.reasoningPreview')}
                  </p>
                  <p className="truncate text-sm text-emerald-900 dark:text-emerald-100">
                    {question.reasoning
                      ? question.reasoning.substring(0, 100) + '...'
                      : t('tasks.questionCard.noReasoningProvided')}
                  </p>
                </div>
              </div>
            ) : (
              /* Expanded view */
              <div className="space-y-4">
                {question.case && (
                  <div>
                    <p className="mb-1 text-sm font-medium text-emerald-700 dark:text-emerald-300">
                      {t('tasks.questionCard.caseLabel')}
                    </p>
                    <p className="whitespace-pre-wrap rounded bg-emerald-50 p-2 text-sm italic text-emerald-600 dark:bg-emerald-900/30 dark:text-emerald-400">
                      {question.case}
                    </p>
                  </div>
                )}

                <div>
                  <p className="mb-1 text-sm font-medium text-emerald-700 dark:text-emerald-300">
                    {t('tasks.questionCard.questionLabel')}
                  </p>
                  <p className="whitespace-pre-wrap rounded bg-emerald-50 p-2 text-sm text-emerald-900 dark:bg-emerald-900/30 dark:text-emerald-100">
                    {question.question || t('tasks.questionCard.noQuestionText')}
                  </p>
                </div>

                <div>
                  <p className="mb-1 text-sm font-medium text-emerald-700 dark:text-emerald-300">
                    {t('tasks.questionCard.answerLabel')}
                  </p>
                  <p className="whitespace-pre-wrap rounded bg-emerald-50 p-2 text-sm text-emerald-900 dark:bg-emerald-900/30 dark:text-emerald-100">
                    {question.reference_answer || t('tasks.questionCard.noAnswerProvided')}
                  </p>
                </div>

                <div>
                  <p className="mb-1 text-sm font-medium text-emerald-700 dark:text-emerald-300">
                    {t('tasks.questionCard.reasoningLabel')}
                  </p>
                  <p className="whitespace-pre-wrap rounded bg-emerald-50 p-2 text-sm text-emerald-900 dark:bg-emerald-900/30 dark:text-emerald-100">
                    {question.reasoning || t('tasks.questionCard.noReasoningProvided')}
                  </p>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

export type { QuestionData }

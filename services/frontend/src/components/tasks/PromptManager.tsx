/**
 * PromptManager - Component for managing prompts in generation tasks
 * Similar to QuestionManager but designed for text generation prompts
 */

import { Button } from '@/components/shared/Button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/shared/Select'
import { useToast } from '@/components/shared/Toast'
import { useI18n } from '@/contexts/I18nContext'
import { useDefaultConfig } from '@/hooks/useDefaultConfig'
import { api } from '@/lib/api'
import {
  ArrowUpTrayIcon,
  PlusIcon,
  TrashIcon,
} from '@heroicons/react/24/outline'
import React, { useRef, useState } from 'react'

export interface PromptData {
  prompt: string
  expected_output?: string
  metadata?: {
    max_tokens?: number
    temperature?: number
    context?: string
    prompt_type?: 'system' | 'instruction' | 'evaluation'
  }
}

interface PromptManagerProps {
  prompts: PromptData[]
  onPromptsChange: (prompts: PromptData[]) => void
  taskId?: string // Optional taskId for upload functionality
  taskType?: string // Task type for getting default configuration
}

export function PromptManager({
  prompts,
  onPromptsChange,
  taskId,
  taskType = 'generation',
}: PromptManagerProps) {
  const { t } = useI18n()
  const { addToast } = useToast()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [showAddPrompt, setShowAddPrompt] = useState(false)

  // Get default configuration for the task type
  const { config } = useDefaultConfig(taskType)

  const [newPrompt, setNewPrompt] = useState<PromptData>({
    prompt: '',
    expected_output: '',
    metadata: {
      max_tokens: config?.max_tokens || 500,
      temperature: config?.temperature || 0,
      context: '',
      prompt_type: 'instruction' as const,
    },
  })

  const handleAddPrompt = () => {
    if (newPrompt.prompt.trim()) {
      onPromptsChange([...prompts, newPrompt])
      setNewPrompt({
        prompt: '',
        expected_output: '',
        metadata: {
          max_tokens: config?.max_tokens || 500,
          temperature: config?.temperature || 0,
          context: '',
          prompt_type: 'instruction' as const,
        },
      })
      setShowAddPrompt(false)
    }
  }

  const handleRemovePrompt = (index: number) => {
    const updatedPrompts = prompts.filter((_, i) => i !== index)
    onPromptsChange(updatedPrompts)
  }

  const handleUpdatePrompt = (
    index: number,
    field: keyof PromptData,
    value: any
  ) => {
    const updatedPrompts = [...prompts]
    if (field === 'metadata' && updatedPrompts[index].metadata) {
      updatedPrompts[index] = {
        ...updatedPrompts[index],
        metadata: { ...updatedPrompts[index].metadata, ...value },
      }
    } else {
      updatedPrompts[index] = { ...updatedPrompts[index], [field]: value }
    }
    onPromptsChange(updatedPrompts)
  }

  const handleFileUpload = async (
    event: React.ChangeEvent<HTMLInputElement>
  ) => {
    const file = event.target.files?.[0]
    if (!file || !taskId) return

    try {
      // Show loading toast
      addToast(t('tasks.prompts.uploading'), 'info')

      // Use the api.uploadData function which auto-detects prompt content
      const result = await api.uploadData(file, taskId)

      // Refresh the prompts list by fetching from the task
      // For now, we'll show a success message and let the parent component handle refresh
      addToast(
        t('tasks.prompts.uploadSuccess', { count: result.uploaded_items }),
        'success'
      )

      // Clear the file input
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }

      // TODO: Parent component should refresh the task data to get updated prompts
      // This would typically be handled by the parent component
    } catch (error: any) {
      console.error('Failed to upload prompts:', error)
      addToast(error.message || t('tasks.prompts.uploadFailed'), 'error')
    }
  }

  return (
    <div className="space-y-4">
      {/* Existing Prompts */}
      {prompts.length > 0 && (
        <div className="space-y-4">
          {prompts.map((prompt, index) => (
            <div
              key={index}
              className="space-y-3 rounded-lg bg-zinc-50 p-4 dark:bg-zinc-800"
            >
              <div className="flex items-start justify-between">
                <h4 className="text-sm font-medium text-zinc-900 dark:text-white">
                  {t('tasks.prompts.promptNumber', { number: index + 1 })}
                </h4>
                <button
                  onClick={() => handleRemovePrompt(index)}
                  className="text-red-600 hover:text-red-700 dark:text-red-400 dark:hover:text-red-300"
                >
                  <TrashIcon className="h-5 w-5" />
                </button>
              </div>

              <div>
                <label className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
                  {t('tasks.prompts.promptText')}
                </label>
                <textarea
                  value={prompt.prompt}
                  onChange={(e) =>
                    handleUpdatePrompt(index, 'prompt', e.target.value)
                  }
                  rows={3}
                  className="block w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-zinc-900 transition-colors focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/20 dark:border-zinc-600 dark:bg-zinc-900 dark:text-white dark:focus:border-emerald-400 dark:focus:ring-emerald-400/20 sm:text-sm"
                  placeholder={t('tasks.prompts.promptPlaceholder')}
                />
              </div>

              <div>
                <label className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
                  {t('tasks.prompts.expectedOutput')}
                </label>
                <textarea
                  value={prompt.expected_output || ''}
                  onChange={(e) =>
                    handleUpdatePrompt(index, 'expected_output', e.target.value)
                  }
                  rows={3}
                  className="block w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-zinc-900 transition-colors focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/20 dark:border-zinc-600 dark:bg-zinc-900 dark:text-white dark:focus:border-emerald-400 dark:focus:ring-emerald-400/20 sm:text-sm"
                  placeholder={t('tasks.prompts.expectedOutputPlaceholder')}
                />
              </div>

              <div>
                <label className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
                  {t('tasks.prompts.promptType')}
                </label>
                <Select
                  value={prompt.metadata?.prompt_type || 'instruction'}
                  onValueChange={(v) =>
                    handleUpdatePrompt(index, 'metadata', {
                      prompt_type: v as
                        | 'system'
                        | 'instruction'
                        | 'evaluation',
                    })
                  }
                  displayValue={
                    (prompt.metadata?.prompt_type || 'instruction') === 'system' ? t('tasks.prompts.system') :
                    (prompt.metadata?.prompt_type || 'instruction') === 'instruction' ? t('tasks.prompts.instruction') :
                    t('tasks.prompts.evaluation')
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="system">{t('tasks.prompts.system')}</SelectItem>
                    <SelectItem value="instruction">
                      {t('tasks.prompts.instruction')}
                    </SelectItem>
                    <SelectItem value="evaluation">
                      {t('tasks.prompts.evaluation')}
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
                    {t('tasks.prompts.maxTokens')}
                  </label>
                  <input
                    type="number"
                    value={prompt.metadata?.max_tokens || 500}
                    onChange={(e) =>
                      handleUpdatePrompt(index, 'metadata', {
                        max_tokens: parseInt(e.target.value),
                      })
                    }
                    className="block w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-zinc-900 transition-colors focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/20 dark:border-zinc-600 dark:bg-zinc-900 dark:text-white dark:focus:border-emerald-400 dark:focus:ring-emerald-400/20 sm:text-sm"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
                    {t('tasks.prompts.temperature')}
                  </label>
                  <input
                    type="number"
                    step="0.1"
                    min="0"
                    max="2"
                    value={
                      prompt.metadata?.temperature || config?.temperature || 0
                    }
                    onChange={(e) =>
                      handleUpdatePrompt(index, 'metadata', {
                        temperature: parseFloat(e.target.value),
                      })
                    }
                    className="block w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-zinc-900 transition-colors focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/20 dark:border-zinc-600 dark:bg-zinc-900 dark:text-white dark:focus:border-emerald-400 dark:focus:ring-emerald-400/20 sm:text-sm"
                  />
                </div>
              </div>

              <div>
                <label className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
                  {t('tasks.prompts.context')}
                </label>
                <input
                  type="text"
                  value={prompt.metadata?.context || ''}
                  onChange={(e) =>
                    handleUpdatePrompt(index, 'metadata', {
                      context: e.target.value,
                    })
                  }
                  className="block w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-zinc-900 transition-colors focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/20 dark:border-zinc-600 dark:bg-zinc-900 dark:text-white dark:focus:border-emerald-400 dark:focus:ring-emerald-400/20 sm:text-sm"
                  placeholder={t('tasks.prompts.contextPlaceholder')}
                />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Add Prompt Form */}
      {showAddPrompt && (
        <div className="space-y-3 rounded-lg bg-emerald-50 p-4 dark:bg-emerald-900/20">
          <h4 className="text-sm font-medium text-emerald-900 dark:text-emerald-100">
            {t('tasks.prompts.addNew')}
          </h4>

          <div>
            <label className="mb-1 block text-sm font-medium text-emerald-700 dark:text-emerald-300">
              {t('tasks.prompts.promptText')}
            </label>
            <textarea
              value={newPrompt.prompt}
              onChange={(e) =>
                setNewPrompt({ ...newPrompt, prompt: e.target.value })
              }
              rows={3}
              className="block w-full rounded-lg border border-emerald-300 bg-white px-3 py-2 text-emerald-900 transition-colors focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/20 dark:border-emerald-600 dark:bg-emerald-900/20 dark:text-emerald-100 dark:focus:border-emerald-400 dark:focus:ring-emerald-400/20 sm:text-sm"
              placeholder={t('tasks.prompts.promptPlaceholder')}
            />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-emerald-700 dark:text-emerald-300">
              {t('tasks.prompts.expectedOutput')}
            </label>
            <textarea
              value={newPrompt.expected_output}
              onChange={(e) =>
                setNewPrompt({ ...newPrompt, expected_output: e.target.value })
              }
              rows={3}
              className="block w-full rounded-lg border border-emerald-300 bg-white px-3 py-2 text-emerald-900 transition-colors focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/20 dark:border-emerald-600 dark:bg-emerald-900/20 dark:text-emerald-100 dark:focus:border-emerald-400 dark:focus:ring-emerald-400/20 sm:text-sm"
              placeholder={t('tasks.prompts.expectedOutputPlaceholder')}
            />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-emerald-700 dark:text-emerald-300">
              {t('tasks.prompts.promptType')}
            </label>
            <Select
              value={newPrompt.metadata?.prompt_type || 'instruction'}
              onValueChange={(v) =>
                setNewPrompt({
                  ...newPrompt,
                  metadata: {
                    ...newPrompt.metadata,
                    prompt_type: v as
                      | 'system'
                      | 'instruction'
                      | 'evaluation',
                  },
                })
              }
              displayValue={
                (newPrompt.metadata?.prompt_type || 'instruction') === 'system' ? t('tasks.prompts.system') :
                (newPrompt.metadata?.prompt_type || 'instruction') === 'instruction' ? t('tasks.prompts.instruction') :
                t('tasks.prompts.evaluation')
              }
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="system">{t('tasks.prompts.system')}</SelectItem>
                <SelectItem value="instruction">
                  {t('tasks.prompts.instruction')}
                </SelectItem>
                <SelectItem value="evaluation">
                  {t('tasks.prompts.evaluation')}
                </SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="flex justify-end space-x-3">
            <Button
              onClick={() => setShowAddPrompt(false)}
              variant="text"
              className="text-zinc-700 dark:text-zinc-300"
            >
              {t('tasks.prompts.cancel')}
            </Button>
            <Button
              onClick={handleAddPrompt}
              disabled={!newPrompt.prompt.trim()}
              className="bg-emerald-600 text-white hover:bg-emerald-700"
            >
              {t('tasks.prompts.addPrompt')}
            </Button>
          </div>
        </div>
      )}

      {/* Add Prompt and Upload Buttons */}
      {!showAddPrompt && (
        <div className="flex gap-2">
          <Button
            onClick={() => setShowAddPrompt(true)}
            variant="outline"
            className="flex-1 border-2 border-dashed border-zinc-300 hover:border-emerald-500 dark:border-zinc-600 dark:hover:border-emerald-400"
          >
            <PlusIcon className="mr-2 h-5 w-5" />
            {t('tasks.prompts.addPrompt')}
          </Button>
          {taskId && (
            <>
              <input
                ref={fileInputRef}
                type="file"
                accept=".json"
                onChange={handleFileUpload}
                className="hidden"
              />
              <Button
                onClick={() => fileInputRef.current?.click()}
                variant="outline"
                className="flex-1 border-2 border-dashed border-zinc-300 hover:border-emerald-500 dark:border-zinc-600 dark:hover:border-emerald-400"
              >
                <ArrowUpTrayIcon className="mr-2 h-5 w-5" />
                {t('tasks.prompts.uploadPrompts')}
              </Button>
            </>
          )}
        </div>
      )}

      {prompts.length === 0 && !showAddPrompt && (
        <p className="py-8 text-center text-sm text-zinc-500 dark:text-zinc-400">
          {t('tasks.prompts.emptyState')}
        </p>
      )}
    </div>
  )
}

export function promptsToJson(prompts: PromptData[]): any[] {
  return prompts.map((prompt) => ({
    prompt: prompt.prompt,
    expected_output: prompt.expected_output || null,
    metadata: prompt.metadata || {},
  }))
}

'use client'

import { Alert } from '@/components/shared/Alert'
import { Card } from '@/components/shared/Card'
import { Label } from '@/components/shared/Label'
import { Textarea } from '@/components/shared/Textarea'
import { useI18n } from '@/contexts/I18nContext'
import { cn } from '@/lib/utils'
import { useRef } from 'react'

interface PromptTemplate {
  id: string
  nameKey: string
  descriptionKey: string
  systemPrompt: string
  instructionPrompt: string
}

const PROMPT_TEMPLATES: PromptTemplate[] = [
  {
    id: 'question-answering',
    nameKey: 'projects.creation.wizard.step6.templates.qa.name',
    descriptionKey: 'projects.creation.wizard.step6.templates.qa.description',
    systemPrompt:
      'You are an expert assistant. Answer questions accurately and concisely based on the provided context.',
    instructionPrompt:
      'Context:\n$context\n\nQuestion:\n$question\n\nProvide a detailed answer based on the context above.',
  },
  {
    id: 'legal-analysis',
    nameKey: 'projects.creation.wizard.step6.templates.legal.name',
    descriptionKey:
      'projects.creation.wizard.step6.templates.legal.description',
    systemPrompt:
      'Sie sind ein Experte für deutsches Recht. Analysieren Sie juristische Sachverhalte nach der juristischen Methodik (ODSE).',
    instructionPrompt:
      'Sachverhalt:\n$sachverhalt\n\nErstellen Sie eine vollständige juristische Falllösung mit Gliederung und Begründung.',
  },
  {
    id: 'classification',
    nameKey: 'projects.creation.wizard.step6.templates.classification.name',
    descriptionKey:
      'projects.creation.wizard.step6.templates.classification.description',
    systemPrompt:
      'You are a text classifier. Classify the given text into the appropriate category.',
    instructionPrompt:
      'Text:\n$text\n\nClassify this text and explain your reasoning.',
  },
  {
    id: 'custom',
    nameKey: 'projects.creation.wizard.step6.templates.custom.name',
    descriptionKey:
      'projects.creation.wizard.step6.templates.custom.description',
    systemPrompt: '',
    instructionPrompt: '',
  },
]

interface StepPromptsProps {
  promptTemplate: string
  systemPrompt: string
  instructionPrompt: string
  availableVariables: string[]
  onPromptTemplateChange: (templateId: string) => void
  onSystemPromptChange: (prompt: string) => void
  onInstructionPromptChange: (prompt: string) => void
}

export function StepPrompts({
  promptTemplate,
  systemPrompt,
  instructionPrompt,
  availableVariables,
  onPromptTemplateChange,
  onSystemPromptChange,
  onInstructionPromptChange,
}: StepPromptsProps) {
  const { t } = useI18n()
  const systemPromptRef = useRef<HTMLTextAreaElement>(null)
  const instructionPromptRef = useRef<HTMLTextAreaElement>(null)

  const selectTemplate = (template: PromptTemplate) => {
    onPromptTemplateChange(template.id)
    if (template.id !== 'custom') {
      onSystemPromptChange(template.systemPrompt)
      onInstructionPromptChange(template.instructionPrompt)
    }
  }

  const insertVariable = (
    variable: string,
    ref: React.RefObject<HTMLTextAreaElement | null>,
    currentValue: string,
    onChange: (val: string) => void
  ) => {
    const textarea = ref.current
    const insertion = `$${variable}`
    if (textarea) {
      const start = textarea.selectionStart
      const end = textarea.selectionEnd
      const newValue =
        currentValue.substring(0, start) +
        insertion +
        currentValue.substring(end)
      onChange(newValue)
      // Restore cursor position after insertion
      requestAnimationFrame(() => {
        textarea.selectionStart = textarea.selectionEnd =
          start + insertion.length
        textarea.focus()
      })
    } else {
      onChange(currentValue + insertion)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="mb-2 text-2xl font-semibold text-zinc-900 dark:text-white">
          {t('projects.creation.wizard.step6.title')}
        </h2>
        <p className="text-zinc-600 dark:text-zinc-400">
          {t('projects.creation.wizard.step6.subtitle')}
        </p>
      </div>

      {/* Template selector */}
      <div>
        <Label>{t('projects.creation.wizard.step6.templateLabel')}</Label>
        <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
          {PROMPT_TEMPLATES.map((template) => (
            <Card
              key={template.id}
              className={cn(
                'cursor-pointer p-3 transition-colors hover:border-emerald-600',
                promptTemplate === template.id &&
                  'border-emerald-600 bg-emerald-50 dark:bg-emerald-900/20'
              )}
              onClick={() => selectTemplate(template)}
              data-testid={`wizard-prompt-template-${template.id}`}
            >
              <p className="text-sm font-medium text-zinc-900 dark:text-white">
                {t(template.nameKey)}
              </p>
              <p className="text-xs text-zinc-500 dark:text-zinc-400">
                {t(template.descriptionKey)}
              </p>
            </Card>
          ))}
        </div>
      </div>

      {/* System Prompt */}
      <div>
        <Label htmlFor="system-prompt">
          {t('projects.creation.wizard.step6.systemPromptLabel')}
        </Label>
        <p className="mb-2 text-xs text-zinc-500 dark:text-zinc-400">
          {t('projects.creation.wizard.step6.systemPromptHint')}
        </p>
        <Textarea
          id="system-prompt"
          ref={systemPromptRef}
          placeholder={t(
            'projects.creation.wizard.step6.systemPromptPlaceholder'
          )}
          value={systemPrompt}
          onChange={(e) => onSystemPromptChange(e.target.value)}
          rows={5}
          className="font-mono text-sm"
          data-testid="wizard-system-prompt"
        />
        {availableVariables.length > 0 && (
          <div className="mt-1 flex flex-wrap gap-1">
            {availableVariables.map((v) => (
              <button
                key={`sys-${v}`}
                type="button"
                onClick={() =>
                  insertVariable(
                    v,
                    systemPromptRef,
                    systemPrompt,
                    onSystemPromptChange
                  )
                }
                className="rounded bg-zinc-100 px-1.5 py-0.5 font-mono text-xs text-zinc-600 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-400 dark:hover:bg-zinc-700"
              >
                ${v}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Instruction Prompt */}
      <div>
        <Label htmlFor="instruction-prompt">
          {t('projects.creation.wizard.step6.instructionPromptLabel')}
        </Label>
        <p className="mb-2 text-xs text-zinc-500 dark:text-zinc-400">
          {t('projects.creation.wizard.step6.instructionPromptHint')}
        </p>
        <Textarea
          id="instruction-prompt"
          ref={instructionPromptRef}
          placeholder={t(
            'projects.creation.wizard.step6.instructionPromptPlaceholder'
          )}
          value={instructionPrompt}
          onChange={(e) => onInstructionPromptChange(e.target.value)}
          rows={5}
          className="font-mono text-sm"
          data-testid="wizard-instruction-prompt"
        />
        {availableVariables.length > 0 && (
          <div className="mt-1 flex flex-wrap gap-1">
            {availableVariables.map((v) => (
              <button
                key={`inst-${v}`}
                type="button"
                onClick={() =>
                  insertVariable(
                    v,
                    instructionPromptRef,
                    instructionPrompt,
                    onInstructionPromptChange
                  )
                }
                className="rounded bg-zinc-100 px-1.5 py-0.5 font-mono text-xs text-zinc-600 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-400 dark:hover:bg-zinc-700"
              >
                ${v}
              </button>
            ))}
          </div>
        )}
      </div>

      {availableVariables.length === 0 && (
        <Alert variant="info">
          <p className="text-sm">
            {t('projects.creation.wizard.step6.noVariablesNote')}
          </p>
        </Alert>
      )}
    </div>
  )
}

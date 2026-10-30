/**
 * Read-only prompt block for the project page's Prompts card: a small label
 * above the prompt text in a scrollable monospace box. Object-shaped prompts
 * (prompt structures with template + fields) render as pretty JSON.
 */

'use client'

import { useI18n } from '@/contexts/I18nContext'

interface PromptTextProps {
  label: string
  value: unknown
}

export function promptToText(value: unknown): string {
  if (value === null || value === undefined) return ''
  if (typeof value === 'string') return value
  return JSON.stringify(value, null, 2)
}

export function PromptText({ label, value }: PromptTextProps) {
  const { t } = useI18n()
  const text = promptToText(value)

  return (
    <div>
      <p className="mb-1 text-xs font-medium text-zinc-600 dark:text-zinc-400">
        {label}
      </p>
      {text.trim() ? (
        <pre className="max-h-72 overflow-auto rounded-md border border-zinc-200 bg-zinc-50 p-3 font-mono text-xs leading-relaxed whitespace-pre-wrap text-zinc-800 dark:border-zinc-700 dark:bg-zinc-800/60 dark:text-zinc-200">
          {text}
        </pre>
      ) : (
        <p className="text-xs text-zinc-400 italic dark:text-zinc-500">
          {t('project.prompts.empty')}
        </p>
      )}
    </div>
  )
}

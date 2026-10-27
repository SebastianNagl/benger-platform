'use client'

import { Textarea } from '@/components/shared/Textarea'
import { useI18n } from '@/contexts/I18nContext'
import { InformationCircleIcon } from '@heroicons/react/24/outline'
import clsx from 'clsx'
import { useCallback, useMemo, useRef } from 'react'

interface PromptTemplateEditorProps {
  value: string
  onChange: (template: string) => void
  /**
   * Variables known to be available for substitution. The component
   * shows pills for these; clicking inserts `{{name}}` at the cursor.
   * Variables detected in the textarea but absent from this list are
   * surfaced as a warning ("not yet mapped").
   */
  knownVariables: string[]
  /**
   * Dimension keys from custom_criteria. Used to detect when the user
   * has authored a prompt that asks the judge to score dimensions
   * inline (we can't auto-validate the prompt's semantics, but we can
   * sanity-check that every dimension key is mentioned somewhere).
   */
  dimensionKeys?: string[]
  placeholder?: string
}

const PLACEHOLDER_REGEX = /\{\{(\w+)\}\}|\{(\w+)\}/g

export function PromptTemplateEditor({
  value,
  onChange,
  knownVariables,
  dimensionKeys = [],
  placeholder,
}: PromptTemplateEditorProps) {
  const { t } = useI18n()
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const detectedVariables = useMemo(() => {
    const found = new Set<string>()
    const re = new RegExp(PLACEHOLDER_REGEX.source, 'g')
    let m: RegExpExecArray | null
    while ((m = re.exec(value || '')) !== null) {
      found.add(m[1] || m[2])
    }
    return Array.from(found)
  }, [value])

  const unmappedVariables = detectedVariables.filter(
    (v) => !knownVariables.includes(v),
  )
  const missingDimensions = dimensionKeys.filter(
    (k) => !(value || '').includes(k),
  )

  const insertAtCursor = useCallback(
    (snippet: string) => {
      const ta = textareaRef.current
      if (!ta) {
        onChange((value || '') + snippet)
        return
      }
      const start = ta.selectionStart ?? value.length
      const end = ta.selectionEnd ?? value.length
      const next =
        (value || '').slice(0, start) + snippet + (value || '').slice(end)
      onChange(next)
      requestAnimationFrame(() => {
        ta.focus()
        const cursor = start + snippet.length
        ta.setSelectionRange(cursor, cursor)
      })
    },
    [onChange, value],
  )

  return (
    <div className="space-y-2">
      <label className="block text-xs font-medium text-zinc-700 dark:text-zinc-300">
        {t('evaluationBuilder.parameters.customPromptTemplate')}
      </label>

      <Textarea
        ref={textareaRef}
        value={value || ''}
        onChange={(e) => onChange(e.target.value)}
        placeholder={
          placeholder ||
          t('evaluationBuilder.parameters.promptTemplatePlaceholder')
        }
        rows={14}
        spellCheck={false}
        className="font-mono text-xs leading-relaxed sm:text-xs"
      />

      <div className="flex flex-wrap gap-2">
        <span className="text-xs text-zinc-500 dark:text-zinc-400">
          {t('evaluationBuilder.parameters.insertVariable')}:
        </span>
        {knownVariables.map((name) => {
          const used = detectedVariables.includes(name)
          return (
            <button
              key={name}
              type="button"
              onClick={() => insertAtCursor(`{{${name}}}`)}
              className={clsx(
                'rounded-full border px-2 py-0.5 text-xs transition-colors',
                used
                  ? 'border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300'
                  : 'border-zinc-300 bg-white text-zinc-700 hover:bg-zinc-50 dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-300',
              )}
              title={
                used
                  ? t('evaluationBuilder.parameters.variableInUse')
                  : t('evaluationBuilder.parameters.variableAvailable')
              }
            >
              {used ? '✓ ' : ''}
              {`{{${name}}}`}
            </button>
          )
        })}
      </div>

      {unmappedVariables.length > 0 && (
        <div className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800 dark:border-amber-800/40 dark:bg-amber-900/20 dark:text-amber-200">
          <InformationCircleIcon className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <div>
            {t('evaluationBuilder.parameters.unmappedVariables')}:{' '}
            <code className="font-mono">{unmappedVariables.join(', ')}</code>.{' '}
            {t('evaluationBuilder.parameters.unmappedVariablesHint')}
          </div>
        </div>
      )}

      {missingDimensions.length > 0 && (
        <div className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800 dark:border-amber-800/40 dark:bg-amber-900/20 dark:text-amber-200">
          <InformationCircleIcon className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <div>
            {t('evaluationBuilder.parameters.missingDimensions')}:{' '}
            <code className="font-mono">{missingDimensions.join(', ')}</code>.{' '}
            {t('evaluationBuilder.parameters.missingDimensionsHint')}
          </div>
        </div>
      )}
    </div>
  )
}

'use client'

import { useCallback, useMemo, useRef } from 'react'
import { useI18n } from '@/contexts/I18nContext'
import { InformationCircleIcon } from '@heroicons/react/24/outline'
import clsx from 'clsx'

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
    (v) => !knownVariables.includes(v)
  )
  const missingDimensions = dimensionKeys.filter(
    (k) => !(value || '').includes(k)
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
      const next = (value || '').slice(0, start) + snippet + (value || '').slice(end)
      onChange(next)
      requestAnimationFrame(() => {
        ta.focus()
        const cursor = start + snippet.length
        ta.setSelectionRange(cursor, cursor)
      })
    },
    [onChange, value]
  )

  return (
    <div className="space-y-2">
      <label className="block text-xs font-medium text-gray-700 dark:text-gray-300">
        {t('evaluationBuilder.parameters.customPromptTemplate', 'Prompt Template')}
      </label>

      <textarea
        ref={textareaRef}
        value={value || ''}
        onChange={(e) => onChange(e.target.value)}
        placeholder={
          placeholder ||
          'Du bist ein juristischer Korrektor.\n\nFall: {{fall}}\nFrage: {{task}}\nReferenz: {{binary_solution}} / {{reasoning}}\n\nZu bewerten: {{answer}}\n\nAntworte als JSON mit den Feldern scores, total_score, overall_assessment.'
        }
        rows={14}
        spellCheck={false}
        className="w-full rounded-md border border-gray-300 px-3 py-2 font-mono text-xs leading-relaxed dark:border-gray-600 dark:bg-gray-800"
      />

      <div className="flex flex-wrap gap-2">
        <span className="text-xs text-gray-500 dark:text-gray-400">
          {t('evaluationBuilder.parameters.insertVariable', 'Insert variable')}:
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
                  ? 'border-green-300 bg-green-50 text-green-700 dark:border-green-700 dark:bg-green-900/30 dark:text-green-300'
                  : 'border-gray-300 bg-white text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-300'
              )}
              title={
                used
                  ? t('evaluationBuilder.parameters.variableInUse', 'Already used in template')
                  : t('evaluationBuilder.parameters.variableAvailable', 'Click to insert')
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
            {t(
              'evaluationBuilder.parameters.unmappedVariables',
              'Template references variables not yet mapped to task fields'
            )}
            :{' '}
            <code className="font-mono">{unmappedVariables.join(', ')}</code>.{' '}
            {t(
              'evaluationBuilder.parameters.unmappedVariablesHint',
              'Add them to Field Mappings below so they resolve to task data.'
            )}
          </div>
        </div>
      )}

      {missingDimensions.length > 0 && (
        <div className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800 dark:border-amber-800/40 dark:bg-amber-900/20 dark:text-amber-200">
          <InformationCircleIcon className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <div>
            {t(
              'evaluationBuilder.parameters.missingDimensions',
              'Dimension keys not mentioned in the prompt'
            )}
            : <code className="font-mono">{missingDimensions.join(', ')}</code>.{' '}
            {t(
              'evaluationBuilder.parameters.missingDimensionsHint',
              "The judge won't know to score them unless they appear in the prompt's instructions and JSON schema example."
            )}
          </div>
        </div>
      )}
    </div>
  )
}

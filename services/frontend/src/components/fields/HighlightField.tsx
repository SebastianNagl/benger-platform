/**
 * Highlight Field Component
 *
 * Text highlighting/annotation field for the template system.
 *
 * Issue #216: Implement Unified Task Configuration and Display System
 */

import { useI18n } from '@/contexts/I18nContext'
import React, { useCallback, useMemo, useState } from 'react'
import { BaseFieldProps, FieldWrapper } from './BaseField'

interface Highlight {
  start: number
  end: number
  text: string
  label?: string
}

export function HighlightField({
  field,
  value,
  onChange,
  readonly = false,
  errors = [],
  context,
  className = '',
}: BaseFieldProps) {
  const { t } = useI18n()
  const [sourceText] = useState(
    field.metadata?.source_text || t('fields.noTextForHighlighting')
  )
  const highlights = useMemo<Highlight[]>(
    () => (Array.isArray(value) ? value : []),
    [value]
  )

  const handleTextSelection = useCallback(() => {
    if (readonly) return

    const selection = window.getSelection()
    if (!selection || selection.isCollapsed) return

    const range = selection.getRangeAt(0)
    const container = document.getElementById(`highlight-${field.name}`)

    if (!container || !container.contains(range.commonAncestorContainer)) return

    const start = range.startOffset
    const end = range.endOffset
    const text = selection.toString()

    if (text.trim()) {
      const newHighlight: Highlight = {
        start,
        end,
        text,
        label: field.choices?.[0], // Use first choice as default label
      }

      onChange([...highlights, newHighlight])
      selection.removeAllRanges()
    }
  }, [highlights, onChange, readonly, field])

  const removeHighlight = (index: number) => {
    if (readonly) return
    onChange(highlights.filter((_, i) => i !== index))
  }

  const renderHighlightedText = () => {
    if (highlights.length === 0) {
      return sourceText
    }

    // Sort highlights by start position
    const sortedHighlights = [...highlights].sort((a, b) => a.start - b.start)

    const elements: React.ReactNode[] = []
    let lastEnd = 0

    sortedHighlights.forEach((highlight, index) => {
      // Add text before highlight
      if (highlight.start > lastEnd) {
        elements.push(
          <span key={`text-${lastEnd}`}>
            {sourceText.substring(lastEnd, highlight.start)}
          </span>
        )
      }

      // Add highlighted text
      elements.push(
        <span
          key={`highlight-${index}`}
          className="group relative cursor-pointer rounded bg-yellow-200 px-1 dark:bg-yellow-800"
          onClick={() => removeHighlight(index)}
        >
          {highlight.text}
          {!readonly && (
            <span className="absolute -top-6 left-0 hidden rounded bg-gray-800 px-2 py-1 text-xs text-white group-hover:block">
              {t('fields.clickToRemove')}
            </span>
          )}
        </span>
      )

      lastEnd = highlight.end
    })

    // Add remaining text
    if (lastEnd < sourceText.length) {
      elements.push(
        <span key={`text-${lastEnd}`}>{sourceText.substring(lastEnd)}</span>
      )
    }

    return elements
  }

  return (
    <FieldWrapper field={field} errors={errors} className={className}>
      <div
        id={`highlight-${field.name}`}
        className={`rounded-md border border-gray-300 p-4 dark:border-gray-600 ${
          readonly ? 'bg-gray-50 dark:bg-gray-800' : 'bg-white dark:bg-gray-700'
        }`}
        onMouseUp={handleTextSelection}
      >
        <div className="prose max-w-none dark:prose-invert">
          {renderHighlightedText()}
        </div>
      </div>

      {!readonly && (
        <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
          {t('fields.highlightInstructions')}
        </p>
      )}

      {highlights.length > 0 && (
        <div className="mt-3">
          <h4 className="mb-2 text-sm font-medium text-gray-700 dark:text-gray-300">
            {t('fields.highlightsCount', { count: highlights.length })}
          </h4>
          <ul className="space-y-1 text-sm">
            {highlights.map((highlight, index) => (
              <li key={index} className="flex items-center justify-between">
                <span className="text-gray-600 dark:text-gray-400">
                  "{highlight.text}"
                </span>
                {!readonly && (
                  <button
                    type="button"
                    onClick={() => removeHighlight(index)}
                    className="text-xs text-red-600 hover:text-red-500"
                  >
                    {t('fields.remove')}
                  </button>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </FieldWrapper>
  )
}

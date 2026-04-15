/**
 * Text Highlight Field Component
 *
 * Allows annotators to highlight and label text passages.
 * Features:
 * - Multiple highlight colors/categories
 * - Overlapping highlights
 * - Comments on highlights
 * - Keyboard navigation
 *
 * Issue #218: ize Annotation System with Label Studio-Inspired Architecture
 */

import { ChatBubbleLeftIcon, TrashIcon } from '@heroicons/react/24/outline'
import React, { useCallback, useMemo, useRef, useState } from 'react'
import { useI18n } from '@/contexts/I18nContext'
import { BaseFieldProps, FieldWrapper } from './BaseField'

interface TextHighlight {
  id: string
  start: number
  end: number
  text: string
  label: string
  color: string
  comment?: string
}

interface HighlightLabel {
  id: string
  name: string
  color: string
  shortcut?: string
}

interface TextHighlightValue {
  text: string
  highlights: TextHighlight[]
}

const DEFAULT_LABELS: HighlightLabel[] = [
  { id: 'entity', name: 'Entity', color: '#60A5FA', shortcut: '1' },
  { id: 'claim', name: 'Claim', color: '#34D399', shortcut: '2' },
  { id: 'evidence', name: 'Evidence', color: '#FBBF24', shortcut: '3' },
  { id: 'reasoning', name: 'Reasoning', color: '#A78BFA', shortcut: '4' },
  { id: 'conclusion', name: 'Conclusion', color: '#F87171', shortcut: '5' },
]

export function TextHighlightField({
  field,
  value,
  onChange,
  readonly = false,
  errors = [],
  context,
  className = '',
}: BaseFieldProps<TextHighlightValue>) {
  const { t } = useI18n()
  const [selectedLabel, setSelectedLabel] = useState<HighlightLabel>(
    DEFAULT_LABELS[0]
  )
  const [showLabelMenu, setShowLabelMenu] = useState(false)
  const [selectedHighlight, setSelectedHighlight] = useState<string | null>(
    null
  )
  const textRef = useRef<HTMLDivElement>(null)

  const labels = (field as any).options?.labels || DEFAULT_LABELS
  const text = value?.text || ''
  const highlights = useMemo(() => value?.highlights || [], [value?.highlights])

  // Sort highlights by position for rendering
  const sortedHighlights = useMemo(() => {
    return [...highlights].sort((a, b) => a.start - b.start)
  }, [highlights])

  // Handle text selection and highlighting
  const handleTextSelection = useCallback(() => {
    if (readonly) return

    const selection = window.getSelection()
    if (!selection || selection.rangeCount === 0) return

    const range = selection.getRangeAt(0)
    const selectedText = selection.toString().trim()

    if (!selectedText || !textRef.current) return

    // Calculate character positions
    const textContent = textRef.current.textContent || ''
    const preSelectionRange = range.cloneRange()
    preSelectionRange.selectNodeContents(textRef.current)
    preSelectionRange.setEnd(range.startContainer, range.startOffset)
    const start = preSelectionRange.toString().length
    const end = start + selectedText.length

    // Create new highlight
    const newHighlight: TextHighlight = {
      id: `highlight-${Date.now()}`,
      start,
      end,
      text: selectedText,
      label: selectedLabel.name,
      color: selectedLabel.color,
    }

    // Add to highlights
    const newHighlights = [...highlights, newHighlight]
    onChange({
      text,
      highlights: newHighlights,
    })

    // Clear selection
    selection.removeAllRanges()
  }, [readonly, selectedLabel, highlights, text, onChange])

  // Remove highlight
  const handleRemoveHighlight = useCallback(
    (highlightId: string) => {
      if (readonly) return

      const newHighlights = highlights.filter((h) => h.id !== highlightId)
      onChange({
        text,
        highlights: newHighlights,
      })
      setSelectedHighlight(null)
    },
    [readonly, highlights, text, onChange]
  )

  // Update highlight comment
  const handleUpdateComment = useCallback(
    (highlightId: string, comment: string) => {
      if (readonly) return

      const newHighlights = highlights.map((h) =>
        h.id === highlightId ? { ...h, comment } : h
      )
      onChange({
        text,
        highlights: newHighlights,
      })
    },
    [readonly, highlights, text, onChange]
  )

  // Render text with highlights
  const renderHighlightedText = useMemo(() => {
    if (!text) return null

    // Create segments from highlights
    const segments: Array<{
      start: number
      end: number
      text: string
      highlights: TextHighlight[]
    }> = []

    // Add all segment boundaries
    const boundaries = new Set([0, text.length])
    highlights.forEach((h) => {
      boundaries.add(h.start)
      boundaries.add(h.end)
    })

    // Sort boundaries
    const sortedBoundaries = Array.from(boundaries).sort((a, b) => a - b)

    // Create segments
    for (let i = 0; i < sortedBoundaries.length - 1; i++) {
      const start = sortedBoundaries[i]
      const end = sortedBoundaries[i + 1]
      const segmentText = text.substring(start, end)

      // Find highlights that cover this segment
      const segmentHighlights = highlights.filter(
        (h) => h.start <= start && h.end >= end
      )

      segments.push({
        start,
        end,
        text: segmentText,
        highlights: segmentHighlights,
      })
    }

    return segments.map((segment, index) => {
      const isHighlighted = segment.highlights.length > 0
      const topHighlight = segment.highlights[segment.highlights.length - 1]

      if (!isHighlighted) {
        return <span key={index}>{segment.text}</span>
      }

      return (
        <span
          key={index}
          className="highlighted-text relative cursor-pointer"
          style={{
            backgroundColor: topHighlight.color + '40',
            borderBottom: `2px solid ${topHighlight.color}`,
            padding: '2px 0',
          }}
          onClick={() => setSelectedHighlight(topHighlight.id)}
          title={`${topHighlight.label}${topHighlight.comment ? ': ' + topHighlight.comment : ''}`}
        >
          {segment.text}
          {segment.highlights.length > 1 && (
            <span className="absolute -right-1 -top-1 flex h-3 w-3 items-center justify-center rounded-full bg-gray-600 text-xs text-white">
              {segment.highlights.length}
            </span>
          )}
        </span>
      )
    })
  }, [text, highlights])

  // Keyboard shortcuts
  React.useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (readonly) return

      // Number keys for quick label selection
      const key = e.key
      if (key >= '1' && key <= '9') {
        const index = parseInt(key) - 1
        if (labels[index]) {
          e.preventDefault()
          setSelectedLabel(labels[index])
        }
      }

      // Delete key to remove selected highlight
      if (e.key === 'Delete' && selectedHighlight) {
        e.preventDefault()
        handleRemoveHighlight(selectedHighlight)
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [readonly, labels, selectedHighlight, handleRemoveHighlight])

  return (
    <FieldWrapper field={field} errors={errors} className={className}>
      <div className="text-highlight-field">
        {/* Label selector */}
        {!readonly && (
          <div className="mb-3 flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <span className="text-sm text-gray-600 dark:text-gray-400">
                {t('labeling.textHighlight.highlightWith')}:
              </span>
              <div className="flex items-center space-x-1">
                {labels.map((label: any) => (
                  <button
                    key={label.id}
                    onClick={() => setSelectedLabel(label)}
                    className={`rounded-md px-3 py-1 text-sm transition-colors ${
                      selectedLabel.id === label.id
                        ? 'text-white'
                        : 'text-gray-700 hover:opacity-80 dark:text-gray-300'
                    }`}
                    style={{
                      backgroundColor:
                        selectedLabel.id === label.id
                          ? label.color
                          : label.color + '20',
                    }}
                    title={`${label.name} (${label.shortcut})`}
                  >
                    {label.name}
                    {label.shortcut && (
                      <span className="ml-1 text-xs opacity-60">
                        {label.shortcut}
                      </span>
                    )}
                  </button>
                ))}
              </div>
            </div>
            <div className="text-xs text-gray-500 dark:text-gray-500">
              {highlights.length} {highlights.length !== 1 ? t('labeling.textHighlight.highlightsPlural') : t('labeling.textHighlight.highlightSingular')}
            </div>
          </div>
        )}

        {/* Text display area */}
        <div
          ref={textRef}
          className={`text-display-area rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800 ${
            readonly ? 'cursor-default' : 'cursor-text'
          }`}
          onMouseUp={handleTextSelection}
          style={{
            lineHeight: '1.8',
            fontSize: '15px',
            fontFamily: 'system-ui, -apple-system, sans-serif',
          }}
        >
          {renderHighlightedText}
        </div>

        {/* Highlights list */}
        {highlights.length > 0 && (
          <div className="mt-3 space-y-2">
            <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300">
              {t('labeling.textHighlight.highlightsTitle')}
            </h4>
            <div className="max-h-48 space-y-1 overflow-y-auto">
              {sortedHighlights.map((highlight) => (
                <div
                  key={highlight.id}
                  className={`flex cursor-pointer items-start space-x-2 rounded-md p-2 transition-colors ${
                    selectedHighlight === highlight.id
                      ? 'bg-gray-100 dark:bg-gray-700'
                      : 'hover:bg-gray-50 dark:hover:bg-gray-800'
                  }`}
                  onClick={() => setSelectedHighlight(highlight.id)}
                >
                  <div
                    className="mt-0.5 h-3 w-3 flex-shrink-0 rounded-full"
                    style={{ backgroundColor: highlight.color }}
                  />
                  <div className="flex-1 text-sm">
                    <div className="flex items-center space-x-2">
                      <span className="font-medium text-gray-700 dark:text-gray-300">
                        {highlight.label}
                      </span>
                      <span className="text-gray-500 dark:text-gray-500">
                        ({highlight.start}-{highlight.end})
                      </span>
                    </div>
                    <p className="italic text-gray-600 dark:text-gray-400">
                      "{highlight.text}"
                    </p>
                    {highlight.comment && (
                      <p className="mt-1 text-xs text-gray-500 dark:text-gray-500">
                        <ChatBubbleLeftIcon className="mr-1 inline h-3 w-3" />
                        {highlight.comment}
                      </p>
                    )}
                  </div>
                  {!readonly && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        handleRemoveHighlight(highlight.id)
                      }}
                      className="text-red-600 hover:text-red-700 dark:text-red-400 dark:hover:text-red-300"
                      title={t('labeling.textHighlight.removeHighlight')}
                    >
                      <TrashIcon className="h-4 w-4" />
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Instructions */}
        {!readonly && (
          <div className="mt-3 text-xs text-gray-500 dark:text-gray-500">
            <strong>{t('labeling.textHighlight.instructionsLabel')}:</strong> {t('labeling.textHighlight.instructionsText', { max: String(labels.length) })}
          </div>
        )}
      </div>
    </FieldWrapper>
  )
}

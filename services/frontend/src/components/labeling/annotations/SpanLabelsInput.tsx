/**
 * SpanLabelsInput Component
 *
 * NER-style span annotation component following Label Studio patterns.
 * Allows users to select text spans and assign labels to them.
 *
 * Issue #964: Add Span Annotation as a project type for NER and text highlighting
 *
 * Label Studio Format:
 * - Uses <Labels name="label" toName="text"> with child <Label> elements
 * - Produces annotations with {start, end, text, labels} in value
 *
 * References:
 * - Label Studio Labels tag: https://labelstud.io/tags/labels
 * - CoNLL-2003 NER format: https://www.clips.uantwerpen.be/conll2003/ner/
 */

'use client'

import { buildSpanAnnotationResult } from '@/lib/labelConfig/dataBinding'
import { AnnotationComponentProps } from '@/lib/labelConfig/registry'
import { XMarkIcon } from '@heroicons/react/24/outline'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useI18n } from '@/contexts/I18nContext'

// Helper to compare span arrays for equality
function spansEqual(a: Span[], b: Span[]): boolean {
  if (a.length !== b.length) return false
  return a.every(
    (span, i) =>
      span.id === b[i].id &&
      span.start === b[i].start &&
      span.end === b[i].end &&
      span.text === b[i].text &&
      JSON.stringify(span.labels) === JSON.stringify(b[i].labels)
  )
}

interface SpanLabel {
  value: string
  background: string
  alias?: string
}

interface Span {
  id: string
  start: number
  end: number
  text: string
  labels: string[]
}

interface SpanLabelsInputProps extends AnnotationComponentProps {
  sourceText?: string // Optional - Text content to annotate (from linked Text component)
}

/**
 * Generate a unique span ID
 */
function generateSpanId(): string {
  return `span-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`
}

// Parse initial spans from external value - defined before component to use in useState
function parseInitialSpans(value: any): Span[] {
  if (!value) return []
  if (Array.isArray(value)) {
    return value.map((v) => ({
      id: v.id || generateSpanId(),
      start: v.start || v.value?.start || 0,
      end: v.end || v.value?.end || 0,
      text: v.text || v.value?.text || '',
      labels: v.labels || v.value?.labels || [],
    }))
  }
  return []
}

/**
 * SpanLabelsInput - Main component for NER-style span annotation
 */
export default function SpanLabelsInput({
  config,
  taskData,
  value: externalValue,
  onChange,
  onAnnotation,
  sourceText: propSourceText,
}: SpanLabelsInputProps) {
  const { t } = useI18n()

  // Configuration from parsed XML
  const name = config.props.name || config.name || 'label'
  const toName = config.props.toName || 'text'
  const choice = config.props.choice || 'single' // 'single' or 'multiple' labels per span

  // Get source text from props or resolve from taskData via toName
  const sourceText = useMemo(() => {
    if (propSourceText) return propSourceText
    // Try to get text from taskData using toName reference
    const textValue = taskData[toName] || taskData?.data?.[toName]
    return typeof textValue === 'string' ? textValue : ''
  }, [propSourceText, taskData, toName])

  // Extract labels from children <Label> elements
  const labels: SpanLabel[] = useMemo(() => {
    return config.children
      .filter((child) => child.type === 'Label')
      .map((child) => ({
        value: child.props.value || child.props.content || '',
        background: child.props.background
          ? child.props.background
          : child.props.hotkey
            ? getHotkeyColor(child.props.hotkey)
            : getDefaultColor(child.props.value || ''),
        alias: child.props.alias || child.props.hotkey,
      }))
  }, [config.children])

  // State
  const [spans, setSpans] = useState<Span[]>(() =>
    parseInitialSpans(externalValue)
  )
  const [selectedLabel, setSelectedLabel] = useState<string | null>(
    labels.length > 0 ? labels[0].value : null
  )
  const [pendingSelection, setPendingSelection] = useState<{
    start: number
    end: number
    text: string
  } | null>(null)
  const textContainerRef = useRef<HTMLDivElement>(null)

  // Use refs to store callbacks to avoid infinite loop when parent re-renders
  const onChangeRef = useRef(onChange)
  const onAnnotationRef = useRef(onAnnotation)

  // Keep refs up to date
  useEffect(() => {
    onChangeRef.current = onChange
    onAnnotationRef.current = onAnnotation
  }, [onChange, onAnnotation])

  // Track if we should notify parent (only when spans actually change)
  const previousSpansRef = useRef<Span[]>(spans)

  // Notify parent when spans change (separate from state update to prevent loops)
  useEffect(() => {
    // Only notify if spans actually changed
    if (!spansEqual(spans, previousSpansRef.current)) {
      previousSpansRef.current = spans
      // Use refs to call callbacks without triggering re-renders
      onChangeRef.current(spans)
      const result = buildSpanAnnotationResult(name, toName, spans)
      onAnnotationRef.current(result)
    }
  }, [spans, name, toName])

  // Sync with external value changes (e.g., when task changes and parent clears state)
  const previousExternalValueRef = useRef(externalValue)
  useEffect(() => {
    // Check if external value changed (not just on initial mount)
    const prevVal = previousExternalValueRef.current
    previousExternalValueRef.current = externalValue

    // If external value was cleared (task change), reset spans
    if (
      prevVal !== undefined &&
      (externalValue === undefined ||
        externalValue === null ||
        (Array.isArray(externalValue) && externalValue.length === 0))
    ) {
      // Use ref to check current spans to avoid stale closure
      if (previousSpansRef.current.length > 0) {
        // eslint-disable-next-line react-hooks/set-state-in-effect -- Intentional: clear on external reset
        setSpans([])
        previousSpansRef.current = []
         
        setPendingSelection(null)
      }
    }
    // If external value has new data (loading existing annotation), parse it
    // Only process if this is a genuine external update (not our own onChange feedback)
    else if (
      externalValue &&
      Array.isArray(externalValue) &&
      externalValue.length > 0
    ) {
      const parsed = parseInitialSpans(externalValue)
      // Compare against the ref to avoid stale closure issues
      if (!spansEqual(parsed, previousSpansRef.current)) {
        setSpans(parsed)
        previousSpansRef.current = parsed
      }
    }
  }, [externalValue])

  // Create a new span (notifications handled by useEffect)
  const createSpan = useCallback(
    (start: number, end: number, text: string, labelValues: string[]) => {
      const newSpan: Span = {
        id: generateSpanId(),
        start,
        end,
        text,
        labels: labelValues,
      }

      setSpans((prev) => [...prev, newSpan])
    },
    []
  )

  // Handle text selection
  const handleTextSelection = useCallback(() => {
    const selection = window.getSelection()
    if (!selection || selection.isCollapsed || !textContainerRef.current) {
      return
    }

    const range = selection.getRangeAt(0)
    const container = textContainerRef.current

    // Check if selection is within our text container
    if (!container.contains(range.commonAncestorContainer)) {
      return
    }

    // Calculate character offsets relative to source text
    const selectedText = selection.toString()
    if (!selectedText.trim()) {
      return
    }

    // Find the start offset by counting characters from the beginning
    const preCaretRange = document.createRange()
    preCaretRange.selectNodeContents(container)
    preCaretRange.setEnd(range.startContainer, range.startOffset)
    const startOffset = preCaretRange.toString().length

    const endOffset = startOffset + selectedText.length

    // Store pending selection
    setPendingSelection({
      start: startOffset,
      end: endOffset,
      text: selectedText,
    })

    // If we have a selected label, create the span immediately
    if (selectedLabel) {
      createSpan(startOffset, endOffset, selectedText, [selectedLabel])
      selection.removeAllRanges()
      setPendingSelection(null)
    }
  }, [selectedLabel, createSpan])

  // Apply label to pending selection
  const applyLabelToSelection = useCallback(
    (labelValue: string) => {
      if (!pendingSelection) return

      const labelArray =
        choice === 'multiple'
          ? [labelValue] // In multiple mode, can add more labels later
          : [labelValue]

      createSpan(
        pendingSelection.start,
        pendingSelection.end,
        pendingSelection.text,
        labelArray
      )

      setPendingSelection(null)
      window.getSelection()?.removeAllRanges()
    },
    [pendingSelection, createSpan, choice]
  )

  // Remove a span (notifications handled by useEffect)
  const removeSpan = useCallback((spanId: string) => {
    setSpans((prev) => prev.filter((s) => s.id !== spanId))
  }, [])

  // Keyboard shortcuts for labels (1-9)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Number keys 1-9 for label shortcuts
      if (e.key >= '1' && e.key <= '9') {
        const index = parseInt(e.key) - 1
        if (index < labels.length) {
          const label = labels[index]
          setSelectedLabel(label.value)
          if (pendingSelection) {
            applyLabelToSelection(label.value)
          }
        }
      }
      // Delete/Backspace to remove last span
      if (
        (e.key === 'Delete' || e.key === 'Backspace') &&
        spans.length > 0 &&
        !e.target
      ) {
        removeSpan(spans[spans.length - 1].id)
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [labels, pendingSelection, spans, applyLabelToSelection, removeSpan])

  // Render highlighted text with spans
  const renderHighlightedText = useMemo(() => {
    if (!sourceText) {
      return (
        <span className="italic text-zinc-400">
          {t('labeling.spanLabels.noText')}
        </span>
      )
    }

    if (spans.length === 0) {
      return sourceText
    }

    // Sort spans by start position
    const sortedSpans = [...spans].sort((a, b) => a.start - b.start)

    const elements: React.ReactNode[] = []
    let lastEnd = 0

    sortedSpans.forEach((span, index) => {
      // Add text before this span
      if (span.start > lastEnd) {
        elements.push(
          <span key={`text-${lastEnd}`}>
            {sourceText.substring(lastEnd, span.start)}
          </span>
        )
      }

      // Find the label color
      const labelConfig = labels.find((l) => span.labels.includes(l.value))
      const bgColor = labelConfig?.background || '#fef08a'

      // Add the highlighted span
      elements.push(
        <span
          key={`span-${span.id}`}
          className="group relative cursor-pointer rounded px-0.5"
          style={{ backgroundColor: bgColor, color: getContrastColor(bgColor) }}
          onClick={() => removeSpan(span.id)}
          title={`${span.labels.join(', ')} (${t('labeling.spanLabels.clickToRemove')})`}
        >
          {span.text}
          <span className="absolute -top-6 left-0 z-10 hidden whitespace-nowrap rounded bg-zinc-800 px-2 py-1 text-xs text-white group-hover:block">
            {span.labels.join(', ')} - {t('labeling.spanLabels.clickToRemove')}
          </span>
        </span>
      )

      lastEnd = span.end
    })

    // Add remaining text after last span
    if (lastEnd < sourceText.length) {
      elements.push(
        <span key={`text-${lastEnd}`}>{sourceText.substring(lastEnd)}</span>
      )
    }

    return elements
  }, [sourceText, spans, labels, removeSpan])

  return (
    <div className="span-labels-input space-y-4">
      {/* Label selector */}
      <div className="space-y-2">
        <div className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
          {t('labeling.spanLabels.selectLabelThenHighlight')}
          {labels.some((l) => l.alias) && (
            <span className="ml-2 text-xs text-zinc-500">
              ({t('labeling.spanLabels.orUseKeyboardShortcuts')})
            </span>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          {labels.map((label, index) => (
            <button
              key={label.value}
              type="button"
              onClick={() => {
                setSelectedLabel(label.value)
                if (pendingSelection) {
                  applyLabelToSelection(label.value)
                }
              }}
              className={`rounded-full px-3 py-1.5 text-sm font-medium transition-all ${
                selectedLabel === label.value
                  ? 'ring-2 ring-emerald-500 ring-offset-2 dark:ring-emerald-400'
                  : 'opacity-70 hover:opacity-100'
              }`}
              style={{
                backgroundColor: label.background,
                color: getContrastColor(label.background),
              }}
            >
              {label.alias && (
                <span className="mr-1 rounded bg-white/20 px-1 text-xs">
                  {index + 1}
                </span>
              )}
              {label.value}
            </button>
          ))}
        </div>
      </div>

      {/* Pending selection indicator */}
      {pendingSelection && (
        <div className="rounded-lg border border-emerald-300 bg-emerald-50 p-3 dark:border-emerald-700 dark:bg-emerald-900/20">
          <div className="text-sm text-emerald-800 dark:text-emerald-200">
            {t('labeling.spanLabels.selected')}: "{pendingSelection.text}"
          </div>
          <div className="mt-2 flex flex-wrap gap-2">
            {labels.map((label, index) => (
              <button
                key={label.value}
                type="button"
                onClick={() => applyLabelToSelection(label.value)}
                className="rounded-full px-2.5 py-1 text-xs font-medium transition-opacity hover:opacity-90"
                style={{
                  backgroundColor: label.background,
                  color: getContrastColor(label.background),
                }}
              >
                {index + 1}. {label.value}
              </button>
            ))}
            <button
              type="button"
              onClick={() => {
                setPendingSelection(null)
                window.getSelection()?.removeAllRanges()
              }}
              className="rounded-full bg-zinc-200 px-2.5 py-1 text-xs font-medium text-zinc-700 transition-colors hover:bg-zinc-300 dark:bg-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-600"
            >
              {t('labeling.spanLabels.cancel')}
            </button>
          </div>
        </div>
      )}

      {/* Text content with highlights */}
      <div
        ref={textContainerRef}
        onMouseUp={handleTextSelection}
        onTouchEnd={handleTextSelection}
        className="rounded-lg border border-zinc-200 bg-white p-4 leading-relaxed dark:border-zinc-700 dark:bg-zinc-800"
        style={{ userSelect: 'text' }}
      >
        {renderHighlightedText}
      </div>

      {/* Span list */}
      {spans.length > 0 && (
        <div className="space-y-2">
          <div className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
            {t('labeling.spanLabels.annotations')} ({spans.length})
          </div>
          <div className="max-h-40 space-y-1 overflow-y-auto rounded-lg border border-zinc-200 bg-zinc-50 p-2 dark:border-zinc-700 dark:bg-zinc-900">
            {spans.map((span) => {
              const labelConfig = labels.find((l) =>
                span.labels.includes(l.value)
              )
              return (
                <div
                  key={span.id}
                  className="flex items-center justify-between rounded bg-white p-2 text-sm dark:bg-zinc-800"
                >
                  <div className="flex items-center gap-2">
                    <span
                      className="rounded-full px-2.5 py-0.5 text-xs font-medium"
                      style={{
                        backgroundColor: labelConfig?.background || '#e5e7eb',
                        color: getContrastColor(
                          labelConfig?.background || '#e5e7eb'
                        ),
                      }}
                    >
                      {span.labels.join(', ')}
                    </span>
                    <span className="text-zinc-600 dark:text-zinc-400">
                      "
                      {span.text.length > 30
                        ? span.text.substring(0, 30) + '...'
                        : span.text}
                      "
                    </span>
                    <span className="text-xs text-zinc-400">
                      [{span.start}:{span.end}]
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() => removeSpan(span.id)}
                    className="rounded p-0.5 text-zinc-400 transition-colors hover:bg-red-50 hover:text-red-500 dark:hover:bg-red-900/20"
                    title={t('labeling.spanLabels.removeAnnotation')}
                  >
                    <XMarkIcon className="h-4 w-4" />
                  </button>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Help text */}
      <div className="text-xs text-zinc-500 dark:text-zinc-400">
        <strong>{t('labeling.spanLabels.tipLabel')}:</strong> {t('labeling.spanLabels.tipText')}
      </div>
    </div>
  )
}

// Helper functions

/**
 * Get default color based on label value hash
 */
function getDefaultColor(value: string): string {
  const colors = [
    '#FF6B6B',
    '#4ECDC4',
    '#45B7D1',
    '#96CEB4',
    '#FFEAA7',
    '#DDA0DD',
    '#98D8C8',
    '#F7DC6F',
    '#BB8FCE',
    '#85C1E9',
  ]
  const hash = value
    .split('')
    .reduce((acc, char) => acc + char.charCodeAt(0), 0)
  return colors[hash % colors.length]
}

/**
 * Get color based on hotkey
 */
function getHotkeyColor(hotkey: string): string {
  const hotkeyColors: Record<string, string> = {
    r: '#FF6B6B', // red
    g: '#4ECDC4', // green
    b: '#45B7D1', // blue
    y: '#FFEAA7', // yellow
    p: '#DDA0DD', // purple
    o: '#FFB347', // orange
  }
  return hotkeyColors[hotkey.toLowerCase()] || getDefaultColor(hotkey)
}

/**
 * Get contrasting text color for background
 */
function getContrastColor(bgColor: string): string {
  // Convert hex to RGB
  const hex = bgColor.replace('#', '')
  const r = parseInt(hex.substr(0, 2), 16)
  const g = parseInt(hex.substr(2, 2), 16)
  const b = parseInt(hex.substr(4, 2), 16)

  // Calculate luminance
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255

  return luminance > 0.5 ? '#000000' : '#ffffff'
}

/**
 * MilkdownEditor Component
 *
 * WYSIWYG markdown editor using Milkdown with custom Tailwind styling.
 * Renders styled markdown as you type (true WYSIWYG experience).
 *
 * Issue #1041: Gliederung and Loesung annotation fields
 */

'use client'

import { defaultValueCtx, Editor, editorViewCtx, editorViewOptionsCtx, rootCtx, serializerCtx } from '@milkdown/core'
import { history } from '@milkdown/plugin-history'
import { listener, listenerCtx } from '@milkdown/plugin-listener'
import {
  commonmark,
  toggleStrongCommand,
  toggleEmphasisCommand,
  wrapInBulletListCommand,
  wrapInOrderedListCommand,
} from '@milkdown/preset-commonmark'
import { Milkdown, MilkdownProvider, useEditor, useInstance } from '@milkdown/react'
import { callCommand, replaceAll } from '@milkdown/utils'
import { ChevronDownIcon, ChevronUpIcon } from '@heroicons/react/20/solid'
import { TextSelection } from 'prosemirror-state'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useI18n } from '@/contexts/I18nContext'

import {
  LEGAL_LEVELS,
  extractHeadingsFromMarkdown,
  getNextPrefix,
} from '@/lib/utils/legalHeadingUtils'

interface MilkdownEditorProps {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  minHeight?: number
  className?: string
  showToolbar?: boolean
  readOnly?: boolean
}

// Editor styles for WYSIWYG markdown rendering with Tailwind-compatible design
const editorStyles = `
  /* MilkdownProvider renders an extra wrapper div around .milkdown */
  .milkdown-wrapper > div:has(> .milkdown) {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
  }

  .milkdown-wrapper .milkdown {
    outline: none;
    flex: 1;
    min-height: 0;
    overflow-y: auto;
  }

  .milkdown-wrapper .milkdown .editor {
    outline: none;
    padding: 1rem;
    min-height: var(--editor-min-height, 200px);
  }

  /* ProseMirror focus */
  .milkdown-wrapper .ProseMirror {
    outline: none;
  }

  .milkdown-wrapper .ProseMirror:focus {
    outline: none;
  }

  /* Headers */
  .milkdown-wrapper h1 {
    font-size: 1.875rem;
    font-weight: 700;
    margin-top: 1.5rem;
    margin-bottom: 0.75rem;
    line-height: 1.25;
  }

  .milkdown-wrapper h2 {
    font-size: 1.5rem;
    font-weight: 600;
    margin-top: 1.25rem;
    margin-bottom: 0.5rem;
    line-height: 1.3;
  }

  .milkdown-wrapper h3 {
    font-size: 1.25rem;
    font-weight: 600;
    margin-top: 1rem;
    margin-bottom: 0.5rem;
    line-height: 1.4;
  }

  .milkdown-wrapper h4 {
    font-size: 1.125rem;
    font-weight: 600;
    margin-top: 0.875rem;
    margin-bottom: 0.375rem;
    line-height: 1.4;
  }

  .milkdown-wrapper h5 {
    font-size: 1rem;
    font-weight: 600;
    margin-top: 0.75rem;
    margin-bottom: 0.25rem;
    line-height: 1.5;
  }

  .milkdown-wrapper h6 {
    font-size: 0.9375rem;
    font-weight: 500;
    margin-top: 0.625rem;
    margin-bottom: 0.25rem;
    line-height: 1.5;
  }

  /* Paragraphs */
  .milkdown-wrapper p {
    margin-bottom: 0.75rem;
    line-height: 1.625;
  }

  /* Lists */
  .milkdown-wrapper ul {
    list-style-type: disc;
    padding-left: 1.5rem;
    margin-bottom: 0.75rem;
  }

  .milkdown-wrapper ol {
    list-style-type: decimal;
    padding-left: 1.5rem;
    margin-bottom: 0.75rem;
  }

  .milkdown-wrapper li {
    margin-bottom: 0.25rem;
    line-height: 1.5;
  }

  .milkdown-wrapper li > ul, .milkdown-wrapper li > ol {
    margin-top: 0.25rem;
    margin-bottom: 0;
  }

  /* Inline styles */
  .milkdown-wrapper strong {
    font-weight: 700;
  }

  .milkdown-wrapper em {
    font-style: italic;
  }

  .milkdown-wrapper code {
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    font-size: 0.875em;
    padding: 0.125rem 0.375rem;
    border-radius: 0.25rem;
  }

  /* Code blocks */
  .milkdown-wrapper pre {
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    font-size: 0.875rem;
    padding: 1rem;
    border-radius: 0.5rem;
    margin-bottom: 0.75rem;
    overflow-x: auto;
  }

  /* Blockquotes */
  .milkdown-wrapper blockquote {
    border-left-width: 4px;
    padding-left: 1rem;
    margin-bottom: 0.75rem;
    font-style: italic;
  }

  /* Horizontal rule */
  .milkdown-wrapper hr {
    border: none;
    border-top-width: 1px;
    margin: 1.5rem 0;
  }

  /* Links */
  .milkdown-wrapper a {
    text-decoration: underline;
    text-underline-offset: 2px;
  }

  /* Placeholder */
  .milkdown-wrapper .ProseMirror p.is-editor-empty:first-child::before {
    content: attr(data-placeholder);
    float: left;
    pointer-events: none;
    height: 0;
  }

  /* Light mode colors (default) */
  .milkdown-wrapper {
    color: #18181b; /* zinc-900 */
  }

  .milkdown-wrapper h1, .milkdown-wrapper h2, .milkdown-wrapper h3,
  .milkdown-wrapper h4, .milkdown-wrapper h5, .milkdown-wrapper h6 {
    color: #18181b; /* zinc-900 */
  }

  .milkdown-wrapper code {
    background-color: #f4f4f5; /* zinc-100 */
    color: #18181b; /* zinc-900 */
  }

  .milkdown-wrapper pre {
    background-color: #f4f4f5; /* zinc-100 */
    color: #18181b; /* zinc-900 */
  }

  .milkdown-wrapper blockquote {
    border-color: #d4d4d8; /* zinc-300 */
    color: #52525b; /* zinc-600 */
  }

  .milkdown-wrapper hr {
    border-color: #e4e4e7; /* zinc-200 */
  }

  .milkdown-wrapper a {
    color: #059669; /* emerald-600 */
  }

  .milkdown-wrapper a:hover {
    color: #047857; /* emerald-700 */
  }

  .milkdown-wrapper .ProseMirror p.is-editor-empty:first-child::before {
    color: #a1a1aa; /* zinc-400 */
  }

  /* Dark mode colors */
  .dark .milkdown-wrapper {
    color: #fafafa; /* zinc-50 */
  }

  .dark .milkdown-wrapper h1, .dark .milkdown-wrapper h2, .dark .milkdown-wrapper h3,
  .dark .milkdown-wrapper h4, .dark .milkdown-wrapper h5, .dark .milkdown-wrapper h6 {
    color: #f4f4f5; /* zinc-100 */
  }

  .dark .milkdown-wrapper code {
    background-color: #27272a; /* zinc-800 */
    color: #f4f4f5; /* zinc-100 */
  }

  .dark .milkdown-wrapper pre {
    background-color: #27272a; /* zinc-800 */
    color: #f4f4f5; /* zinc-100 */
  }

  .dark .milkdown-wrapper blockquote {
    border-color: #52525b; /* zinc-600 */
    color: #a1a1aa; /* zinc-400 */
  }

  .dark .milkdown-wrapper hr {
    border-color: #3f3f46; /* zinc-700 */
  }

  .dark .milkdown-wrapper a {
    color: #34d399; /* emerald-400 */
  }

  .dark .milkdown-wrapper a:hover {
    color: #6ee7b7; /* emerald-300 */
  }

  .dark .milkdown-wrapper .ProseMirror p.is-editor-empty:first-child::before {
    color: #71717a; /* zinc-500 */
  }
`

interface EditorComponentProps {
  value: string
  onChange: (value: string) => void
  showToolbar?: boolean
  readOnly?: boolean
}

// Toolbar component that uses the editor instance
interface EditorToolbarProps {
  currentMarkdown: string
  onInsertHeading: (mdLevel: number, prefix: string, text: string) => void
  onPromote: () => void
  onDemote: () => void
  onBulletList: () => void
  onOrderedList: () => void
}

function EditorToolbar({ currentMarkdown, onInsertHeading, onPromote, onDemote, onBulletList, onOrderedList }: EditorToolbarProps) {
  const { t } = useI18n()
  const [loading, getEditor] = useInstance()

  const handleLegalLevel = useCallback((legalLevel: number) => {
    if (loading) return
    const editor = getEditor()
    if (!editor) return

    const view = editor.ctx.get(editorViewCtx)

    // CRITICAL: Get fresh markdown directly from the editor, not from React state
    // React state can be stale during rapid button clicks
    const serializer = editor.ctx.get(serializerCtx)
    const freshMarkdown = serializer(view.state.doc)

    const levelDef = LEGAL_LEVELS.find(l => l.level === legalLevel)
    if (!levelDef) return

    // Since we always append at the end, the insertion line is AFTER all existing content
    // Count the lines in the markdown to determine the insertion position
    const lines = freshMarkdown.split('\n')
    const insertionLine = lines.length // Insert after all existing lines

    const prefix = getNextPrefix(legalLevel, freshMarkdown, insertionLine)
    onInsertHeading(levelDef.mdLevel, prefix, '')
  }, [loading, getEditor, onInsertHeading])

  const handleBold = useCallback(() => {
    if (loading) return
    const editor = getEditor()
    if (editor) {
      editor.action(callCommand(toggleStrongCommand.key))
      editor.ctx.get(editorViewCtx).focus()
    }
  }, [loading, getEditor])

  const handleItalic = useCallback(() => {
    if (loading) return
    const editor = getEditor()
    if (editor) {
      editor.action(callCommand(toggleEmphasisCommand.key))
      editor.ctx.get(editorViewCtx).focus()
    }
  }, [loading, getEditor])

  return (
    <div className="flex flex-shrink-0 flex-wrap items-center gap-1 border-b border-zinc-200 bg-zinc-50 px-2 py-1.5 dark:border-zinc-700 dark:bg-zinc-800">
      {/* Legal outline level buttons */}
      <div className="flex items-center gap-0.5 border-r border-zinc-300 pr-2 dark:border-zinc-600">
        {LEGAL_LEVELS.map((level) => (
          <button
            key={level.level}
            type="button"
            onClick={() => handleLegalLevel(level.level)}
            className="rounded px-1.5 py-1 text-xs font-medium text-zinc-600 hover:bg-zinc-200 dark:text-zinc-400 dark:hover:bg-zinc-700"
            title={`${t('labeling.milkdown.level')} ${level.level}: ${level.prefix}`}
          >
            {level.prefix}
          </button>
        ))}
      </div>

      {/* Promote/Demote buttons */}
      <div className="flex items-center gap-0.5 border-r border-zinc-300 pr-2 dark:border-zinc-600">
        <button
          type="button"
          onMouseDown={e => e.preventDefault()}
          onClick={onPromote}
          className="flex items-center rounded px-1.5 py-1 text-xs text-zinc-600 hover:bg-zinc-200 dark:text-zinc-400 dark:hover:bg-zinc-700"
          title={t('labeling.milkdown.promoteLevel')}
        >
          <ChevronUpIcon className="h-4 w-4" />
        </button>
        <button
          type="button"
          onMouseDown={e => e.preventDefault()}
          onClick={onDemote}
          className="flex items-center rounded px-1.5 py-1 text-xs text-zinc-600 hover:bg-zinc-200 dark:text-zinc-400 dark:hover:bg-zinc-700"
          title={t('labeling.milkdown.demoteLevel')}
        >
          <ChevronDownIcon className="h-4 w-4" />
        </button>
      </div>

      {/* Text formatting */}
      <div className="flex items-center gap-0.5 border-r border-zinc-300 pr-2 dark:border-zinc-600">
        <button
          type="button"
          onMouseDown={e => e.preventDefault()}
          onClick={handleBold}
          className="rounded px-2 py-1 text-sm font-bold text-zinc-600 hover:bg-zinc-200 dark:text-zinc-400 dark:hover:bg-zinc-700"
          title={t('labeling.milkdown.bold')}
        >
          B
        </button>
        <button
          type="button"
          onMouseDown={e => e.preventDefault()}
          onClick={handleItalic}
          className="rounded px-2 py-1 text-sm italic text-zinc-600 hover:bg-zinc-200 dark:text-zinc-400 dark:hover:bg-zinc-700"
          title={t('labeling.milkdown.italic')}
        >
          I
        </button>
      </div>

      {/* List formatting */}
      <div className="flex items-center gap-0.5">
        <button
          type="button"
          onMouseDown={e => e.preventDefault()}
          onClick={onBulletList}
          className="rounded px-1.5 py-1 text-zinc-600 hover:bg-zinc-200 dark:text-zinc-400 dark:hover:bg-zinc-700"
          title={t('labeling.milkdown.bulletList')}
        >
          <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="9" y1="6" x2="20" y2="6" />
            <line x1="9" y1="12" x2="20" y2="12" />
            <line x1="9" y1="18" x2="20" y2="18" />
            <circle cx="5" cy="6" r="1.5" fill="currentColor" stroke="none" />
            <circle cx="5" cy="12" r="1.5" fill="currentColor" stroke="none" />
            <circle cx="5" cy="18" r="1.5" fill="currentColor" stroke="none" />
          </svg>
        </button>
        <button
          type="button"
          onMouseDown={e => e.preventDefault()}
          onClick={onOrderedList}
          className="rounded px-1.5 py-1 text-zinc-600 hover:bg-zinc-200 dark:text-zinc-400 dark:hover:bg-zinc-700"
          title={t('labeling.milkdown.orderedList')}
        >
          <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="10" y1="6" x2="20" y2="6" />
            <line x1="10" y1="12" x2="20" y2="12" />
            <line x1="10" y1="18" x2="20" y2="18" />
            <text x="4" y="8" fontSize="7" fill="currentColor" stroke="none" fontFamily="sans-serif">1</text>
            <text x="4" y="14" fontSize="7" fill="currentColor" stroke="none" fontFamily="sans-serif">2</text>
            <text x="4" y="20" fontSize="7" fill="currentColor" stroke="none" fontFamily="sans-serif">3</text>
          </svg>
        </button>
      </div>
    </div>
  )
}

function EditorComponent({ value, onChange, showToolbar, readOnly }: EditorComponentProps) {
  const { t } = useI18n()
  const onChangeRef = useRef(onChange)

  // Keep ref in sync with prop
  useEffect(() => {
    onChangeRef.current = onChange
  }, [onChange])

  // Store the initial value in a ref to prevent useEditor from recreating on every keystroke
  const initialValueRef = useRef(value)
  const [currentMarkdown, setCurrentMarkdown] = useState(value)
  const [loading, getEditor] = useInstance()

  // Track whether a value change originated from inside the editor (typing, toolbar)
  const isFromEditorRef = useRef(false)
  // Track the last value we emitted to parent, to detect external changes
  const lastEmittedValueRef = useRef(value)
  // Store external values that arrive before editor is ready
  const pendingExternalValueRef = useRef<string | null>(null)

  useEditor((root) =>
    Editor.make()
      .config((ctx) => {
        ctx.set(rootCtx, root)
        ctx.set(defaultValueCtx, initialValueRef.current)
        if (readOnly) {
          ctx.update(editorViewOptionsCtx, (prev) => ({ ...prev, editable: () => false }))
        }

        // Listen for content changes
        ctx.get(listenerCtx).markdownUpdated((_, markdown) => {
          setCurrentMarkdown(markdown)
          isFromEditorRef.current = true
          lastEmittedValueRef.current = markdown
          onChangeRef.current(markdown)
        })
      })
      .use(commonmark)
      .use(history as any)
      .use(listener),
    [] // Empty deps - only create editor once per mount
  )

  // Handle external value changes (e.g., heading sync from another field) via replaceAll
  // instead of destroying and recreating the editor
  useEffect(() => {
    // Skip changes that originated from our own editor
    if (isFromEditorRef.current) {
      isFromEditorRef.current = false
      return
    }

    // Use trimEnd() normalization because Milkdown's serializer may add/remove trailing whitespace
    if (value.trimEnd() !== lastEmittedValueRef.current.trimEnd()) {
      if (loading) {
        // Editor not ready yet - store for later
        pendingExternalValueRef.current = value
        return
      }
      const editor = getEditor()
      if (editor) {
        lastEmittedValueRef.current = value
        setCurrentMarkdown(value)
        editor.action(replaceAll(value))
      }
    }
  }, [value, loading, getEditor])

  // Apply pending external value once editor is ready
  useEffect(() => {
    if (!loading && pendingExternalValueRef.current !== null) {
      const editor = getEditor()
      if (editor) {
        const pending = pendingExternalValueRef.current
        pendingExternalValueRef.current = null
        lastEmittedValueRef.current = pending
        setCurrentMarkdown(pending)
        editor.action(replaceAll(pending))
      }
    }
  }, [loading, getEditor])

  // Insert a heading at the current cursor position or convert selected text
  const handleInsertHeading = useCallback((mdLevel: number, prefix: string, text: string) => {
    if (loading) return
    const editor = getEditor()
    if (!editor) return

    const view = editor.ctx.get(editorViewCtx)
    const { from, to } = view.state.selection
    const hasSelection = from !== to

    // Get selected text if any
    const selectedText = hasSelection
      ? view.state.doc.textBetween(from, to, ' ')
      : ''

    // Use selected text or default placeholder
    const headingTitle = selectedText.trim() || text || t('labeling.milkdown.heading')

    // Create the heading markdown
    const hashes = '#'.repeat(mdLevel)
    const headingText = `${hashes} ${prefix} ${headingTitle}`

    // CRITICAL: Get fresh markdown directly from the editor, not from React state
    // React state can be stale during rapid operations
    const serializer = editor.ctx.get(serializerCtx)
    const freshMarkdown = serializer(view.state.doc)

    let newMarkdown: string

    if (freshMarkdown.trim() === '') {
      // Empty document - just set the heading
      newMarkdown = headingText + '\n'
    } else if (hasSelection) {
      // With selection - replace selected content with heading
      // Work with the fresh markdown string directly
      const lines = freshMarkdown.split('\n')

      // Find which line contains the selection start by mapping position
      // For simplicity with selection, just replace at the beginning
      const selectedContent = selectedText.trim() || headingTitle
      newMarkdown = `${hashes} ${prefix} ${selectedContent}\n\n${freshMarkdown}`
    } else {
      // No selection - ALWAYS append new heading at the end
      // This is the most intuitive behavior when clicking toolbar buttons
      // The prefix is already calculated based on ALL existing headings
      const trimmed = freshMarkdown.trimEnd()
      newMarkdown = trimmed + '\n\n' + headingText + '\n'
    }

    // Update markdown using replaceAll to avoid full remount
    setCurrentMarkdown(newMarkdown)
    isFromEditorRef.current = true
    lastEmittedValueRef.current = newMarkdown
    onChangeRef.current(newMarkdown)
    editor.action(replaceAll(newMarkdown))

    // Position cursor at the END of the document after insertion
    // This ensures that subsequent heading additions are always appended
    // Using ProseMirror's position system (not markdown character positions)
    setTimeout(() => {
      try {
        const newView = editor.ctx.get(editorViewCtx)
        // Position at the end of the last block node
        const endPos = newView.state.doc.content.size - 1
        const tr = newView.state.tr.setSelection(
          TextSelection.create(newView.state.doc, Math.max(1, endPos))
        )
        newView.dispatch(tr)
        newView.focus()
      } catch (e) {
        // Cursor restoration failed, not critical
      }
    }, 50)
  }, [loading, getEditor])

  // Promote current heading (move up one level)
  const handlePromote = useCallback(() => {
    if (loading) return
    const editor = getEditor()
    if (!editor) return

    const view = editor.ctx.get(editorViewCtx)
    const { from } = view.state.selection

    // CRITICAL: Get fresh markdown directly from the editor, not from React state
    const serializer = editor.ctx.get(serializerCtx)
    const freshMarkdown = serializer(view.state.doc)

    // Find which heading the cursor is in by counting nodes in ProseMirror
    let currentLineIndex = -1
    let nodeIndex = 0
    view.state.doc.descendants((node, pos) => {
      if (node.type.name === 'heading') {
        if (pos <= from && from <= pos + node.nodeSize) {
          currentLineIndex = nodeIndex
          return false // stop iteration
        }
        nodeIndex++
      }
      return true
    })

    // If not found in a heading, try to find by line in markdown
    const lines = freshMarkdown.split('\n')
    if (currentLineIndex === -1) {
      // Fallback: find first heading line
      for (let i = 0; i < lines.length; i++) {
        if (lines[i].match(/^#{1,6}\s+/)) {
          currentLineIndex = i
          break
        }
      }
    } else {
      // Convert node index to line index (headings may not be contiguous lines)
      let headingCount = 0
      for (let i = 0; i < lines.length; i++) {
        if (lines[i].match(/^#{1,6}\s+/)) {
          if (headingCount === currentLineIndex) {
            currentLineIndex = i
            break
          }
          headingCount++
        }
      }
    }

    if (currentLineIndex < 0 || currentLineIndex >= lines.length) return

    const currentLine = lines[currentLineIndex]
    const headingMatch = currentLine.match(/^(#{1,6})\s+(.+)$/)

    if (headingMatch) {
      const content = headingMatch[2]

      // Find the current legal level from the prefix
      const prefixMatch = content.match(/^([ABCDEFGHJKLMNOPQRSTUWYZ]\.|[IVXLCDM]+\.|[0-9]+\.|[a-z]\)|[a-z]{2}\)|\(\d+\))\s*/)

      if (prefixMatch) {
        const oldPrefix = prefixMatch[1]
        const textAfterPrefix = content.slice(prefixMatch[0].length)

        // Find current level
        let currentLegalLevel = 0
        if (oldPrefix.match(/^[ABCDEFGHJKLMNOPQRSTUWYZ]\.$/)) currentLegalLevel = 1
        else if (oldPrefix.match(/^[IVXLCDM]+\.$/)) currentLegalLevel = 2
        else if (oldPrefix.match(/^[0-9]+\.$/)) currentLegalLevel = 3
        else if (oldPrefix.match(/^[a-z]\)$/) && !oldPrefix.match(/^[a-z]{2}\)$/)) currentLegalLevel = 4
        else if (oldPrefix.match(/^[a-z]{2}\)$/)) currentLegalLevel = 5
        else if (oldPrefix.match(/^\(\d+\)$/)) currentLegalLevel = 6

        if (currentLegalLevel > 1) {
          const newLegalLevel = currentLegalLevel - 1
          const newLevelDef = LEGAL_LEVELS.find(l => l.level === newLegalLevel)

          if (newLevelDef) {
            const newPrefix = getNextPrefix(newLegalLevel, freshMarkdown, currentLineIndex)
            const newHashes = '#'.repeat(newLevelDef.mdLevel)
            lines[currentLineIndex] = `${newHashes} ${newPrefix} ${textAfterPrefix}`

            const newMarkdown = lines.join('\n')
            setCurrentMarkdown(newMarkdown)
            isFromEditorRef.current = true
            lastEmittedValueRef.current = newMarkdown
            onChangeRef.current(newMarkdown)
            editor.action(replaceAll(newMarkdown))
          }
        }
      }
    }
    // Restore focus after toolbar action
    view.focus()
  }, [loading, getEditor])

  // Demote current heading (move down one level)
  const handleDemote = useCallback(() => {
    if (loading) return
    const editor = getEditor()
    if (!editor) return

    const view = editor.ctx.get(editorViewCtx)
    const { from } = view.state.selection

    // CRITICAL: Get fresh markdown directly from the editor, not from React state
    const serializer = editor.ctx.get(serializerCtx)
    const freshMarkdown = serializer(view.state.doc)

    // Find which heading the cursor is in by counting nodes in ProseMirror
    let currentLineIndex = -1
    let nodeIndex = 0
    view.state.doc.descendants((node, pos) => {
      if (node.type.name === 'heading') {
        if (pos <= from && from <= pos + node.nodeSize) {
          currentLineIndex = nodeIndex
          return false // stop iteration
        }
        nodeIndex++
      }
      return true
    })

    // If not found in a heading, try to find by line in markdown
    const lines = freshMarkdown.split('\n')
    if (currentLineIndex === -1) {
      // Fallback: find first heading line
      for (let i = 0; i < lines.length; i++) {
        if (lines[i].match(/^#{1,6}\s+/)) {
          currentLineIndex = i
          break
        }
      }
    } else {
      // Convert node index to line index (headings may not be contiguous lines)
      let headingCount = 0
      for (let i = 0; i < lines.length; i++) {
        if (lines[i].match(/^#{1,6}\s+/)) {
          if (headingCount === currentLineIndex) {
            currentLineIndex = i
            break
          }
          headingCount++
        }
      }
    }

    if (currentLineIndex < 0 || currentLineIndex >= lines.length) return

    const currentLine = lines[currentLineIndex]
    const headingMatch = currentLine.match(/^(#{1,6})\s+(.+)$/)

    if (headingMatch) {
      const content = headingMatch[2]

      // Find the current legal level from the prefix
      const prefixMatch = content.match(/^([ABCDEFGHJKLMNOPQRSTUWYZ]\.|[IVXLCDM]+\.|[0-9]+\.|[a-z]\)|[a-z]{2}\)|\(\d+\))\s*/)

      if (prefixMatch) {
        const oldPrefix = prefixMatch[1]
        const textAfterPrefix = content.slice(prefixMatch[0].length)

        // Find current level
        let currentLegalLevel = 0
        if (oldPrefix.match(/^[ABCDEFGHJKLMNOPQRSTUWYZ]\.$/)) currentLegalLevel = 1
        else if (oldPrefix.match(/^[IVXLCDM]+\.$/)) currentLegalLevel = 2
        else if (oldPrefix.match(/^[0-9]+\.$/)) currentLegalLevel = 3
        else if (oldPrefix.match(/^[a-z]\)$/) && !oldPrefix.match(/^[a-z]{2}\)$/)) currentLegalLevel = 4
        else if (oldPrefix.match(/^[a-z]{2}\)$/)) currentLegalLevel = 5
        else if (oldPrefix.match(/^\(\d+\)$/)) currentLegalLevel = 6

        if (currentLegalLevel > 0 && currentLegalLevel < 6) {
          const newLegalLevel = currentLegalLevel + 1
          const newLevelDef = LEGAL_LEVELS.find(l => l.level === newLegalLevel)

          if (newLevelDef) {
            const newPrefix = getNextPrefix(newLegalLevel, freshMarkdown, currentLineIndex)
            const newHashes = '#'.repeat(newLevelDef.mdLevel)
            lines[currentLineIndex] = `${newHashes} ${newPrefix} ${textAfterPrefix}`

            const newMarkdown = lines.join('\n')
            setCurrentMarkdown(newMarkdown)
            isFromEditorRef.current = true
            lastEmittedValueRef.current = newMarkdown
            onChangeRef.current(newMarkdown)
            editor.action(replaceAll(newMarkdown))
          }
        }
      }
    }
    // Restore focus after toolbar action
    view.focus()
  }, [loading, getEditor])

  // Convert current line to bullet list
  const handleBulletList = useCallback(() => {
    if (loading) return
    const editor = getEditor()
    if (!editor) return

    const view = editor.ctx.get(editorViewCtx)
    const { from } = view.state.selection

    // Check if we're in a heading by looking at the current line in markdown
    const lines = currentMarkdown.split('\n')
    let charCount = 0
    let currentLineIndex = 0

    for (let i = 0; i < lines.length; i++) {
      if (charCount + lines[i].length >= from) {
        currentLineIndex = i
        break
      }
      charCount += lines[i].length + 1
    }

    const currentLine = lines[currentLineIndex]
    const headingMatch = currentLine.match(/^#{1,6}\s+(.+)$/)

    if (headingMatch) {
      // Current line is a heading - convert it to a bullet list item
      const headingContent = headingMatch[1]
      lines[currentLineIndex] = `- ${headingContent}`
      const newMarkdown = lines.join('\n')
      setCurrentMarkdown(newMarkdown)
      isFromEditorRef.current = true
      lastEmittedValueRef.current = newMarkdown
      onChangeRef.current(newMarkdown)
      editor.action(replaceAll(newMarkdown))
    } else {
      // Not a heading - use standard command
      editor.action(callCommand(wrapInBulletListCommand.key))
    }
    view.focus()
  }, [loading, getEditor, currentMarkdown])

  // Convert current line to ordered list
  const handleOrderedList = useCallback(() => {
    if (loading) return
    const editor = getEditor()
    if (!editor) return

    const view = editor.ctx.get(editorViewCtx)
    const { from } = view.state.selection

    // Check if we're in a heading by looking at the current line in markdown
    const lines = currentMarkdown.split('\n')
    let charCount = 0
    let currentLineIndex = 0

    for (let i = 0; i < lines.length; i++) {
      if (charCount + lines[i].length >= from) {
        currentLineIndex = i
        break
      }
      charCount += lines[i].length + 1
    }

    const currentLine = lines[currentLineIndex]
    const headingMatch = currentLine.match(/^#{1,6}\s+(.+)$/)

    if (headingMatch) {
      // Current line is a heading - convert it to a numbered list item
      const headingContent = headingMatch[1]
      lines[currentLineIndex] = `1. ${headingContent}`
      const newMarkdown = lines.join('\n')
      setCurrentMarkdown(newMarkdown)
      isFromEditorRef.current = true
      lastEmittedValueRef.current = newMarkdown
      onChangeRef.current(newMarkdown)
      editor.action(replaceAll(newMarkdown))
    } else {
      // Not a heading - use standard command
      editor.action(callCommand(wrapInOrderedListCommand.key))
    }
    view.focus()
  }, [loading, getEditor, currentMarkdown])

  return (
    <>
      {showToolbar && (
        <EditorToolbar
          currentMarkdown={currentMarkdown}
          onInsertHeading={handleInsertHeading}
          onPromote={handlePromote}
          onDemote={handleDemote}
          onBulletList={handleBulletList}
          onOrderedList={handleOrderedList}
        />
      )}
      <Milkdown />
    </>
  )
}

export function MilkdownEditor({
  value,
  onChange,
  placeholder,
  minHeight = 200,
  className = '',
  showToolbar = false,
  readOnly = false,
}: MilkdownEditorProps) {
  return (
    <div
      className={`milkdown-wrapper flex flex-col overflow-hidden rounded-lg border border-zinc-200 bg-white focus-within:ring-2 focus-within:ring-emerald-500 focus-within:ring-offset-1 dark:border-zinc-700 dark:bg-zinc-900 dark:focus-within:ring-offset-zinc-900 ${className}`}
      style={{ '--editor-min-height': `${minHeight}px` } as React.CSSProperties}
    >
      <style>{editorStyles}</style>
      <MilkdownProvider>
        <EditorComponent
          value={value}
          onChange={onChange}
          showToolbar={showToolbar && !readOnly}
          readOnly={readOnly}
        />
      </MilkdownProvider>
    </div>
  )
}

export default MilkdownEditor

// Export utility functions for testing
export { extractHeadingsFromMarkdown, getNextPrefix, LEGAL_LEVELS }

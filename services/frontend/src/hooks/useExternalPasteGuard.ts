/**
 * Blocks pasting (and dropping) text that was copied outside BenGER.
 *
 * Projects can switch off `allow_external_paste` so annotators cannot paste
 * answers prepared elsewhere (another document, a chatbot, another tab). Text
 * copied inside the page stays pasteable: every copy/cut while the guard is
 * active records the copied text, and a paste is accepted only when its text
 * matches one of those recordings.
 *
 * The listeners sit on `document`, so they also cover editors rendered by
 * overlay packages (Milkdown, sheets) and editors inside portalled modals.
 * `paste`/`drop` listen in the capture phase so they run before ProseMirror
 * or a textarea handles the event; `copy`/`cut` listen in the bubble phase so
 * they see the data an editor put on the clipboard in its own copy handler.
 */
import { useEffect, useRef } from 'react'

/** How many recent internal copies are remembered. */
const MAX_INTERNAL_COPIES = 20

/**
 * Normalizes clipboard text for comparison: browsers and editors differ in
 * line endings, non-breaking spaces and trailing whitespace between what was
 * copied and what is pasted back.
 */
export function normalizeClipboardText(text: string): string {
  return text
    .replace(/\r\n?/g, '\n')
    .replace(/ /g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

function hasFiles(data: DataTransfer | null): boolean {
  if (!data) return false
  if (data.files && data.files.length > 0) return true
  return Array.from(data.types || []).includes('Files')
}

export function useExternalPasteGuard(
  enabled: boolean,
  onBlocked: () => void,
): void {
  const onBlockedRef = useRef(onBlocked)
  useEffect(() => {
    onBlockedRef.current = onBlocked
  }, [onBlocked])

  useEffect(() => {
    if (!enabled || typeof document === 'undefined') return

    const internalCopies: string[] = []
    let internalDragActive = false

    const remember = (raw: string) => {
      const text = normalizeClipboardText(raw)
      if (!text) return
      const existing = internalCopies.indexOf(text)
      if (existing !== -1) internalCopies.splice(existing, 1)
      internalCopies.push(text)
      if (internalCopies.length > MAX_INTERNAL_COPIES) internalCopies.shift()
    }

    const isInternal = (raw: string) => {
      const text = normalizeClipboardText(raw)
      return text === '' || internalCopies.includes(text)
    }

    const handleCopy = (event: ClipboardEvent) => {
      // Record both the clipboard payload an editor may have set and the
      // plain selection; either can come back on paste.
      const set = event.clipboardData?.getData('text/plain') ?? ''
      if (set) remember(set)
      const selection =
        typeof window !== 'undefined' && window.getSelection
          ? (window.getSelection()?.toString() ?? '')
          : ''
      if (selection) remember(selection)
    }

    const block = (event: Event) => {
      event.preventDefault()
      event.stopPropagation()
      onBlockedRef.current()
    }

    const handlePaste = (event: ClipboardEvent) => {
      const data = event.clipboardData
      if (!data) return
      if (hasFiles(data)) {
        block(event)
        return
      }
      const text = data.getData('text/plain') || data.getData('text') || ''
      if (!isInternal(text)) block(event)
    }

    const handleDragStart = () => {
      internalDragActive = true
    }
    const handleDragEnd = () => {
      internalDragActive = false
    }

    const handleDrop = (event: DragEvent) => {
      if (internalDragActive) {
        internalDragActive = false
        return
      }
      const data = event.dataTransfer
      if (!data) return
      if (hasFiles(data)) {
        // File drops are left to their own drop zones (file upload fields);
        // only text is guarded here.
        return
      }
      const text = data.getData('text/plain') || data.getData('text') || ''
      if (!isInternal(text)) block(event)
    }

    document.addEventListener('copy', handleCopy)
    document.addEventListener('cut', handleCopy)
    document.addEventListener('paste', handlePaste, true)
    document.addEventListener('dragstart', handleDragStart, true)
    document.addEventListener('dragend', handleDragEnd, true)
    document.addEventListener('drop', handleDrop, true)
    return () => {
      document.removeEventListener('copy', handleCopy)
      document.removeEventListener('cut', handleCopy)
      document.removeEventListener('paste', handlePaste, true)
      document.removeEventListener('dragstart', handleDragStart, true)
      document.removeEventListener('dragend', handleDragEnd, true)
      document.removeEventListener('drop', handleDrop, true)
    }
  }, [enabled])
}

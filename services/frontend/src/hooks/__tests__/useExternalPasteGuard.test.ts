import { renderHook } from '@testing-library/react'
import {
  normalizeClipboardText,
  useExternalPasteGuard,
} from '../useExternalPasteGuard'

/** A clipboard/drag payload jsdom does not provide natively. */
function fakeData(text: string, opts: { files?: boolean } = {}) {
  const store: Record<string, string> = { 'text/plain': text }
  return {
    getData: (type: string) => store[type] ?? '',
    setData: (type: string, value: string) => {
      store[type] = value
    },
    files: opts.files ? [new File(['x'], 'x.png')] : [],
    types: opts.files ? ['Files'] : ['text/plain'],
  }
}

function fire(
  type: 'copy' | 'cut' | 'paste' | 'drop' | 'dragstart' | 'dragend',
  text = '',
  opts: { files?: boolean; target?: EventTarget } = {},
) {
  const event = new Event(type, { bubbles: true, cancelable: true })
  const data = fakeData(text, opts)
  Object.defineProperty(event, 'clipboardData', { value: data })
  Object.defineProperty(event, 'dataTransfer', { value: data })
  ;(opts.target ?? document.body).dispatchEvent(event)
  return event
}

describe('normalizeClipboardText', () => {
  it('ignores line endings, nbsp and surrounding whitespace', () => {
    expect(normalizeClipboardText('  a\r\nb  c\n')).toBe('a b c')
  })
})

describe('useExternalPasteGuard', () => {
  it('blocks a paste of text that was not copied inside the page', () => {
    const onBlocked = jest.fn()
    renderHook(() => useExternalPasteGuard(true, onBlocked))
    const event = fire('paste', 'answer from a chatbot')
    expect(event.defaultPrevented).toBe(true)
    expect(onBlocked).toHaveBeenCalledTimes(1)
  })

  it('stops the blocked paste before element handlers see it', () => {
    const onBlocked = jest.fn()
    const inner = jest.fn()
    const textarea = document.createElement('textarea')
    document.body.appendChild(textarea)
    textarea.addEventListener('paste', inner)
    renderHook(() => useExternalPasteGuard(true, onBlocked))
    fire('paste', 'external', { target: textarea })
    expect(inner).not.toHaveBeenCalled()
    textarea.remove()
  })

  it('allows pasting text copied inside the page', () => {
    const onBlocked = jest.fn()
    renderHook(() => useExternalPasteGuard(true, onBlocked))
    fire('copy', 'Sachverhalt: A verkauft B ein Auto.')
    const event = fire('paste', 'Sachverhalt: A verkauft B ein Auto.')
    expect(event.defaultPrevented).toBe(false)
    expect(onBlocked).not.toHaveBeenCalled()
  })

  it('allows cut text and tolerates whitespace and line-ending changes', () => {
    const onBlocked = jest.fn()
    renderHook(() => useExternalPasteGuard(true, onBlocked))
    fire('cut', 'erste Zeile\nzweite Zeile')
    const event = fire('paste', 'erste Zeile\r\nzweite Zeile  ')
    expect(event.defaultPrevented).toBe(false)
    expect(onBlocked).not.toHaveBeenCalled()
  })

  it('records the selection when the copy event carries no data', () => {
    const onBlocked = jest.fn()
    const getSelection = jest
      .spyOn(window, 'getSelection')
      .mockReturnValue({ toString: () => 'markierter Text' } as Selection)
    renderHook(() => useExternalPasteGuard(true, onBlocked))
    fire('copy', '')
    expect(fire('paste', 'markierter Text').defaultPrevented).toBe(false)
    getSelection.mockRestore()
  })

  it('blocks pasted files and images', () => {
    const onBlocked = jest.fn()
    renderHook(() => useExternalPasteGuard(true, onBlocked))
    expect(fire('paste', '', { files: true }).defaultPrevented).toBe(true)
    expect(onBlocked).toHaveBeenCalledTimes(1)
  })

  it('blocks text dropped from outside but allows drags inside the page', () => {
    const onBlocked = jest.fn()
    renderHook(() => useExternalPasteGuard(true, onBlocked))
    expect(fire('drop', 'external text').defaultPrevented).toBe(true)
    fire('dragstart', 'inner text')
    expect(fire('drop', 'inner text').defaultPrevented).toBe(false)
    expect(onBlocked).toHaveBeenCalledTimes(1)
  })

  it('leaves file drops to their drop zones', () => {
    const onBlocked = jest.fn()
    renderHook(() => useExternalPasteGuard(true, onBlocked))
    expect(fire('drop', '', { files: true }).defaultPrevented).toBe(false)
    expect(onBlocked).not.toHaveBeenCalled()
  })

  it('does nothing when disabled', () => {
    const onBlocked = jest.fn()
    renderHook(() => useExternalPasteGuard(false, onBlocked))
    expect(fire('paste', 'external').defaultPrevented).toBe(false)
    expect(onBlocked).not.toHaveBeenCalled()
  })

  it('removes its listeners on unmount and when switched off', () => {
    const onBlocked = jest.fn()
    const { rerender, unmount } = renderHook(
      ({ enabled }) => useExternalPasteGuard(enabled, onBlocked),
      { initialProps: { enabled: true } },
    )
    rerender({ enabled: false })
    expect(fire('paste', 'external').defaultPrevented).toBe(false)
    rerender({ enabled: true })
    unmount()
    expect(fire('paste', 'external').defaultPrevented).toBe(false)
    expect(onBlocked).not.toHaveBeenCalled()
  })

  it('calls the latest onBlocked callback', () => {
    const first = jest.fn()
    const second = jest.fn()
    const { rerender } = renderHook(
      ({ cb }) => useExternalPasteGuard(true, cb),
      { initialProps: { cb: first } },
    )
    rerender({ cb: second })
    fire('paste', 'external')
    expect(first).not.toHaveBeenCalled()
    expect(second).toHaveBeenCalledTimes(1)
  })
})

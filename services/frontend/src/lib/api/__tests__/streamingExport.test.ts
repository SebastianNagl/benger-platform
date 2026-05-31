/**
 * Unit tests for the streaming JSON export download.
 *
 * Covers the two download paths (File System Access API + Blob fallback) and
 * the completeness-sentinel validation that turns a silently-truncated
 * download into a surfaced error.
 */

import apiClient from '@/lib/api'
import {
  EXPORT_COMPLETE_SENTINEL,
  streamJsonExport,
  supportsFileSystemAccess,
  TruncatedExportError,
} from '../streamingExport'

jest.mock('@/lib/api', () => ({
  __esModule: true,
  default: { requestRaw: jest.fn() },
}))

jest.mock('@/lib/utils/logger', () => ({
  __esModule: true,
  default: {
    debug: jest.fn(),
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
  },
}))

const requestRaw = (apiClient as any).requestRaw as jest.Mock

// Minimal `response.body` substitute: jsdom does not implement ReadableStream,
// so we hand the code a stream-shaped object exposing `getReader()`.
function fakeStream(parts: string[], severAfter?: number) {
  const enc = new TextEncoder()
  const chunks = parts.map((p) => enc.encode(p))
  let i = 0
  return {
    getReader() {
      return {
        read: async () => {
          if (severAfter !== undefined && i >= severAfter) {
            throw new TypeError('network error: connection reset')
          }
          if (i < chunks.length) {
            return { done: false, value: chunks[i++] }
          }
          return { done: true, value: undefined }
        },
      }
    },
  }
}

function mockResponse(parts: string[], severAfter?: number) {
  return { body: fakeStream(parts, severAfter) } as unknown as Response
}

const COMPLETE_BODY = ['{"tasks": [{"id": "t1"}], ', EXPORT_COMPLETE_SENTINEL]
const TRUNCATED_BODY = ['{"tasks": [{"id": "t1"}', ', {"id": "t2", "evaluations": []}']

describe('streamJsonExport', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    delete (window as any).showSaveFilePicker
  })

  describe('Blob fallback (no File System Access API)', () => {
    let clickSpy: jest.Mock

    beforeEach(() => {
      clickSpy = jest.fn()
      global.URL.createObjectURL = jest.fn(() => 'blob:mock')
      global.URL.revokeObjectURL = jest.fn()
      const realCreate = document.createElement.bind(document)
      jest.spyOn(document, 'createElement').mockImplementation((tag: any) => {
        const el = realCreate(tag)
        if (tag === 'a') (el as any).click = clickSpy
        return el
      })
    })

    afterEach(() => {
      jest.restoreAllMocks()
    })

    it('downloads when the completeness sentinel is present', async () => {
      requestRaw.mockResolvedValue(mockResponse(COMPLETE_BODY))

      const result = await streamJsonExport({
        endpoint: '/projects/p1/tasks/bulk-export',
        method: 'POST',
        body: { task_ids: ['t1'], format: 'json' },
        suggestedName: 'p1.json',
      })

      expect(result.savedVia).toBe('blob')
      expect(clickSpy).toHaveBeenCalledTimes(1)
      expect(requestRaw).toHaveBeenCalledWith(
        '/projects/p1/tasks/bulk-export',
        { method: 'POST', body: JSON.stringify({ task_ids: ['t1'], format: 'json' }) }
      )
    })

    it('throws TruncatedExportError and never downloads when the sentinel is missing', async () => {
      requestRaw.mockResolvedValue(mockResponse(TRUNCATED_BODY))

      await expect(
        streamJsonExport({ endpoint: '/x', suggestedName: 'p1.json' })
      ).rejects.toBeInstanceOf(TruncatedExportError)
      expect(clickSpy).not.toHaveBeenCalled()
    })

    it('propagates a severed stream as an error without downloading', async () => {
      requestRaw.mockResolvedValue(mockResponse(TRUNCATED_BODY, 1))

      await expect(
        streamJsonExport({ endpoint: '/x', suggestedName: 'p1.json' })
      ).rejects.toThrow(/network error/)
      expect(clickSpy).not.toHaveBeenCalled()
    })
  })

  describe('File System Access API', () => {
    function setupPicker() {
      const writes: Uint8Array[] = []
      const writable = {
        write: jest.fn(async (c: Uint8Array) => {
          writes.push(c)
        }),
        close: jest.fn(async () => {}),
        abort: jest.fn(async () => {}),
      }
      const fileHandle = { createWritable: jest.fn(async () => writable) }
      ;(window as any).showSaveFilePicker = jest.fn(async () => fileHandle)
      return { writable, fileHandle, writes }
    }

    it('streams to disk and commits when the sentinel is present', async () => {
      const { writable } = setupPicker()
      requestRaw.mockResolvedValue(mockResponse(COMPLETE_BODY))

      const result = await streamJsonExport({
        endpoint: '/x',
        body: { a: 1 },
        suggestedName: 'p1.json',
      })

      expect(result.savedVia).toBe('file-system-access')
      expect(writable.write).toHaveBeenCalled()
      expect(writable.close).toHaveBeenCalledTimes(1)
      expect(writable.abort).not.toHaveBeenCalled()
    })

    it('aborts the write and throws when the sentinel is missing', async () => {
      const { writable } = setupPicker()
      requestRaw.mockResolvedValue(mockResponse(TRUNCATED_BODY))

      await expect(
        streamJsonExport({ endpoint: '/x', suggestedName: 'p1.json' })
      ).rejects.toBeInstanceOf(TruncatedExportError)
      expect(writable.abort).toHaveBeenCalledTimes(1)
      expect(writable.close).not.toHaveBeenCalled()
    })

    it('aborts the write when the stream is severed mid-body', async () => {
      const { writable } = setupPicker()
      requestRaw.mockResolvedValue(mockResponse(COMPLETE_BODY, 1))

      await expect(
        streamJsonExport({ endpoint: '/x', suggestedName: 'p1.json' })
      ).rejects.toThrow(/network error/)
      expect(writable.abort).toHaveBeenCalledTimes(1)
      expect(writable.close).not.toHaveBeenCalled()
    })

    it('propagates a save-dialog cancellation without making a request', async () => {
      ;(window as any).showSaveFilePicker = jest
        .fn()
        .mockRejectedValue(new DOMException('User cancelled', 'AbortError'))

      await expect(
        streamJsonExport({ endpoint: '/x', suggestedName: 'p1.json' })
      ).rejects.toMatchObject({ name: 'AbortError' })
      expect(requestRaw).not.toHaveBeenCalled()
    })
  })

  describe('supportsFileSystemAccess', () => {
    it('reflects presence of window.showSaveFilePicker', () => {
      delete (window as any).showSaveFilePicker
      expect(supportsFileSystemAccess()).toBe(false)
      ;(window as any).showSaveFilePicker = jest.fn()
      expect(supportsFileSystemAccess()).toBe(true)
    })
  })
})

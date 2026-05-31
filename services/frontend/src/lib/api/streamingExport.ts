/**
 * Streaming JSON export download.
 *
 * Large project exports (the ZJS dataset is ~4.5 GB / hundreds of tasks)
 * cannot go through the normal `response.blob()` path: buffering the whole
 * body in browser memory either OOMs the tab or — worse — gets severed by a
 * proxy / connection drop and silently saved as a truncated, invalid file.
 *
 * This module streams the response straight to disk via the File System
 * Access API when available (Chromium), so the body never sits in memory,
 * and validates the server's completeness sentinel on every path so a
 * severed stream surfaces as an error instead of a corrupt download.
 */

import apiClient from '@/lib/api'
import logger from '@/lib/utils/logger'

/**
 * Trailing marker the server emits as the very last bytes of a complete JSON
 * export (see `services/api/routers/projects/_export_stream.py`). Its presence
 * is the only reliable completeness signal: a truncated file's tail (a task
 * object's `"evaluations": []}`) is otherwise indistinguishable from a clean
 * end (`]}`).
 */
export const EXPORT_COMPLETE_SENTINEL = '"export_complete": true}'

// Trailing bytes retained to test for the sentinel — large enough to hold the
// marker plus any whitespace the server might emit after it.
const TAIL_BYTES = 256

export class TruncatedExportError extends Error {
  constructor(
    message = 'The export ended before the server finished writing it — the file is incomplete. Please retry.'
  ) {
    super(message)
    this.name = 'TruncatedExportError'
  }
}

export interface StreamExportResult {
  bytesWritten: number
  savedVia: 'file-system-access' | 'blob'
}

export interface StreamExportOptions {
  endpoint: string
  method?: string
  body?: unknown
  /** Default filename offered in the save dialog / used by the fallback. */
  suggestedName: string
  /** Fired once, after the save target is acquired and just before the
   *  network request begins. Lets callers defer their progress UI past the
   *  (cancelable) save-file picker. */
  onStart?: () => void
  onProgress?: (bytesWritten: number) => void
}

export function supportsFileSystemAccess(): boolean {
  return (
    typeof window !== 'undefined' &&
    typeof (window as any).showSaveFilePicker === 'function'
  )
}

/**
 * Stream a JSON export to disk, validating the completeness sentinel.
 *
 * On Chromium the body streams directly to the user-chosen file and never
 * buffers in memory; elsewhere it falls back to buffering a Blob (still
 * validated, but bounded by available memory). Throws {@link TruncatedExportError}
 * if the stream was severed, and may throw a DOMException with name
 * `'AbortError'` if the user dismisses the save dialog — callers should treat
 * that as a silent cancellation.
 */
export async function streamJsonExport(
  options: StreamExportOptions
): Promise<StreamExportResult> {
  const { endpoint, method = 'POST', body, suggestedName, onStart, onProgress } =
    options

  // Acquire the save target BEFORE the request so the picker runs under the
  // originating click's transient activation, and so a cancel here bails out
  // before any work or progress UI is started.
  let fileHandle: any = null
  if (supportsFileSystemAccess()) {
    fileHandle = await (window as any).showSaveFilePicker({
      suggestedName,
      types: [
        {
          description: 'JSON export',
          accept: { 'application/json': ['.json'] },
        },
      ],
    })
  }

  onStart?.()

  const response = await apiClient.requestRaw(endpoint, {
    method,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })

  if (!response.body) {
    throw new Error('Export response did not include a readable body stream')
  }

  if (fileHandle) {
    return streamToFileHandle(response.body, fileHandle, onProgress)
  }
  return bufferToBlobDownload(response.body, suggestedName, onProgress)
}

async function streamToFileHandle(
  stream: ReadableStream<Uint8Array>,
  fileHandle: any,
  onProgress?: (bytesWritten: number) => void
): Promise<StreamExportResult> {
  const writable = await fileHandle.createWritable()
  const reader = stream.getReader()
  let bytesWritten = 0
  let tail: Uint8Array = new Uint8Array(0)

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      if (value && value.byteLength) {
        await writable.write(value)
        bytesWritten += value.byteLength
        tail = keepTail(tail, value)
        onProgress?.(bytesWritten)
      }
    }
  } catch (err) {
    // Connection severed mid-stream: discard the partial write so the user is
    // never left with a half-written file that looks complete.
    await safeAbort(writable)
    throw err
  }

  if (!tailHasSentinel(tail)) {
    // Clean TCP close but truncated content — abort before commit so no file
    // is produced, then surface the error.
    await safeAbort(writable)
    throw new TruncatedExportError()
  }

  await writable.close()
  return { bytesWritten, savedVia: 'file-system-access' }
}

async function bufferToBlobDownload(
  stream: ReadableStream<Uint8Array>,
  suggestedName: string,
  onProgress?: (bytesWritten: number) => void
): Promise<StreamExportResult> {
  const reader = stream.getReader()
  const chunks: Uint8Array[] = []
  let bytesWritten = 0
  let tail: Uint8Array = new Uint8Array(0)

  // A severed connection throws here and propagates — no partial download is
  // ever triggered.
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    if (value && value.byteLength) {
      chunks.push(value)
      bytesWritten += value.byteLength
      tail = keepTail(tail, value)
      onProgress?.(bytesWritten)
    }
  }

  // Everything is in memory here, so validate before producing a file: a
  // truncated stream never yields a download at all.
  if (!tailHasSentinel(tail)) {
    throw new TruncatedExportError()
  }

  triggerBlobDownload(
    new Blob(chunks as BlobPart[], { type: 'application/json' }),
    suggestedName
  )
  return { bytesWritten, savedVia: 'blob' }
}

function triggerBlobDownload(blob: Blob, filename: string): void {
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.style.display = 'none'
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  window.URL.revokeObjectURL(url)
  document.body.removeChild(a)
}

function keepTail(prev: Uint8Array, chunk: Uint8Array): Uint8Array {
  if (chunk.byteLength >= TAIL_BYTES) {
    return chunk.slice(chunk.byteLength - TAIL_BYTES)
  }
  const combined = new Uint8Array(prev.byteLength + chunk.byteLength)
  combined.set(prev, 0)
  combined.set(chunk, prev.byteLength)
  return combined.byteLength > TAIL_BYTES
    ? combined.slice(combined.byteLength - TAIL_BYTES)
    : combined
}

function tailHasSentinel(tail: Uint8Array): boolean {
  return new TextDecoder().decode(tail).trimEnd().endsWith(EXPORT_COMPLETE_SENTINEL)
}

async function safeAbort(writable: any): Promise<void> {
  try {
    await writable.abort?.()
  } catch (err) {
    logger.debug('Failed to abort export writable stream', err)
  }
}

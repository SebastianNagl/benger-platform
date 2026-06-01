/**
 * @jest-environment node
 *
 * Streaming proxy tests (GH #68).
 *
 * The catch-all proxy used to buffer every non-204 response with
 * `await response.text()`, which OOMed the frontend pod on multi-MB exports.
 * Attachment / binary responses now stream through; everything else still
 * buffers (preserves dev preview log + simple Set-Cookie path).
 */

import { NextRequest } from 'next/server'
import { GET, POST } from '../route'
import { fetch as undiciFetch } from 'undici'

// Export/download paths in the proxy fetch through undici's own `fetch` (with a
// no-body-timeout dispatcher), not Node's global fetch. Mock it and delegate to
// the same global-fetch mock queue so a single `mockResolvedValueOnce(upstream)`
// per test covers whichever implementation the path selects.
jest.mock('undici', () => ({
  Agent: jest.fn(),
  fetch: jest.fn(),
}))

global.fetch = jest.fn()

function makeChunkStream(
  totalBytes: number,
  chunkBytes: number
): { stream: ReadableStream<Uint8Array>; chunkCount: number } {
  let emitted = 0
  const chunkCount = Math.ceil(totalBytes / chunkBytes)
  const stream = new ReadableStream<Uint8Array>({
    pull(controller) {
      if (emitted >= totalBytes) {
        controller.close()
        return
      }
      const remaining = totalBytes - emitted
      const size = Math.min(chunkBytes, remaining)
      // Fill with a non-zero byte so the bytes survive any naive truthiness check.
      controller.enqueue(new Uint8Array(size).fill(0x41))
      emitted += size
    },
  })
  return { stream, chunkCount }
}

async function readAllBytes(body: ReadableStream<Uint8Array> | null): Promise<number> {
  if (!body) return 0
  const reader = body.getReader()
  let total = 0
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    total += value.byteLength
  }
  return total
}

describe('catch-all proxy: streaming attachment responses (GH #68)', () => {
  let mockFetch: jest.MockedFunction<typeof fetch>

  beforeEach(() => {
    mockFetch = global.fetch as jest.MockedFunction<typeof fetch>
    mockFetch.mockClear()
    const mockUndiciFetch = undiciFetch as unknown as jest.Mock
    mockUndiciFetch.mockReset()
    mockUndiciFetch.mockImplementation((...args: unknown[]) =>
      (mockFetch as unknown as (...a: unknown[]) => unknown)(...args)
    )
    jest.spyOn(console, 'error').mockImplementation()
  })

  afterEach(() => {
    jest.restoreAllMocks()
  })

  it('passes attachment JSON through as a stream without buffering', async () => {
    const PAYLOAD_BYTES = 50 * 1024 * 1024 // 50MB
    const CHUNK_BYTES = 64 * 1024
    const { stream } = makeChunkStream(PAYLOAD_BYTES, CHUNK_BYTES)

    // Track whether the proxy buffered the body. If it did, `text()` would be
    // called by the implementation and the body stream would be drained before
    // we got to read it.
    const textSpy = jest.fn(async () => 'should-not-be-called')

    const upstream = {
      status: 200,
      statusText: 'OK',
      headers: new Headers({
        'content-type': 'application/json',
        'content-disposition': 'attachment; filename="tasks_export.json"',
      }),
      body: stream,
      text: textSpy,
    }
    mockFetch.mockResolvedValueOnce(upstream as unknown as Response)

    const request = new NextRequest(
      'http://localhost:3000/api/projects/p1/tasks/bulk-export',
      { method: 'POST', body: JSON.stringify({ task_ids: ['t1'] }) }
    )

    const response = await POST(request, {
      params: Promise.resolve({ path: ['projects', 'p1', 'tasks', 'bulk-export'] }),
    })

    expect(textSpy).not.toHaveBeenCalled()
    expect(response.status).toBe(200)
    expect(response.headers.get('content-disposition')).toBe(
      'attachment; filename="tasks_export.json"'
    )
    // content-length must be dropped: we're emitting chunked transfer encoding.
    expect(response.headers.get('content-length')).toBeNull()

    const totalBytes = await readAllBytes(response.body)
    expect(totalBytes).toBe(PAYLOAD_BYTES)
  })

  it('streams ZIP downloads (Content-Type alone triggers streaming)', async () => {
    const PAYLOAD_BYTES = 1 * 1024 * 1024
    const { stream } = makeChunkStream(PAYLOAD_BYTES, 32 * 1024)
    const textSpy = jest.fn()

    const upstream = {
      status: 200,
      statusText: 'OK',
      headers: new Headers({ 'content-type': 'application/zip' }),
      body: stream,
      text: textSpy,
    }
    mockFetch.mockResolvedValueOnce(upstream as unknown as Response)

    const request = new NextRequest(
      'http://localhost:3000/api/projects/bulk-export-full',
      { method: 'POST' }
    )

    const response = await POST(request, {
      params: Promise.resolve({ path: ['projects', 'bulk-export-full'] }),
    })

    expect(textSpy).not.toHaveBeenCalled()
    expect(await readAllBytes(response.body)).toBe(PAYLOAD_BYTES)
  })

  it('streams CSV downloads', async () => {
    const { stream } = makeChunkStream(64 * 1024, 4 * 1024)
    const textSpy = jest.fn()

    mockFetch.mockResolvedValueOnce({
      status: 200,
      statusText: 'OK',
      headers: new Headers({ 'content-type': 'text/csv; charset=utf-8' }),
      body: stream,
      text: textSpy,
    } as unknown as Response)

    const request = new NextRequest('http://localhost:3000/api/projects/p1/export')
    const response = await GET(request, {
      params: Promise.resolve({ path: ['projects', 'p1', 'export'] }),
    })

    expect(textSpy).not.toHaveBeenCalled()
    expect(response.body).not.toBeNull()
  })

  it('keeps buffering small JSON CRUD responses (no attachment, JSON content-type)', async () => {
    // The 99% case — must NOT regress. `text()` is called and the body is
    // returned as a string-backed NextResponse, preserving the dev preview log.
    const payload = JSON.stringify({ id: 'abc', name: 'Project X' })
    const textSpy = jest.fn(async () => payload)
    const upstream = {
      status: 200,
      statusText: 'OK',
      headers: new Headers({ 'content-type': 'application/json' }),
      body: new ReadableStream({
        start(c) {
          c.enqueue(new TextEncoder().encode(payload))
          c.close()
        },
      }),
      text: textSpy,
    }
    mockFetch.mockResolvedValueOnce(upstream as unknown as Response)

    const request = new NextRequest('http://localhost:3000/api/projects/abc')
    const response = await GET(request, {
      params: Promise.resolve({ path: ['projects', 'abc'] }),
    })

    expect(textSpy).toHaveBeenCalledTimes(1)
    expect(response.status).toBe(200)
    expect(await response.text()).toBe(payload)
  })

  it('case-insensitive Content-Disposition match (Attachment, ATTACHMENT, leading whitespace)', async () => {
    for (const disposition of [
      'Attachment; filename="x.json"',
      'ATTACHMENT; filename=y.json',
      '  attachment; filename=z.json',
    ]) {
      mockFetch.mockClear()
      const { stream } = makeChunkStream(4 * 1024, 1024)
      const textSpy = jest.fn()
      mockFetch.mockResolvedValueOnce({
        status: 200,
        statusText: 'OK',
        headers: new Headers({
          'content-type': 'application/json',
          'content-disposition': disposition,
        }),
        body: stream,
        text: textSpy,
      } as unknown as Response)

      const request = new NextRequest('http://localhost:3000/api/x/export')
      const response = await GET(request, {
        params: Promise.resolve({ path: ['x', 'export'] }),
      })
      expect(textSpy).not.toHaveBeenCalled()
      expect(response.body).not.toBeNull()
    }
  })

  it('inline Content-Disposition does NOT trigger streaming', async () => {
    // `inline` is for in-page rendering, not download. Should buffer.
    const payload = '{"ok":true}'
    const textSpy = jest.fn(async () => payload)
    mockFetch.mockResolvedValueOnce({
      status: 200,
      statusText: 'OK',
      headers: new Headers({
        'content-type': 'application/json',
        'content-disposition': 'inline',
      }),
      body: new ReadableStream({
        start(c) {
          c.enqueue(new TextEncoder().encode(payload))
          c.close()
        },
      }),
      text: textSpy,
    } as unknown as Response)

    const request = new NextRequest('http://localhost:3000/api/foo')
    await GET(request, { params: Promise.resolve({ path: ['foo'] }) })

    expect(textSpy).toHaveBeenCalledTimes(1)
  })

  it('forwards Content-Disposition and other headers on the streamed response', async () => {
    const { stream } = makeChunkStream(16 * 1024, 4 * 1024)
    mockFetch.mockResolvedValueOnce({
      status: 200,
      statusText: 'OK',
      headers: new Headers({
        'content-type': 'application/json',
        'content-disposition': 'attachment; filename="r.json"',
        'x-custom-header': 'preserved',
        'cache-control': 'no-store',
      }),
      body: stream,
      text: jest.fn(),
    } as unknown as Response)

    const request = new NextRequest('http://localhost:3000/api/x/export')
    const response = await GET(request, {
      params: Promise.resolve({ path: ['x', 'export'] }),
    })

    expect(response.headers.get('content-disposition')).toBe(
      'attachment; filename="r.json"'
    )
    expect(response.headers.get('x-custom-header')).toBe('preserved')
    expect(response.headers.get('cache-control')).toBe('no-store')
  })
})

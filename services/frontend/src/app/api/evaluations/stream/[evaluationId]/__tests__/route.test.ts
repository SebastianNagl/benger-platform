/**
 * @jest-environment node
 */

import { NextRequest } from 'next/server'
import { GET } from '../route'

// Mock global fetch
const mockFetch = jest.fn()
global.fetch = mockFetch

describe('GET /api/evaluations/stream/[evaluationId]', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('should proxy SSE request to backend API on localhost', async () => {
    const mockBody = new ReadableStream()
    mockFetch.mockResolvedValue({
      ok: true,
      body: mockBody,
    })

    const request = new NextRequest('http://localhost:3000/api/evaluations/stream/eval-123', {
      headers: { host: 'localhost:3000', cookie: 'session=abc' },
    })
    const params = Promise.resolve({ evaluationId: 'eval-123' })

    const response = await GET(request, { params })

    expect(mockFetch).toHaveBeenCalledWith(
      'http://localhost:8001/api/evaluations/stream/eval-123',
      expect.objectContaining({
        headers: expect.objectContaining({
          Cookie: 'session=abc',
          Accept: 'text/event-stream',
        }),
      })
    )
    expect(response.headers.get('Content-Type')).toBe('text/event-stream')
  })

  it('should use Docker API URL for benger.localhost', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      body: new ReadableStream(),
    })

    const request = new NextRequest('http://benger.localhost/api/evaluations/stream/eval-456', {
      headers: { host: 'benger.localhost', cookie: '' },
    })
    const params = Promise.resolve({ evaluationId: 'eval-456' })

    await GET(request, { params })

    expect(mockFetch).toHaveBeenCalledWith(
      'http://api:8000/api/evaluations/stream/eval-456',
      expect.anything()
    )
  })

  it('should use staging API URL for staging host', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      body: new ReadableStream(),
    })

    const request = new NextRequest('http://staging.what-a-benger.net/api/evaluations/stream/eval-789', {
      headers: { host: 'staging.what-a-benger.net', cookie: '' },
    })
    const params = Promise.resolve({ evaluationId: 'eval-789' })

    await GET(request, { params })

    expect(mockFetch).toHaveBeenCalledWith(
      'http://benger-api:8000/api/evaluations/stream/eval-789',
      expect.anything()
    )
  })

  it('should use production API URL for what-a-benger.net host', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      body: new ReadableStream(),
    })

    const request = new NextRequest('http://what-a-benger.net/api/evaluations/stream/eval-100', {
      headers: { host: 'what-a-benger.net', cookie: '' },
    })
    const params = Promise.resolve({ evaluationId: 'eval-100' })

    await GET(request, { params })

    expect(mockFetch).toHaveBeenCalledWith(
      'http://benger-api:8000/api/evaluations/stream/eval-100',
      expect.anything()
    )
  })

  it('should return error status when backend returns non-ok response', async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 404,
    })

    const request = new NextRequest('http://localhost:3000/api/evaluations/stream/missing', {
      headers: { host: 'localhost:3000', cookie: '' },
    })
    const params = Promise.resolve({ evaluationId: 'missing' })

    const response = await GET(request, { params })

    expect(response.status).toBe(404)
    const body = await response.json()
    expect(body.error).toBe('Failed to connect to evaluation stream')
  })

  it('should return 500 when fetch throws an error', async () => {
    mockFetch.mockRejectedValue(new Error('Connection refused'))

    const request = new NextRequest('http://localhost:3000/api/evaluations/stream/fail', {
      headers: { host: 'localhost:3000', cookie: '' },
    })
    const params = Promise.resolve({ evaluationId: 'fail' })

    const response = await GET(request, { params })

    expect(response.status).toBe(500)
    const body = await response.json()
    expect(body.error).toBe('Failed to connect to evaluation stream')
  })

  it('should pass cookies from request to backend', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      body: new ReadableStream(),
    })

    const request = new NextRequest('http://localhost:3000/api/evaluations/stream/eval-123', {
      headers: {
        host: 'localhost:3000',
        cookie: 'session=xyz123; other=abc',
      },
    })
    const params = Promise.resolve({ evaluationId: 'eval-123' })

    await GET(request, { params })

    expect(mockFetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        headers: expect.objectContaining({
          Cookie: 'session=xyz123; other=abc',
        }),
      })
    )
  })
})

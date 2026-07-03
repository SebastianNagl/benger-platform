/**
 * Tests for the resend-verification API route — a dedicated proxy (the generic
 * [...path] proxy blocks /api/auth/*). Its reason to exist is forwarding
 * x-forwarded-host so the backend brands the verification email host-aware.
 */
import '@testing-library/jest-dom'
import { NextRequest } from 'next/server'
import { POST } from '../route'

describe('/api/auth/resend-verification', () => {
  let originalFetch: typeof global.fetch

  beforeEach(() => {
    originalFetch = global.fetch
    global.fetch = jest.fn()
    jest.spyOn(console, 'log').mockImplementation(() => {})
    jest.spyOn(console, 'error').mockImplementation(() => {})
  })

  afterEach(() => {
    global.fetch = originalFetch
    jest.restoreAllMocks()
  })

  const makeReq = (host: string, body: unknown = { email: 'x@example.com', language: 'de' }) =>
    new NextRequest(`http://${host}/api/auth/resend-verification`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', host },
      body: JSON.stringify(body),
    })

  it('forwards to the backend and returns its status/body', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValueOnce({
      status: 200,
      json: async () => ({ message: 'If the email exists and is unverified, a link has been sent' }),
    })

    const response = await POST(makeReq('benger.localhost'))

    expect(response.status).toBe(200)
    const data = await response.json()
    expect(data.message).toContain('If the email exists')
  })

  it('forwards x-forwarded-host so the backend can brand the email', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValueOnce({
      status: 200,
      json: async () => ({ message: 'ok' }),
    })

    await POST(makeReq('vertretbar.localhost'))

    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/auth/resend-verification'),
      expect.objectContaining({
        headers: expect.objectContaining({ 'x-forwarded-host': 'vertretbar.localhost' }),
      })
    )
  })

  it('passes through a backend error status (e.g. rate limit)', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValueOnce({
      status: 429,
      json: async () => ({ detail: 'Too many requests' }),
    })

    const response = await POST(makeReq('benger.localhost'))
    expect(response.status).toBe(429)
  })

  it('returns 500 on a network error', async () => {
    ;(global.fetch as jest.Mock).mockRejectedValueOnce(new Error('Network error'))

    const response = await POST(makeReq('benger.localhost'))
    expect(response.status).toBe(500)
    const data = await response.json()
    expect(data.error).toBe('Internal server error')
  })

  it('returns 500 on an invalid JSON body', async () => {
    const request = new NextRequest('http://benger.localhost/api/auth/resend-verification', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', host: 'benger.localhost' },
      body: 'not json',
    })

    const response = await POST(request)
    expect(response.status).toBe(500)
  })
})

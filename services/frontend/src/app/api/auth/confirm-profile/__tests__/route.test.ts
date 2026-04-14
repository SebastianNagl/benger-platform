/**
 * @jest-environment node
 */

import { NextRequest } from 'next/server'
import { POST } from '../route'

// Mock fetch
const mockFetch = jest.fn()
global.fetch = mockFetch

describe('POST /api/auth/confirm-profile', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('should proxy request to backend and return JSON on success', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ confirmed: true }),
    })

    const request = new NextRequest('http://benger.localhost/api/auth/confirm-profile', {
      method: 'POST',
      headers: {
        host: 'benger.localhost',
        cookie: 'session=abc',
        authorization: 'Bearer token123',
      },
    })

    const response = await POST(request)
    const data = await response.json()

    expect(data).toEqual({ confirmed: true })
    expect(mockFetch).toHaveBeenCalledWith(
      'http://api:8000/api/auth/confirm-profile',
      expect.objectContaining({
        method: 'POST',
      })
    )
  })

  it('should return error on backend failure', async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 400,
      text: () => Promise.resolve('Bad request'),
    })

    const request = new NextRequest('http://benger.localhost/api/auth/confirm-profile', {
      method: 'POST',
      headers: { host: 'benger.localhost' },
    })

    const response = await POST(request)
    const data = await response.json()

    expect(response.status).toBe(400)
    expect(data.error).toBe('Bad request')
  })

  it('should return 500 on fetch error', async () => {
    mockFetch.mockRejectedValue(new Error('Network error'))

    const request = new NextRequest('http://benger.localhost/api/auth/confirm-profile', {
      method: 'POST',
      headers: { host: 'benger.localhost' },
    })

    const response = await POST(request)
    expect(response.status).toBe(500)
  })

  it('should use correct API URL for test environment', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({}),
    })

    const request = new NextRequest('http://benger-test.localhost/api/auth/confirm-profile', {
      method: 'POST',
      headers: { host: 'benger-test.localhost' },
    })

    await POST(request)

    expect(mockFetch).toHaveBeenCalledWith(
      'http://test-api:8000/api/auth/confirm-profile',
      expect.anything()
    )
  })

  it('should use correct API URL for production', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({}),
    })

    const request = new NextRequest('http://what-a-benger.net/api/auth/confirm-profile', {
      method: 'POST',
      headers: { host: 'what-a-benger.net' },
    })

    await POST(request)

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/auth/confirm-profile'),
      expect.anything()
    )
  })
})

/**
 * @jest-environment node
 *
 * Coverage tests for signup route - specifically the cookie forwarding paths
 * that are skipped in the main test file due to Cookie API limitations.
 */

import { NextRequest } from 'next/server'
import { POST } from '../route'

describe('/api/auth/signup - cookie forwarding coverage', () => {
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

  it('should forward and modify Set-Cookie headers with domain and SameSite', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      status: 201,
      headers: {
        getSetCookie: () => [
          'session=abc123; Path=/; HttpOnly; Secure',
          'token=xyz789; Domain=api.localhost; HttpOnly',
        ],
      },
      json: async () => ({
        id: 1,
        email: 'user@example.com',
        access_token: 'token_123',
      }),
    })

    const request = new NextRequest('http://benger.localhost/api/auth/signup', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        host: 'benger.localhost',
      },
      body: JSON.stringify({
        email: 'user@example.com',
        password: 'SecurePass123!',
        username: 'newuser',
      }),
    })

    const response = await POST(request)

    expect(response.status).toBe(201)

    // Verify Set-Cookie headers were forwarded with modifications
    const setCookieHeaders = response.headers.getSetCookie()
    expect(setCookieHeaders.length).toBe(2)

    // First cookie: should have Secure removed, SameSite added, Domain added
    const cookie1 = setCookieHeaders[0]
    expect(cookie1).toContain('session=abc123')
    expect(cookie1).toContain('Domain=.benger.localhost')
    expect(cookie1).not.toMatch(/;\s*Secure/i) // Secure removed for dev
    expect(cookie1).toContain('SameSite=Lax')

    // Second cookie: existing Domain should be replaced
    const cookie2 = setCookieHeaders[1]
    expect(cookie2).toContain('token=xyz789')
    expect(cookie2).not.toContain('Domain=api.localhost')
    expect(cookie2).toContain('Domain=.benger.localhost')
    expect(cookie2).toContain('SameSite=Lax')
  })

  it('should add Path=/ when not present in cookie', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      status: 201,
      headers: {
        getSetCookie: () => [
          'session=abc123; HttpOnly',
        ],
      },
      json: async () => ({
        id: 1,
        email: 'user@example.com',
      }),
    })

    const request = new NextRequest('http://benger.localhost/api/auth/signup', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        host: 'benger.localhost',
      },
      body: JSON.stringify({
        email: 'user@example.com',
        password: 'SecurePass123!',
        username: 'newuser',
      }),
    })

    const response = await POST(request)
    const setCookieHeaders = response.headers.getSetCookie()
    expect(setCookieHeaders.length).toBe(1)
    expect(setCookieHeaders[0]).toContain('Path=/')
  })

  it('should not duplicate Path when already present', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      status: 201,
      headers: {
        getSetCookie: () => [
          'session=abc; Path=/api; HttpOnly',
        ],
      },
      json: async () => ({ id: 1 }),
    })

    const request = new NextRequest('http://benger.localhost/api/auth/signup', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        host: 'benger.localhost',
      },
      body: JSON.stringify({ email: 'u@e.com', password: 'Pass123!', username: 'u' }),
    })

    const response = await POST(request)
    const cookies = response.headers.getSetCookie()
    // Path=/ should NOT be appended since Path=/api already exists
    expect(cookies[0]).toContain('Path=/api')
  })

  it('should use staging API URL for staging host', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      status: 201,
      headers: { getSetCookie: () => [] },
      json: async () => ({ id: 1 }),
    })

    const request = new NextRequest('http://staging.what-a-benger.net/api/auth/signup', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        host: 'staging.what-a-benger.net',
      },
      body: JSON.stringify({ email: 'u@e.com', password: 'Pass123!', username: 'u' }),
    })

    await POST(request)

    expect(global.fetch).toHaveBeenCalledWith(
      'http://benger-api:8000/api/auth/signup',
      expect.any(Object)
    )
  })

  it('should use API_BASE_URL env var when set', async () => {
    const orig = process.env.API_BASE_URL
    process.env.API_BASE_URL = 'http://custom:9000'

    ;(global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      status: 201,
      headers: { getSetCookie: () => [] },
      json: async () => ({ id: 1 }),
    })

    const request = new NextRequest('http://localhost:3000/api/auth/signup', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        host: 'localhost:3000',
      },
      body: JSON.stringify({ email: 'u@e.com', password: 'Pass123!', username: 'u' }),
    })

    await POST(request)

    expect(global.fetch).toHaveBeenCalledWith(
      'http://custom:9000/api/auth/signup',
      expect.any(Object)
    )

    if (orig) {
      process.env.API_BASE_URL = orig
    } else {
      delete process.env.API_BASE_URL
    }
  })

  it('should use benger-test API URL for test host', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      status: 201,
      headers: { getSetCookie: () => [] },
      json: async () => ({ id: 1 }),
    })

    const request = new NextRequest('http://benger-test.localhost/api/auth/signup', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        host: 'benger-test.localhost',
      },
      body: JSON.stringify({ email: 'u@e.com', password: 'Pass123!', username: 'u' }),
    })

    await POST(request)

    expect(global.fetch).toHaveBeenCalledWith(
      'http://test-api:8000/api/auth/signup',
      expect.any(Object)
    )
  })

  it('should default to http://api:8000 for unknown hosts', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      status: 201,
      headers: { getSetCookie: () => [] },
      json: async () => ({ id: 1 }),
    })

    const request = new NextRequest('http://unknown-host/api/auth/signup', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        host: 'unknown-host',
      },
      body: JSON.stringify({ email: 'u@e.com', password: 'Pass123!', username: 'u' }),
    })

    await POST(request)

    expect(global.fetch).toHaveBeenCalledWith(
      'http://api:8000/api/auth/signup',
      expect.any(Object)
    )
  })
})

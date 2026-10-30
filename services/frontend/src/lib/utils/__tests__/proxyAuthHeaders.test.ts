/**
 * @jest-environment node
 *
 * Dedicated Next route handlers pass the caller's access key through to the
 * API (core 2.45: keys work on the whole API), next to the session cookie.
 */

global.fetch = jest.fn()

import { NextRequest } from 'next/server'

import { GET as getMandatoryProfileStatus } from '@/app/api/auth/mandatory-profile-status/route'
import { GET as getMeContexts } from '@/app/api/auth/me/contexts/route'
import { GET as getMe } from '@/app/api/auth/me/route'
import { GET as getProfileHistory } from '@/app/api/auth/profile-history/route'
import { GET as getProfile } from '@/app/api/auth/profile/route'
import { GET as getEvaluationStream } from '@/app/api/evaluations/stream/[evaluationId]/route'

import { proxyAuthHeaders } from '../proxyAuthHeaders'

const KEY = 'Bearer bgr_live_abcd1234_SECRET'

const req = (url: string, headers: Record<string, string> = {}) =>
  new NextRequest(url, { headers })

describe('proxyAuthHeaders', () => {
  it('forwards the cookie and an incoming Authorization header unchanged', () => {
    expect(
      proxyAuthHeaders(
        req('http://localhost/x', {
          cookie: 'access_token=t',
          authorization: KEY,
        }),
      ),
    ).toEqual({ Cookie: 'access_token=t', Authorization: KEY })
  })

  it('keeps an empty cookie and sends no Authorization without one', () => {
    const headers = proxyAuthHeaders(req('http://localhost/x'))
    expect(headers).toEqual({ Cookie: '' })
    expect(headers).not.toHaveProperty('Authorization')
  })
})

describe('route handlers forward the access key', () => {
  const mockFetch = global.fetch as jest.MockedFunction<typeof fetch>

  beforeEach(() => {
    mockFetch.mockReset()
    mockFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({}),
      text: () => Promise.resolve('{}'),
      body: null,
    } as unknown as Response)
  })

  const sentHeaders = () =>
    mockFetch.mock.calls[0][1]?.headers as Record<string, string>

  it.each([
    [
      'auth/me',
      () =>
        getMe(req('http://localhost:3000/api/auth/me', { authorization: KEY })),
    ],
    [
      'auth/me/contexts',
      () =>
        getMeContexts(
          req('http://localhost:3000/api/auth/me/contexts', {
            authorization: KEY,
          }),
        ),
    ],
    [
      'auth/profile',
      () =>
        getProfile(
          req('http://localhost:3000/api/auth/profile', { authorization: KEY }),
        ),
    ],
    [
      'auth/profile-history',
      () =>
        getProfileHistory(
          req('http://localhost:3000/api/auth/profile-history', {
            authorization: KEY,
          }),
        ),
    ],
    [
      'auth/mandatory-profile-status',
      () =>
        getMandatoryProfileStatus(
          req('http://localhost:3000/api/auth/mandatory-profile-status', {
            authorization: KEY,
          }),
        ),
    ],
    [
      'evaluations/stream',
      () =>
        getEvaluationStream(
          req('http://localhost:3000/api/evaluations/stream/ev-1', {
            authorization: KEY,
          }),
          { params: Promise.resolve({ evaluationId: 'ev-1' }) },
        ),
    ],
  ])('%s passes Authorization through', async (_name, call) => {
    await call()
    expect(mockFetch).toHaveBeenCalledTimes(1)
    expect(sentHeaders()).toEqual(
      expect.objectContaining({ Authorization: KEY, Cookie: '' }),
    )
  })

  it('keeps forwarding the session cookie without a key', async () => {
    await getMe(
      req('http://localhost:3000/api/auth/me', { cookie: 'access_token=t' }),
    )
    expect(sentHeaders()).toEqual({ Cookie: 'access_token=t' })
  })
})

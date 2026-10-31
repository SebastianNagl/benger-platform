import {
  apiErrorMessage,
  formatErrorDetail,
  rateLimitMessage,
  rateLimitRetryAfter,
} from '../errors'

const apiError = (detail: unknown) =>
  Object.assign(new Error('HTTP error! status: 422'), {
    response: { status: 422, data: detail === undefined ? null : { detail } },
  })

describe('apiErrorMessage', () => {
  it('uses the server detail string', () => {
    expect(apiErrorMessage(apiError('No prompt structure'), 'fallback')).toBe(
      'No prompt structure',
    )
  })

  it('flattens a FastAPI validation list instead of passing the array on', () => {
    const detail = [{ loc: ['body', 'structure_keys'], msg: 'field required' }]
    expect(apiErrorMessage(apiError(detail), 'fallback')).toBe(
      'structure_keys: field required',
    )
  })

  it('falls back when the server sent no detail', () => {
    expect(apiErrorMessage(apiError(undefined), 'fallback')).toBe('fallback')
    expect(apiErrorMessage(new Error('network'), 'fallback')).toBe('fallback')
    expect(apiErrorMessage(undefined, 'fallback')).toBe('fallback')
  })
})

describe('formatErrorDetail', () => {
  it('returns null for an empty detail', () => {
    expect(formatErrorDetail(null)).toBeNull()
  })
})

describe('rateLimitRetryAfter / rateLimitMessage', () => {
  const t = (key: string, vars?: Record<string, string | number>) =>
    `${key}:${vars?.minutes}`
  const limited = (retryAfter: number) => ({
    detail: { code: 'rate_limited', retry_after: retryAfter },
  })

  it('reads retry_after from a 429 rate_limited body only', () => {
    expect(rateLimitRetryAfter(429, limited(120))).toBe(120)
    expect(rateLimitRetryAfter(401, limited(120))).toBeNull()
    expect(rateLimitRetryAfter(429, { detail: 'Too many' })).toBeNull()
    expect(rateLimitRetryAfter(429, { detail: { code: 'other' } })).toBeNull()
    expect(rateLimitRetryAfter(429, null)).toBeNull()
  })

  it('rounds the wait up to whole minutes', () => {
    expect(rateLimitMessage(429, t, limited(900))).toBe('auth.rateLimited:15')
    expect(rateLimitMessage(429, t, limited(61))).toBe('auth.rateLimited:2')
    expect(rateLimitMessage(429, t, limited(5))).toBe('auth.rateLimited:1')
  })

  it('reads a thrown API client error', () => {
    const error = Object.assign(new Error('{"code":"rate_limited"}'), {
      response: { status: 429, data: limited(300) },
    })
    expect(rateLimitMessage(error, t)).toBe('auth.rateLimited:5')
    expect(rateLimitMessage(new Error('Incorrect password'), t)).toBeNull()
    expect(rateLimitMessage(undefined, t)).toBeNull()
  })
})

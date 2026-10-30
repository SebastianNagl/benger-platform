import { apiErrorMessage, formatErrorDetail } from '../errors'

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

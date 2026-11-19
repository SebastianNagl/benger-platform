/**
 * Tests for the annotator agreement client (routers/evaluations/metadata/agreement.py).
 */

import { getAnnotatorAgreement, hasAgreement } from '../agreement'

const mockApi = { get: jest.fn() }

jest.mock('@/lib/api', () => ({
  __esModule: true,
  get default() {
    return mockApi
  },
}))

describe('annotator agreement client', () => {
  beforeEach(() => {
    mockApi.get.mockReset()
  })

  it('reads the project route with an encoded id', async () => {
    mockApi.get.mockResolvedValue({ available: false })
    await expect(getAnnotatorAgreement('a/b')).resolves.toEqual({
      available: false,
    })
    expect(mockApi.get).toHaveBeenCalledWith(
      '/evaluations/projects/a%2Fb/annotator-agreement',
    )
  })

  it('hasAgreement needs at least one scored control', () => {
    expect(hasAgreement(null)).toBe(false)
    expect(hasAgreement(undefined)).toBe(false)
    expect(hasAgreement({ controls: [] })).toBe(false)
    expect(hasAgreement({ controls: [{} as any] })).toBe(true)
  })
})

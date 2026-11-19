/**
 * Tests for the code validation client (services/api/routers/coding.py).
 */

import { codingAPI } from '../coding'

const mockApi = { get: jest.fn() }

jest.mock('@/lib/api', () => ({
  __esModule: true,
  get default() {
    return mockApi
  },
}))

describe('codingAPI', () => {
  beforeEach(() => {
    mockApi.get.mockReset()
    mockApi.get.mockResolvedValue({ items: [], total: 0 })
  })

  it('reads one validation with an encoded id', async () => {
    mockApi.get.mockResolvedValue({ id: 'a/b' })
    await expect(codingAPI.getValidation('a/b')).resolves.toEqual({
      id: 'a/b',
    })
    expect(mockApi.get).toHaveBeenCalledWith('/code-validations/a%2Fb', {
      cache: 'no-store',
    })
  })

  it("lists the validations of a project's answers, paged", async () => {
    await expect(codingAPI.listAnswerValidations('p 1')).resolves.toEqual({
      items: [],
      total: 0,
    })
    expect(mockApi.get).toHaveBeenCalledWith(
      '/projects/p%201/code-validations?of=answers&limit=50&offset=0',
      { cache: 'no-store' },
    )
    await codingAPI.listAnswerValidations('p', 10, 20)
    expect(mockApi.get).toHaveBeenLastCalledWith(
      '/projects/p/code-validations?of=answers&limit=10&offset=20',
      { cache: 'no-store' },
    )
  })
})

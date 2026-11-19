/**
 * The client of the variant and request views: the request path of every
 * call and how it unpacks the answers.
 */

import { variantViewsAPI } from '../variantViews'

const mockGet = jest.fn()
const mockPost = jest.fn()
jest.mock('@/lib/api', () => ({
  __esModule: true,
  default: {
    get: (...a: unknown[]) => mockGet(...a),
    post: (...a: unknown[]) => mockPost(...a),
  },
}))

beforeEach(() => jest.clearAllMocks())

describe('variantViewsAPI', () => {
  it('lists the designs of a project', async () => {
    mockGet.mockResolvedValueOnce({ items: [{ key: 'a' }] })
    await expect(variantViewsAPI.listDesigns('p 1')).resolves.toEqual([
      { key: 'a' },
    ])
    expect(mockGet).toHaveBeenCalledWith('/projects/p%201/variant-designs', {
      cache: 'no-store',
    })
    mockGet.mockResolvedValueOnce(null)
    await expect(variantViewsAPI.listDesigns('p')).resolves.toEqual([])
  })

  it('checks a design', async () => {
    mockPost.mockResolvedValueOnce({ content_hash: 'h' })
    await variantViewsAPI.checkDesign('p', 'a/b')
    expect(mockPost).toHaveBeenCalledWith(
      '/projects/p/variant-designs/a%2Fb/check',
      {},
    )
  })

  it('pages through units and loads one', async () => {
    mockGet.mockResolvedValue({})
    await variantViewsAPI.listUnits('p', 'swap')
    expect(mockGet).toHaveBeenLastCalledWith(
      '/projects/p/variant-designs/swap/units?limit=20&offset=0',
    )
    await variantViewsAPI.listUnits('p', 'swap', 5, 10)
    expect(mockGet).toHaveBeenLastCalledWith(
      '/projects/p/variant-designs/swap/units?limit=5&offset=10',
    )
    await variantViewsAPI.getUnit('p', 'swap', 'case/1')
    expect(mockGet).toHaveBeenLastCalledWith(
      '/projects/p/variant-designs/swap/units/case%2F1',
    )
    await variantViewsAPI.getUnit('p', 'swap', 'u1', 'model@abc')
    expect(mockGet).toHaveBeenLastCalledWith(
      '/projects/p/variant-designs/swap/units/u1?system=model%40abc',
    )
  })

  it('loads a request record under its run or by the trial alone', async () => {
    mockGet.mockResolvedValue({})
    await variantViewsAPI.getTrialRequest('t1', 'g1')
    expect(mockGet).toHaveBeenLastCalledWith(
      '/runs/generations/g1/trials/t1/request',
    )
    await variantViewsAPI.getTrialRequest('t 2')
    expect(mockGet).toHaveBeenLastCalledWith('/runs/trials/t%202/request')
  })
})

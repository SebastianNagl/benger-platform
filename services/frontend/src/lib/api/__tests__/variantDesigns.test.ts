/**
 * The variant designs API client: request paths and bodies, and the reading
 * of a refusal (code, message, problems and the check report of a refused
 * freeze).
 */

import { variantDesignRefusalOf, variantDesignsAPI } from '../variantDesigns'

const mockGet = jest.fn()
const mockPost = jest.fn()
jest.mock('@/lib/api', () => ({
  __esModule: true,
  default: {
    get: (...a: unknown[]) => mockGet(...a),
    post: (...a: unknown[]) => mockPost(...a),
  },
}))

beforeEach(() => {
  jest.clearAllMocks()
})

describe('variantDesignsAPI', () => {
  it('lists the designs of a project, uncached', async () => {
    mockGet.mockResolvedValue({ items: [{ key: 'a' }] })
    expect(await variantDesignsAPI.list('p/1')).toEqual([{ key: 'a' }])
    expect(mockGet).toHaveBeenCalledWith('/projects/p%2F1/variant-designs', {
      cache: 'no-store',
    })
    mockGet.mockResolvedValue(null)
    expect(await variantDesignsAPI.list('p1')).toEqual([])
  })

  it('checks, freezes and imports through the design routes', async () => {
    mockPost.mockResolvedValue({})
    await variantDesignsAPI.check('p1', 'role swap')
    expect(mockPost).toHaveBeenLastCalledWith(
      '/projects/p1/variant-designs/role%20swap/check',
      {},
    )
    await variantDesignsAPI.freeze('p1', 'd')
    expect(mockPost).toHaveBeenLastCalledWith(
      '/projects/p1/variant-designs/d/freeze',
      {},
    )
    const doc = { format: 'f', key: 'k', spec: {} }
    await variantDesignsAPI.importDocument('p1', doc)
    expect(mockPost).toHaveBeenLastCalledWith(
      '/projects/p1/variant-designs/import',
      doc,
    )
  })
})

describe('variantDesignRefusalOf', () => {
  const error = (status: number, detail: unknown) => ({
    response: { status, data: { detail } },
  })

  it('reads code, message, problems and report', () => {
    const report = { ok: false }
    expect(
      variantDesignRefusalOf(
        error(409, {
          code: 'variant_design_checks_failed',
          message: 'fails',
          report,
        }),
      ),
    ).toEqual({
      status: 409,
      code: 'variant_design_checks_failed',
      message: 'fails',
      problems: [],
      report,
    })
    expect(
      variantDesignRefusalOf(
        error(422, {
          code: 'variant_design_invalid',
          problems: [{ message: 'm' }],
        }),
      ),
    ).toEqual({
      status: 422,
      code: 'variant_design_invalid',
      message: 'variant_design_invalid',
      problems: [{ message: 'm' }],
      report: null,
    })
  })

  it('is null for errors without a coded detail', () => {
    expect(variantDesignRefusalOf(error(403, 'Access denied'))).toBeNull()
    expect(variantDesignRefusalOf(error(500, { message: 'x' }))).toBeNull()
    expect(variantDesignRefusalOf(new Error('x'))).toBeNull()
    expect(variantDesignRefusalOf(null)).toBeNull()
  })
})

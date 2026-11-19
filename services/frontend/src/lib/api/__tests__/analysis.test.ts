/**
 * The analysis API client: the request paths and bodies of every call, the
 * paging of the estimates, and the helpers that read run statuses and API
 * errors.
 */

import {
  analysisAPI,
  ESTIMATES_PAGE_SIZE,
  isRunActive,
  specErrorsOf,
  statusOf,
} from '../analysis'

const mockGet = jest.fn()
const mockPost = jest.fn()
jest.mock('@/lib/api', () => ({
  __esModule: true,
  default: {
    get: (...a: unknown[]) => mockGet(...a),
    post: (...a: unknown[]) => mockPost(...a),
  },
}))

const NO_STORE = { cache: 'no-store' }

beforeEach(() => {
  jest.clearAllMocks()
})

describe('analysis API helpers', () => {
  it('tells which run statuses can still change', () => {
    expect(isRunActive('pending')).toBe(true)
    expect(isRunActive('running')).toBe(true)
    expect(isRunActive('completed')).toBe(false)
    expect(isRunActive('failed')).toBe(false)
  })

  it('reads the problems of a rejected spec', () => {
    const rejected = {
      response: {
        status: 422,
        data: {
          detail: { code: 'invalid_analysis_spec', errors: ['a', 2] },
        },
      },
    }
    expect(specErrorsOf(rejected)).toEqual(['a', '2'])
    expect(
      specErrorsOf({
        response: { status: 422, data: { detail: { code: 'other' } } },
      }),
    ).toBeNull()
    expect(
      specErrorsOf({ response: { status: 422, data: { detail: 'text' } } }),
    ).toBeNull()
    expect(
      specErrorsOf({
        response: {
          status: 422,
          data: { detail: { code: 'invalid_analysis_spec', errors: 'x' } },
        },
      }),
    ).toBeNull()
    expect(specErrorsOf({ response: { status: 500 } })).toBeNull()
    expect(specErrorsOf(new Error('x'))).toBeNull()
    expect(specErrorsOf(null)).toBeNull()
  })

  it('reads the HTTP status of an error', () => {
    expect(statusOf({ response: { status: 404 } })).toBe(404)
    expect(statusOf(new Error('x'))).toBeUndefined()
    expect(statusOf(null)).toBeUndefined()
  })
})

describe('analysisAPI', () => {
  it('lists the runs of a project, uncached', async () => {
    mockGet.mockResolvedValue({ items: [], total: 0 })
    await analysisAPI.listRuns('p/1')
    expect(mockGet).toHaveBeenCalledWith(
      '/projects/p%2F1/analysis-runs?limit=50&offset=0',
      NO_STORE,
    )
    await analysisAPI.listRuns('p1', 1, 10)
    expect(mockGet).toHaveBeenLastCalledWith(
      '/projects/p1/analysis-runs?limit=1&offset=10',
      NO_STORE,
    )
  })

  it('reads one run and its frame download', async () => {
    mockGet.mockResolvedValue({})
    await analysisAPI.getRun('r 1')
    expect(mockGet).toHaveBeenCalledWith('/analysis-runs/r%201', NO_STORE)
    await analysisAPI.getFrameDownload('r1')
    expect(mockGet).toHaveBeenLastCalledWith(
      '/analysis-runs/r1/frame?json=1',
      NO_STORE,
    )
  })

  it('pages through the estimates until a short page', async () => {
    const full = Array.from({ length: ESTIMATES_PAGE_SIZE }, (_, i) => ({
      position: i,
    }))
    mockGet
      .mockResolvedValueOnce({ items: full })
      .mockResolvedValueOnce({ items: [{ position: ESTIMATES_PAGE_SIZE }] })
    const all = await analysisAPI.listEstimates('r1')
    expect(all).toHaveLength(ESTIMATES_PAGE_SIZE + 1)
    expect(mockGet).toHaveBeenNthCalledWith(
      1,
      `/analysis-runs/r1/estimates?limit=${ESTIMATES_PAGE_SIZE}&offset=0`,
      NO_STORE,
    )
    expect(mockGet).toHaveBeenNthCalledWith(
      2,
      `/analysis-runs/r1/estimates?limit=${ESTIMATES_PAGE_SIZE}&offset=${ESTIMATES_PAGE_SIZE}`,
      NO_STORE,
    )
  })

  it('treats a page without items as the last one', async () => {
    mockGet.mockResolvedValue(null)
    expect(await analysisAPI.listEstimates('r1')).toEqual([])
  })

  it('lists the design keys, skipping malformed entries', async () => {
    mockGet.mockResolvedValue({
      items: [{ key: 'a' }, { key: 3 }, {}, null, { key: 'b' }],
    })
    expect(await analysisAPI.listDesignKeys('p1')).toEqual(['a', 'b'])
    expect(mockGet).toHaveBeenCalledWith(
      '/projects/p1/variant-designs',
      NO_STORE,
    )
    mockGet.mockResolvedValue(undefined)
    expect(await analysisAPI.listDesignKeys('p1')).toEqual([])
  })

  it('validates a spec and starts runs with a trimmed name', async () => {
    mockPost.mockResolvedValue({})
    await analysisAPI.validateSpec({ spec_version: 1 })
    expect(mockPost).toHaveBeenCalledWith('/analysis/specs/validate', {
      spec: { spec_version: 1 },
    })
    await analysisAPI.startRun('p1', { s: 1 }, '  My run ')
    expect(mockPost).toHaveBeenLastCalledWith('/projects/p1/analysis-runs', {
      spec: { s: 1 },
      name: 'My run',
    })
    await analysisAPI.startRun('p1', { s: 1 }, '   ')
    expect(mockPost).toHaveBeenLastCalledWith('/projects/p1/analysis-runs', {
      spec: { s: 1 },
    })
    await analysisAPI.startRun('p1', { s: 1 })
    expect(mockPost).toHaveBeenLastCalledWith('/projects/p1/analysis-runs', {
      spec: { s: 1 },
    })
  })
})

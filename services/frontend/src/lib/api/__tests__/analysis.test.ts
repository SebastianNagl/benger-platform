/**
 * Tests for the analysis API client: run and estimate reads (uncached, the
 * estimates paged through), spec validation, starting runs, and the error
 * helpers the analysis pages use.
 */

import apiClient from '@/lib/api'
import {
  analysisAPI,
  ESTIMATES_PAGE_SIZE,
  isRunActive,
  specErrorsOf,
  statusOf,
} from '../analysis'

jest.mock('@/lib/api', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn() },
}))

const mockGet = apiClient.get as jest.Mock
const mockPost = apiClient.post as jest.Mock
const NO_STORE = { cache: 'no-store' }

beforeEach(() => jest.clearAllMocks())

describe('analysis API helpers', () => {
  it('knows which runs can still change', () => {
    expect(isRunActive('pending')).toBe(true)
    expect(isRunActive('running')).toBe(true)
    expect(isRunActive('completed')).toBe(false)
    expect(isRunActive('failed')).toBe(false)
  })

  it('reads the problems of a rejected spec and nothing else', () => {
    const rejected = {
      response: {
        status: 422,
        data: { detail: { code: 'invalid_analysis_spec', errors: ['a', 2] } },
      },
    }
    expect(specErrorsOf(rejected)).toEqual(['a', '2'])
    expect(
      specErrorsOf({ response: { status: 422, data: { detail: 'bad' } } }),
    ).toBeNull()
    expect(
      specErrorsOf({
        response: {
          status: 422,
          data: { detail: { code: 'other', errors: [] } },
        },
      }),
    ).toBeNull()
    expect(specErrorsOf({ response: { status: 500 } })).toBeNull()
    expect(specErrorsOf(null)).toBeNull()
    expect(specErrorsOf(new Error('x'))).toBeNull()
  })

  it('reads the HTTP status of a failed call', () => {
    expect(statusOf({ response: { status: 403 } })).toBe(403)
    expect(statusOf(new Error('x'))).toBeUndefined()
    expect(statusOf(null)).toBeUndefined()
  })
})

describe('analysisAPI', () => {
  it('lists runs with paging, uncached', async () => {
    mockGet.mockResolvedValue({ items: [], total: 0 })
    await analysisAPI.listRuns('p/1', 20, 40)
    expect(mockGet).toHaveBeenCalledWith(
      '/projects/p%2F1/analysis-runs?limit=20&offset=40',
      NO_STORE,
    )
    await analysisAPI.listRuns('p1')
    expect(mockGet).toHaveBeenLastCalledWith(
      '/projects/p1/analysis-runs?limit=50&offset=0',
      NO_STORE,
    )
  })

  it('reads one run and its frame download, uncached', async () => {
    mockGet.mockResolvedValue({ id: 'r1' })
    expect(await analysisAPI.getRun('r 1')).toEqual({ id: 'r1' })
    expect(mockGet).toHaveBeenCalledWith('/analysis-runs/r%201', NO_STORE)
    await analysisAPI.getFrameDownload('r1')
    expect(mockGet).toHaveBeenLastCalledWith(
      '/analysis-runs/r1/frame?json=1',
      NO_STORE,
    )
  })

  it('pages through every estimate of a run', async () => {
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

  it('treats an empty estimates answer as the last page', async () => {
    mockGet.mockResolvedValue(null)
    expect(await analysisAPI.listEstimates('r1')).toEqual([])
    expect(mockGet).toHaveBeenCalledTimes(1)
  })

  it('lists the keys of the variant designs', async () => {
    mockGet.mockResolvedValue({
      items: [{ key: 'a' }, { key: 3 }, {}, null, { key: 'b' }],
    })
    expect(await analysisAPI.listDesignKeys('p1')).toEqual(['a', 'b'])
    expect(mockGet).toHaveBeenCalledWith(
      '/projects/p1/variant-designs',
      NO_STORE,
    )
    mockGet.mockResolvedValue(null)
    expect(await analysisAPI.listDesignKeys('p1')).toEqual([])
  })

  it('validates specs and starts runs with a trimmed name', async () => {
    mockPost.mockResolvedValue({ valid: true })
    await analysisAPI.validateSpec({ spec_version: 1 })
    expect(mockPost).toHaveBeenCalledWith('/analysis/specs/validate', {
      spec: { spec_version: 1 },
    })

    await analysisAPI.startRun('p1', { a: 1 }, '  main  ')
    expect(mockPost).toHaveBeenLastCalledWith('/projects/p1/analysis-runs', {
      spec: { a: 1 },
      name: 'main',
    })
    await analysisAPI.startRun('p1', { a: 1 }, '   ')
    expect(mockPost).toHaveBeenLastCalledWith('/projects/p1/analysis-runs', {
      spec: { a: 1 },
    })
    await analysisAPI.startRun('p1', { a: 1 })
    expect(mockPost).toHaveBeenLastCalledWith('/projects/p1/analysis-runs', {
      spec: { a: 1 },
    })
  })
})

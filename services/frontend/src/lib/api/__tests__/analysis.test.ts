/**
 * Tests for the analysis-run API client (lib/api/analysis): the request
 * paths and bodies, estimate paging, the design-key list, the analysis
 * plans read from and saved to the evaluation config, and the error helpers
 * the run pages use.
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
const mockPut = jest.fn()

jest.mock('@/lib/api', () => ({
  __esModule: true,
  default: {
    get: (...args: unknown[]) => mockGet(...args),
    post: (...args: unknown[]) => mockPost(...args),
    put: (...args: unknown[]) => mockPut(...args),
  },
}))

const NO_STORE = { cache: 'no-store' }

beforeEach(() => {
  mockGet.mockReset()
  mockPost.mockReset()
  mockPut.mockReset()
})

describe('analysisAPI', () => {
  it('lists the runs of a project with limit and offset', async () => {
    mockGet.mockResolvedValue({ items: [], total: 0 })
    await analysisAPI.listRuns('p/1')
    expect(mockGet).toHaveBeenCalledWith(
      '/projects/p%2F1/analysis-runs?limit=50&offset=0',
      NO_STORE,
    )
    await analysisAPI.listRuns('p1', 10, 20)
    expect(mockGet).toHaveBeenLastCalledWith(
      '/projects/p1/analysis-runs?limit=10&offset=20',
      NO_STORE,
    )
  })

  it('reads one run and its frame download', async () => {
    mockGet.mockResolvedValue({ id: 'r 1' })
    await analysisAPI.getRun('r 1')
    expect(mockGet).toHaveBeenCalledWith('/analysis-runs/r%201', NO_STORE)
    await analysisAPI.getFrameDownload('r1')
    expect(mockGet).toHaveBeenLastCalledWith(
      '/analysis-runs/r1/frame?json=1',
      NO_STORE,
    )
  })

  it('pages through the estimates until a page is not full', async () => {
    const full = Array.from({ length: ESTIMATES_PAGE_SIZE }, (_, i) => ({
      position: i,
    }))
    mockGet
      .mockResolvedValueOnce({ items: full })
      .mockResolvedValueOnce({ items: [{ position: ESTIMATES_PAGE_SIZE }] })
    const all = await analysisAPI.listEstimates('r1')
    expect(all).toHaveLength(ESTIMATES_PAGE_SIZE + 1)
    expect(mockGet.mock.calls.map((c) => c[0])).toEqual([
      `/analysis-runs/r1/estimates?limit=${ESTIMATES_PAGE_SIZE}&offset=0`,
      `/analysis-runs/r1/estimates?limit=${ESTIMATES_PAGE_SIZE}&offset=${ESTIMATES_PAGE_SIZE}`,
    ])
  })

  it('treats an empty estimates answer as no estimates', async () => {
    mockGet.mockResolvedValueOnce(null)
    expect(await analysisAPI.listEstimates('r1')).toEqual([])
  })

  it('keeps only string design keys', async () => {
    mockGet.mockResolvedValueOnce({
      items: [{ key: 'swap' }, { key: 3 }, {}, null, { key: 'order' }],
    })
    expect(await analysisAPI.listDesignKeys('p1')).toEqual(['swap', 'order'])
    expect(mockGet).toHaveBeenCalledWith(
      '/projects/p1/variant-designs',
      NO_STORE,
    )
    mockGet.mockResolvedValueOnce(undefined)
    expect(await analysisAPI.listDesignKeys('p1')).toEqual([])
  })

  it('validates a spec and starts a run with a trimmed name', async () => {
    mockPost.mockResolvedValue({})
    const spec = { spec_version: 1 }
    await analysisAPI.validateSpec(spec)
    expect(mockPost).toHaveBeenCalledWith('/analysis/specs/validate', { spec })
    await analysisAPI.startRun('p1', spec, '  main  ')
    expect(mockPost).toHaveBeenLastCalledWith('/projects/p1/analysis-runs', {
      spec,
      name: 'main',
    })
    await analysisAPI.startRun('p1', spec, '   ')
    expect(mockPost).toHaveBeenLastCalledWith('/projects/p1/analysis-runs', {
      spec,
    })
  })

  it('reads the saved plans from the evaluation config, uncached', async () => {
    const plan = {
      id: 'p1',
      name: 'Plan',
      spec: {},
      spec_hash: 'h',
      saved_at: null,
      saved_by: null,
    }
    mockGet.mockResolvedValue({
      evaluation_configs: [],
      analysis_plans: [plan, { name: 'no id' }, null, { id: 2, name: 'x' }],
    })
    expect(await analysisAPI.listPlans('p/1')).toEqual([plan])
    expect(mockGet).toHaveBeenCalledWith(
      '/evaluations/projects/p%2F1/evaluation-config',
      NO_STORE,
    )
    mockGet.mockResolvedValue({ evaluation_configs: [] })
    expect(await analysisAPI.listPlans('p1')).toEqual([])
    mockGet.mockResolvedValue({ analysis_plans: 'broken' })
    expect(await analysisAPI.listPlans('p1')).toEqual([])
  })

  it('saves the plans as the only key of the evaluation config', async () => {
    const stored = [
      {
        id: 'a',
        name: 'A',
        spec: { s: 1 },
        spec_hash: 'h',
        saved_at: 't',
        saved_by: 'u',
      },
    ]
    mockPut.mockResolvedValue({ config: { analysis_plans: stored } })
    const result = await analysisAPI.savePlans('p1', [
      { id: 'a', name: 'A', spec: { s: 1 } },
      { name: 'B', spec: { s: 2 } },
    ])
    expect(mockPut).toHaveBeenCalledWith(
      '/evaluations/projects/p1/evaluation-config',
      {
        analysis_plans: [
          { id: 'a', name: 'A', spec: { s: 1 } },
          { name: 'B', spec: { s: 2 } },
        ],
      },
    )
    expect(result).toEqual(stored)
    mockPut.mockResolvedValue(undefined)
    expect(await analysisAPI.savePlans('p1', [])).toEqual([])
  })
})

describe('helpers', () => {
  it('isRunActive is true for pending and running only', () => {
    expect(isRunActive('pending')).toBe(true)
    expect(isRunActive('running')).toBe(true)
    expect(isRunActive('completed')).toBe(false)
    expect(isRunActive('failed')).toBe(false)
  })

  it('specErrorsOf reads the engine messages of a 422 spec rejection', () => {
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
      specErrorsOf({ response: { status: 422, data: { detail: 'x' } } }),
    ).toBeNull()
    expect(
      specErrorsOf({
        response: { status: 422, data: { detail: { code: 'other' } } },
      }),
    ).toBeNull()
    expect(specErrorsOf({ response: { status: 500 } })).toBeNull()
    expect(specErrorsOf(null)).toBeNull()
  })

  it('specErrorsOf reads the problems of a rejected analysis plan', () => {
    expect(
      specErrorsOf({
        response: {
          status: 422,
          data: {
            detail: {
              code: 'invalid_analysis_plan',
              errors: ['/analysis_plans/0/name: must be a non-empty string'],
            },
          },
        },
      }),
    ).toEqual(['/analysis_plans/0/name: must be a non-empty string'])
  })

  it('statusOf reads the HTTP status when there is one', () => {
    expect(statusOf({ response: { status: 403 } })).toBe(403)
    expect(statusOf(new Error('x'))).toBeUndefined()
    expect(statusOf(null)).toBeUndefined()
  })
})

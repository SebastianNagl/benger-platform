/**
 * Client of the problem reports admin routes (`routers/bug_reports.py`).
 */

import defaultExport, {
  BUG_REPORT_STATUSES,
  bugReportsAPI,
} from '../bugReports'

jest.mock('@/lib/api', () => ({
  __esModule: true,
  default: {
    get: jest.fn(),
    post: jest.fn(),
  },
}))

const client = () => require('@/lib/api').default

beforeEach(() => jest.clearAllMocks())

describe('bugReportsAPI', () => {
  it('is also the default export and knows the four statuses', () => {
    expect(defaultExport).toBe(bugReportsAPI)
    expect(BUG_REPORT_STATUSES).toEqual([
      'pending',
      'delivered',
      'failed',
      'stored',
    ])
  })

  it('lists the first page by default, past the GET cache', async () => {
    const page = { items: [], total: 0 }
    client().get.mockResolvedValue(page)

    expect(await bugReportsAPI.list()).toBe(page)
    expect(client().get).toHaveBeenCalledWith(
      '/bug-reports?limit=50&offset=0',
      { cache: 'no-store' },
    )
  })

  it('filters by status and pages', async () => {
    client().get.mockResolvedValue({ items: [], total: 0 })

    await bugReportsAPI.list({ status: 'failed', limit: 10, offset: 20 })
    expect(client().get).toHaveBeenCalledWith(
      '/bug-reports?status=failed&limit=10&offset=20',
      { cache: 'no-store' },
    )
  })

  it('reads one report with its id encoded', async () => {
    client().get.mockResolvedValue({ id: 'a/b' })

    expect(await bugReportsAPI.get('a/b')).toEqual({ id: 'a/b' })
    expect(client().get).toHaveBeenCalledWith('/bug-reports/a%2Fb', {
      cache: 'no-store',
    })
  })

  it('redelivers a report', async () => {
    client().post.mockResolvedValue({ id: 'r1', status: 'pending' })

    expect(await bugReportsAPI.redeliver('r1')).toEqual({
      id: 'r1',
      status: 'pending',
    })
    expect(client().post).toHaveBeenCalledWith('/bug-reports/r1/redeliver')
  })

  it('builds the same-origin screenshot URL', () => {
    expect(bugReportsAPI.screenshotUrl('r 1')).toBe(
      '/api/bug-reports/r%201/screenshot',
    )
  })
})

/**
 * @jest-environment jsdom
 *
 * The dashboard stats endpoint answers 503 when its aggregation fails (for
 * example at the database statement timeout). Repeating that request only
 * repeats the expensive scan and delays the "unavailable" state, so
 * getDashboardStats sends it once, while every other request keeps the
 * 502/503 restart retries.
 */
jest.unmock('@/lib/api/base')

jest.mock('@/lib/utils/logger', () => ({
  __esModule: true,
  default: {
    debug: jest.fn(),
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
  },
}))

import { EvaluationsClient } from '../evaluations'

const unavailable = () => ({
  ok: false,
  status: 503,
  statusText: 'Service Unavailable',
  headers: new Headers({ 'content-type': 'application/json' }),
  text: async () =>
    JSON.stringify({
      detail: 'Dashboard statistics are temporarily unavailable.',
    }),
})

describe('getDashboardStats on a 503', () => {
  const originalFetch = global.fetch

  beforeEach(() => {
    global.fetch = jest.fn().mockImplementation(async () => unavailable())
  })

  afterEach(() => {
    global.fetch = originalFetch
  })

  it('sends the request once and rejects with the 503', async () => {
    const client = new EvaluationsClient()

    await expect(client.getDashboardStats()).rejects.toMatchObject({
      response: { status: 503 },
    })
    expect(global.fetch).toHaveBeenCalledTimes(1)
    expect((global.fetch as jest.Mock).mock.calls[0][0]).toContain(
      '/dashboard/stats',
    )
    expect((global.fetch as jest.Mock).mock.calls[0][1]).not.toHaveProperty(
      'retryUnavailable',
    )
  })

  it('still retries a 503 twice for a request without the opt-out', async () => {
    const client = new EvaluationsClient()

    await expect(client.getEvaluations()).rejects.toMatchObject({
      response: { status: 503 },
    })
    expect(global.fetch).toHaveBeenCalledTimes(3)
  }, 10000)
})

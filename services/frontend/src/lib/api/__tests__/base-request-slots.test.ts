/**
 * @jest-environment jsdom
 *
 * BaseApiClient request limiter, retries and the GET cache opt-out.
 *
 * Retries used to recurse into request() while the parent still held its
 * slot, so ten concurrent 503s (a pod rollover) took all ten slots and every
 * retry queued behind its own parent forever. Retries now loop and release
 * the slot before backing off, a queued request gives up after a timeout,
 * and `cache: 'no-store'` keeps live polls out of the 30 s GET cache.
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

type BaseModule = typeof import('../base')

function load(slotWaitTimeoutMs?: number) {
  let base: BaseModule | undefined
  jest.isolateModules(() => {
    base = require('../base')
  })
  class TestApiClient extends base!.BaseApiClient {
    constructor() {
      super()
      if (slotWaitTimeoutMs !== undefined) {
        this.slotWaitTimeoutMs = slotWaitTimeoutMs
      }
    }
    call(endpoint: string, options: RequestInit = {}) {
      return (this as any).request(endpoint, options)
    }
  }
  return new TestApiClient()
}

function response(status: number, body: unknown) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 503 ? 'Service Unavailable' : 'OK',
    headers: new Headers({ 'content-type': 'application/json' }),
    text: async () => JSON.stringify(body),
    json: async () => body,
    body: null,
  }
}

describe('BaseApiClient request slots', () => {
  const originalFetch = global.fetch

  afterEach(() => {
    global.fetch = originalFetch
    jest.useRealTimers()
  })

  it('resolves ten parallel requests that each get one 503 first', async () => {
    jest.useFakeTimers()
    const seen = new Set<string>()
    global.fetch = jest.fn(async (url: any) => {
      const key = String(url)
      if (!seen.has(key)) {
        seen.add(key)
        return response(503, { detail: 'restarting' })
      }
      return response(200, { url: key })
    }) as any

    const client = load()
    const all = Promise.all(
      Array.from({ length: 10 }, (_, i) => client.call(`/items/${i}`)),
    )
    // Let the first attempts fail, then fire the 1 s backoff timers.
    await jest.advanceTimersByTimeAsync(1500)
    const results = await all

    expect(results).toEqual(
      Array.from({ length: 10 }, (_, i) => ({ url: `/api/items/${i}` })),
    )
    expect(global.fetch).toHaveBeenCalledTimes(20)
  })

  it('serves more than ten parallel retrying requests through the queue', async () => {
    jest.useFakeTimers()
    const seen = new Set<string>()
    global.fetch = jest.fn(async (url: any) => {
      const key = String(url)
      if (!seen.has(key)) {
        seen.add(key)
        return response(503, {})
      }
      return response(200, { ok: true })
    }) as any

    const client = load()
    const all = Promise.all(
      Array.from({ length: 25 }, (_, i) => client.call(`/many/${i}`)),
    )
    await jest.advanceTimersByTimeAsync(5000)
    const results = await all
    expect(results).toHaveLength(25)
    expect(results.every((r) => r.ok)).toBe(true)
  })

  it('rejects a request that waits for a slot longer than the timeout', async () => {
    const releases: Array<() => void> = []
    let blocking = true
    global.fetch = jest.fn((_url: any) =>
      blocking
        ? new Promise((resolve) => {
            releases.push(() => resolve(response(200, {})))
          })
        : Promise.resolve(response(200, {})),
    ) as any

    const client = load(50)
    // Ten requests that never finish occupy every slot. Passing a signal
    // keeps the 30 s request timeout out of the picture.
    const controller = new AbortController()
    const blockers = Array.from({ length: 10 }, (_, i) =>
      client.call(`/stuck/${i}`, { signal: controller.signal }),
    )

    const error = await client.call('/queued').catch((e: Error) => e)
    expect(error).toBeInstanceOf(Error)
    expect(error.name).toBe('RequestQueueTimeoutError')
    expect(error.message).toMatch(/zu viele Anfragen|too many requests/)
    // The timed-out request never reached fetch.
    expect(global.fetch).toHaveBeenCalledTimes(10)

    // Freeing the slots lets later requests through again.
    blocking = false
    releases.forEach((release) => release())
    await Promise.all(blockers)
    await expect(client.call('/after')).resolves.toEqual({})
  })
})

describe('BaseApiClient GET cache opt-out', () => {
  const originalFetch = global.fetch

  afterEach(() => {
    global.fetch = originalFetch
  })

  it("bypasses the cache for reads and writes with cache: 'no-store'", async () => {
    let counter = 0
    global.fetch = jest.fn(async () => {
      counter += 1
      return response(200, { counter })
    }) as any

    const client = load()
    // Cached read populates the cache.
    await expect(client.call('/progress')).resolves.toEqual({ counter: 1 })
    // no-store skips the cached copy and goes to the network.
    await expect(
      client.call('/progress', { cache: 'no-store' }),
    ).resolves.toEqual({ counter: 2 })
    // ...and does not overwrite the cache entry either.
    await expect(client.call('/progress')).resolves.toEqual({ counter: 1 })
    // no-store never seeds the cache for a fresh key.
    await client.call('/live', { cache: 'no-store' })
    await expect(client.call('/live')).resolves.toEqual({ counter: 4 })
    expect(global.fetch).toHaveBeenCalledTimes(4)
  })
})

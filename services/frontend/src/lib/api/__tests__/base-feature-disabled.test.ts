/**
 * @jest-environment jsdom
 *
 * BaseApiClient and runtime feature switches: a 404 whose
 * `detail.code === 'feature_disabled'` (a flag or a whole extension package
 * switched off since the page loaded its flags) is reported to the feature
 * flag store through lib/featureFlags/disabled.ts, which refetches the flags.
 * Every other error is ignored, and the request still fails as before.
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
type DisabledModule = typeof import('@/lib/featureFlags/disabled')

function load() {
  let base: BaseModule | undefined
  let disabled: DisabledModule | undefined
  jest.isolateModules(() => {
    disabled = require('@/lib/featureFlags/disabled')
    base = require('../base')
  })
  class TestApiClient extends base!.BaseApiClient {
    call(endpoint: string, options: RequestInit = {}) {
      return (this as any).request(endpoint, options)
    }
    raw(endpoint: string) {
      return (this as any).requestRaw(endpoint)
    }
  }
  const handler = jest.fn()
  disabled!.setFeatureDisabledHandler(handler)
  return { client: new TestApiClient(), handler, disabled: disabled! }
}

function response(status: number, body: unknown) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 404 ? 'Not Found' : 'Error',
    headers: new Headers({ 'content-type': 'application/json' }),
    text: async () => JSON.stringify(body),
    json: async () => body,
    body: null,
  }
}

const DISABLED = {
  detail: { code: 'feature_disabled', flag: 'extension.compliance' },
}

it('refetches the flags on a feature_disabled 404 and still fails', async () => {
  const { client, handler } = load()
  global.fetch = jest.fn().mockResolvedValue(response(404, DISABLED))
  await expect(client.call('/ext/compliance/status')).rejects.toMatchObject({
    response: { status: 404, data: DISABLED },
  })
  expect(handler).toHaveBeenCalledTimes(1)
})

it('also reports from the unbuffered request path', async () => {
  const { client, handler } = load()
  global.fetch = jest.fn().mockResolvedValue(response(404, DISABLED))
  await expect(client.raw('/ext/compliance/report')).rejects.toBeTruthy()
  expect(handler).toHaveBeenCalledTimes(1)
})

it('ignores a plain 404 and other codes or statuses', async () => {
  const { client, handler } = load()
  global.fetch = jest
    .fn()
    .mockResolvedValueOnce(response(404, { detail: 'Not found' }))
    .mockResolvedValueOnce(response(404, { detail: { code: 'other' } }))
    .mockResolvedValueOnce(response(400, DISABLED))
  await expect(client.call('/a')).rejects.toBeTruthy()
  await expect(client.call('/b')).rejects.toBeTruthy()
  await expect(client.call('/c')).rejects.toBeTruthy()
  expect(handler).not.toHaveBeenCalled()
})

it('a throwing handler never changes how the request fails', async () => {
  const { client, disabled } = load()
  disabled.setFeatureDisabledHandler(() => {
    throw new Error('boom')
  })
  global.fetch = jest.fn().mockResolvedValue(response(404, DISABLED))
  await expect(client.call('/x')).rejects.toMatchObject({
    response: { status: 404 },
  })
})

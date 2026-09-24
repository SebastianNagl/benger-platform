/**
 * @jest-environment jsdom
 *
 * BaseApiClient forwards the Safe Exam Browser JS-API proof on every request
 * (see lib/seb.ts), so SEB exams verify on macOS / iOS too.
 */
jest.unmock('@/lib/api/base')

import { BaseApiClient } from '../base'

jest.mock('@/lib/seb', () => ({
  sebRequestHeaders: jest.fn(() => ({
    'X-Benger-SEB-CK': 'ck-hash',
    'X-Benger-SEB-URL': 'http://localhost/student/exams/p1',
  })),
}))

jest.mock('@/lib/utils/logger', () => ({
  __esModule: true,
  default: {
    debug: jest.fn(),
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
  },
}))

global.fetch = jest.fn()

class TestApiClient extends BaseApiClient {
  call(endpoint: string, options: RequestInit) {
    return (this as any).request(endpoint, options)
  }
}

function ok() {
  return {
    ok: true,
    status: 200,
    statusText: 'OK',
    headers: new Headers({ 'content-type': 'application/json' }),
    text: async () => '{}',
    body: null,
  }
}

beforeEach(() => {
  ;(global.fetch as jest.Mock).mockReset().mockResolvedValue(ok())
})

it('adds the SEB headers to request()', async () => {
  await new TestApiClient().call('/projects/p1/tasks/t1/draft', {
    method: 'PUT',
    body: '{}',
  })
  const headers = (global.fetch as jest.Mock).mock.calls[0][1].headers
  expect(headers['X-Benger-SEB-CK']).toBe('ck-hash')
  expect(headers['X-Benger-SEB-URL']).toBe('http://localhost/student/exams/p1')
  expect(headers['Content-Type']).toBe('application/json')
})

it('adds the SEB headers to requestRaw()', async () => {
  await new TestApiClient().requestRaw('/seb/projects/p1/status')
  const headers = (global.fetch as jest.Mock).mock.calls[0][1].headers
  expect(headers['X-Benger-SEB-CK']).toBe('ck-hash')
})

/**
 * Tests for API client.ts module exports
 *
 * Note: getApiUrl() behavior depends on window.location which cannot be reliably
 * mocked in jsdom. URL routing behavior is tested via E2E tests instead.
 */
describe('client.ts - Module Exports', () => {
  beforeEach(() => {
    jest.resetModules()
  })

  it('should export ApiClient', () => {
    const { ApiClient } = require('../client')
    expect(ApiClient).toBeDefined()
  })

  it('should export api', () => {
    const { api } = require('../client')
    expect(api).toBeDefined()
  })

  it('should export default', () => {
    const clientModule = require('../client')
    expect(clientModule.default).toBeDefined()
  })

  it('should export apiClient as default', () => {
    const clientModule = require('../client')
    expect(clientModule.default).toBe(clientModule.api)
  })

  it('should export getApiUrl function', () => {
    const { getApiUrl } = require('../client')
    expect(typeof getApiUrl).toBe('function')
  })
})

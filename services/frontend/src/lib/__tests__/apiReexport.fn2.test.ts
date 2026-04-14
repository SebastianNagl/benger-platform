/**
 * Function coverage for lib/api.ts (deprecated re-export module)
 * This file has 0% function coverage - importing it covers the module
 */

describe('lib/api.ts - re-export module coverage', () => {
  it('re-exports apiClient default', () => {
    const mod = require('../api')
    expect(mod).toBeDefined()
    expect(mod.default).toBeDefined()
  })

  it('re-exports ApiClient class', () => {
    const { ApiClient } = require('../api')
    expect(ApiClient).toBeDefined()
  })
})

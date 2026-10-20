/**
 * Tests for the feature flags admin client: every superadmin route of
 * routers/feature_flags.py, name/id encoding and the cache bust before a
 * list read.
 */

import { featureFlagsAPI } from '../featureFlags'

const mockApi = {
  get: jest.fn(),
  put: jest.fn(),
  post: jest.fn(),
  delete: jest.fn(),
  invalidateCache: jest.fn(),
}

jest.mock('@/lib/api', () => ({
  __esModule: true,
  get default() {
    return mockApi
  },
}))

describe('featureFlagsAPI', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    Object.values(mockApi).forEach((fn) => fn.mockResolvedValue(undefined))
  })

  it('list busts the cached list before reading it', async () => {
    const rows = [{ name: 'extension.compliance' }]
    mockApi.get.mockResolvedValue(rows)

    await expect(featureFlagsAPI.list()).resolves.toBe(rows)

    expect(mockApi.invalidateCache).toHaveBeenCalledWith('/feature-flags')
    expect(mockApi.get).toHaveBeenCalledWith('/feature-flags')
    expect(mockApi.invalidateCache.mock.invocationCallOrder[0]).toBeLessThan(
      mockApi.get.mock.invocationCallOrder[0],
    )
  })

  it('list works with a client that has no cache to bust', async () => {
    const { invalidateCache } = mockApi
    delete (mockApi as Partial<typeof mockApi>).invalidateCache
    try {
      mockApi.get.mockResolvedValue([])
      await expect(featureFlagsAPI.list()).resolves.toEqual([])
    } finally {
      mockApi.invalidateCache = invalidateCache
    }
  })

  it('setState puts the new state under the encoded name', async () => {
    await featureFlagsAPI.setState('extension.compliance', 'allowlist')
    expect(mockApi.put).toHaveBeenCalledWith(
      '/feature-flags/extension.compliance',
      { state: 'allowlist' },
    )
  })

  it('addTarget posts a user or an organization', async () => {
    await featureFlagsAPI.addTarget('live overview', { user_id: 'u1' })
    await featureFlagsAPI.addTarget('live overview', { organization_id: 'o1' })
    expect(mockApi.post).toHaveBeenNthCalledWith(
      1,
      '/feature-flags/live%20overview/targets',
      { user_id: 'u1' },
    )
    expect(mockApi.post).toHaveBeenNthCalledWith(
      2,
      '/feature-flags/live%20overview/targets',
      { organization_id: 'o1' },
    )
  })

  it('removeTarget deletes one encoded allowlist entry', async () => {
    await featureFlagsAPI.removeTarget('billing_ui', 'a/b')
    expect(mockApi.delete).toHaveBeenCalledWith(
      '/feature-flags/billing_ui/targets/a%2Fb',
    )
  })

  it('remove deletes an unregistered row', async () => {
    await featureFlagsAPI.remove('old_flag')
    expect(mockApi.delete).toHaveBeenCalledWith('/feature-flags/old_flag')
  })
})

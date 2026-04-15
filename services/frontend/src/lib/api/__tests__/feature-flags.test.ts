/**
 * Tests for FeatureFlagsClient
 */

import { FeatureFlagsClient } from '../feature-flags'
import type { FeatureFlagCreate, FeatureFlagUpdate } from '../types'

// Mock BaseApiClient
jest.mock('../base', () => ({
  BaseApiClient: class MockBaseApiClient {
    protected async get(endpoint: string): Promise<any> {
      return this.mockRequest('GET', endpoint)
    }

    protected async post(endpoint: string, data?: any): Promise<any> {
      return this.mockRequest('POST', endpoint, data)
    }

    protected async put(endpoint: string, data?: any): Promise<any> {
      return this.mockRequest('PUT', endpoint, data)
    }

    protected async delete(endpoint: string): Promise<any> {
      return this.mockRequest('DELETE', endpoint)
    }

    private mockRequest(method: string, endpoint: string, data?: any): any {
      // Get all feature flags for admin
      if (endpoint === '/feature-flags' && method === 'GET') {
        return [
          {
            id: 'flag-1',
            name: 'reports',
            description: 'Enable reports feature',
            enabled: true,
            created_at: '2024-01-01T00:00:00Z',
          },
          {
            id: 'flag-2',
            name: 'data',
            description: 'Enable data management',
            enabled: false,
            created_at: '2024-01-01T00:00:00Z',
          },
        ]
      }

      // Create feature flag
      if (endpoint === '/feature-flags' && method === 'POST') {
        return {
          id: 'flag-new',
          name: data.name,
          description: data.description,
          enabled: data.enabled ?? false,
          created_at: '2024-01-01T00:00:00Z',
        }
      }

      // Get specific feature flag
      if (endpoint.match(/^\/feature-flags\/flag-\d+$/) && method === 'GET') {
        return {
          id: endpoint.split('/').pop(),
          name: 'test-flag',
          description: 'Test flag',
          enabled: true,
          created_at: '2024-01-01T00:00:00Z',
        }
      }

      // Update feature flag
      if (endpoint.match(/^\/feature-flags\/flag-\d+$/) && method === 'PUT') {
        return {
          id: endpoint.split('/').pop(),
          name: 'test-flag',
          description: data.description || 'Updated description',
          enabled: data.enabled ?? true,
          updated_at: '2024-01-02T00:00:00Z',
        }
      }

      // Delete feature flag
      if (
        endpoint.match(/^\/feature-flags\/flag-\d+$/) &&
        method === 'DELETE'
      ) {
        return undefined
      }

      // Check feature flag
      if (
        endpoint.match(/^\/feature-flags\/check\/[\w-]+$/) &&
        method === 'GET'
      ) {
        const flagName = endpoint.split('/').pop()
        return {
          flag_name: flagName,
          enabled: flagName === 'reports',
        }
      }

      // Get all feature flags (with cache busting)
      if (
        endpoint.match(/^\/feature-flags\/all\?_t=\d+$/) &&
        method === 'GET'
      ) {
        return {
          reports: true,
          data: false,
          generations: true,
          evaluations: false,
        }
      }

      throw new Error(`Unmocked request: ${method} ${endpoint}`)
    }

    clearCache() {}
  },
}))

describe('FeatureFlagsClient', () => {
  let client: FeatureFlagsClient

  beforeEach(() => {
    client = new FeatureFlagsClient()
  })

  describe('getAllFeatureFlagsForAdmin', () => {
    it('should get all feature flags for admin', async () => {
      const result = await client.getAllFeatureFlagsForAdmin()

      expect(result).toHaveLength(2)
      expect(result[0]).toEqual({
        id: 'flag-1',
        name: 'reports',
        description: 'Enable reports feature',
        enabled: true,
        created_at: '2024-01-01T00:00:00Z',
      })
      expect(result[1]).toEqual({
        id: 'flag-2',
        name: 'data',
        description: 'Enable data management',
        enabled: false,
        created_at: '2024-01-01T00:00:00Z',
      })
    })

    it('should call correct endpoint', async () => {
      const getSpy = jest.spyOn(client as any, 'get')
      await client.getAllFeatureFlagsForAdmin()

      expect(getSpy).toHaveBeenCalledWith('/feature-flags')
    })
  })

  describe('createFeatureFlag', () => {
    it('should create a new feature flag', async () => {
      const flagData: FeatureFlagCreate = {
        name: 'new-feature',
        description: 'New feature flag',
        enabled: true,
      }

      const result = await client.createFeatureFlag(flagData)

      expect(result).toEqual({
        id: 'flag-new',
        name: 'new-feature',
        description: 'New feature flag',
        enabled: true,
        created_at: '2024-01-01T00:00:00Z',
      })
    })

    it('should create feature flag with default enabled=false', async () => {
      const flagData: FeatureFlagCreate = {
        name: 'disabled-feature',
        description: 'Disabled by default',
      }

      const result = await client.createFeatureFlag(flagData)

      expect(result.enabled).toBe(false)
    })

    it('should call correct endpoint with data', async () => {
      const postSpy = jest.spyOn(client as any, 'post')
      const flagData: FeatureFlagCreate = {
        name: 'test',
        description: 'Test',
      }

      await client.createFeatureFlag(flagData)

      expect(postSpy).toHaveBeenCalledWith('/feature-flags', flagData)
    })
  })

  describe('getFeatureFlag', () => {
    it('should get a specific feature flag', async () => {
      const result = await client.getFeatureFlag('flag-1')

      expect(result).toEqual({
        id: 'flag-1',
        name: 'test-flag',
        description: 'Test flag',
        enabled: true,
        created_at: '2024-01-01T00:00:00Z',
      })
    })

    it('should call correct endpoint', async () => {
      const getSpy = jest.spyOn(client as any, 'get')
      await client.getFeatureFlag('flag-123')

      expect(getSpy).toHaveBeenCalledWith('/feature-flags/flag-123')
    })
  })

  describe('updateFeatureFlag', () => {
    it('should update feature flag description', async () => {
      const updates: FeatureFlagUpdate = {
        description: 'Updated description',
      }

      const result = await client.updateFeatureFlag('flag-1', updates)

      expect(result.description).toBe('Updated description')
    })

    it('should update feature flag enabled status', async () => {
      const updates: FeatureFlagUpdate = {
        enabled: false,
      }

      const result = await client.updateFeatureFlag('flag-1', updates)

      expect(result.enabled).toBe(false)
    })

    it('should update multiple fields', async () => {
      const updates: FeatureFlagUpdate = {
        description: 'New description',
        enabled: true,
      }

      const result = await client.updateFeatureFlag('flag-1', updates)

      expect(result.description).toBe('New description')
      expect(result.enabled).toBe(true)
      expect(result.updated_at).toBeDefined()
    })

    it('should call correct endpoint', async () => {
      const putSpy = jest.spyOn(client as any, 'put')
      const updates: FeatureFlagUpdate = { enabled: true }

      await client.updateFeatureFlag('flag-456', updates)

      expect(putSpy).toHaveBeenCalledWith('/feature-flags/flag-456', updates)
    })
  })

  describe('deleteFeatureFlag', () => {
    it('should delete a feature flag', async () => {
      const result = await client.deleteFeatureFlag('flag-1')

      expect(result).toBeUndefined()
    })

    it('should call correct endpoint', async () => {
      const deleteSpy = jest.spyOn(client as any, 'delete')
      await client.deleteFeatureFlag('flag-789')

      expect(deleteSpy).toHaveBeenCalledWith('/feature-flags/flag-789')
    })
  })

  describe('checkFeatureFlag', () => {
    it('should check if a feature flag is enabled', async () => {
      const result = await client.checkFeatureFlag('reports')

      expect(result).toEqual({
        flag_name: 'reports',
        enabled: true,
      })
    })

    it('should check if a feature flag is disabled', async () => {
      const result = await client.checkFeatureFlag('disabled-feature')

      expect(result).toEqual({
        flag_name: 'disabled-feature',
        enabled: false,
      })
    })

    it('should call correct endpoint', async () => {
      const getSpy = jest.spyOn(client as any, 'get')
      await client.checkFeatureFlag('test-flag')

      expect(getSpy).toHaveBeenCalledWith('/feature-flags/check/test-flag')
    })
  })

  describe('getFeatureFlags', () => {
    it('should get all feature flags as record', async () => {
      const result = await client.getFeatureFlags()

      expect(result).toEqual({
        reports: true,
        data: false,
        generations: true,
        evaluations: false,
      })
    })

    it('should include cache-busting parameter', async () => {
      const getSpy = jest.spyOn(client as any, 'get')
      await client.getFeatureFlags()

      const callArg = getSpy.mock.calls[0][0]
      expect(callArg).toMatch(/^\/feature-flags\/all\?_t=\d+$/)
    })

    it('should use current timestamp for cache busting', async () => {
      const now = Date.now()
      const getSpy = jest.spyOn(client as any, 'get')

      await client.getFeatureFlags()

      const callArg = getSpy.mock.calls[0][0]
      const timestamp = parseInt(callArg.match(/_t=(\d+)/)?.[1] || '0')

      // Timestamp should be recent (within 1 second)
      expect(timestamp).toBeGreaterThanOrEqual(now - 1000)
      expect(timestamp).toBeLessThanOrEqual(now + 1000)
    })
  })

  describe('error handling', () => {
    it('should handle network errors in getAllFeatureFlagsForAdmin', async () => {
      const getSpy = jest
        .spyOn(client as any, 'get')
        .mockRejectedValueOnce(new Error('Network error'))

      await expect(client.getAllFeatureFlagsForAdmin()).rejects.toThrow(
        'Network error'
      )
    })

    it('should handle validation errors in createFeatureFlag', async () => {
      const postSpy = jest
        .spyOn(client as any, 'post')
        .mockRejectedValueOnce(new Error('Validation failed'))

      const flagData: FeatureFlagCreate = {
        name: '',
        description: '',
      }

      await expect(client.createFeatureFlag(flagData)).rejects.toThrow(
        'Validation failed'
      )
    })

    it('should handle 404 errors in getFeatureFlag', async () => {
      const getSpy = jest
        .spyOn(client as any, 'get')
        .mockRejectedValueOnce(new Error('Not found'))

      await expect(client.getFeatureFlag('invalid-id')).rejects.toThrow(
        'Not found'
      )
    })

    it('should handle unauthorized errors in updateFeatureFlag', async () => {
      const putSpy = jest
        .spyOn(client as any, 'put')
        .mockRejectedValueOnce(new Error('Unauthorized'))

      await expect(
        client.updateFeatureFlag('flag-1', { enabled: true })
      ).rejects.toThrow('Unauthorized')
    })

    it('should handle errors in deleteFeatureFlag', async () => {
      const deleteSpy = jest
        .spyOn(client as any, 'delete')
        .mockRejectedValueOnce(new Error('Cannot delete'))

      await expect(client.deleteFeatureFlag('flag-1')).rejects.toThrow(
        'Cannot delete'
      )
    })
  })

  describe('request formatting', () => {
    it('should format getAllFeatureFlagsForAdmin request correctly', async () => {
      const getSpy = jest.spyOn(client as any, 'get')
      await client.getAllFeatureFlagsForAdmin()

      expect(getSpy).toHaveBeenCalledWith('/feature-flags')
      expect(getSpy).toHaveBeenCalledTimes(1)
    })

    it('should format createFeatureFlag request correctly', async () => {
      const postSpy = jest.spyOn(client as any, 'post')
      const flagData: FeatureFlagCreate = {
        name: 'test',
        description: 'Test flag',
        enabled: true,
      }

      await client.createFeatureFlag(flagData)

      expect(postSpy).toHaveBeenCalledWith('/feature-flags', flagData)
    })

    it('should format checkFeatureFlag request correctly', async () => {
      const getSpy = jest.spyOn(client as any, 'get')
      await client.checkFeatureFlag('test-feature')

      expect(getSpy).toHaveBeenCalledWith('/feature-flags/check/test-feature')
    })
  })
})

/**
 * Additional coverage for OrganizationsClient - API key methods
 * Covers: getOrgApiKeyStatus, setOrgApiKey, removeOrgApiKey,
 *         testOrgApiKey, testSavedOrgApiKey, getOrgApiKeySettings,
 *         updateOrgApiKeySettings
 */

import { OrganizationsClient } from '../organizations'

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
      // API Key Status
      if (endpoint.match(/\/organizations\/[\w-]+\/api-keys\/status$/) && method === 'GET') {
        return {
          api_key_status: { openai: true, anthropic: false },
          available_providers: ['openai', 'anthropic', 'google'],
        }
      }

      // Set API Key
      if (endpoint.match(/\/organizations\/[\w-]+\/api-keys\/\w+$/) && method === 'POST') {
        return { message: 'API key saved successfully' }
      }

      // Remove API Key
      if (endpoint.match(/\/organizations\/[\w-]+\/api-keys\/\w+$/) && method === 'DELETE') {
        return { message: 'API key removed successfully' }
      }

      // Test unsaved API Key
      if (endpoint.match(/\/organizations\/[\w-]+\/api-keys\/\w+\/test$/) && method === 'POST') {
        return { status: 'success', message: 'API key is valid' }
      }

      // Test saved API Key
      if (endpoint.match(/\/organizations\/[\w-]+\/api-keys\/\w+\/test-saved$/) && method === 'POST') {
        return { status: 'success', message: 'Saved API key is valid' }
      }

      // Get API Key Settings
      if (endpoint.match(/\/organizations\/[\w-]+\/api-keys\/settings$/) && method === 'GET') {
        return { require_private_keys: true }
      }

      // Update API Key Settings
      if (endpoint.match(/\/organizations\/[\w-]+\/api-keys\/settings$/) && method === 'PUT') {
        return { message: 'Settings updated', require_private_keys: data.require_private_keys }
      }

      throw new Error(`Unmocked request: ${method} ${endpoint}`)
    }

    clearCache() {}
  },
}))

describe('OrganizationsClient - API Key methods', () => {
  let client: OrganizationsClient

  beforeEach(() => {
    client = new OrganizationsClient()
  })

  describe('getOrgApiKeyStatus', () => {
    it('returns API key status for an organization', async () => {
      const result = await client.getOrgApiKeyStatus('org-1')
      expect(result.api_key_status).toEqual({ openai: true, anthropic: false })
      expect(result.available_providers).toContain('openai')
    })

    it('calls correct endpoint', async () => {
      const getSpy = jest.spyOn(client as any, 'get')
      await client.getOrgApiKeyStatus('org-1')
      expect(getSpy).toHaveBeenCalledWith('/organizations/org-1/api-keys/status')
    })
  })

  describe('setOrgApiKey', () => {
    it('sets an API key for a provider', async () => {
      const result = await client.setOrgApiKey('org-1', 'openai', 'sk-test-123')
      expect(result.message).toBe('API key saved successfully')
    })

    it('calls correct endpoint with correct data', async () => {
      const postSpy = jest.spyOn(client as any, 'post')
      await client.setOrgApiKey('org-1', 'anthropic', 'sk-ant-123')
      expect(postSpy).toHaveBeenCalledWith(
        '/organizations/org-1/api-keys/anthropic',
        { api_key: 'sk-ant-123' }
      )
    })
  })

  describe('removeOrgApiKey', () => {
    it('removes an API key for a provider', async () => {
      const result = await client.removeOrgApiKey('org-1', 'openai')
      expect(result.message).toBe('API key removed successfully')
    })

    it('calls correct endpoint', async () => {
      const deleteSpy = jest.spyOn(client as any, 'delete')
      await client.removeOrgApiKey('org-1', 'google')
      expect(deleteSpy).toHaveBeenCalledWith('/organizations/org-1/api-keys/google')
    })
  })

  describe('testOrgApiKey', () => {
    it('tests an unsaved API key', async () => {
      const result = await client.testOrgApiKey('org-1', 'openai', 'sk-test-key')
      expect(result.status).toBe('success')
      expect(result.message).toBe('API key is valid')
    })

    it('calls correct endpoint with correct data', async () => {
      const postSpy = jest.spyOn(client as any, 'post')
      await client.testOrgApiKey('org-1', 'anthropic', 'sk-ant-test')
      expect(postSpy).toHaveBeenCalledWith(
        '/organizations/org-1/api-keys/anthropic/test',
        { api_key: 'sk-ant-test' }
      )
    })
  })

  describe('testSavedOrgApiKey', () => {
    it('tests a saved API key', async () => {
      const result = await client.testSavedOrgApiKey('org-1', 'openai')
      expect(result.status).toBe('success')
      expect(result.message).toBe('Saved API key is valid')
    })

    it('calls correct endpoint', async () => {
      const postSpy = jest.spyOn(client as any, 'post')
      await client.testSavedOrgApiKey('org-1', 'google')
      expect(postSpy).toHaveBeenCalledWith(
        '/organizations/org-1/api-keys/google/test-saved',
        {}
      )
    })
  })

  describe('getOrgApiKeySettings', () => {
    it('returns API key settings', async () => {
      const result = await client.getOrgApiKeySettings('org-1')
      expect(result.require_private_keys).toBe(true)
    })

    it('calls correct endpoint', async () => {
      const getSpy = jest.spyOn(client as any, 'get')
      await client.getOrgApiKeySettings('org-1')
      expect(getSpy).toHaveBeenCalledWith('/organizations/org-1/api-keys/settings')
    })
  })

  describe('updateOrgApiKeySettings', () => {
    it('updates API key settings to require private keys', async () => {
      const result = await client.updateOrgApiKeySettings('org-1', true)
      expect(result.require_private_keys).toBe(true)
    })

    it('updates API key settings to not require private keys', async () => {
      const result = await client.updateOrgApiKeySettings('org-1', false)
      expect(result.require_private_keys).toBe(false)
    })

    it('calls correct endpoint with correct data', async () => {
      const putSpy = jest.spyOn(client as any, 'put')
      await client.updateOrgApiKeySettings('org-1', true)
      expect(putSpy).toHaveBeenCalledWith(
        '/organizations/org-1/api-keys/settings',
        { require_private_keys: true }
      )
    })
  })
})

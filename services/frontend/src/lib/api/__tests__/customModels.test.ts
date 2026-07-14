/**
 * Tests for the customModelsAPI (BYOM)
 */

import apiClient from '@/lib/api'
import { customModelsAPI } from '../customModels'
import type { CustomModel } from '../types'

// Mock the apiClient
jest.mock('@/lib/api', () => ({
  __esModule: true,
  default: {
    get: jest.fn(),
    post: jest.fn(),
    patch: jest.fn(),
    delete: jest.fn(),
    put: jest.fn(),
  },
}))

const mockModel: CustomModel = {
  id: 'custom-123',
  name: 'My Llama',
  description: null,
  provider: 'Custom',
  model_type: 'chat',
  capabilities: ['text-generation'],
  base_url: 'https://api.example.com/v1',
  endpoint_model_name: 'llama-3.3-70b',
  requires_api_key: true,
  input_cost_per_million: null,
  output_cost_per_million: null,
  parameter_constraints: null,
  is_active: true,
  is_official: false,
  created_by: 'user-1',
  created_by_username: 'alice',
  is_private: true,
  is_public: false,
  organization_ids: [],
  has_credential: false,
  can_edit: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: null,
}

describe('customModelsAPI', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('list', () => {
    it('GETs /custom-models', async () => {
      ;(apiClient.get as jest.Mock).mockResolvedValue([mockModel])

      const result = await customModelsAPI.list()

      expect(apiClient.get).toHaveBeenCalledWith('/custom-models')
      expect(result).toEqual([mockModel])
    })
  })

  describe('get', () => {
    it('GETs /custom-models/{id}', async () => {
      ;(apiClient.get as jest.Mock).mockResolvedValue(mockModel)

      const result = await customModelsAPI.get('custom-123')

      expect(apiClient.get).toHaveBeenCalledWith('/custom-models/custom-123')
      expect(result).toEqual(mockModel)
    })
  })

  describe('create', () => {
    it('POSTs the full create payload to /custom-models', async () => {
      ;(apiClient.post as jest.Mock).mockResolvedValue(mockModel)

      const payload = {
        name: 'My Llama',
        description: 'Local endpoint',
        base_url: 'https://api.example.com/v1',
        endpoint_model_name: 'llama-3.3-70b',
        requires_api_key: true,
        input_cost_per_million: 0.5,
        output_cost_per_million: 1.5,
        api_key: 'sk-secret',
      }
      const result = await customModelsAPI.create(payload)

      expect(apiClient.post).toHaveBeenCalledWith('/custom-models', payload)
      expect(result).toEqual(mockModel)
    })
  })

  describe('update', () => {
    it('PATCHes only the given fields to /custom-models/{id}', async () => {
      ;(apiClient.patch as jest.Mock).mockResolvedValue(mockModel)

      await customModelsAPI.update('custom-123', { name: 'Renamed' })

      expect(apiClient.patch).toHaveBeenCalledWith(
        '/custom-models/custom-123',
        { name: 'Renamed' }
      )
    })
  })

  describe('remove', () => {
    it('DELETEs /custom-models/{id}', async () => {
      ;(apiClient.delete as jest.Mock).mockResolvedValue(undefined)

      await customModelsAPI.remove('custom-123')

      expect(apiClient.delete).toHaveBeenCalledWith(
        '/custom-models/custom-123'
      )
    })
  })

  describe('updateVisibility', () => {
    it('sends the private payload shape', async () => {
      ;(apiClient.patch as jest.Mock).mockResolvedValue(mockModel)

      await customModelsAPI.updateVisibility('custom-123', {
        is_private: true,
      })

      expect(apiClient.patch).toHaveBeenCalledWith(
        '/custom-models/custom-123/visibility',
        { is_private: true }
      )
    })

    it('sends the organization payload shape', async () => {
      ;(apiClient.patch as jest.Mock).mockResolvedValue(mockModel)

      await customModelsAPI.updateVisibility('custom-123', {
        is_private: false,
        organization_ids: ['org-1', 'org-2'],
      })

      expect(apiClient.patch).toHaveBeenCalledWith(
        '/custom-models/custom-123/visibility',
        { is_private: false, organization_ids: ['org-1', 'org-2'] }
      )
    })

    it('sends the public payload shape', async () => {
      ;(apiClient.patch as jest.Mock).mockResolvedValue(mockModel)

      await customModelsAPI.updateVisibility('custom-123', {
        is_public: true,
      })

      expect(apiClient.patch).toHaveBeenCalledWith(
        '/custom-models/custom-123/visibility',
        { is_public: true }
      )
    })
  })

  describe('credentials', () => {
    it('setCredential PUTs the api_key', async () => {
      ;(apiClient.put as jest.Mock).mockResolvedValue({
        has_credential: true,
      })

      await customModelsAPI.setCredential('custom-123', 'sk-secret')

      expect(apiClient.put).toHaveBeenCalledWith(
        '/custom-models/custom-123/credential',
        { api_key: 'sk-secret' }
      )
    })

    it('deleteCredential DELETEs the credential', async () => {
      ;(apiClient.delete as jest.Mock).mockResolvedValue(undefined)

      await customModelsAPI.deleteCredential('custom-123')

      expect(apiClient.delete).toHaveBeenCalledWith(
        '/custom-models/custom-123/credential'
      )
    })

    it('getCredentialStatus GETs the credential state', async () => {
      ;(apiClient.get as jest.Mock).mockResolvedValue({
        has_credential: true,
        updated_at: '2026-01-01T00:00:00Z',
      })

      const result = await customModelsAPI.getCredentialStatus('custom-123')

      expect(apiClient.get).toHaveBeenCalledWith(
        '/custom-models/custom-123/credential'
      )
      expect(result).toEqual({
        has_credential: true,
        updated_at: '2026-01-01T00:00:00Z',
      })
    })
  })

  describe('connection tests', () => {
    it('testConnection POSTs an empty body without options', async () => {
      ;(apiClient.post as jest.Mock).mockResolvedValue({
        status: 'success',
        message: 'ok',
      })

      const result = await customModelsAPI.testConnection('custom-123')

      expect(apiClient.post).toHaveBeenCalledWith(
        '/custom-models/custom-123/test',
        {}
      )
      expect(result).toEqual({ status: 'success', message: 'ok' })
    })

    it('testConnection forwards api_key and chat_ping', async () => {
      ;(apiClient.post as jest.Mock).mockResolvedValue({
        status: 'error',
        message: 'nope',
        error_type: 'auth',
      })

      await customModelsAPI.testConnection('custom-123', {
        api_key: 'sk-secret',
        chat_ping: true,
      })

      expect(apiClient.post).toHaveBeenCalledWith(
        '/custom-models/custom-123/test',
        { api_key: 'sk-secret', chat_ping: true }
      )
    })

    it('testEndpoint POSTs base_url and optional api_key to /custom-models/test', async () => {
      ;(apiClient.post as jest.Mock).mockResolvedValue({
        status: 'success',
        message: 'ok',
      })

      await customModelsAPI.testEndpoint({
        base_url: 'https://api.example.com/v1',
        api_key: 'sk-secret',
      })

      expect(apiClient.post).toHaveBeenCalledWith('/custom-models/test', {
        base_url: 'https://api.example.com/v1',
        api_key: 'sk-secret',
      })
    })
  })
})

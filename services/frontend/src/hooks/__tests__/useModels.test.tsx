/**
 * @jest-environment jsdom
 */

import { renderHook, waitFor } from '@testing-library/react'
import { Model, useModels } from '../useModels'

jest.mock('@/lib/api', () => ({
  api: {
    getAvailableModels: jest.fn(),
  },
}))

const stableT = (key: string) => key
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: stableT,
    locale: 'en',
    changeLocale: jest.fn(),
    isReady: true,
  }),
}))

import { api } from '@/lib/api'

const mockGetAvailableModels = api.getAvailableModels as jest.MockedFunction<
  typeof api.getAvailableModels
>

const mockModels: Model[] = [
  {
    id: 'gpt-4',
    name: 'GPT-4',
    description: 'OpenAI GPT-4 model',
    provider: 'openai',
    model_type: 'chat',
    capabilities: ['text-generation', 'chat'],
    is_active: true,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
  },
  {
    id: 'claude-3-opus',
    name: 'Claude 3 Opus',
    description: 'Anthropic Claude 3 Opus',
    provider: 'anthropic',
    model_type: 'chat',
    capabilities: ['text-generation', 'chat', 'vision'],
    is_active: true,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: null,
  },
  {
    id: 'gemini-pro',
    name: 'Gemini Pro',
    provider: 'google',
    model_type: 'chat',
    capabilities: ['text-generation'],
    is_active: false,
    created_at: null,
    updated_at: null,
  },
]

describe('useModels', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('Basic Hook Behavior', () => {
    it('should return expected interface', async () => {
      mockGetAvailableModels.mockResolvedValue(mockModels)

      const { result } = renderHook(() => useModels())

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current).toHaveProperty('models')
      expect(result.current).toHaveProperty('loading')
      expect(result.current).toHaveProperty('error')
      expect(result.current).toHaveProperty('refetch')
      expect(result.current).toHaveProperty('hasApiKeys')
      expect(result.current).toHaveProperty('apiKeyStatus')
      expect(typeof result.current.refetch).toBe('function')
    })

    it('should initialize with loading state', () => {
      mockGetAvailableModels.mockImplementation(() => new Promise(() => {}))

      const { result } = renderHook(() => useModels())

      expect(result.current.loading).toBe(true)
      expect(result.current.models).toEqual([])
      expect(result.current.error).toBeNull()
    })

    it('should fetch data automatically on mount', async () => {
      mockGetAvailableModels.mockResolvedValue([])

      renderHook(() => useModels())

      await waitFor(() => {
        expect(mockGetAvailableModels).toHaveBeenCalledTimes(1)
      })
    })
  })

  describe('Data Fetching', () => {
    it('should successfully fetch models', async () => {
      mockGetAvailableModels.mockResolvedValue(mockModels)

      const { result } = renderHook(() => useModels())

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.models).toEqual(mockModels)
      expect(result.current.error).toBeNull()
      expect(result.current.hasApiKeys).toBe(true)
    })

    it('should handle multiple models from different providers', async () => {
      mockGetAvailableModels.mockResolvedValue(mockModels)

      const { result } = renderHook(() => useModels())

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.hasApiKeys).toBe(true)
      expect(result.current.models).toHaveLength(3)
    })

    it('should handle single model', async () => {
      mockGetAvailableModels.mockResolvedValue([mockModels[1]])

      const { result } = renderHook(() => useModels())

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.hasApiKeys).toBe(true)
      expect(result.current.models).toHaveLength(1)
    })
  })

  describe('Loading States', () => {
    it('should set loading to true while fetching', async () => {
      let resolveModels: any
      mockGetAvailableModels.mockImplementation(
        () =>
          new Promise((resolve) => {
            resolveModels = resolve
          })
      )

      const { result } = renderHook(() => useModels())

      expect(result.current.loading).toBe(true)

      resolveModels([])

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })
    })

    it('should set loading to false after successful fetch', async () => {
      mockGetAvailableModels.mockResolvedValue(mockModels)

      const { result } = renderHook(() => useModels())

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.models).toHaveLength(3)
    })

    it('should set loading to false after error', async () => {
      mockGetAvailableModels.mockRejectedValue(new Error('Network error'))

      const { result } = renderHook(() => useModels())

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.error).not.toBeNull()
    })

    it('should set loading to false when no models are available', async () => {
      mockGetAvailableModels.mockResolvedValue([])

      const { result } = renderHook(() => useModels())

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.error?.type).toBe('NO_API_KEYS')
    })
  })

  describe('Error Handling', () => {
    it('should handle NO_API_KEYS error when no models returned', async () => {
      mockGetAvailableModels.mockResolvedValue([])

      const { result } = renderHook(() => useModels())

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.error).toEqual({
        type: 'NO_API_KEYS',
        message: 'models.errors.noApiKeys',
        details: 'models.errors.noApiKeysDetails',
      })
      expect(result.current.models).toEqual([])
      expect(result.current.hasApiKeys).toBe(false)
    })

    it('should handle AUTH_FAILED error for 401 status', async () => {
      mockGetAvailableModels.mockRejectedValue({
        status: 401,
        message: 'Unauthorized',
      })

      const { result } = renderHook(() => useModels())

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.error?.type).toBe('AUTH_FAILED')
      expect(result.current.error?.message).toBe('models.errors.authFailed')
      expect(result.current.error?.details).toBe(
        'models.errors.authFailedDetails'
      )
      expect(result.current.models).toEqual([])
    })

    it('should handle AUTH_FAILED error for unauthorized message', async () => {
      mockGetAvailableModels.mockRejectedValue({
        message: 'Unauthorized access',
      })

      const { result } = renderHook(() => useModels())

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.error?.type).toBe('AUTH_FAILED')
    })

    it('should handle AUTH_FAILED error for credentials message', async () => {
      mockGetAvailableModels.mockRejectedValue({
        message: 'Invalid credentials',
      })

      const { result } = renderHook(() => useModels())

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.error?.type).toBe('AUTH_FAILED')
    })

    it('should handle SERVER_ERROR for 500 status', async () => {
      mockGetAvailableModels.mockRejectedValue({
        status: 500,
        message: 'Server error',
      })

      const { result } = renderHook(() => useModels())

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.error?.type).toBe('SERVER_ERROR')
      expect(result.current.error?.message).toBe('models.errors.serverError')
      expect(result.current.error?.details).toBe(
        'models.errors.serverErrorDetails'
      )
    })

    it('should handle SERVER_ERROR for status >= 500', async () => {
      mockGetAvailableModels.mockRejectedValue({
        status: 503,
        message: 'Service unavailable',
      })

      const { result } = renderHook(() => useModels())

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.error?.type).toBe('SERVER_ERROR')
    })

    it('should handle SERVER_ERROR for internal server error message', async () => {
      mockGetAvailableModels.mockRejectedValue({
        message: 'Internal server error occurred',
      })

      const { result } = renderHook(() => useModels())

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.error?.type).toBe('SERVER_ERROR')
    })

    it('should handle NETWORK_ERROR for fetch TypeError', async () => {
      const fetchError = new TypeError('Failed to fetch')
      mockGetAvailableModels.mockRejectedValue(fetchError)

      const { result } = renderHook(() => useModels())

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.error?.type).toBe('NETWORK_ERROR')
      expect(result.current.error?.message).toBe('models.errors.networkError')
      expect(result.current.error?.details).toBe(
        'models.errors.networkErrorDetails'
      )
    })

    it('should handle UNKNOWN error type for unrecognized errors', async () => {
      mockGetAvailableModels.mockRejectedValue({
        message: 'Something unexpected happened',
      })

      const { result } = renderHook(() => useModels())

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.error?.type).toBe('UNKNOWN')
      expect(result.current.error?.message).toBe('models.errors.loadFailed')
      expect(result.current.error?.details).toBe(
        'Something unexpected happened'
      )
    })

    it('should handle error without message', async () => {
      mockGetAvailableModels.mockRejectedValue({})

      const { result } = renderHook(() => useModels())

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.error?.type).toBe('UNKNOWN')
      expect(result.current.error?.details).toBe('models.errors.unexpected')
    })

    it('should clear error state on successful refetch after error', async () => {
      mockGetAvailableModels.mockRejectedValueOnce(new Error('Network error'))

      const { result } = renderHook(() => useModels())

      await waitFor(() => {
        expect(result.current.error).not.toBeNull()
      })

      mockGetAvailableModels.mockResolvedValueOnce(mockModels)

      await result.current.refetch()

      await waitFor(() => {
        expect(result.current.error).toBeNull()
        expect(result.current.models).toEqual(mockModels)
      })
    })

    it('should log errors to console', async () => {
      const consoleErrorSpy = jest
        .spyOn(console, 'error')
        .mockImplementation(() => {})

      mockGetAvailableModels.mockRejectedValue(new Error('Test error'))

      renderHook(() => useModels())

      await waitFor(() => {
        expect(consoleErrorSpy).toHaveBeenCalledWith(
          'Failed to fetch models:',
          expect.any(Error)
        )
      })

      consoleErrorSpy.mockRestore()
    })
  })

  describe('Data Transformation', () => {
    it('should preserve all model fields', async () => {
      mockGetAvailableModels.mockResolvedValue([mockModels[0]])

      const { result } = renderHook(() => useModels())

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      const model = result.current.models[0]
      expect(model.id).toBe('gpt-4')
      expect(model.name).toBe('GPT-4')
      expect(model.description).toBe('OpenAI GPT-4 model')
      expect(model.provider).toBe('openai')
      expect(model.model_type).toBe('chat')
      expect(model.capabilities).toEqual(['text-generation', 'chat'])
      expect(model.is_active).toBe(true)
      expect(model.created_at).toBe('2024-01-01T00:00:00Z')
      expect(model.updated_at).toBe('2024-01-01T00:00:00Z')
    })

    it('should handle models with null timestamps', async () => {
      mockGetAvailableModels.mockResolvedValue([mockModels[2]])

      const { result } = renderHook(() => useModels())

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.models[0].created_at).toBeNull()
      expect(result.current.models[0].updated_at).toBeNull()
    })

    it('should handle models with optional fields', async () => {
      const minimalModel: Model = {
        id: 'test-model',
        name: 'Test Model',
        provider: 'test',
        model_type: 'test',
        capabilities: [],
        is_active: true,
        created_at: null,
      }

      mockGetAvailableModels.mockResolvedValue([minimalModel])

      const { result } = renderHook(() => useModels())

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.models[0].description).toBeUndefined()
      expect(result.current.models[0].updated_at).toBeUndefined()
    })

    it('should derive hasApiKeys from models array', async () => {
      mockGetAvailableModels.mockResolvedValue([mockModels[0]])

      const { result } = renderHook(() => useModels())

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.hasApiKeys).toBe(true)
    })

    it('should return hasApiKeys false when no models available', async () => {
      mockGetAvailableModels.mockResolvedValue([])

      const { result } = renderHook(() => useModels())

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.hasApiKeys).toBe(false)
      expect(result.current.apiKeyStatus).toBeNull()
    })
  })

  describe('Refetch/Invalidation', () => {
    it('should allow manual refetch via refetch function', async () => {
      mockGetAvailableModels.mockResolvedValue([mockModels[0]])

      const { result } = renderHook(() => useModels())

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(mockGetAvailableModels).toHaveBeenCalledTimes(1)

      mockGetAvailableModels.mockResolvedValue(mockModels)

      await result.current.refetch()

      await waitFor(() => {
        expect(mockGetAvailableModels).toHaveBeenCalledTimes(2)
      })

      expect(result.current.models).toEqual(mockModels)
    })

    it('should set loading state during refetch', async () => {
      mockGetAvailableModels.mockResolvedValue([mockModels[0]])

      const { result } = renderHook(() => useModels())

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      let resolveRefetch: any
      mockGetAvailableModels.mockImplementation(
        () =>
          new Promise((resolve) => {
            resolveRefetch = resolve
          })
      )

      const refetchPromise = result.current.refetch()

      await waitFor(() => {
        expect(result.current.loading).toBe(true)
      })

      resolveRefetch(mockModels)

      await refetchPromise

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })
    })

    it('should update models after refetch with new data', async () => {
      mockGetAvailableModels.mockResolvedValue([mockModels[0]])

      const { result } = renderHook(() => useModels())

      await waitFor(() => {
        expect(result.current.models).toHaveLength(1)
      })

      mockGetAvailableModels.mockResolvedValue(mockModels)

      await result.current.refetch()

      await waitFor(() => {
        expect(result.current.models).toHaveLength(3)
      })
    })
  })

  describe('Edge Cases', () => {
    it('should handle empty models array as NO_API_KEYS', async () => {
      mockGetAvailableModels.mockResolvedValue([])

      const { result } = renderHook(() => useModels())

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.models).toEqual([])
      expect(result.current.error?.type).toBe('NO_API_KEYS')
      expect(result.current.error?.message).toBe('models.errors.noApiKeys')
    })

    it('should handle very large models array', async () => {
      const largeModelsArray = Array.from({ length: 100 }, (_, i) => ({
        ...mockModels[0],
        id: `model-${i}`,
        name: `Model ${i}`,
      }))

      mockGetAvailableModels.mockResolvedValue(largeModelsArray)

      const { result } = renderHook(() => useModels())

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.models).toHaveLength(100)
      expect(result.current.error).toBeNull()
    })

    it('should handle mixed active and inactive models', async () => {
      const mixedModels = [
        { ...mockModels[0], is_active: true },
        { ...mockModels[1], is_active: false },
        { ...mockModels[2], is_active: true },
      ]

      mockGetAvailableModels.mockResolvedValue(mixedModels)

      const { result } = renderHook(() => useModels())

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.models).toHaveLength(3)
      expect(result.current.models[0].is_active).toBe(true)
      expect(result.current.models[1].is_active).toBe(false)
    })

    it('should handle rapid consecutive refetch calls', async () => {
      mockGetAvailableModels.mockResolvedValue(mockModels)

      const { result } = renderHook(() => useModels())

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      const refetch1 = result.current.refetch()
      const refetch2 = result.current.refetch()
      const refetch3 = result.current.refetch()

      await Promise.all([refetch1, refetch2, refetch3])

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.models).toEqual(mockModels)
    })

    it('should maintain stable refetch function reference', async () => {
      mockGetAvailableModels.mockResolvedValue(mockModels)

      const { result, rerender } = renderHook(() => useModels())

      const firstRefetch = result.current.refetch

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      rerender()

      const secondRefetch = result.current.refetch

      expect(firstRefetch).toBe(secondRefetch)
    })
  })

  describe('API Integration', () => {
    it('should call getAvailableModels with correct parameters', async () => {
      mockGetAvailableModels.mockResolvedValue(mockModels)

      renderHook(() => useModels())

      await waitFor(() => {
        expect(mockGetAvailableModels).toHaveBeenCalledWith()
      })
    })

    it('should not retry failed API calls automatically', async () => {
      mockGetAvailableModels.mockRejectedValue(new Error('Network error'))

      renderHook(() => useModels())

      await waitFor(() => {
        expect(mockGetAvailableModels).toHaveBeenCalledTimes(1)
      })

      await new Promise((resolve) => setTimeout(resolve, 100))

      expect(mockGetAvailableModels).toHaveBeenCalledTimes(1)
    })

    it('should handle API response with extra fields gracefully', async () => {
      const modelsWithExtraFields = [
        {
          ...mockModels[0],
          extra_field: 'extra_value',
          another_field: 123,
        },
      ]

      mockGetAvailableModels.mockResolvedValue(modelsWithExtraFields)

      const { result } = renderHook(() => useModels())

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.models[0]).toMatchObject(mockModels[0])
    })
  })
})

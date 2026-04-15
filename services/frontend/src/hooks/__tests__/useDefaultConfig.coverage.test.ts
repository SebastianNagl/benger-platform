/**
 * @jest-environment jsdom
 *
 * useDefaultConfig branch coverage extension tests.
 * Tests helper functions getDefaultTemperature and getDefaultMaxTokens,
 * and error handling in both hooks.
 */

import { getDefaultTemperature, getDefaultMaxTokens } from '../useDefaultConfig'

// Mock the API admin-defaults module
jest.mock('@/lib/api/admin-defaults', () => ({
  getDefaultConfig: jest.fn(),
  getAllDefaultConfigs: jest.fn(),
}))

describe('getDefaultTemperature', () => {
  it('should return 0 for any task type', () => {
    expect(getDefaultTemperature('qa')).toBe(0)
    expect(getDefaultTemperature('generation')).toBe(0)
    expect(getDefaultTemperature('unknown')).toBe(0)
    expect(getDefaultTemperature('')).toBe(0)
  })
})

describe('getDefaultMaxTokens', () => {
  it('should return correct defaults for known task types', () => {
    expect(getDefaultMaxTokens('qa')).toBe(500)
    expect(getDefaultMaxTokens('qa_reasoning')).toBe(1000)
    expect(getDefaultMaxTokens('multiple_choice')).toBe(200)
    expect(getDefaultMaxTokens('generation')).toBe(2000)
  })

  it('should return 500 as fallback for unknown task types', () => {
    expect(getDefaultMaxTokens('unknown')).toBe(500)
    expect(getDefaultMaxTokens('custom')).toBe(500)
    expect(getDefaultMaxTokens('')).toBe(500)
    expect(getDefaultMaxTokens('something_else')).toBe(500)
  })
})

describe('useDefaultConfig error handling', () => {
  it('should provide fallback config on API error', async () => {
    const { getDefaultConfig } = require('@/lib/api/admin-defaults')
    getDefaultConfig.mockRejectedValue(new Error('API Error'))

    const consoleSpy = jest.spyOn(console, 'error').mockImplementation()
    const { renderHook, waitFor } = require('@testing-library/react')
    const { useDefaultConfig } = require('../useDefaultConfig')

    const { result } = renderHook(() => useDefaultConfig('qa'))

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    expect(result.current.error).toBe('API Error')
    expect(result.current.config).not.toBeNull()
    expect(result.current.config.task_type).toBe('qa')
    expect(result.current.config.temperature).toBe(0)

    consoleSpy.mockRestore()
  })

  it('should handle non-Error thrown in fetch', async () => {
    const { getDefaultConfig } = require('@/lib/api/admin-defaults')
    getDefaultConfig.mockRejectedValue('string error')

    const consoleSpy = jest.spyOn(console, 'error').mockImplementation()
    const { renderHook, waitFor } = require('@testing-library/react')
    const { useDefaultConfig } = require('../useDefaultConfig')

    const { result } = renderHook(() => useDefaultConfig('qa'))

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    expect(result.current.error).toBe('Failed to fetch default config')

    consoleSpy.mockRestore()
  })

  it('should not fetch when taskType is empty', async () => {
    const { getDefaultConfig } = require('@/lib/api/admin-defaults')
    getDefaultConfig.mockClear()

    const { renderHook, waitFor } = require('@testing-library/react')
    const { useDefaultConfig } = require('../useDefaultConfig')

    const { result } = renderHook(() => useDefaultConfig(''))

    // Should not call the API with empty taskType
    expect(getDefaultConfig).not.toHaveBeenCalled()
  })
})

describe('useAllDefaultConfigs error handling', () => {
  it('should provide fallback configs on API error', async () => {
    const { getAllDefaultConfigs } = require('@/lib/api/admin-defaults')
    getAllDefaultConfigs.mockRejectedValue(new Error('Network Error'))

    const consoleSpy = jest.spyOn(console, 'error').mockImplementation()
    const { renderHook, waitFor } = require('@testing-library/react')
    const { useAllDefaultConfigs } = require('../useDefaultConfig')

    const { result } = renderHook(() => useAllDefaultConfigs())

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    expect(result.current.error).toBe('Network Error')
    // Should have fallback configs
    expect(result.current.configs.qa).toBeDefined()
    expect(result.current.configs.qa_reasoning).toBeDefined()
    expect(result.current.configs.multiple_choice).toBeDefined()
    expect(result.current.configs.generation).toBeDefined()

    consoleSpy.mockRestore()
  })

  it('should handle non-Error thrown in fetchAll', async () => {
    const { getAllDefaultConfigs } = require('@/lib/api/admin-defaults')
    getAllDefaultConfigs.mockRejectedValue(42)

    const consoleSpy = jest.spyOn(console, 'error').mockImplementation()
    const { renderHook, waitFor } = require('@testing-library/react')
    const { useAllDefaultConfigs } = require('../useDefaultConfig')

    const { result } = renderHook(() => useAllDefaultConfigs())

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    expect(result.current.error).toBe('Failed to fetch default configs')

    consoleSpy.mockRestore()
  })
})

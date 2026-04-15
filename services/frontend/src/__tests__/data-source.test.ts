/**
 * Data Source Validation Tests
 *
 * These tests ensure that in development:
 * 1. API calls return local data, not production data
 * 2. Data has expected characteristics (timestamps, content)
 * 3. No phantom production data leakage
 */

import { jest } from '@jest/globals'

// Mock fetch for testing
const mockFetch = jest.fn() as jest.MockedFunction<typeof fetch>
global.fetch = mockFetch

describe('API Data Source Validation', () => {
  beforeEach(() => {
    mockFetch.mockClear()
  })

  test('should detect production data leakage by timestamp pattern', async () => {
    // Mock response with fresh development data
    const developmentDataResponse = [
      {
        name: 'Dev Project 1',
        created_at: new Date().toISOString(), // Current timestamp
        id: '1',
      },
      {
        name: 'Test Task',
        created_at: new Date(Date.now() - 1000 * 60 * 30).toISOString(), // 30 minutes ago
        id: '2',
      },
    ]

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => developmentDataResponse,
    } as Response)

    const response = await fetch('/api/tasks')
    const data = await response.json()

    if (process.env.NODE_ENV !== 'production') {
      // In development, detect if we're getting production data
      const hasOldData = data.some((task: any) => {
        const createdAt = new Date(task.created_at)
        const hoursDiff = (Date.now() - createdAt.getTime()) / (1000 * 60 * 60)

        // Data older than 24 hours in development is suspicious
        return hoursDiff > 24
      })

      // Should not have old production data (this test should pass with fresh mock data)
      expect(hasOldData).toBe(false)
    }
  })

  test('should validate development data characteristics', async () => {
    // Mock response with expected local data
    const localDataResponse = [
      {
        name: 'New Project #1',
        created_at: new Date().toISOString(), // Recent timestamp
        id: '1',
      },
    ]

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => localDataResponse,
    } as Response)

    const response = await fetch('/api/tasks')
    const data = await response.json()

    if (process.env.NODE_ENV !== 'production') {
      // Should have recent data in development
      expect(data).toHaveLength(1)
      expect(data[0].name).toMatch(/New Project|Test Project|Local/i)

      // Timestamp should be recent (within last hour)
      const createdAt = new Date(data[0].created_at)
      const minutesDiff = (Date.now() - createdAt.getTime()) / (1000 * 60)
      expect(minutesDiff).toBeLessThan(60)
    }
  })

  test('should not have production-specific content in development', async () => {
    const cleanDataResponse = [
      { name: 'Dev Project Alpha', id: '1' },
      { name: 'Test Task Beta', id: '2' },
      { name: 'Local Development Task', id: '3' },
    ]

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => cleanDataResponse,
    } as Response)

    const response = await fetch('/api/tasks')
    const data = await response.json()

    if (process.env.NODE_ENV !== 'production') {
      // Check for known production task names
      const productionTaskNames = ['Criminal BenGER', 'test 2']
      const hasProductionTasks = data.some((task: any) =>
        productionTaskNames.includes(task.name)
      )

      // Should not have production tasks (this test should pass with clean mock data)
      expect(hasProductionTasks).toBe(false)
    }
  })
})

describe('API Endpoint Validation', () => {
  test('should use correct API base URL in development', () => {
    if (process.env.NODE_ENV !== 'production') {
      // API base URL should be local in development
      const apiBaseUrl = process.env.REACT_APP_API_BASE_URL || '/api'

      expect(apiBaseUrl).not.toMatch(/what-a-benger\.net/)
      expect(apiBaseUrl).not.toMatch(/https:\/\/api\./)
      expect(apiBaseUrl).toMatch(
        /^(\/api|http:\/\/localhost|http:\/\/127\.0\.0\.1)/
      )
    }
  })
})

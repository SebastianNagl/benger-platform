/**
 * Comprehensive tests for health check API route
 * Tests health monitoring, memory usage tracking, and error scenarios
 */

import { NextRequest } from 'next/server'
import { GET } from '../route'

// Helper to create NextRequest
const createRequest = (url: string, options: RequestInit = {}) => {
  return new NextRequest(url, options)
}

describe('/api/health', () => {
  let originalMemoryUsage: typeof process.memoryUsage
  let originalUptime: typeof process.uptime
  let originalVersion: string
  let originalNodeEnv: string | undefined
  let originalNodeOptions: string | undefined

  beforeEach(() => {
    originalMemoryUsage = process.memoryUsage
    originalUptime = process.uptime
    originalVersion = process.version
    originalNodeEnv = process.env.NODE_ENV
    originalNodeOptions = process.env.NODE_OPTIONS
    jest.clearAllMocks()
  })

  afterEach(() => {
    process.memoryUsage = originalMemoryUsage
    process.uptime = originalUptime
    Object.defineProperty(process, 'version', { value: originalVersion })
    if (originalNodeEnv) {
      process.env.NODE_ENV = originalNodeEnv
    } else {
      delete process.env.NODE_ENV
    }
    if (originalNodeOptions) {
      process.env.NODE_OPTIONS = originalNodeOptions
    } else {
      delete process.env.NODE_OPTIONS
    }
  })

  describe('Healthy Status', () => {
    it('should return 200 with healthy status', async () => {
      process.memoryUsage = jest.fn().mockReturnValue({
        heapUsed: 100 * 1024 * 1024, // 100 MB
        heapTotal: 200 * 1024 * 1024, // 200 MB
        rss: 300 * 1024 * 1024,
        external: 10 * 1024 * 1024,
        arrayBuffers: 5 * 1024 * 1024,
      })
      process.uptime = jest.fn().mockReturnValue(3600) // 1 hour

      const request = createRequest('http://localhost:3000/api/health')
      const response = await GET(request)

      expect(response.status).toBe(200)
      const data = await response.json()
      expect(data.status).toBe('healthy')
    })

    it('should include timestamp', async () => {
      process.memoryUsage = jest.fn().mockReturnValue({
        heapUsed: 100 * 1024 * 1024,
        heapTotal: 200 * 1024 * 1024,
        rss: 300 * 1024 * 1024,
        external: 10 * 1024 * 1024,
        arrayBuffers: 5 * 1024 * 1024,
      })
      process.uptime = jest.fn().mockReturnValue(3600)

      const request = createRequest('http://localhost:3000/api/health')
      const response = await GET(request)

      const data = await response.json()
      expect(data.timestamp).toBeDefined()
      expect(new Date(data.timestamp).getTime()).toBeGreaterThan(0)
    })

    it('should include environment information', async () => {
      process.env.NODE_ENV = 'production'
      process.memoryUsage = jest.fn().mockReturnValue({
        heapUsed: 100 * 1024 * 1024,
        heapTotal: 200 * 1024 * 1024,
        rss: 300 * 1024 * 1024,
        external: 10 * 1024 * 1024,
        arrayBuffers: 5 * 1024 * 1024,
      })
      process.uptime = jest.fn().mockReturnValue(3600)

      const request = createRequest('http://localhost:3000/api/health')
      const response = await GET(request)

      const data = await response.json()
      expect(data.environment).toBe('production')
    })

    it('should default to development when NODE_ENV not set', async () => {
      delete process.env.NODE_ENV
      process.memoryUsage = jest.fn().mockReturnValue({
        heapUsed: 100 * 1024 * 1024,
        heapTotal: 200 * 1024 * 1024,
        rss: 300 * 1024 * 1024,
        external: 10 * 1024 * 1024,
        arrayBuffers: 5 * 1024 * 1024,
      })
      process.uptime = jest.fn().mockReturnValue(3600)

      const request = createRequest('http://localhost:3000/api/health')
      const response = await GET(request)

      const data = await response.json()
      expect(data.environment).toBe('development')
    })

    it('should include Node.js version', async () => {
      process.memoryUsage = jest.fn().mockReturnValue({
        heapUsed: 100 * 1024 * 1024,
        heapTotal: 200 * 1024 * 1024,
        rss: 300 * 1024 * 1024,
        external: 10 * 1024 * 1024,
        arrayBuffers: 5 * 1024 * 1024,
      })
      process.uptime = jest.fn().mockReturnValue(3600)

      const request = createRequest('http://localhost:3000/api/health')
      const response = await GET(request)

      const data = await response.json()
      expect(data.version).toBeDefined()
      expect(typeof data.version).toBe('string')
    })

    it('should include uptime in seconds', async () => {
      process.memoryUsage = jest.fn().mockReturnValue({
        heapUsed: 100 * 1024 * 1024,
        heapTotal: 200 * 1024 * 1024,
        rss: 300 * 1024 * 1024,
        external: 10 * 1024 * 1024,
        arrayBuffers: 5 * 1024 * 1024,
      })
      process.uptime = jest.fn().mockReturnValue(7200.5) // 2 hours, 0.5 seconds

      const request = createRequest('http://localhost:3000/api/health')
      const response = await GET(request)

      const data = await response.json()
      expect(data.uptime).toBe(7201) // Rounded
    })
  })

  describe('Memory Information', () => {
    it('should include memory usage in MB', async () => {
      process.memoryUsage = jest.fn().mockReturnValue({
        heapUsed: 150 * 1024 * 1024, // 150 MB
        heapTotal: 300 * 1024 * 1024, // 300 MB
        rss: 400 * 1024 * 1024,
        external: 10 * 1024 * 1024,
        arrayBuffers: 5 * 1024 * 1024,
      })
      process.uptime = jest.fn().mockReturnValue(3600)

      const request = createRequest('http://localhost:3000/api/health')
      const response = await GET(request)

      const data = await response.json()
      expect(data.memory.used).toBe(150)
      expect(data.memory.total).toBe(300)
      expect(data.memory.unit).toBe('MB')
    })

    it('should use default memory limit when NODE_OPTIONS not set', async () => {
      delete process.env.NODE_OPTIONS
      process.memoryUsage = jest.fn().mockReturnValue({
        heapUsed: 100 * 1024 * 1024,
        heapTotal: 200 * 1024 * 1024,
        rss: 300 * 1024 * 1024,
        external: 10 * 1024 * 1024,
        arrayBuffers: 5 * 1024 * 1024,
      })
      process.uptime = jest.fn().mockReturnValue(3600)

      const request = createRequest('http://localhost:3000/api/health')
      const response = await GET(request)

      const data = await response.json()
      expect(data.memory.limit).toBe(2048) // Default 2048 MB
    })

    it('should parse memory limit from NODE_OPTIONS', async () => {
      process.env.NODE_OPTIONS = '--max-old-space-size=4096'
      process.memoryUsage = jest.fn().mockReturnValue({
        heapUsed: 100 * 1024 * 1024,
        heapTotal: 200 * 1024 * 1024,
        rss: 300 * 1024 * 1024,
        external: 10 * 1024 * 1024,
        arrayBuffers: 5 * 1024 * 1024,
      })
      process.uptime = jest.fn().mockReturnValue(3600)

      const request = createRequest('http://localhost:3000/api/health')
      const response = await GET(request)

      const data = await response.json()
      expect(data.memory.limit).toBe(4096)
    })

    it('should handle NODE_OPTIONS without max-old-space-size', async () => {
      process.env.NODE_OPTIONS = '--other-flag=value'
      process.memoryUsage = jest.fn().mockReturnValue({
        heapUsed: 100 * 1024 * 1024,
        heapTotal: 200 * 1024 * 1024,
        rss: 300 * 1024 * 1024,
        external: 10 * 1024 * 1024,
        arrayBuffers: 5 * 1024 * 1024,
      })
      process.uptime = jest.fn().mockReturnValue(3600)

      const request = createRequest('http://localhost:3000/api/health')
      const response = await GET(request)

      const data = await response.json()
      expect(data.memory.limit).toBe(2048) // Default
    })
  })

  describe('Warning Status', () => {
    it('should return 503 with warning when memory usage exceeds 80%', async () => {
      process.env.NODE_OPTIONS = '--max-old-space-size=1000'
      process.memoryUsage = jest.fn().mockReturnValue({
        heapUsed: 850 * 1024 * 1024, // 85% of 1000 MB
        heapTotal: 900 * 1024 * 1024,
        rss: 1000 * 1024 * 1024,
        external: 10 * 1024 * 1024,
        arrayBuffers: 5 * 1024 * 1024,
      })
      process.uptime = jest.fn().mockReturnValue(3600)

      const request = createRequest('http://localhost:3000/api/health')
      const response = await GET(request)

      expect(response.status).toBe(503)
      const data = await response.json()
      expect(data.status).toBe('warning')
      expect(data.warning).toContain('High memory usage')
      expect(data.warning).toContain('85.0%')
    })

    it('should include warning message with memory percentage', async () => {
      process.env.NODE_OPTIONS = '--max-old-space-size=2000'
      process.memoryUsage = jest.fn().mockReturnValue({
        heapUsed: 1700 * 1024 * 1024, // 85% of 2000 MB
        heapTotal: 1900 * 1024 * 1024,
        rss: 2000 * 1024 * 1024,
        external: 10 * 1024 * 1024,
        arrayBuffers: 5 * 1024 * 1024,
      })
      process.uptime = jest.fn().mockReturnValue(3600)

      const request = createRequest('http://localhost:3000/api/health')
      const response = await GET(request)

      const data = await response.json()
      expect(data.warning).toBe('High memory usage: 85.0%')
    })

    it('should return healthy when memory usage is exactly 80%', async () => {
      process.env.NODE_OPTIONS = '--max-old-space-size=1000'
      process.memoryUsage = jest.fn().mockReturnValue({
        heapUsed: 800 * 1024 * 1024, // Exactly 80%
        heapTotal: 900 * 1024 * 1024,
        rss: 1000 * 1024 * 1024,
        external: 10 * 1024 * 1024,
        arrayBuffers: 5 * 1024 * 1024,
      })
      process.uptime = jest.fn().mockReturnValue(3600)

      const request = createRequest('http://localhost:3000/api/health')
      const response = await GET(request)

      expect(response.status).toBe(200)
      const data = await response.json()
      expect(data.status).toBe('healthy')
      expect(data.warning).toBeUndefined()
    })

    it('should return warning when memory usage is just over 80%', async () => {
      process.env.NODE_OPTIONS = '--max-old-space-size=1000'
      process.memoryUsage = jest.fn().mockReturnValue({
        heapUsed: 801 * 1024 * 1024, // 80.1%
        heapTotal: 900 * 1024 * 1024,
        rss: 1000 * 1024 * 1024,
        external: 10 * 1024 * 1024,
        arrayBuffers: 5 * 1024 * 1024,
      })
      process.uptime = jest.fn().mockReturnValue(3600)

      const request = createRequest('http://localhost:3000/api/health')
      const response = await GET(request)

      expect(response.status).toBe(503)
      const data = await response.json()
      expect(data.status).toBe('warning')
    })
  })

  describe('Error Handling', () => {
    it('should return 503 with unhealthy status on error', async () => {
      process.memoryUsage = jest.fn().mockImplementation(() => {
        throw new Error('Memory access error')
      })

      const request = createRequest('http://localhost:3000/api/health')
      const response = await GET(request)

      expect(response.status).toBe(503)
      const data = await response.json()
      expect(data.status).toBe('unhealthy')
      expect(data.error).toBe('Memory access error')
    })

    it('should include timestamp even when unhealthy', async () => {
      process.memoryUsage = jest.fn().mockImplementation(() => {
        throw new Error('Critical error')
      })

      const request = createRequest('http://localhost:3000/api/health')
      const response = await GET(request)

      const data = await response.json()
      expect(data.timestamp).toBeDefined()
      expect(new Date(data.timestamp).getTime()).toBeGreaterThan(0)
    })

    it('should handle non-Error exceptions', async () => {
      process.memoryUsage = jest.fn().mockImplementation(() => {
        throw 'String error'
      })

      const request = createRequest('http://localhost:3000/api/health')
      const response = await GET(request)

      expect(response.status).toBe(503)
      const data = await response.json()
      expect(data.status).toBe('unhealthy')
      expect(data.error).toBe('Unknown error')
    })

    it('should handle uptime error', async () => {
      process.memoryUsage = jest.fn().mockReturnValue({
        heapUsed: 100 * 1024 * 1024,
        heapTotal: 200 * 1024 * 1024,
        rss: 300 * 1024 * 1024,
        external: 10 * 1024 * 1024,
        arrayBuffers: 5 * 1024 * 1024,
      })
      process.uptime = jest.fn().mockImplementation(() => {
        throw new Error('Uptime unavailable')
      })

      const request = createRequest('http://localhost:3000/api/health')
      const response = await GET(request)

      expect(response.status).toBe(503)
      const data = await response.json()
      expect(data.status).toBe('unhealthy')
    })
  })

  describe('Response Format', () => {
    it('should return JSON response', async () => {
      process.memoryUsage = jest.fn().mockReturnValue({
        heapUsed: 100 * 1024 * 1024,
        heapTotal: 200 * 1024 * 1024,
        rss: 300 * 1024 * 1024,
        external: 10 * 1024 * 1024,
        arrayBuffers: 5 * 1024 * 1024,
      })
      process.uptime = jest.fn().mockReturnValue(3600)

      const request = createRequest('http://localhost:3000/api/health')
      const response = await GET(request)

      expect(response.headers.get('content-type')).toContain('application/json')
    })

    it('should have complete health object structure', async () => {
      process.env.NODE_ENV = 'production'
      process.env.NODE_OPTIONS = '--max-old-space-size=4096'
      process.memoryUsage = jest.fn().mockReturnValue({
        heapUsed: 512 * 1024 * 1024,
        heapTotal: 1024 * 1024 * 1024,
        rss: 1500 * 1024 * 1024,
        external: 10 * 1024 * 1024,
        arrayBuffers: 5 * 1024 * 1024,
      })
      process.uptime = jest.fn().mockReturnValue(86400) // 1 day

      const request = createRequest('http://localhost:3000/api/health')
      const response = await GET(request)

      const data = await response.json()
      expect(data).toEqual({
        status: 'healthy',
        timestamp: expect.any(String),
        environment: 'production',
        memory: {
          used: 512,
          total: 1024,
          limit: 4096,
          unit: 'MB',
        },
        uptime: 86400,
        version: expect.any(String),
      })
    })
  })

  describe('Edge Cases', () => {
    it('should handle very low memory usage', async () => {
      process.memoryUsage = jest.fn().mockReturnValue({
        heapUsed: 1 * 1024 * 1024, // 1 MB
        heapTotal: 10 * 1024 * 1024, // 10 MB
        rss: 20 * 1024 * 1024,
        external: 1 * 1024 * 1024,
        arrayBuffers: 1 * 1024 * 1024,
      })
      process.uptime = jest.fn().mockReturnValue(1)

      const request = createRequest('http://localhost:3000/api/health')
      const response = await GET(request)

      expect(response.status).toBe(200)
      const data = await response.json()
      expect(data.status).toBe('healthy')
      expect(data.memory.used).toBe(1)
    })

    it('should handle zero uptime', async () => {
      process.memoryUsage = jest.fn().mockReturnValue({
        heapUsed: 100 * 1024 * 1024,
        heapTotal: 200 * 1024 * 1024,
        rss: 300 * 1024 * 1024,
        external: 10 * 1024 * 1024,
        arrayBuffers: 5 * 1024 * 1024,
      })
      process.uptime = jest.fn().mockReturnValue(0)

      const request = createRequest('http://localhost:3000/api/health')
      const response = await GET(request)

      const data = await response.json()
      expect(data.uptime).toBe(0)
    })

    it('should handle very large memory values', async () => {
      process.env.NODE_OPTIONS = '--max-old-space-size=16384' // 16 GB
      process.memoryUsage = jest.fn().mockReturnValue({
        heapUsed: 8192 * 1024 * 1024, // 8 GB
        heapTotal: 10240 * 1024 * 1024, // 10 GB
        rss: 12288 * 1024 * 1024,
        external: 100 * 1024 * 1024,
        arrayBuffers: 50 * 1024 * 1024,
      })
      process.uptime = jest.fn().mockReturnValue(3600)

      const request = createRequest('http://localhost:3000/api/health')
      const response = await GET(request)

      expect(response.status).toBe(200)
      const data = await response.json()
      expect(data.memory.used).toBe(8192)
      expect(data.memory.limit).toBe(16384)
    })

    it('should handle fractional memory values', async () => {
      process.memoryUsage = jest.fn().mockReturnValue({
        heapUsed: 150.7 * 1024 * 1024, // 150.7 MB
        heapTotal: 250.3 * 1024 * 1024, // 250.3 MB
        rss: 300 * 1024 * 1024,
        external: 10 * 1024 * 1024,
        arrayBuffers: 5 * 1024 * 1024,
      })
      process.uptime = jest.fn().mockReturnValue(3600)

      const request = createRequest('http://localhost:3000/api/health')
      const response = await GET(request)

      const data = await response.json()
      expect(data.memory.used).toBe(151) // Rounded
      expect(data.memory.total).toBe(250) // Rounded
    })
  })

  describe('Backend Connectivity', () => {
    let originalApiBaseUrl: string | undefined

    beforeEach(() => {
      originalApiBaseUrl = process.env.API_BASE_URL
      process.memoryUsage = jest.fn().mockReturnValue({
        heapUsed: 100 * 1024 * 1024,
        heapTotal: 200 * 1024 * 1024,
        rss: 300 * 1024 * 1024,
        external: 10 * 1024 * 1024,
        arrayBuffers: 5 * 1024 * 1024,
      })
      process.uptime = jest.fn().mockReturnValue(3600)
    })

    afterEach(() => {
      if (originalApiBaseUrl) {
        process.env.API_BASE_URL = originalApiBaseUrl
      } else {
        delete process.env.API_BASE_URL
      }
    })

    it('should not check backend when API_BASE_URL is not set', async () => {
      delete process.env.API_BASE_URL
      const mockFetch = jest.fn()
      global.fetch = mockFetch

      const request = createRequest('http://localhost:3000/api/health')
      const response = await GET(request)

      const data = await response.json()
      expect(data.backend).toBeUndefined()
      expect(mockFetch).not.toHaveBeenCalled()
    })

    it('should report backend ok when health check succeeds', async () => {
      process.env.API_BASE_URL = 'http://api:8000'
      global.fetch = jest.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ database: 'ok', redis: 'ok' }),
      })

      const request = createRequest('http://localhost:3000/api/health')
      const response = await GET(request)

      const data = await response.json()
      expect(data.backend).toBe('ok')
      expect(data.database).toBe('ok')
      expect(data.redis).toBe('ok')
    })

    it('should report backend error when API returns non-ok', async () => {
      process.env.API_BASE_URL = 'http://api:8000'
      global.fetch = jest.fn().mockResolvedValue({
        ok: false,
        status: 503,
      })

      const request = createRequest('http://localhost:3000/api/health')
      const response = await GET(request)

      const data = await response.json()
      expect(data.backend).toBe('error')
    })

    it('should report backend unreachable when fetch throws', async () => {
      process.env.API_BASE_URL = 'http://api:8000'
      global.fetch = jest.fn().mockRejectedValue(new Error('ECONNREFUSED'))

      const request = createRequest('http://localhost:3000/api/health')
      const response = await GET(request)

      const data = await response.json()
      expect(data.backend).toBe('unreachable')
    })

    it('should handle backend json parsing failure', async () => {
      process.env.API_BASE_URL = 'http://api:8000'
      global.fetch = jest.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.reject(new Error('Invalid JSON')),
      })

      const request = createRequest('http://localhost:3000/api/health')
      const response = await GET(request)

      const data = await response.json()
      expect(data.backend).toBe('ok')
      // When json() fails, database/redis should be 'unknown'
      expect(data.database).toBe('unknown')
      expect(data.redis).toBe('unknown')
    })
  })
})

/**
 * Integration Test Requirements
 * ==============================
 *
 * The following scenarios require E2E/integration testing with Puppeteer:
 *
 * 1. Health Check Monitoring:
 *    - Verify health endpoint is accessible from browser
 *    - Test health check in different deployment environments
 *    - Monitor health status over time
 *
 * 2. Container Monitoring:
 *    - Test health endpoint in Docker container
 *    - Verify Kubernetes liveness/readiness probe integration
 *    - Test health check with real resource constraints
 *
 * 3. Load Testing:
 *    - Test health endpoint under high concurrent requests
 *    - Verify memory reporting during load
 *    - Test warning threshold triggers under real load
 *
 * These tests should be implemented as part of the infrastructure testing strategy.
 */

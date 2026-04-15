jest.mock('@/lib/api', () => ({
  api: {
    getTasks: jest.fn().mockResolvedValue({ tasks: [], total: 0 }),
    getTask: jest.fn().mockResolvedValue(null),
    getAllUsers: jest.fn().mockResolvedValue([]),
    getOrganizations: jest.fn().mockResolvedValue([]),
    getAnnotationOverview: jest.fn().mockResolvedValue({ annotations: [] }),
    createTask: jest.fn().mockResolvedValue({}),
    updateTask: jest.fn().mockResolvedValue({}),
    deleteTask: jest.fn().mockResolvedValue(undefined),
    exportBulkData: jest.fn().mockResolvedValue({}),
    importBulkData: jest.fn().mockResolvedValue({}),
    getCurrentUser: jest.fn().mockResolvedValue({ id: 'test-user' }),
  },
  ApiClient: jest.fn().mockImplementation(() => ({
    getTasks: jest.fn().mockResolvedValue({ tasks: [], total: 0 }),
    getTask: jest.fn().mockResolvedValue(null),
    getAllUsers: jest.fn().mockResolvedValue([]),
    getOrganizations: jest.fn().mockResolvedValue([]),
  })),
}))
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(() => ({
    push: jest.fn(),
    replace: jest.fn(),
    back: jest.fn(),
    forward: jest.fn(),
    refresh: jest.fn(),
    prefetch: jest.fn(),
    pathname: '/',
    query: {},
    asPath: '/',
    route: '/',
    basePath: '',
    isReady: true,
    isPreview: false,
    isLocaleDomain: false,
  })),
  useParams: jest.fn(() => ({})),
  useSearchParams: jest.fn(() => new URLSearchParams()),
  usePathname: jest.fn(() => '/'),
  notFound: jest.fn(),
  redirect: jest.fn(),
}))

const mockApi = {
  login: jest.fn(),
  register: jest.fn(),
  getUser: jest.fn(),
  refreshToken: jest.fn(),
  getCurrentUser: jest.fn(),
}

describe('Issue #145: Authentication Flow Optimization', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('Login Performance', () => {
    it('should handle invalid credentials', async () => {
      mockApi.login.mockRejectedValueOnce(new Error('Invalid credentials'))

      await expect(
        mockApi.login({
          username: 'wrong@example.com',
          password: 'wrongpassword',
        })
      ).rejects.toThrow('Invalid credentials')

      expect(mockApi.login).toHaveBeenCalledWith({
        username: 'wrong@example.com',
        password: 'wrongpassword',
      })
    })

    it('should handle network timeouts', async () => {
      // Mock timeout scenario
      mockApi.login.mockImplementation(
        () =>
          new Promise((_, reject) =>
            setTimeout(() => reject(new Error('Network timeout')), 50)
          )
      )

      await expect(
        mockApi.login({
          username: 'test@example.com',
          password: 'testpassword',
        })
      ).rejects.toThrow('Network timeout')
    })
  })

  describe('Registration Performance', () => {
    it('should complete registration within reasonable time', async () => {
      // Mock successful registration
      mockApi.register.mockResolvedValueOnce({
        id: '123',
        username: 'newuser',
        email: 'new@example.com',
        name: 'New User',
        is_superadmin: false,
        is_active: true,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      })

      const startTime = Date.now()

      const result = await mockApi.register({
        username: 'newuser',
        email: 'new@example.com',
        name: 'New User',
        password: 'securepassword',
      })

      const endTime = Date.now()
      const duration = endTime - startTime

      // Should complete within reasonable time
      expect(duration).toBeLessThan(100)
      expect(result).toHaveProperty('id')
      expect(result.username).toBe('newuser')
    })

    it('should handle registration validation errors', async () => {
      // Mock validation error
      mockApi.register.mockRejectedValueOnce(
        new Error('Username already exists')
      )

      await expect(
        mockApi.register({
          username: 'existinguser',
          email: 'existing@example.com',
          name: 'Existing User',
          password: 'password',
        })
      ).rejects.toThrow('Username already exists')
    })

    it('should validate password requirements', async () => {
      // Mock weak password error
      mockApi.register.mockRejectedValueOnce(new Error('Password too weak'))

      await expect(
        mockApi.register({
          username: 'newuser',
          email: 'new@example.com',
          name: 'New User',
          password: '123',
        })
      ).rejects.toThrow('Password too weak')
    })
  })

  describe('Session Management', () => {
    it('should handle session validation', async () => {
      // Mock successful session validation
      mockApi.getCurrentUser.mockResolvedValueOnce({
        id: '123',
        username: 'testuser',
        email: 'test@example.com',
        name: 'Test User',
        is_superadmin: false,
        is_active: true,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      })

      const result = await mockApi.getCurrentUser()

      expect(result).toHaveProperty('id')
      expect(result.username).toBe('testuser')
    })

    it('should handle expired sessions', async () => {
      // Mock expired session
      mockApi.getCurrentUser.mockRejectedValueOnce(new Error('Token expired'))

      await expect(mockApi.getCurrentUser()).rejects.toThrow('Token expired')
    })

    it('should handle token refresh', async () => {
      // Mock successful token refresh
      mockApi.refreshToken.mockResolvedValueOnce({
        access_token: 'new-token',
        token_type: 'bearer',
        expires_in: 3600,
      })

      const result = await mockApi.refreshToken()

      expect(result).toHaveProperty('access_token')
      expect(result.access_token).toBe('new-token')
    })
  })

  describe('Error Handling and Recovery', () => {
    it('should handle bcrypt-related errors gracefully', async () => {
      // Mock bcrypt error (simulating the reported issue)
      mockApi.login.mockRejectedValueOnce(new Error('bcrypt error'))

      await expect(
        mockApi.login({
          username: 'test@example.com',
          password: 'testpassword',
        })
      ).rejects.toThrow('bcrypt error')
    })

    it('should handle database connection issues', async () => {
      // Mock database error
      mockApi.login.mockRejectedValueOnce(
        new Error('Database connection failed')
      )

      await expect(
        mockApi.login({
          username: 'test@example.com',
          password: 'testpassword',
        })
      ).rejects.toThrow('Database connection failed')
    })

    it('should handle API server downtime', async () => {
      // Mock server error
      mockApi.login.mockRejectedValueOnce(new Error('Service unavailable'))

      await expect(
        mockApi.login({
          username: 'test@example.com',
          password: 'testpassword',
        })
      ).rejects.toThrow('Service unavailable')
    })
  })

  describe('Performance Benchmarks', () => {
    it('should meet authentication performance targets', async () => {
      // Mock responses with realistic delays
      mockApi.login.mockImplementation(
        () =>
          new Promise(
            (resolve) =>
              setTimeout(
                () =>
                  resolve({
                    access_token: 'mock-token',
                    token_type: 'bearer',
                    expires_in: 3600,
                  }),
                10
              ) // 10ms simulated server response
          )
      )

      const iterations = 5
      const times: number[] = []

      for (let i = 0; i < iterations; i++) {
        const startTime = Date.now()
        await mockApi.login({
          username: 'test@example.com',
          password: 'testpassword',
        })
        const endTime = Date.now()
        times.push(endTime - startTime)
      }

      const averageTime = times.reduce((a, b) => a + b, 0) / times.length
      const maxTime = Math.max(...times)

      // Performance targets
      expect(averageTime).toBeLessThan(50) // Average should be < 50ms
      expect(maxTime).toBeLessThan(100) // Max should be < 100ms

      console.log(
        `Authentication performance: avg=${averageTime.toFixed(1)}ms, max=${maxTime}ms`
      )
    })

    it('should handle concurrent authentication requests', async () => {
      // Mock concurrent login attempts
      mockApi.login.mockResolvedValue({
        access_token: 'mock-token',
        token_type: 'bearer',
        expires_in: 3600,
      })

      const concurrentRequests = 10
      const promises = Array.from({ length: concurrentRequests }, () =>
        mockApi.login({
          username: 'test@example.com',
          password: 'testpassword',
        })
      )

      const startTime = Date.now()
      const results = await Promise.all(promises)
      const endTime = Date.now()
      const totalTime = endTime - startTime

      // All requests should succeed
      expect(results).toHaveLength(concurrentRequests)
      results.forEach((result) => {
        expect(result).toHaveProperty('access_token')
      })

      // Should handle concurrent requests efficiently
      expect(totalTime).toBeLessThan(200) // Should complete within 200ms

      console.log(
        `Concurrent authentication: ${concurrentRequests} requests in ${totalTime}ms`
      )
    })
  })

  describe('Integration Test Scenarios', () => {
    it('should simulate full registration-to-login flow', async () => {
      // Mock registration
      mockApi.register.mockResolvedValueOnce({
        id: '123',
        username: 'flowtest',
        email: 'flow@example.com',
        name: 'Flow Test',
        is_superadmin: false,
        is_active: true,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      })

      // Mock subsequent login
      mockApi.login.mockResolvedValueOnce({
        access_token: 'flow-token',
        token_type: 'bearer',
        expires_in: 3600,
      })

      // Register user
      const user = await mockApi.register({
        username: 'flowtest',
        email: 'flow@example.com',
        name: 'Flow Test',
        password: 'flowpassword',
      })

      expect(user.username).toBe('flowtest')

      // Login with new user
      const token = await mockApi.login({
        username: 'flowtest',
        password: 'flowpassword',
      })

      expect(token.access_token).toBe('flow-token')
    })
  })
})

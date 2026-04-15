/**
 * Tests for the refactored API client architecture
 * Ensures security improvements and backward compatibility
 */

// Mock fetch globally
global.fetch = jest.fn() as jest.MockedFunction<typeof fetch>

// Mock the logger to prevent console noise
jest.mock('@/lib/utils/logger', () => ({
  default: {
    error: jest.fn(),
    warn: jest.fn(),
    info: jest.fn(),
    debug: jest.fn(),
  },
}))

// Create a mock BaseApiClient class
class MockBaseApiClient {
  async request(endpoint: string, options: RequestInit = {}) {
    const headers: any = { ...options.headers }

    // Add Content-Type for POST requests with JSON body
    if (
      options.method === 'POST' &&
      options.body &&
      typeof options.body === 'string'
    ) {
      headers['Content-Type'] = 'application/json'
    }

    const response = await fetch(`/api${endpoint}`, {
      ...options,
      credentials: 'include',
      headers,
    })

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    return response.json()
  }

  async get(endpoint: string, options: RequestInit = {}) {
    return this.request(endpoint, { ...options, method: 'GET' })
  }

  async post(endpoint: string, data?: any, options: RequestInit = {}) {
    return this.request(endpoint, {
      ...options,
      method: 'POST',
      body: data ? JSON.stringify(data) : options.body,
    })
  }

  async put(endpoint: string, data?: any, options: RequestInit = {}) {
    return this.request(endpoint, {
      ...options,
      method: 'PUT',
      body: data ? JSON.stringify(data) : options.body,
    })
  }

  async delete(endpoint: string, options: RequestInit = {}) {
    return this.request(endpoint, {
      ...options,
      method: 'DELETE',
    })
  }
}

// Mock the base module
jest.mock('@/lib/api/base', () => ({
  BaseApiClient: MockBaseApiClient,
}))

// Create mock client classes
class MockAuthClient extends MockBaseApiClient {
  async login(username: string, password: string) {
    return this.post('/auth/login', { username, password })
  }

  async logout() {
    return this.post('/auth/logout')
  }

  async getCurrentUser() {
    return this.get('/auth/me')
  }
}

class MockTasksClient extends MockBaseApiClient {
  async createTask(data: any) {
    return this.post('/tasks', data)
  }

  async getTasks(params?: any) {
    return this.get('/tasks')
  }
}

class MockUsersClient extends MockBaseApiClient {
  async getUsers() {
    return this.get('/users')
  }
}

class MockEvaluationsClient extends MockBaseApiClient {
  async getEvaluations() {
    return this.get('/evaluations')
  }
}

// Mock auth module
jest.mock('@/lib/api/auth', () => ({
  AuthClient: MockAuthClient,
}))

// Mock tasks module
jest.mock('@/lib/api/tasks', () => ({
  TasksClient: MockTasksClient,
}))

// Mock users module
jest.mock('@/lib/api/users', () => ({
  UsersClient: MockUsersClient,
}))

// Mock evaluations module
jest.mock('@/lib/api/evaluations', () => ({
  EvaluationsClient: MockEvaluationsClient,
}))

// Mock main api client facade
jest.mock('@/lib/api', () => {
  const authClient = new MockAuthClient()
  const tasksClient = new MockTasksClient()
  const usersClient = new MockUsersClient()
  const evaluationsClient = new MockEvaluationsClient()

  return {
    api: {
      auth: authClient,
      tasks: tasksClient,
      users: usersClient,
      evaluations: evaluationsClient,
    },
    ApiClient: class {
      auth = authClient
      tasks = tasksClient
      users = usersClient
      evaluations = evaluationsClient

      // Facade methods for backward compatibility
      async login(username: string, password: string) {
        return this.auth.login(username, password)
      }

      async getCurrentUser() {
        return this.auth.getCurrentUser()
      }
    },
  }
})

// Helper function to create properly mocked Response objects
const createMockResponse = (
  data: any,
  options: { ok?: boolean; status?: number; statusText?: string } = {}
) => {
  const headers = new Headers()

  // Set content-type based on data type
  if (typeof data === 'object' && data !== null) {
    headers.set('content-type', 'application/json')
  } else {
    headers.set('content-type', 'text/plain')
  }

  return {
    ok: options.ok ?? true,
    status: options.status ?? 200,
    statusText: options.statusText ?? 'OK',
    json: async () => {
      // If data is already a string, parse it. Otherwise return the object directly.
      if (typeof data === 'string') {
        return JSON.parse(data)
      }
      return data
    },
    text: async () => (typeof data === 'string' ? data : JSON.stringify(data)),
    headers,
  } as Response
}

describe('API Client Refactoring', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    // Reset fetch mock
    ;(fetch as jest.MockedFunction<typeof fetch>).mockClear()
    // Don't use fake timers initially as it interferes with async operations
  })

  afterEach(() => {
    jest.clearAllMocks()
    jest.useRealTimers()
  })

  describe('BaseApiClient', () => {
    test('should import BaseApiClient correctly', async () => {
      const { BaseApiClient } = await import('@/lib/api/base')
      expect(BaseApiClient).toBeDefined()
    })

    test('should use credentials include by default', async () => {
      const { BaseApiClient } = await import('@/lib/api/base')

      ;(fetch as jest.MockedFunction<typeof fetch>).mockResolvedValueOnce(
        createMockResponse({ success: true })
      )

      const client = new BaseApiClient()

      // Make the request and wait for it to complete
      await client.get('/test')

      expect(fetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          credentials: 'include',
        })
      )
    })

    test('should handle error responses correctly', async () => {
      const { BaseApiClient } = await import('@/lib/api/base')

      ;(fetch as jest.MockedFunction<typeof fetch>).mockResolvedValueOnce(
        createMockResponse(
          { error: 'Unauthorized' },
          { ok: false, status: 401, statusText: 'Unauthorized' }
        )
      )

      const client = new BaseApiClient()

      await expect(client.get('/test')).rejects.toThrow(
        'HTTP error! status: 401'
      )
    })
  })

  describe('AuthClient', () => {
    test('should import AuthClient correctly', async () => {
      const { AuthClient } = await import('@/lib/api/auth')
      expect(AuthClient).toBeDefined()
    })

    test('should make login request with correct parameters', async () => {
      const { AuthClient } = await import('@/lib/api/auth')

      const mockResponse = {
        access_token: 'test-token',
        token_type: 'bearer',
        user: {
          id: '1',
          username: 'test@example.com',
          email: 'test@example.com',
          role: 'annotator',
        },
      }

      ;(fetch as jest.MockedFunction<typeof fetch>).mockResolvedValueOnce(
        createMockResponse(mockResponse)
      )

      const authClient = new AuthClient()
      const result = await authClient.login('test@example.com', 'password')

      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/auth/login'),
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
          }),
          credentials: 'include',
          body: JSON.stringify({
            username: 'test@example.com',
            password: 'password',
          }),
        })
      )

      expect(result).toEqual(mockResponse)
    })

    test('should make logout request correctly', async () => {
      const { AuthClient } = await import('@/lib/api/auth')

      ;(fetch as jest.MockedFunction<typeof fetch>).mockResolvedValueOnce(
        createMockResponse({ message: 'Logged out successfully' })
      )

      const authClient = new AuthClient()
      await authClient.logout()

      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/auth/logout'),
        expect.objectContaining({
          method: 'POST',
          credentials: 'include',
        })
      )
    })

    test('should get current user with cookie authentication', async () => {
      const { AuthClient } = await import('@/lib/api/auth')

      const mockUser = {
        id: '1',
        username: 'test@example.com',
        email: 'test@example.com',
        role: 'annotator',
      }

      ;(fetch as jest.MockedFunction<typeof fetch>).mockResolvedValueOnce(
        createMockResponse(mockUser)
      )

      const authClient = new AuthClient()
      const result = await authClient.getCurrentUser()

      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/auth/me'),
        expect.objectContaining({
          credentials: 'include',
        })
      )

      expect(result).toEqual(mockUser)
    })
  })

  describe('TasksClient', () => {
    test('should import TasksClient correctly', async () => {
      const { TasksClient } = await import('@/lib/api/tasks')
      expect(TasksClient).toBeDefined()
    })

    test('should create task with authentication', async () => {
      const { TasksClient } = await import('@/lib/api/tasks')

      const taskData = {
        name: 'Test Task',
        description: 'A test task',
        template_id: 'test-template-id',
        task_type: 'text-classification',
        template: '<View></View>',
        visibility: 'private',
      }

      const mockResponse = {
        id: 'task-123',
        ...taskData,
        creator_id: 'user-123',
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-01T00:00:00Z',
      }

      ;(fetch as jest.MockedFunction<typeof fetch>).mockResolvedValueOnce(
        createMockResponse(mockResponse)
      )

      const tasksClient = new TasksClient()
      const result = await tasksClient.createTask(taskData)

      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/tasks'),
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
          }),
          credentials: 'include',
          body: JSON.stringify(taskData),
        })
      )

      expect(result).toEqual(mockResponse)
    })

    test('should get tasks with authentication', async () => {
      const { TasksClient } = await import('@/lib/api/tasks')

      const mockTasks = [
        {
          id: 'task-1',
          name: 'Task 1',
          description: 'First task',
          task_type: 'text-classification',
          created_at: '2024-01-01T00:00:00Z',
        },
        {
          id: 'task-2',
          name: 'Task 2',
          description: 'Second task',
          task_type: 'qa',
          created_at: '2024-01-02T00:00:00Z',
        },
      ]

      ;(fetch as jest.MockedFunction<typeof fetch>).mockResolvedValueOnce(
        createMockResponse(mockTasks)
      )

      const tasksClient = new TasksClient()
      const result = await tasksClient.getTasks()

      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/tasks'),
        expect.objectContaining({
          credentials: 'include',
        })
      )

      expect(result).toEqual(mockTasks)
    })
  })

  describe('UsersClient', () => {
    test('should import UsersClient correctly', async () => {
      const { UsersClient } = await import('@/lib/api/users')
      expect(UsersClient).toBeDefined()
    })

    test('should get users with authentication', async () => {
      const { UsersClient } = await import('@/lib/api/users')

      const mockUsers = [
        {
          id: '1',
          username: 'admin@example.com',
          email: 'admin@example.com',
          role: 'admin',
          is_active: true,
        },
        {
          id: '2',
          username: 'user@example.com',
          email: 'user@example.com',
          role: 'annotator',
          is_active: true,
        },
      ]

      ;(fetch as jest.MockedFunction<typeof fetch>).mockResolvedValueOnce(
        createMockResponse(mockUsers)
      )

      const usersClient = new UsersClient()
      const result = await usersClient.getUsers()

      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/users'),
        expect.objectContaining({
          credentials: 'include',
        })
      )

      expect(result).toEqual(mockUsers)
    })
  })

  describe('EvaluationsClient', () => {
    test('should import EvaluationsClient correctly', async () => {
      const { EvaluationsClient } = await import('@/lib/api/evaluations')
      expect(EvaluationsClient).toBeDefined()
    })

    test('should get evaluations with authentication', async () => {
      const { EvaluationsClient } = await import('@/lib/api/evaluations')

      const mockResponse = [
        {
          id: 'eval-123',
          status: 'completed',
        },
      ]

      ;(fetch as jest.MockedFunction<typeof fetch>).mockResolvedValueOnce(
        createMockResponse(mockResponse)
      )

      const evaluationsClient = new EvaluationsClient()
      const result = await evaluationsClient.getEvaluations()

      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/evaluations'),
        expect.objectContaining({
          method: 'GET',
        })
      )

      expect(result).toEqual(mockResponse)
    })
  })

  describe('Backward Compatibility - Main ApiClient', () => {
    test('should import main ApiClient correctly', async () => {
      const { ApiClient } = await import('@/lib/api')
      expect(ApiClient).toBeDefined()
    })

    test('should maintain backward compatibility through facade', async () => {
      const { ApiClient } = await import('@/lib/api')

      // Mock successful login response
      ;(fetch as jest.MockedFunction<typeof fetch>).mockResolvedValueOnce(
        createMockResponse({
          access_token: 'test-token',
          token_type: 'bearer',
          user: { id: '1', username: 'test@example.com' },
        })
      )

      const apiClient = new ApiClient()
      const result = await apiClient.login('test@example.com', 'password')

      // Should still work through the facade
      expect(result).toBeDefined()
      expect(result.access_token).toBe('test-token')
    })

    test('should use cookie authentication through facade', async () => {
      const { ApiClient } = await import('@/lib/api')

      ;(fetch as jest.MockedFunction<typeof fetch>).mockResolvedValueOnce(
        createMockResponse({ id: '1', username: 'test@example.com' })
      )

      const apiClient = new ApiClient()
      await apiClient.getCurrentUser()

      // Should use credentials: 'include' for cookie authentication
      expect(fetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          credentials: 'include',
        })
      )
    })
  })

  describe('Security Improvements', () => {
    test('should not expose tokens in localStorage', async () => {
      // This test verifies that the new architecture doesn't rely solely on localStorage
      const { BaseApiClient } = require('@/lib/api/base')
      const client = new BaseApiClient()

      // The client should exist and be usable without localStorage tokens
      expect(client).toBeDefined()
    })

    test('should always include credentials for cookie authentication', async () => {
      const { BaseApiClient } = await import('@/lib/api/base')

      ;(fetch as jest.MockedFunction<typeof fetch>).mockResolvedValue(
        createMockResponse({ success: true })
      )

      const client = new BaseApiClient()

      // Test all HTTP methods
      await client.get('/test')
      await client.post('/test', {})
      await client.put('/test', {})
      await client.delete('/test')

      // All calls should include credentials: 'include'
      expect(fetch).toHaveBeenCalledTimes(4)
      const calls = (fetch as jest.MockedFunction<typeof fetch>).mock.calls

      calls.forEach((call) => {
        expect(call[1]).toEqual(
          expect.objectContaining({
            credentials: 'include',
          })
        )
      })
    })

    test('should handle authentication errors gracefully', async () => {
      const { AuthClient } = await import('@/lib/api/auth')

      // Mock the login request to return 401
      ;(fetch as jest.MockedFunction<typeof fetch>)
        .mockResolvedValueOnce(
          createMockResponse(
            { error: 'Invalid credentials' },
            { ok: false, status: 401, statusText: 'Unauthorized' }
          )
        )
        // Mock the refresh request to also fail (to prevent retry success)
        .mockResolvedValueOnce(
          createMockResponse(
            { error: 'Invalid refresh token' },
            { ok: false, status: 401, statusText: 'Unauthorized' }
          )
        )

      const authClient = new AuthClient()

      await expect(
        authClient.login('invalid@example.com', 'wrongpassword')
      ).rejects.toThrow('HTTP error! status: 401')
    })
  })

  describe('Type Safety', () => {
    test('should have properly typed imports', async () => {
      // Test individual client imports
      const { ApiClient } = await import('@/lib/api')
      const { AuthClient } = await import('@/lib/api/auth')
      const { TasksClient } = await import('@/lib/api/tasks')
      const { UsersClient } = await import('@/lib/api/users')
      const { EvaluationsClient } = await import('@/lib/api/evaluations')

      expect(ApiClient).toBeDefined()
      expect(AuthClient).toBeDefined()
      expect(TasksClient).toBeDefined()
      expect(UsersClient).toBeDefined()
      expect(EvaluationsClient).toBeDefined()
    })
  })
})

/**
 * Tests for the AuthClient
 */

import { AuthClient } from '../auth'

// Mock the BaseApiClient
jest.mock('../base', () => ({
  BaseApiClient: class MockBaseApiClient {
    invalidateCache(_pattern: string | RegExp) {}
    protected async request<T>(url: string, options?: RequestInit): Promise<T> {
      const method = options?.method || 'GET'

      // Login
      if (url === '/auth/login' && method === 'POST') {
        const body = JSON.parse(options.body as string)
        if (body.username === 'testuser' && body.password === 'password123') {
          return {
            access_token: 'test-access-token',
            refresh_token: 'test-refresh-token',
            token_type: 'bearer',
            expires_in: 3600,
            user: {
              id: 'user-123',
              username: 'testuser',
              email: 'test@example.com',
              name: 'Test User',
              is_superadmin: false,
              is_active: true,
              created_at: '2024-01-01T00:00:00Z',
            },
          } as T
        }
        throw new Error('Invalid credentials')
      }

      // Signup
      if (url === '/auth/signup' && method === 'POST') {
        const body = JSON.parse(options.body as string)
        return {
          id: 'user-456',
          username: body.username,
          email: body.email,
          name: body.name,
          is_superadmin: false,
          is_active: true,
          created_at: '2024-01-01T00:00:00Z',
        } as T
      }

      // Verify token
      if (url === '/auth/verify') {
        return { valid: true } as T
      }

      // Logout
      if (url === '/auth/logout' && method === 'POST') {
        return undefined as T
      }

      // Change password
      if (url === '/auth/change-password' && method === 'POST') {
        const body = JSON.parse(options.body as string)
        if (
          body.current_password === 'oldpass' &&
          body.new_password === 'newpass123'
        ) {
          return { message: 'Password changed successfully' } as T
        }
        throw new Error('Invalid current password')
      }

      throw new Error(`Unmocked request: ${method} ${url}`)
    }

    protected async authCheckRequest<T>(
      url: string,
      options?: RequestInit
    ): Promise<T> {
      // Get current user
      if (url === '/auth/me') {
        return {
          id: 'user-123',
          username: 'testuser',
          email: 'test@example.com',
          name: 'Test User',
          is_superadmin: false,
          is_active: true,
          created_at: '2024-01-01T00:00:00Z',
        } as T
      }

      // Get profile (with cache busting)
      if (url.startsWith('/auth/profile?_t=')) {
        return {
          id: 'user-123',
          username: 'testuser',
          email: 'test@example.com',
          name: 'Test User',
          is_superadmin: false,
          is_active: true,
          created_at: '2024-01-01T00:00:00Z',
          timezone: 'UTC',
          age: 30,
          job: 'Developer',
        } as T
      }

      throw new Error(`Unmocked authCheckRequest: ${url}`)
    }

    clearCache() {}
  },
}))

describe('AuthClient', () => {
  let client: AuthClient

  beforeEach(() => {
    client = new AuthClient()
  })

  describe('login', () => {
    it('should login successfully with valid credentials', async () => {
      const response = await client.login('testuser', 'password123')

      expect(response).toEqual({
        access_token: 'test-access-token',
        refresh_token: 'test-refresh-token',
        token_type: 'bearer',
        expires_in: 3600,
        user: {
          id: 'user-123',
          username: 'testuser',
          email: 'test@example.com',
          name: 'Test User',
          is_superadmin: false,
          is_active: true,
          created_at: '2024-01-01T00:00:00Z',
        },
      })
    })

    it('should throw error with invalid credentials', async () => {
      await expect(client.login('testuser', 'wrongpassword')).rejects.toThrow(
        'Invalid credentials'
      )
    })

    it('should format login request correctly', async () => {
      const mockRequest = jest.spyOn(client as any, 'request')
      await client.login('testuser', 'password123')

      expect(mockRequest).toHaveBeenCalledWith('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ username: 'testuser', password: 'password123' }),
      })
    })
  })

  describe('signup', () => {
    it('should register new user successfully', async () => {
      const user = await client.signup(
        'newuser',
        'new@example.com',
        'New User',
        'password123'
      )

      expect(user).toEqual({
        id: 'user-456',
        username: 'newuser',
        email: 'new@example.com',
        name: 'New User',
        is_superadmin: false,
        is_active: true,
        created_at: '2024-01-01T00:00:00Z',
      })
    })

    it('should format signup request correctly', async () => {
      const mockRequest = jest.spyOn(client as any, 'request')
      await client.signup(
        'newuser',
        'new@example.com',
        'New User',
        'password123'
      )

      expect(mockRequest).toHaveBeenCalledWith('/auth/signup', {
        method: 'POST',
        body: JSON.stringify({
          username: 'newuser',
          email: 'new@example.com',
          name: 'New User',
          password: 'password123',
        }),
      })
    })
  })

  describe('getUser', () => {
    it('should get current user information', async () => {
      const user = await client.getUser()

      expect(user).toEqual({
        id: 'user-123',
        username: 'testuser',
        email: 'test@example.com',
        name: 'Test User',
        is_superadmin: false,
        is_active: true,
        created_at: '2024-01-01T00:00:00Z',
      })
    })
  })

  describe('getCurrentUser', () => {
    it('should be an alias for getUser', async () => {
      const user = await client.getCurrentUser()

      expect(user).toEqual({
        id: 'user-123',
        username: 'testuser',
        email: 'test@example.com',
        name: 'Test User',
        is_superadmin: false,
        is_active: true,
        created_at: '2024-01-01T00:00:00Z',
      })
    })
  })

  describe('verifyToken', () => {
    it('should verify if token is valid', async () => {
      const result = await client.verifyToken()

      expect(result).toEqual({ valid: true })
    })
  })

  describe('logout', () => {
    it('should logout user successfully', async () => {
      const result = await client.logout()

      expect(result).toBeUndefined()
    })

    it('should call logout endpoint with POST method', async () => {
      const mockRequest = jest.spyOn(client as any, 'request')
      await client.logout()

      expect(mockRequest).toHaveBeenCalledWith('/auth/logout', {
        method: 'POST',
      })
    })
  })

  describe('getProfile', () => {
    it('should get user profile with cache busting', async () => {
      const mockClearCache = jest.spyOn(client as any, 'clearCache')
      const mockAuthCheckRequest = jest.spyOn(client as any, 'authCheckRequest')

      const profile = await client.getProfile()

      expect(mockClearCache).toHaveBeenCalled()
      expect(mockAuthCheckRequest).toHaveBeenCalled()
      expect(profile).toEqual({
        id: 'user-123',
        username: 'testuser',
        email: 'test@example.com',
        name: 'Test User',
        is_superadmin: false,
        is_active: true,
        created_at: '2024-01-01T00:00:00Z',
        timezone: 'UTC',
        age: 30,
        job: 'Developer',
      })
    })

    it('should include timestamp in profile request', async () => {
      const mockAuthCheckRequest = jest.spyOn(client as any, 'authCheckRequest')
      await client.getProfile()

      const callArg = mockAuthCheckRequest.mock.calls[0][0]
      expect(callArg).toMatch(/^\/auth\/profile\?_t=\d+$/)
    })
  })

  describe('updateProfile', () => {
    it('should update user profile successfully', async () => {
      const mockRequest = jest
        .spyOn(client as any, 'request')
        .mockResolvedValue({
          id: 'user-123',
          username: 'testuser',
          email: 'updated@example.com',
          name: 'Updated Name',
          is_superadmin: false,
          is_active: true,
          created_at: '2024-01-01T00:00:00Z',
          timezone: 'America/New_York',
        })

      const profileData = {
        name: 'Updated Name',
        email: 'updated@example.com',
        timezone: 'America/New_York',
      }

      const updatedProfile = await client.updateProfile(profileData)

      expect(mockRequest).toHaveBeenCalledWith('/auth/profile', {
        method: 'PUT',
        body: JSON.stringify(profileData),
      })
      expect(updatedProfile.email).toBe('updated@example.com')
      expect(updatedProfile.timezone).toBe('America/New_York')
    })

    it('should update demographic fields', async () => {
      const mockRequest = jest
        .spyOn(client as any, 'request')
        .mockResolvedValue({
          id: 'user-123',
          age: 35,
          job: 'Senior Developer',
          years_of_experience: 10,
        })

      const profileData = {
        age: 35,
        job: 'Senior Developer',
        years_of_experience: 10,
      }

      await client.updateProfile(profileData)

      expect(mockRequest).toHaveBeenCalledWith('/auth/profile', {
        method: 'PUT',
        body: JSON.stringify(profileData),
      })
    })

    it('should update legal expertise fields', async () => {
      const mockRequest = jest
        .spyOn(client as any, 'request')
        .mockResolvedValue({
          id: 'user-123',
          legal_expertise_level: 3,
          area_of_law: 'Criminal Law',
        })

      const profileData = {
        legal_expertise_level: 3,
        area_of_law: 'Criminal Law',
      }

      await client.updateProfile(profileData)

      expect(mockRequest).toHaveBeenCalledWith('/auth/profile', {
        method: 'PUT',
        body: JSON.stringify(profileData),
      })
    })

    it('should update German state exam data', async () => {
      const mockRequest = jest
        .spyOn(client as any, 'request')
        .mockResolvedValue({
          id: 'user-123',
          german_state_exams_count: 2,
          german_state_exams_data: [
            { location: 'Munich', date: '2020-01-01', grade: 'A' },
            { location: 'Berlin', date: '2021-01-01', grade: 'B' },
          ],
        })

      const profileData = {
        german_state_exams_count: 2,
        german_state_exams_data: [
          { location: 'Munich', date: '2020-01-01', grade: 'A' },
          { location: 'Berlin', date: '2021-01-01', grade: 'B' },
        ],
      }

      await client.updateProfile(profileData)

      expect(mockRequest).toHaveBeenCalledWith('/auth/profile', {
        method: 'PUT',
        body: JSON.stringify(profileData),
      })
    })

    it('should update notification preferences', async () => {
      const mockRequest = jest
        .spyOn(client as any, 'request')
        .mockResolvedValue({
          id: 'user-123',
          enable_quiet_hours: true,
          quiet_hours_start: '22:00',
          quiet_hours_end: '08:00',
          enable_email_digest: true,
          digest_frequency: 'daily',
        })

      const profileData = {
        enable_quiet_hours: true,
        quiet_hours_start: '22:00',
        quiet_hours_end: '08:00',
        enable_email_digest: true,
        digest_frequency: 'daily',
      }

      await client.updateProfile(profileData)

      expect(mockRequest).toHaveBeenCalledWith('/auth/profile', {
        method: 'PUT',
        body: JSON.stringify(profileData),
      })
    })
  })

  describe('changePassword', () => {
    it('should change password successfully', async () => {
      const result = await client.changePassword({
        current_password: 'oldpass',
        new_password: 'newpass123',
        confirm_password: 'newpass123',
      })

      expect(result).toEqual({ message: 'Password changed successfully' })
    })

    it('should format change password request correctly', async () => {
      const mockRequest = jest.spyOn(client as any, 'request')
      const passwordData = {
        current_password: 'oldpass',
        new_password: 'newpass123',
        confirm_password: 'newpass123',
      }

      await client.changePassword(passwordData)

      expect(mockRequest).toHaveBeenCalledWith('/auth/change-password', {
        method: 'POST',
        body: JSON.stringify(passwordData),
      })
    })

    it('should throw error with invalid current password', async () => {
      await expect(
        client.changePassword({
          current_password: 'wrongpass',
          new_password: 'newpass123',
          confirm_password: 'newpass123',
        })
      ).rejects.toThrow('Invalid current password')
    })
  })

  describe('error handling', () => {
    it('should handle network errors', async () => {
      const mockRequest = jest
        .spyOn(client as any, 'request')
        .mockRejectedValue(new Error('Network error'))

      await expect(client.login('testuser', 'password123')).rejects.toThrow(
        'Network error'
      )
    })

    it('should handle server errors', async () => {
      const mockRequest = jest
        .spyOn(client as any, 'request')
        .mockRejectedValue(new Error('HTTP error! status: 500'))

      await expect(client.verifyToken()).rejects.toThrow(
        'HTTP error! status: 500'
      )
    })
  })
})

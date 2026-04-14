/**
 * Tests for the UsersClient
 */

import { UsersClient } from '../users'

// Mock the BaseApiClient
jest.mock('../base', () => ({
  BaseApiClient: class MockBaseApiClient {
    protected async request<T>(url: string, options?: RequestInit): Promise<T> {
      const method = options?.method || 'GET'

      // Get all users
      if (url === '/organizations/manage/users' && method === 'GET') {
        return [
          {
            id: 'user-1',
            username: 'user1',
            email: 'user1@example.com',
            name: 'User One',
            is_superadmin: false,
            is_active: true,
            created_at: '2024-01-01T00:00:00Z',
          },
          {
            id: 'user-2',
            username: 'user2',
            email: 'user2@example.com',
            name: 'User Two',
            is_superadmin: true,
            is_active: true,
            created_at: '2024-01-02T00:00:00Z',
          },
          {
            id: 'user-3',
            username: 'user3',
            email: 'user3@example.com',
            name: 'User Three',
            is_superadmin: false,
            is_active: false,
            created_at: '2024-01-03T00:00:00Z',
          },
        ] as T
      }

      // Update user superadmin status
      if (
        url.match(/^\/organizations\/manage\/users\/user-\d+\/superadmin$/) &&
        method === 'PUT'
      ) {
        const body = JSON.parse(options.body as string)
        const userId = url.match(/user-(\d+)/)?.[1]
        return {
          id: `user-${userId}`,
          username: `user${userId}`,
          email: `user${userId}@example.com`,
          name: `User ${userId}`,
          is_superadmin: body.is_superadmin,
          is_active: true,
          created_at: '2024-01-01T00:00:00Z',
        } as T
      }

      // Update user status
      if (url.match(/^\/users\/user-\d+\/status$/) && method === 'PATCH') {
        const body = JSON.parse(options.body as string)
        const userId = url.match(/user-(\d+)/)?.[1]
        return {
          id: `user-${userId}`,
          username: `user${userId}`,
          email: `user${userId}@example.com`,
          name: `User ${userId}`,
          is_superadmin: false,
          is_active: body.is_active,
          created_at: '2024-01-01T00:00:00Z',
        } as T
      }

      // Delete user
      if (
        url.match(/^\/organizations\/manage\/users\/user-\d+$/) &&
        method === 'DELETE'
      ) {
        return undefined as T
      }

      // Verify user email
      if (
        url.match(/^\/users\/user-\d+\/verify-email$/) &&
        method === 'PATCH'
      ) {
        const userId = url.match(/user-(\d+)/)?.[1]
        return {
          id: `user-${userId}`,
          username: `user${userId}`,
          email: `user${userId}@example.com`,
          name: `User ${userId}`,
          is_superadmin: false,
          is_active: true,
          email_verified: true,
          email_verification_method: 'admin',
          email_verified_at: new Date().toISOString(),
          created_at: '2024-01-01T00:00:00Z',
        } as T
      }

      throw new Error(`Unmocked request: ${method} ${url}`)
    }
  },
}))

describe('UsersClient', () => {
  let client: UsersClient

  beforeEach(() => {
    client = new UsersClient()
  })

  describe('getAllUsers', () => {
    it('should fetch all users', async () => {
      const users = await client.getAllUsers()

      expect(users).toHaveLength(3)
      expect(users[0]).toEqual({
        id: 'user-1',
        username: 'user1',
        email: 'user1@example.com',
        name: 'User One',
        is_superadmin: false,
        is_active: true,
        created_at: '2024-01-01T00:00:00Z',
      })
      expect(users[1].is_superadmin).toBe(true)
      expect(users[2].is_active).toBe(false)
    })

    it('should call correct endpoint', async () => {
      const mockRequest = jest.spyOn(client as any, 'request')
      await client.getAllUsers()

      expect(mockRequest).toHaveBeenCalledWith('/organizations/manage/users')
    })
  })

  describe('getUsers', () => {
    it('should be an alias for getAllUsers', async () => {
      const users = await client.getUsers()

      expect(users).toHaveLength(3)
      expect(users[0].username).toBe('user1')
    })
  })

  describe('updateUserSuperadminStatus', () => {
    it('should promote user to superadmin', async () => {
      const user = await client.updateUserSuperadminStatus('user-1', true)

      expect(user.id).toBe('user-1')
      expect(user.is_superadmin).toBe(true)
    })

    it('should demote user from superadmin', async () => {
      const user = await client.updateUserSuperadminStatus('user-2', false)

      expect(user.id).toBe('user-2')
      expect(user.is_superadmin).toBe(false)
    })

    it('should format request correctly', async () => {
      const mockRequest = jest.spyOn(client as any, 'request')
      await client.updateUserSuperadminStatus('user-1', true)

      expect(mockRequest).toHaveBeenCalledWith(
        '/organizations/manage/users/user-1/superadmin',
        {
          method: 'PUT',
          body: JSON.stringify({ is_superadmin: true }),
        }
      )
    })
  })

  describe('updateUserRole', () => {
    it('should update user role (deprecated method)', async () => {
      const user = await client.updateUserRole('user-1', 'superadmin')

      expect(user.id).toBe('user-1')
      expect(user.is_superadmin).toBe(true)
    })

    it('should convert superadmin role to boolean', async () => {
      const mockUpdateSuperadmin = jest.spyOn(
        client,
        'updateUserSuperadminStatus'
      )
      await client.updateUserRole('user-1', 'superadmin')

      expect(mockUpdateSuperadmin).toHaveBeenCalledWith('user-1', true)
    })

    it('should convert non-superadmin role to false', async () => {
      const mockUpdateSuperadmin = jest.spyOn(
        client,
        'updateUserSuperadminStatus'
      )
      await client.updateUserRole('user-1', 'user')

      expect(mockUpdateSuperadmin).toHaveBeenCalledWith('user-1', false)
    })
  })

  describe('updateUserStatus', () => {
    it('should activate user', async () => {
      const user = await client.updateUserStatus('user-3', true)

      expect(user.id).toBe('user-3')
      expect(user.is_active).toBe(true)
    })

    it('should deactivate user', async () => {
      const user = await client.updateUserStatus('user-1', false)

      expect(user.id).toBe('user-1')
      expect(user.is_active).toBe(false)
    })

    it('should format request correctly', async () => {
      const mockRequest = jest.spyOn(client as any, 'request')
      await client.updateUserStatus('user-1', false)

      expect(mockRequest).toHaveBeenCalledWith('/users/user-1/status', {
        method: 'PATCH',
        body: JSON.stringify({ is_active: false }),
      })
    })
  })

  describe('deleteUser', () => {
    it('should delete user successfully', async () => {
      const result = await client.deleteUser('user-1')

      expect(result).toBeUndefined()
    })

    it('should call correct endpoint', async () => {
      const mockRequest = jest.spyOn(client as any, 'request')
      await client.deleteUser('user-1')

      expect(mockRequest).toHaveBeenCalledWith(
        '/organizations/manage/users/user-1',
        {
          method: 'DELETE',
        }
      )
    })
  })

  describe('verifyUserEmail', () => {
    it('should verify user email successfully', async () => {
      const user = await client.verifyUserEmail('user-1')

      expect(user.id).toBe('user-1')
      expect(user.email_verified).toBe(true)
      expect(user.email_verification_method).toBe('admin')
      expect(user.email_verified_at).toBeDefined()
    })

    it('should call correct endpoint', async () => {
      const mockRequest = jest.spyOn(client as any, 'request')
      await client.verifyUserEmail('user-1')

      expect(mockRequest).toHaveBeenCalledWith('/users/user-1/verify-email', {
        method: 'PATCH',
      })
    })
  })

  describe('error handling', () => {
    it('should handle network errors', async () => {
      const mockRequest = jest
        .spyOn(client as any, 'request')
        .mockRejectedValue(new Error('Network error'))

      await expect(client.getAllUsers()).rejects.toThrow('Network error')
    })

    it('should handle unauthorized errors', async () => {
      const mockRequest = jest
        .spyOn(client as any, 'request')
        .mockRejectedValue(new Error('HTTP error! status: 403'))

      await expect(
        client.updateUserSuperadminStatus('user-1', true)
      ).rejects.toThrow('HTTP error! status: 403')
    })

    it('should handle not found errors', async () => {
      const mockRequest = jest
        .spyOn(client as any, 'request')
        .mockRejectedValue(new Error('HTTP error! status: 404'))

      await expect(client.deleteUser('nonexistent-user')).rejects.toThrow(
        'HTTP error! status: 404'
      )
    })
  })

  describe('response parsing', () => {
    it('should parse user list correctly', async () => {
      const users = await client.getAllUsers()

      users.forEach((user) => {
        expect(user).toHaveProperty('id')
        expect(user).toHaveProperty('username')
        expect(user).toHaveProperty('email')
        expect(user).toHaveProperty('name')
        expect(user).toHaveProperty('is_superadmin')
        expect(user).toHaveProperty('is_active')
        expect(user).toHaveProperty('created_at')
      })
    })

    it('should parse updated user correctly', async () => {
      const user = await client.updateUserSuperadminStatus('user-1', true)

      expect(typeof user.id).toBe('string')
      expect(typeof user.is_superadmin).toBe('boolean')
      expect(typeof user.is_active).toBe('boolean')
    })

    it('should handle empty user list', async () => {
      const mockRequest = jest
        .spyOn(client as any, 'request')
        .mockResolvedValue([])

      const users = await client.getAllUsers()

      expect(users).toEqual([])
      expect(Array.isArray(users)).toBe(true)
    })
  })
})

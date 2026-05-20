/**
 * Users API client
 * Handles user management operations (admin only)
 */

import { BaseApiClient } from './base'
import { User } from './types'

export class UsersClient extends BaseApiClient {
  /**
   * Get all users (admin only). Pass `search` to push the filter to the
   * server — the response is bounded by `limit` either way (defaults to
   * 500 to keep the payload sane on large deployments).
   */
  async getAllUsers(options?: { search?: string; limit?: number }): Promise<User[]> {
    const params = new URLSearchParams()
    if (options?.search) params.append('search', options.search)
    if (options?.limit) params.append('limit', String(options.limit))
    const qs = params.toString()
    return this.request(
      `/organizations/manage/users${qs ? '?' + qs : ''}`
    )
  }

  /**
   * Alias for getAllUsers for backward compatibility
   */
  async getUsers(options?: { search?: string; limit?: number }): Promise<User[]> {
    return this.getAllUsers(options)
  }

  /**
   * Update user superadmin status (superadmin only)
   */
  async updateUserSuperadminStatus(
    userId: string,
    isSuperadmin: boolean
  ): Promise<User> {
    return this.request(`/organizations/manage/users/${userId}/superadmin`, {
      method: 'PUT',
      body: JSON.stringify({ is_superadmin: isSuperadmin }),
    })
  }

  /**
   * Update user role (admin only) - for backward compatibility
   * @deprecated Use updateUserSuperadminStatus instead
   */
  async updateUserRole(userId: string, role: string): Promise<User> {
    // Convert old role format to new superadmin boolean
    const isSuperadmin = role === 'superadmin'
    return this.updateUserSuperadminStatus(userId, isSuperadmin)
  }

  /**
   * Update user status (admin only)
   */
  async updateUserStatus(userId: string, isActive: boolean): Promise<User> {
    return this.request(`/users/${userId}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ is_active: isActive }),
    })
  }

  /**
   * Delete a user (admin only)
   */
  async deleteUser(userId: string): Promise<void> {
    return this.request(`/organizations/manage/users/${userId}`, {
      method: 'DELETE',
    })
  }

  /**
   * Verify user's email address (admin only)
   */
  async verifyUserEmail(userId: string): Promise<User> {
    return this.request(`/users/${userId}/verify-email`, {
      method: 'PATCH',
    })
  }
}

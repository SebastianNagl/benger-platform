/**
 * Notifications API client
 * Handles all notification-related API operations
 */

import { BaseApiClient } from './base'

export interface Notification {
  id: string
  type: string
  title: string
  message: string
  data?: Record<string, any>
  is_read: boolean
  created_at: string
  organization_id?: string
}

export interface NotificationPreferences {
  [key: string]: boolean
}

export interface NotificationListResponse {
  notifications: Notification[]
  total: number
  unread_count: number
}

export interface UnreadCountResponse {
  count: number
}

export interface PreferencesResponse {
  preferences: NotificationPreferences
}

export interface EmailStatusResponse {
  available: boolean
  configured: boolean
  message: string
}

export interface TestEmailResponse {
  message: string
}

export interface BulkOperationRequest {
  notification_ids: string[]
}

export interface BulkOperationResponse {
  success: boolean
  count: number
  message: string
}

export interface NotificationGroupsResponse {
  groups: Record<string, Notification[]>
}

export interface NotificationSummaryResponse {
  total_notifications: number
  unread_notifications: number
  read_notifications: number
  notifications_by_type: Record<string, number>
  period_days: number
  summary_generated_at: string
}

export interface TestNotificationRequest {
  type: string
  title: string
  message: string
  data?: Record<string, any>
}

export interface TestNotificationResponse {
  success: boolean
  notification_id: string
  message: string
}

export class NotificationsClient extends BaseApiClient {
  /**
   * Get user's notifications
   */
  async getNotifications(queryString?: string): Promise<Notification[]> {
    const url = queryString
      ? `/notifications/?${queryString}`
      : '/notifications/'
    return this.get(url)
  }

  /**
   * Get unread notifications count
   */
  async getUnreadCount(): Promise<UnreadCountResponse> {
    return this.get('/notifications/unread-count')
  }

  /**
   * Mark notification as read
   */
  async markAsRead(notificationId: string): Promise<void> {
    await this.post(`/notifications/mark-read/${notificationId}`)
  }

  /**
   * Mark all notifications as read
   */
  async markAllAsRead(): Promise<{ message: string }> {
    return this.post('/notifications/mark-all-read')
  }

  /**
   * Get user notification preferences
   */
  async getPreferences(): Promise<NotificationPreferences> {
    const response: PreferencesResponse = await this.get(
      '/notifications/preferences'
    )
    return response.preferences || {}
  }

  /**
   * Update user notification preferences
   */
  async updatePreferences(preferences: NotificationPreferences): Promise<void> {
    await this.post('/notifications/preferences', { preferences })
  }

  /**
   * Create EventSource for notification stream
   * Note: This returns an EventSource object, not a Promise
   */
  createNotificationStream(): EventSource {
    // Use the SSE proxy route to handle authentication via cookies
    return new EventSource('/api/notifications/stream', {
      withCredentials: true,
    })
  }

  /**
   * Get email service status
   */
  async getEmailStatus(): Promise<EmailStatusResponse> {
    return this.get('/notifications/email/status')
  }

  /**
   * Send test email to current user
   */
  async sendTestEmail(): Promise<TestEmailResponse> {
    return this.post('/notifications/email/test')
  }

  /**
   * Send test digest email to current user
   */
  async sendTestDigest(): Promise<TestEmailResponse> {
    return this.post('/notifications/digest/test')
  }

  /**
   * Mark multiple notifications as read
   */
  async markBulkAsRead(
    notificationIds: string[]
  ): Promise<BulkOperationResponse> {
    return this.post('/notifications/bulk/mark-read', {
      notification_ids: notificationIds,
    })
  }

  /**
   * Delete multiple notifications
   */
  async deleteBulk(notificationIds: string[]): Promise<BulkOperationResponse> {
    return this.post('/notifications/bulk/delete', {
      notification_ids: notificationIds,
    })
  }

  /**
   * Get notifications grouped by specified criteria
   */
  async getNotificationGroups(
    groupBy: 'type' | 'date' | 'organization' = 'type',
    limit: number = 50
  ): Promise<NotificationGroupsResponse> {
    const params = new URLSearchParams({
      group_by: groupBy,
      limit: limit.toString(),
    })
    return this.get(`/notifications/groups?${params}`)
  }

  /**
   * Get notification analytics summary
   */
  async getNotificationSummary(
    days: number = 7
  ): Promise<NotificationSummaryResponse> {
    const params = new URLSearchParams({
      days: days.toString(),
    })
    return this.get(`/notifications/summary?${params}`)
  }

  /**
   * Create a test notification (admin only)
   */
  async createTestNotification(
    request: TestNotificationRequest
  ): Promise<TestNotificationResponse> {
    return this.post('/notifications/test/create', request)
  }

  /**
   * Generate multiple test notifications of different types (admin only)
   */
  async generateTestNotifications(): Promise<{
    success: boolean
    count: number
    message: string
  }> {
    return this.post('/notifications/test/generate-all')
  }
}

/**
 * Tests for the NotificationsClient
 * Covers all notification API endpoints including email, bulk operations, and analytics
 */

import type { NotificationPreferences } from '../notifications'
import { NotificationsClient } from '../notifications'

// Mock the BaseApiClient
jest.mock('../base', () => ({
  BaseApiClient: class MockBaseApiClient {
    protected async get<T>(url: string): Promise<T> {
      return this.handleRequest<T>('GET', url)
    }

    protected async post<T>(url: string, data?: any): Promise<T> {
      return this.handleRequest<T>('POST', url, data)
    }

    protected async put<T>(url: string, data?: any): Promise<T> {
      return this.handleRequest<T>('PUT', url, data)
    }

    protected async delete<T>(url: string): Promise<T> {
      return this.handleRequest<T>('DELETE', url)
    }

    private async handleRequest<T>(
      method: string,
      url: string,
      data?: any
    ): Promise<T> {
      // Mock notifications list
      if (
        method === 'GET' &&
        (url === '/notifications/' ||
          url.startsWith('/notifications/?') ||
          url === '/api/notifications/' ||
          url.startsWith('/api/notifications/?'))
      ) {
        return [
          {
            id: 'notif-1',
            type: 'TASK_CREATED',
            title: 'New Task Created',
            message: 'A new task has been created',
            is_read: false,
            created_at: '2024-01-01T00:00:00Z',
            organization_id: 'org-123',
          },
          {
            id: 'notif-2',
            type: 'EVALUATION_COMPLETED',
            title: 'Evaluation Completed',
            message: 'Your evaluation has finished',
            is_read: true,
            created_at: '2024-01-02T00:00:00Z',
            organization_id: 'org-123',
          },
        ] as T
      }

      // Mock unread count
      if (
        method === 'GET' &&
        (url === '/notifications/unread-count' ||
          url === '/api/notifications/unread-count')
      ) {
        return { count: 5 } as T
      }

      // Mock mark as read
      if (
        method === 'POST' &&
        (url.match(/\/notifications\/mark-read\/notif-\d+/) ||
          url.match(/\/api\/notifications\/notif-\d+\/read/))
      ) {
        return { message: 'Notification marked as read' } as T
      }

      // Mock mark all as read
      if (
        method === 'POST' &&
        (url === '/notifications/mark-all-read' ||
          url === '/api/notifications/mark-all-read')
      ) {
        return { message: 'All notifications marked as read' } as T
      }

      // Mock preferences
      if (
        method === 'GET' &&
        (url === '/notifications/preferences' ||
          url === '/api/notifications/preferences')
      ) {
        return {
          preferences: {
            TASK_CREATED: true,
            TASK_COMPLETED: true,
            EVALUATION_COMPLETED: false,
            MEMBER_JOINED: true,
          },
        } as T
      }

      // Mock update preferences
      if (
        method === 'POST' &&
        (url === '/notifications/preferences' ||
          url === '/api/notifications/preferences')
      ) {
        return { message: 'Preferences updated successfully' } as T
      }

      // Mock email status
      if (
        method === 'GET' &&
        (url === '/notifications/email/status' ||
          url === '/api/notifications/email/status')
      ) {
        return {
          smtp_configured: true,
          sendgrid_configured: false,
          preferred_provider: 'smtp',
          status: 'operational',
          from_address: 'noreply@benger.com',
          from_name: 'BenGER Platform',
        } as T
      }

      // Mock test email
      if (
        method === 'POST' &&
        (url === '/notifications/email/test' ||
          url === '/api/notifications/email/test')
      ) {
        return {
          message: 'Test email sent successfully',
          recipient: 'user@example.com',
          sent_at: '2024-01-01T12:00:00Z',
        } as T
      }

      // Mock test digest
      if (
        method === 'POST' &&
        (url === '/notifications/digest/test' ||
          url === '/api/notifications/digest/test')
      ) {
        return {
          message: 'Test digest email sent successfully',
          recipient: 'user@example.com',
          notifications_included: 3,
          sent_at: '2024-01-01T12:00:00Z',
        } as T
      }

      // Mock bulk mark as read
      if (
        method === 'POST' &&
        (url === '/notifications/bulk/mark-read' ||
          url === '/api/notifications/bulk/mark-read')
      ) {
        const notificationIds = data?.notification_ids || []
        return {
          message: `Marked ${notificationIds.length} notifications as read`,
          updated_count: notificationIds.length,
          processed_ids: notificationIds,
        } as T
      }

      // Mock bulk delete
      if (
        method === 'POST' &&
        (url === '/notifications/bulk/delete' ||
          url === '/api/notifications/bulk/delete')
      ) {
        const notificationIds = data?.notification_ids || []
        return {
          message: `Deleted ${notificationIds.length} notifications`,
          deleted_count: notificationIds.length,
          processed_ids: notificationIds,
        } as T
      }

      // Mock notification groups
      if (
        method === 'GET' &&
        (url.startsWith('/notifications/groups') ||
          url.startsWith('/api/notifications/groups'))
      ) {
        return {
          groups: [
            {
              type: 'TASK_CREATED',
              read: 5,
              unread: 3,
              total: 8,
            },
            {
              type: 'EVALUATION_COMPLETED',
              read: 10,
              unread: 2,
              total: 12,
            },
          ],
          total_types: 2,
        } as T
      }

      // Mock notification summary
      if (
        method === 'GET' &&
        (url.startsWith('/notifications/summary') ||
          url.startsWith('/api/notifications/summary'))
      ) {
        return {
          total_notifications: 20,
          unread_notifications: 5,
          read_notifications: 15,
          read_percentage: 75.0,
          recent_notifications_7_days: 8,
          most_common_type: 'TASK_CREATED',
          most_common_count: 12,
          summary_generated_at: '2024-01-01T12:00:00Z',
        } as T
      }

      throw new Error(`Unmocked request: ${method} ${url}`)
    }
  },
}))

// Mock EventSource constants
const EventSourceMock = {
  CONNECTING: 0,
  OPEN: 1,
  CLOSED: 2,
}

// Mock EventSource for SSE testing
const mockEventSource = {
  addEventListener: jest.fn(),
  removeEventListener: jest.fn(),
  close: jest.fn(),
  readyState: EventSourceMock.OPEN,
  url: '',
  withCredentials: true,
  onopen: null,
  onmessage: null,
  onerror: null,
  CONNECTING: EventSourceMock.CONNECTING,
  OPEN: EventSourceMock.OPEN,
  CLOSED: EventSourceMock.CLOSED,
  dispatchEvent: jest.fn(),
}

// Mock EventSource constructor
Object.defineProperty(global, 'EventSource', {
  writable: true,
  value: jest.fn().mockImplementation((url: string, options?: any) => {
    const instance = { ...mockEventSource }
    instance.url = url
    instance.withCredentials = options?.withCredentials || false
    return instance
  }),
})

// Add static properties to the EventSource mock
Object.assign(global.EventSource, EventSourceMock)

describe('NotificationsClient', () => {
  let client: NotificationsClient

  beforeEach(() => {
    client = new NotificationsClient()
    jest.clearAllMocks()
  })

  describe('Basic notification operations', () => {
    it('should fetch notifications list', async () => {
      const notifications = await client.getNotifications()

      expect(notifications).toHaveLength(2)
      expect(notifications[0]).toEqual({
        id: 'notif-1',
        type: 'TASK_CREATED',
        title: 'New Task Created',
        message: 'A new task has been created',
        is_read: false,
        created_at: '2024-01-01T00:00:00Z',
        organization_id: 'org-123',
      })
    })

    it('should fetch notifications with query parameters', async () => {
      const queryString = 'limit=10&offset=0&unread_only=true'
      const notifications = await client.getNotifications(queryString)

      expect(notifications).toHaveLength(2)
    })

    it('should fetch unread count', async () => {
      const response = await client.getUnreadCount()

      expect(response).toEqual({ count: 5 })
    })

    it('should mark notification as read', async () => {
      await expect(client.markAsRead('notif-1')).resolves.not.toThrow()
    })

    it('should mark all notifications as read', async () => {
      const response = await client.markAllAsRead()

      expect(response).toEqual({ message: 'All notifications marked as read' })
    })
  })

  describe('Notification preferences', () => {
    it('should fetch user preferences', async () => {
      const preferences = await client.getPreferences()

      expect(preferences).toEqual({
        TASK_CREATED: true,
        TASK_COMPLETED: true,
        EVALUATION_COMPLETED: false,
        MEMBER_JOINED: true,
      })
    })

    it('should update user preferences', async () => {
      const newPreferences: NotificationPreferences = {
        TASK_CREATED: false,
        EVALUATION_COMPLETED: true,
      }

      await expect(
        client.updatePreferences(newPreferences)
      ).resolves.not.toThrow()
    })
  })

  describe('Server-Sent Events', () => {
    it('should create notification stream EventSource', async () => {
      const eventSource = client.createNotificationStream()

      // The createNotificationStream method hardcodes '/api/notifications/stream'
      expect(EventSource).toHaveBeenCalledWith('/api/notifications/stream', {
        withCredentials: true,
      })
      expect(eventSource).toBeDefined()
      expect(eventSource.withCredentials).toBe(true)
    })

    it('should use hardcoded URL regardless of environment', async () => {
      const originalEnv = process.env.NEXT_PUBLIC_API_URL
      process.env.NEXT_PUBLIC_API_URL = 'https://api.example.com'

      // Clear previous calls
      jest.clearAllMocks()

      client.createNotificationStream()

      // The method always uses '/api/notifications/stream' regardless of environment
      expect(EventSource).toHaveBeenCalledWith('/api/notifications/stream', {
        withCredentials: true,
      })

      process.env.NEXT_PUBLIC_API_URL = originalEnv
    })

    it('should fall back to /api when NEXT_PUBLIC_API_URL is not set', async () => {
      const originalEnv = process.env.NEXT_PUBLIC_API_URL
      delete process.env.NEXT_PUBLIC_API_URL

      // Clear previous calls
      jest.clearAllMocks()

      client.createNotificationStream()

      expect(EventSource).toHaveBeenCalledWith('/api/notifications/stream', {
        withCredentials: true,
      })

      process.env.NEXT_PUBLIC_API_URL = originalEnv
    })
  })

  describe('Email functionality', () => {
    it('should get email service status', async () => {
      const status = await client.getEmailStatus()

      expect(status).toEqual({
        smtp_configured: true,
        sendgrid_configured: false,
        preferred_provider: 'smtp',
        status: 'operational',
        from_address: 'noreply@benger.com',
        from_name: 'BenGER Platform',
      })
    })

    it('should send test email', async () => {
      const response = await client.sendTestEmail()

      expect(response).toEqual({
        message: 'Test email sent successfully',
        recipient: 'user@example.com',
        sent_at: '2024-01-01T12:00:00Z',
      })
    })

    it('should send test digest email', async () => {
      const response = await client.sendTestDigest()

      expect(response).toEqual({
        message: 'Test digest email sent successfully',
        recipient: 'user@example.com',
        notifications_included: 3,
        sent_at: '2024-01-01T12:00:00Z',
      })
    })
  })

  describe('Bulk operations', () => {
    it('should mark multiple notifications as read', async () => {
      const notificationIds = ['notif-1', 'notif-2', 'notif-3']
      const response = await client.markBulkAsRead(notificationIds)

      expect(response).toEqual({
        message: 'Marked 3 notifications as read',
        updated_count: 3,
        processed_ids: notificationIds,
      })
    })

    it('should delete multiple notifications', async () => {
      const notificationIds = ['notif-1', 'notif-2']
      const response = await client.deleteBulk(notificationIds)

      expect(response).toEqual({
        message: 'Deleted 2 notifications',
        deleted_count: 2,
        processed_ids: notificationIds,
      })
    })

    it('should handle empty notification list for bulk mark as read', async () => {
      const response = await client.markBulkAsRead([])

      expect(response).toEqual({
        message: 'Marked 0 notifications as read',
        updated_count: 0,
        processed_ids: [],
      })
    })

    it('should handle empty notification list for bulk delete', async () => {
      const response = await client.deleteBulk([])

      expect(response).toEqual({
        message: 'Deleted 0 notifications',
        deleted_count: 0,
        processed_ids: [],
      })
    })
  })

  describe('Analytics and grouping', () => {
    it('should get notification groups with default parameters', async () => {
      const response = await client.getNotificationGroups()

      expect(response).toEqual({
        groups: [
          {
            type: 'TASK_CREATED',
            read: 5,
            unread: 3,
            total: 8,
          },
          {
            type: 'EVALUATION_COMPLETED',
            read: 10,
            unread: 2,
            total: 12,
          },
        ],
        total_types: 2,
      })
    })

    it('should get notification groups with custom parameters', async () => {
      const response = await client.getNotificationGroups('date', 25)

      expect(response).toEqual({
        groups: [
          {
            type: 'TASK_CREATED',
            read: 5,
            unread: 3,
            total: 8,
          },
          {
            type: 'EVALUATION_COMPLETED',
            read: 10,
            unread: 2,
            total: 12,
          },
        ],
        total_types: 2,
      })
    })

    it('should get notification summary with default days', async () => {
      const response = await client.getNotificationSummary()

      expect(response).toEqual({
        total_notifications: 20,
        unread_notifications: 5,
        read_notifications: 15,
        read_percentage: 75.0,
        recent_notifications_7_days: 8,
        most_common_type: 'TASK_CREATED',
        most_common_count: 12,
        summary_generated_at: '2024-01-01T12:00:00Z',
      })
    })

    it('should get notification summary with custom days', async () => {
      const response = await client.getNotificationSummary(30)

      expect(response).toEqual({
        total_notifications: 20,
        unread_notifications: 5,
        read_notifications: 15,
        read_percentage: 75.0,
        recent_notifications_7_days: 8,
        most_common_type: 'TASK_CREATED',
        most_common_count: 12,
        summary_generated_at: '2024-01-01T12:00:00Z',
      })
    })
  })

  describe('Error handling', () => {
    it('should handle API errors gracefully', async () => {
      // Create a client that will throw errors
      const errorClient = new NotificationsClient()

      // Mock a method to throw an error by overriding the handleRequest method
      jest
        .spyOn(errorClient as any, 'get')
        .mockRejectedValue(new Error('Network error'))

      await expect(errorClient.getNotifications()).rejects.toThrow(
        'Network error'
      )
    })

    it('should handle malformed API responses', async () => {
      const malformedClient = new NotificationsClient()

      // Mock to return malformed response
      jest.spyOn(malformedClient as any, 'get').mockResolvedValue(null)

      const notifications = await malformedClient.getNotifications()
      expect(notifications).toBeNull()
    })
  })

  describe('Method parameter validation', () => {
    it('should handle invalid notification ID in markAsRead', async () => {
      await expect(client.markAsRead('')).rejects.toThrow()
    })

    it('should validate groupBy parameter in getNotificationGroups', async () => {
      // Test with valid values
      await expect(client.getNotificationGroups('type')).resolves.toBeDefined()
      await expect(client.getNotificationGroups('date')).resolves.toBeDefined()
      await expect(
        client.getNotificationGroups('organization')
      ).resolves.toBeDefined()
    })

    it('should validate limit parameter in getNotificationGroups', async () => {
      await expect(
        client.getNotificationGroups('type', 100)
      ).resolves.toBeDefined()
      await expect(
        client.getNotificationGroups('type', 1)
      ).resolves.toBeDefined()
    })

    it('should validate days parameter in getNotificationSummary', async () => {
      await expect(client.getNotificationSummary(1)).resolves.toBeDefined()
      await expect(client.getNotificationSummary(365)).resolves.toBeDefined()
    })
  })
})

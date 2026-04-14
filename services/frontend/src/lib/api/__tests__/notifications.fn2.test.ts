/**
 * Additional function coverage for notifications.ts
 * Covers: createNotificationStream, sendTestDigest, deleteBulk,
 * getNotificationGroups, getNotificationSummary, createTestNotification,
 * generateTestNotifications
 */

import { NotificationsClient } from '../notifications'

// Mock the base class methods
jest.mock('../base', () => ({
  BaseApiClient: class {
    async get(url: string) {
      return { url }
    }
    async post(url: string, data?: any) {
      return { url, data }
    }
    async put(url: string, data?: any) {
      return { url, data }
    }
    async delete(url: string) {
      return { url }
    }
  },
}))

// Mock EventSource
const mockEventSource = jest.fn()
;(global as any).EventSource = mockEventSource

describe('NotificationsClient - additional function coverage', () => {
  let client: NotificationsClient

  beforeEach(() => {
    client = new NotificationsClient()
    mockEventSource.mockClear()
  })

  describe('createNotificationStream', () => {
    it('creates EventSource with correct URL', () => {
      mockEventSource.mockImplementation(function (this: any, url: string, opts?: any) {
        this.url = url
        this.withCredentials = opts?.withCredentials
      })
      const stream = client.createNotificationStream()
      expect(mockEventSource).toHaveBeenCalledWith('/api/notifications/stream', {
        withCredentials: true,
      })
    })
  })

  describe('sendTestDigest', () => {
    it('calls post with correct endpoint', async () => {
      const result: any = await client.sendTestDigest()
      expect(result.url).toBe('/notifications/digest/test')
    })
  })

  describe('deleteBulk', () => {
    it('calls post with notification IDs', async () => {
      const result: any = await client.deleteBulk(['id1', 'id2'])
      expect(result.url).toBe('/notifications/bulk/delete')
      expect(result.data).toEqual({ notification_ids: ['id1', 'id2'] })
    })
  })

  describe('getNotificationGroups', () => {
    it('calls get with default parameters', async () => {
      const result: any = await client.getNotificationGroups()
      expect(result.url).toContain('/notifications/groups')
      expect(result.url).toContain('group_by=type')
      expect(result.url).toContain('limit=50')
    })

    it('calls get with custom parameters', async () => {
      const result: any = await client.getNotificationGroups('date', 20)
      expect(result.url).toContain('group_by=date')
      expect(result.url).toContain('limit=20')
    })
  })

  describe('getNotificationSummary', () => {
    it('calls get with default days', async () => {
      const result: any = await client.getNotificationSummary()
      expect(result.url).toContain('/notifications/summary')
      expect(result.url).toContain('days=7')
    })

    it('calls get with custom days', async () => {
      const result: any = await client.getNotificationSummary(30)
      expect(result.url).toContain('days=30')
    })
  })

  describe('createTestNotification', () => {
    it('posts test notification request', async () => {
      const request = {
        type: 'test',
        title: 'Test',
        message: 'Test notification',
      }
      const result: any = await client.createTestNotification(request)
      expect(result.url).toBe('/notifications/test/create')
      expect(result.data).toEqual(request)
    })
  })

  describe('generateTestNotifications', () => {
    it('posts to generate-all endpoint', async () => {
      const result: any = await client.generateTestNotifications()
      expect(result.url).toBe('/notifications/test/generate-all')
    })
  })
})

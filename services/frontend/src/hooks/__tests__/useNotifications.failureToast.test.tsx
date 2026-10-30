/**
 * Live notifications of failed runs (generation / evaluation) toast as
 * errors; everything else keeps the success toast. Before, every
 * notification arriving on the stream toasted green, failures included.
 */
import { toast } from '@/components/shared/Toast'
import { useAuth } from '@/contexts/AuthContext'
import { act, renderHook, waitFor } from '@testing-library/react'
import React from 'react'
import {
  isFailureNotificationType,
  useNotifications,
} from '../useNotifications'

jest.mock('@/contexts/AuthContext', () => ({ useAuth: jest.fn() }))
jest.mock('@/components/shared/Toast', () => ({ toast: jest.fn() }))

class MockEventSource {
  readyState = 1
  onopen: ((event: Event) => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onerror: ((event: Event) => void) | null = null
  close() {
    this.readyState = 2
  }
  simulateMessage(data: unknown) {
    this.onmessage?.(
      new MessageEvent('message', { data: JSON.stringify(data) }),
    )
  }
}

const mockApiClient = {
  getNotifications: jest.fn().mockResolvedValue([]),
  getUnreadNotificationCount: jest.fn().mockResolvedValue({ count: 0 }),
  getNotificationPreferences: jest.fn().mockResolvedValue({}),
  createNotificationStream: jest.fn(() => new MockEventSource()),
}

const wrapper = ({ children }: { children: React.ReactNode }) => <>{children}</>

beforeEach(() => {
  jest.clearAllMocks()
  ;(useAuth as jest.Mock).mockReturnValue({
    user: { id: '1' },
    apiClient: mockApiClient,
  })
})

async function push(notification: Record<string, unknown>) {
  renderHook(() => useNotifications(), { wrapper })
  await waitFor(() =>
    expect(mockApiClient.createNotificationStream).toHaveBeenCalled(),
  )
  const source = mockApiClient.createNotificationStream.mock.results[0]
    .value as MockEventSource
  act(() => {
    source.simulateMessage({
      type: 'new_notification',
      notification: {
        id: 'n1',
        is_read: false,
        created_at: new Date().toISOString(),
        message: 'raw message',
        ...notification,
      },
    })
  })
}

describe('isFailureNotificationType', () => {
  it.each([
    ['llm_generation_failed', true],
    ['evaluation_failed', true],
    ['error_occurred', true],
    ['llm_generation_completed', false],
    ['evaluation_completed', false],
    [undefined, false],
  ])('%s -> %s', (type, expected) => {
    expect(isFailureNotificationType(type)).toBe(expected)
  })
})

describe('live notification toasts', () => {
  it('a failed generation toasts as an error', async () => {
    await push({ type: 'llm_generation_failed', title: 'Generation Failed' })
    expect(toast).toHaveBeenCalledWith(expect.any(String), 'error')
  })

  it('a failed evaluation toasts as an error', async () => {
    await push({ type: 'evaluation_failed', title: 'Evaluation Failed' })
    expect(toast).toHaveBeenCalledWith(expect.any(String), 'error')
  })

  it('a completed run keeps the success toast', async () => {
    await push({ type: 'evaluation_completed', title: 'Evaluation Completed' })
    expect(toast).toHaveBeenCalledWith(expect.any(String), 'success')
  })
})

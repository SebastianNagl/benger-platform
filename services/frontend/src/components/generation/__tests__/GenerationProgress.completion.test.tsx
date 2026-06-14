/**
 * @jest-environment jsdom
 *
 * Supplemental branch coverage for GenerationProgress. The base suite covers
 * progress/error messages, per-row actions, and the reconnect/poll fallback.
 * This file targets the still-uncovered handlers:
 *
 *   - the `complete` message summary toasts: all-failed (error),
 *     partial-success (warning), full-success (success)
 *   - the worker per-row `data.generation_id` publish → one-shot
 *     `fetchStatusOnce` refetch of /generation-status
 *   - the 4401 / 4403 WS-close auth-rejection path → redirectToLoginAsExpired,
 *     no reconnect
 */
import { apiClient } from '@/lib/api/client'
import '@testing-library/jest-dom'
import { render, screen, waitFor } from '@testing-library/react'
import React from 'react'
import { GenerationProgress } from '../GenerationProgress'

jest.mock('@/lib/api/client', () => ({
  apiClient: {
    get: jest.fn(),
    post: jest.fn(),
  },
  getApiUrl: jest.fn(() => 'http://localhost:8000'),
}))

const mockRedirect = jest.fn()
jest.mock('@/lib/auth/sessionExpired', () => ({
  redirectToLoginAsExpired: (...args: any[]) => mockRedirect(...args),
}))

const mockAddToast = jest.fn()
jest.mock('@/components/shared/Toast', () => ({
  useToast: jest.fn(() => ({
    addToast: mockAddToast,
    showToast: jest.fn(),
    removeToast: jest.fn(),
    toasts: [],
  })),
  ToastProvider: ({ children }: { children: React.ReactNode }) => (
    <>{children}</>
  ),
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: jest.fn(() => ({
    t: (key: string, params?: any) => {
      const translations: Record<string, string> = {
        'generation.overallProgress': 'Overall Progress',
        'generation.modelsCompleted': `${params?.completed || 0} of ${params?.total || 0} models completed`,
        'generation.error.allFailed': `All ${params?.failed} generation(s) failed`,
        'generation.success.allComplete': `${params?.count} generation(s) complete`,
        'generation.success.completeWithFailures': `${params?.completed} done, ${params?.failed} failed of ${params?.total}`,
        'generation.generatingResponses': 'Generating responses...',
        'generation.generationComplete': 'Generation complete',
        'generation.generationFailed': 'Generation failed',
        'generation.waitingToStart': 'Waiting to start...',
        'generation.connectionFallback': 'Using fallback connection method',
      }
      return translations[key] || key
    },
    changeLanguage: jest.fn(),
    currentLanguage: 'en',
    languages: ['en', 'de'],
  })),
}))

// WebSocket mock — same shape as the base GenerationProgress suite so the
// component's handlers are wired the same way.
class MockWebSocket {
  url: string
  onopen: ((event: Event) => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onerror: ((event: Event) => void) | null = null
  onclose: ((event: CloseEvent) => void) | null = null
  readyState: number = WebSocket.CONNECTING

  constructor(url: string) {
    this.url = url
    setTimeout(() => {
      this.readyState = WebSocket.OPEN
      if (this.onopen) this.onopen(new Event('open'))
    }, 0)
  }

  send() {}

  close() {
    this.readyState = WebSocket.CLOSED
    if (this.onclose) this.onclose(new CloseEvent('close'))
  }

  simulateMessage(data: any) {
    if (this.onmessage) {
      this.onmessage(
        new MessageEvent('message', { data: JSON.stringify(data) }),
      )
    }
  }

  // Fire a close with a specific code, bypassing the reconnect-tracking helper.
  simulateClose(code: number) {
    this.readyState = WebSocket.CLOSED
    if (this.onclose) {
      this.onclose(new CloseEvent('close', { code }))
    }
  }
}

let mockWebSocket: MockWebSocket | null = null
let trackWebSocketCreation = true

global.WebSocket = jest.fn((url: string) => {
  const ws = new MockWebSocket(url)
  if (trackWebSocketCreation) mockWebSocket = ws
  return ws as any
}) as any

describe('GenerationProgress — completion summaries & auth close', () => {
  const defaultProps = {
    projectId: 'project-1',
    generationIds: ['gen-1', 'gen-2'],
    models: ['gpt-4', 'claude-3'],
    onComplete: jest.fn(),
  }

  beforeEach(() => {
    jest.clearAllMocks()
    mockWebSocket = null
    trackWebSocketCreation = true
    ;(global.WebSocket as jest.Mock).mockImplementation((url: string) => {
      const ws = new MockWebSocket(url)
      if (trackWebSocketCreation) mockWebSocket = ws
      return ws as any
    })
  })

  afterEach(() => {
    trackWebSocketCreation = false
  })

  const renderAndOpen = async (props = defaultProps) => {
    const onComplete = jest.fn()
    render(<GenerationProgress {...props} onComplete={onComplete} />)
    await waitFor(() => {
      expect(mockWebSocket).not.toBeNull()
      expect(mockWebSocket!.readyState).toBe(WebSocket.OPEN)
    })
    return { onComplete }
  }

  it('shows a success toast when every generation completes', async () => {
    const onComplete = jest.fn()
    render(<GenerationProgress {...defaultProps} onComplete={onComplete} />)
    await waitFor(() => expect(mockWebSocket).not.toBeNull())

    mockWebSocket!.simulateMessage({
      type: 'complete',
      generations: [
        { id: 'gen-1', model_id: 'gpt-4', status: 'completed' },
        { id: 'gen-2', model_id: 'claude-3', status: 'completed' },
      ],
    })

    await waitFor(() =>
      expect(mockAddToast).toHaveBeenCalledWith(
        '2 generation(s) complete',
        'success',
      ),
    )
    expect(onComplete).toHaveBeenCalled()
  })

  it('shows a warning toast on partial success (some failed)', async () => {
    const onComplete = jest.fn()
    render(<GenerationProgress {...defaultProps} onComplete={onComplete} />)
    await waitFor(() => expect(mockWebSocket).not.toBeNull())

    mockWebSocket!.simulateMessage({
      type: 'complete',
      generations: [
        { id: 'gen-1', model_id: 'gpt-4', status: 'completed' },
        { id: 'gen-2', model_id: 'claude-3', status: 'failed' },
      ],
    })

    await waitFor(() =>
      expect(mockAddToast).toHaveBeenCalledWith(
        '1 done, 1 failed of 2',
        'warning',
      ),
    )
    expect(onComplete).toHaveBeenCalled()
  })

  it('shows an error toast when all generations fail', async () => {
    const onComplete = jest.fn()
    render(<GenerationProgress {...defaultProps} onComplete={onComplete} />)
    await waitFor(() => expect(mockWebSocket).not.toBeNull())

    mockWebSocket!.simulateMessage({
      type: 'complete',
      generations: [
        { id: 'gen-1', model_id: 'gpt-4', status: 'failed' },
        { id: 'gen-2', model_id: 'claude-3', status: 'failed' },
      ],
    })

    await waitFor(() =>
      expect(mockAddToast).toHaveBeenCalledWith(
        'All 2 generation(s) failed',
        'error',
      ),
    )
    expect(onComplete).toHaveBeenCalled()
  })

  it('does a one-shot status refetch on a per-row generation_id publish', async () => {
    ;(apiClient.get as jest.Mock).mockResolvedValue({
      generations: [
        { id: 'gen-1', model_id: 'gpt-4', status: 'completed' },
        { id: 'gen-2', model_id: 'claude-3', status: 'running', progress: 40 },
      ],
      is_running: true,
    })
    const onComplete = jest.fn()
    render(<GenerationProgress {...defaultProps} onComplete={onComplete} />)
    await waitFor(() => expect(mockWebSocket).not.toBeNull())

    // Worker per-row publish: single generation_id, no full list.
    mockWebSocket!.simulateMessage({
      type: 'progress',
      generation_id: 'gen-1',
    })

    // The component fetches /generation-status to rebuild state.
    await waitFor(() =>
      expect(apiClient.get).toHaveBeenCalledWith(
        '/projects/project-1/generation-status',
      ),
    )
    // The refetched state surfaces the completed row's "complete" label.
    await waitFor(() =>
      expect(screen.getByText('Generation complete')).toBeInTheDocument(),
    )
    // is_running was true → onComplete NOT fired from the refetch.
    expect(onComplete).not.toHaveBeenCalled()
  })

  it('fires onComplete from the one-shot refetch when is_running is false', async () => {
    ;(apiClient.get as jest.Mock).mockResolvedValue({
      generations: [
        { id: 'gen-1', model_id: 'gpt-4', status: 'completed' },
        { id: 'gen-2', model_id: 'claude-3', status: 'completed' },
      ],
      is_running: false,
    })
    const onComplete = jest.fn()
    render(<GenerationProgress {...defaultProps} onComplete={onComplete} />)
    await waitFor(() => expect(mockWebSocket).not.toBeNull())

    mockWebSocket!.simulateMessage({
      type: 'progress',
      generation_id: 'gen-2',
    })

    await waitFor(() => expect(onComplete).toHaveBeenCalled())
  })

  it('redirects to login (no reconnect) when the WS closes with 4401', async () => {
    render(<GenerationProgress {...defaultProps} />)
    await waitFor(() => expect(mockWebSocket).not.toBeNull())

    // Don't let leaked reconnect logic replace our reference.
    trackWebSocketCreation = false
    const wsCallsBefore = (global.WebSocket as jest.Mock).mock.calls.length
    mockWebSocket!.simulateClose(4401)

    await waitFor(() => expect(mockRedirect).toHaveBeenCalledTimes(1))
    // Auth-rejection path returns early — it must NOT schedule a reconnect.
    expect((global.WebSocket as jest.Mock).mock.calls.length).toBe(
      wsCallsBefore,
    )
  })

  it('also redirects for a 4403 (no project access) close code', async () => {
    render(<GenerationProgress {...defaultProps} />)
    await waitFor(() => expect(mockWebSocket).not.toBeNull())

    trackWebSocketCreation = false
    mockWebSocket!.simulateClose(4403)

    await waitFor(() => expect(mockRedirect).toHaveBeenCalledTimes(1))
  })
})

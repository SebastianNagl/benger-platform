/**
 * @jest-environment jsdom
 */

import { render } from '@testing-library/react'

import type { ServerDraftSyncState } from '@/hooks/useServerDraftSync'
import { useNotificationStore } from '@/stores/notificationStore'
import { ServerDraftSyncWarning } from '../ServerDraftSyncWarning'

const mockShowToast = jest.fn()
const mockRemoveToast = jest.fn()
jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({
    showToast: (...a: any[]) => mockShowToast(...a),
    removeToast: (...a: any[]) => mockRemoveToast(...a),
  }),
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    locale: 'de',
    t: (key: string, vars?: Record<string, any>) =>
      vars ? `${key} ${JSON.stringify(vars)}` : key,
  }),
}))

const setOnline = (value: boolean) =>
  Object.defineProperty(navigator, 'onLine', { value, configurable: true })

const healthy: ServerDraftSyncState = {
  status: 'saved',
  lastSavedAt: new Date(2026, 9, 7, 14, 5),
  failures: 0,
}
const failing = (failures: number, lastSavedAt: Date | null = null) =>
  ({ status: 'error', lastSavedAt, failures }) as ServerDraftSyncState

describe('ServerDraftSyncWarning', () => {
  beforeEach(() => {
    mockShowToast.mockReset().mockReturnValue('toast-1')
    mockRemoveToast.mockReset()
    useNotificationStore.setState({ toasts: [] })
  })
  afterEach(() => setOnline(true))

  it('renders nothing and raises no toast while the sync is healthy', () => {
    const { container } = render(<ServerDraftSyncWarning sync={healthy} />)
    expect(container).toBeEmptyDOMElement()
    expect(mockShowToast).not.toHaveBeenCalled()
  })

  it('stays quiet after a single failed attempt while online', () => {
    render(<ServerDraftSyncWarning sync={failing(1)} />)
    expect(mockShowToast).not.toHaveBeenCalled()
  })

  it('raises a persistent warning toast after a single failure when offline', () => {
    setOnline(false)
    render(<ServerDraftSyncWarning sync={failing(1)} />)
    expect(mockShowToast).toHaveBeenCalledTimes(1)
    const [message, type, duration] = mockShowToast.mock.calls[0]
    expect(message).toContain('annotation.serverDraft.offlineTitle.')
    expect(message).toContain('annotation.serverDraft.neverSaved')
    expect(type).toBe('warning')
    expect(duration).toBe(0)
  })

  it('names the last server save time and toasts only once while failing', () => {
    const { rerender } = render(
      <ServerDraftSyncWarning sync={failing(2, healthy.lastSavedAt)} />,
    )
    rerender(<ServerDraftSyncWarning sync={failing(3, healthy.lastSavedAt)} />)
    expect(mockShowToast).toHaveBeenCalledTimes(1)
    expect(mockShowToast.mock.calls[0][0]).toContain('"time":"14:05"')
  })

  it('removes the warning and confirms once a save succeeds again', () => {
    const { rerender } = render(<ServerDraftSyncWarning sync={failing(2)} />)
    rerender(<ServerDraftSyncWarning sync={healthy} />)
    expect(mockRemoveToast).toHaveBeenCalledWith('toast-1')
    expect(mockShowToast).toHaveBeenLastCalledWith(
      'annotation.serverDraft.restored',
      'success',
    )
  })

  it('removes the warning silently when the view stops syncing (idle)', () => {
    const { rerender } = render(<ServerDraftSyncWarning sync={failing(2)} />)
    rerender(
      <ServerDraftSyncWarning
        sync={{ status: 'idle', lastSavedAt: null, failures: 0 }}
      />,
    )
    expect(mockRemoveToast).toHaveBeenCalledWith('toast-1')
    expect(mockShowToast).toHaveBeenCalledTimes(1)
  })

  it('removes the warning on unmount', () => {
    const { unmount } = render(<ServerDraftSyncWarning sync={failing(2)} />)
    unmount()
    expect(mockRemoveToast).toHaveBeenCalledWith('toast-1')
  })

  it('drops a warning toast left over from before a reload', () => {
    useNotificationStore.setState({
      toasts: [
        {
          id: 'stale',
          message: 'annotation.serverDraft.offlineTitle. old text',
          type: 'warning',
          duration: 0,
        } as any,
        { id: 'other', message: 'Gespeichert', type: 'success' } as any,
      ],
    })
    render(<ServerDraftSyncWarning sync={healthy} />)
    expect(mockRemoveToast).toHaveBeenCalledWith('stale')
    expect(mockRemoveToast).not.toHaveBeenCalledWith('other')
  })

  it('uses host-provided title and body when given', () => {
    render(
      <ServerDraftSyncWarning
        sync={failing(2)}
        copy={{ title: 'Offline', body: 'Schließ den Tab nicht.' }}
      />,
    )
    const message = mockShowToast.mock.calls[0][0]
    expect(message).toMatch(/^Offline\. Schließ den Tab nicht\. /)
    expect(message).not.toContain('annotation.serverDraft.offlineTitle')
  })

  it('uses the host-provided recovery message when given', () => {
    const copy = { title: 'Offline', body: 'Body.', restored: 'Wieder da.' }
    const { rerender } = render(
      <ServerDraftSyncWarning sync={failing(2)} copy={copy} />,
    )
    rerender(<ServerDraftSyncWarning sync={healthy} copy={copy} />)
    expect(mockShowToast).toHaveBeenLastCalledWith('Wieder da.', 'success')
  })
})

/**
 * @jest-environment jsdom
 *
 * The app-wide report host: it records from the moment the app loads, so an
 * uncaught error and a failed API request of the first page load (while the
 * `bug_reports` flag is still loading) reach the dialog's preview; when the
 * flag reads off it stops recording and keeps nothing.
 */
import '@testing-library/jest-dom'
import { act, render, screen } from '@testing-library/react'

import { openBugReport } from '@/lib/bugReport/store'

let mockStatus: 'loading' | 'on' | 'off' = 'loading'
jest.mock('@/lib/featureFlags', () => ({
  useFeatureFlag: () => mockStatus === 'on',
  useFeatureFlagStatus: () => mockStatus,
  getFeatureFlagMap: () => ({ bug_reports: mockStatus === 'on' }),
}))
jest.mock('@/lib/extensions/active', () => ({
  getActiveExtensions: () => [],
}))
jest.mock('@/contexts/AuthContext', () => ({
  useOptionalAuth: () => ({ user: { id: 'u1' }, organizations: [] }),
}))
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({ t: (key: string) => key, locale: 'en' }),
}))
jest.mock('@/hooks/useResolvedUiMode', () => ({
  useResolvedUiMode: () => 'expert',
}))
jest.mock('next/navigation', () => ({
  usePathname: () => '/projects',
  useParams: () => ({}),
}))

const fetchMock = jest.fn(async () => ({
  ok: false,
  status: 404,
  headers: { get: () => null },
}))

// The page's fetch exists before the app's modules load.
;(window as any).fetch = fetchMock
// eslint-disable-next-line @typescript-eslint/no-require-imports
const { BugReportHost } = require('../BugReportHost')

function previewContext(): Record<string, any> {
  return JSON.parse(screen.getByTestId('bug-report-context').textContent!)
}

describe('BugReportHost', () => {
  it('keeps what failed while the flag was still loading', async () => {
    const { rerender, container } = render(<BugReportHost />)
    expect(container).toBeEmptyDOMElement()

    // First page load: the app's requests and a crash in a timer run
    // before the flag store has answered.
    await window.fetch('/api/notifications/unread-count')
    act(() => {
      window.dispatchEvent(
        new ErrorEvent('error', {
          error: new Error('boom on load'),
          message: 'boom on load',
        }),
      )
    })

    mockStatus = 'on'
    rerender(<BugReportHost />)
    act(() => openBugReport('footer'))

    const ctx = previewContext()
    expect(ctx.errors).toEqual([
      expect.objectContaining({
        message: 'boom on load',
        source: 'window.error',
      }),
    ])
    expect(ctx.failed_requests).toEqual([
      expect.objectContaining({
        method: 'GET',
        path: '/api/notifications/unread-count',
        status: 404,
      }),
    ])
  })

  it('stops recording and drops everything once the flag reads off', async () => {
    mockStatus = 'off'
    const { rerender, container } = render(<BugReportHost />)
    expect(container).toBeEmptyDOMElement()
    expect(window.fetch).toBe(fetchMock)

    await window.fetch('/api/projects/x')

    mockStatus = 'on'
    rerender(<BugReportHost />)
    act(() => openBugReport('footer'))

    const ctx = previewContext()
    expect(ctx.errors).toBeUndefined()
    expect(ctx.failed_requests).toBeUndefined()
  })
})

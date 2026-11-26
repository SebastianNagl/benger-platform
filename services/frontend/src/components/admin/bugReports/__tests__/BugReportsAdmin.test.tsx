/**
 * @jest-environment jsdom
 *
 * BugReportsAdmin (/admin/bug-reports): the list with its status filter, a
 * report opened by `?report=<id>` (text, issue link, screenshot behind the
 * superadmin route, technical context) and "Deliver again".
 */
import '@testing-library/jest-dom'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'

import type { BugReportDetail, BugReportSummary } from '@/lib/api/bugReports'

import { BugReportsAdmin } from '../BugReportsAdmin'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, vars?: Record<string, unknown>) =>
      vars ? `${key} ${JSON.stringify(vars)}` : key,
    locale: 'de',
  }),
}))
const mockAddToast = jest.fn()
jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({ addToast: mockAddToast }),
}))
jest.mock('@/components/shared/Breadcrumb', () => ({
  Breadcrumb: () => <nav data-testid="breadcrumb" />,
}))
let mockSearch = new URLSearchParams()
const mockReplace = jest.fn((url: string) => {
  mockSearch = new URLSearchParams(url.split('?')[1] ?? '')
})
jest.mock('next/navigation', () => ({
  useRouter: () => ({ replace: mockReplace }),
  useSearchParams: () => mockSearch,
}))

const mockList = jest.fn()
const mockGet = jest.fn()
const mockRedeliver = jest.fn()
jest.mock('@/lib/api/bugReports', () => ({
  BUG_REPORT_STATUSES: ['pending', 'delivered', 'failed', 'stored'],
  bugReportsAPI: {
    list: (...args: unknown[]) => mockList(...args),
    get: (...args: unknown[]) => mockGet(...args),
    redeliver: (...args: unknown[]) => mockRedeliver(...args),
    screenshotUrl: (id: string) => `/api/bug-reports/${id}/screenshot`,
  },
}))

const summary = (extra: Partial<BugReportSummary> = {}): BugReportSummary => ({
  id: 'r1',
  created_at: '2026-11-26T10:00:00Z',
  title: 'Save fails',
  status: 'delivered',
  reporter_id: 'u1',
  anonymous: false,
  page: '/projects/p-1',
  has_screenshot: true,
  delivery_attempts: 1,
  delivery_error: null,
  issue_url: 'https://github.example/o/r/issues/7',
  issue_number: 7,
  delivered_at: '2026-11-26T10:00:05Z',
  ...extra,
})

const detail = (extra: Partial<BugReportDetail> = {}): BugReportDetail => ({
  ...summary(),
  description: 'Nothing happens',
  expected: 'It saves',
  contact_email: null,
  context: { page: '/projects/p-1' },
  screenshot_content_type: 'image/png',
  screenshot_size: 10,
  ...extra,
})

beforeEach(() => {
  mockSearch = new URLSearchParams()
  mockReplace.mockClear()
  mockList.mockReset()
  mockGet.mockReset()
  mockRedeliver.mockReset()
  mockAddToast.mockReset()
})

describe('BugReportsAdmin', () => {
  it('lists reports and filters by status', async () => {
    mockList.mockResolvedValue({
      items: [
        summary(),
        summary({
          id: 'r2',
          title: 'Crash',
          status: 'failed',
          issue_url: null,
          issue_number: null,
        }),
      ],
      total: 2,
    })
    render(<BugReportsAdmin />)
    expect(await screen.findByText('Save fails')).toBeInTheDocument()
    expect(screen.getByText('Crash')).toBeInTheDocument()
    expect(screen.getByText('#7')).toHaveAttribute(
      'href',
      'https://github.example/o/r/issues/7',
    )
    expect(screen.getByTestId('bug-report-status-failed')).toBeInTheDocument()
    expect(mockList).toHaveBeenLastCalledWith({
      status: undefined,
      limit: 25,
      offset: 0,
    })

    await act(async () => {
      fireEvent.change(screen.getByTestId('bug-report-status-filter'), {
        target: { value: 'failed' },
      })
    })
    expect(mockList).toHaveBeenLastCalledWith({
      status: 'failed',
      limit: 25,
      offset: 0,
    })
  })

  it('shows an empty list and a load error', async () => {
    mockList.mockResolvedValueOnce({ items: [], total: 0 })
    const { unmount } = render(<BugReportsAdmin />)
    expect(await screen.findByText('bugReport.admin.empty')).toBeInTheDocument()
    unmount()
    mockList.mockRejectedValueOnce(new Error('403'))
    render(<BugReportsAdmin />)
    expect(
      await screen.findByText('bugReport.admin.loadFailed'),
    ).toBeInTheDocument()
  })

  it('opens a report from the URL and from the list', async () => {
    mockList.mockResolvedValue({ items: [summary()], total: 1 })
    mockGet.mockResolvedValue(detail())
    mockSearch = new URLSearchParams('report=r1')
    render(<BugReportsAdmin />)
    const card = await screen.findByTestId('bug-report-detail')
    expect(card).toHaveTextContent('Nothing happens')
    expect(card).toHaveTextContent('It saves')
    expect(card).toHaveTextContent('bugReport.admin.reporterUser {"id":"u1"}')
    expect(screen.getByTestId('bug-report-screenshot')).toHaveAttribute(
      'src',
      '/api/bug-reports/r1/screenshot',
    )
    // Delivered: nothing to deliver again.
    expect(screen.queryByTestId('bug-report-redeliver')).toBeNull()
    expect(mockGet).toHaveBeenCalledWith('r1')

    fireEvent.click(screen.getByTestId('bug-report-row'))
    expect(mockReplace).toHaveBeenCalledWith('/admin/bug-reports', {
      scroll: false,
    })
  })

  it('delivers a failed report again', async () => {
    mockList.mockResolvedValue({
      items: [summary({ status: 'failed' })],
      total: 1,
    })
    mockGet.mockResolvedValue(
      detail({
        status: 'failed',
        issue_url: null,
        issue_number: null,
        delivery_error: 'GitHub answered 401: Bad credentials',
        reporter_id: null,
        anonymous: true,
        contact_email: 'someone@example.org',
      }),
    )
    mockRedeliver.mockResolvedValue(
      detail({ status: 'pending', issue_url: null, delivery_error: null }),
    )
    mockSearch = new URLSearchParams('report=r1')
    render(<BugReportsAdmin />)
    const card = await screen.findByTestId('bug-report-detail')
    expect(card).toHaveTextContent('GitHub answered 401: Bad credentials')
    expect(card).toHaveTextContent('someone@example.org')
    expect(card).toHaveTextContent('bugReport.admin.reporterAnonymous')
    await act(async () => {
      fireEvent.click(screen.getByTestId('bug-report-redeliver'))
    })
    expect(mockRedeliver).toHaveBeenCalledWith('r1')
    await waitFor(() =>
      expect(mockAddToast).toHaveBeenCalledWith(
        'bugReport.admin.redeliverQueued',
        'success',
      ),
    )
    expect(screen.getByTestId('bug-report-status-pending')).toBeInTheDocument()
  })
})

/**
 * Problem reports admin API client (`/api/bug-reports`, superadmin only,
 * flag `bug_reports`). Sending a report is a plain multipart POST from the
 * report dialog (components/bugReport/BugReportDialog.tsx).
 */

import apiClient from '@/lib/api'

export type BugReportStatus = 'pending' | 'delivered' | 'failed' | 'stored'

export const BUG_REPORT_STATUSES: BugReportStatus[] = [
  'pending',
  'delivered',
  'failed',
  'stored',
]

export interface BugReportSummary {
  id: string
  created_at: string
  title: string
  status: BugReportStatus
  reporter_id: string | null
  anonymous: boolean
  page: string | null
  has_screenshot: boolean
  delivery_attempts: number
  delivery_error: string | null
  issue_url: string | null
  issue_number: number | null
  delivered_at: string | null
}

export interface BugReportDetail extends BugReportSummary {
  description: string
  expected: string | null
  contact_email: string | null
  context: Record<string, unknown>
  screenshot_content_type: string | null
  screenshot_size: number | null
}

export interface BugReportPage {
  items: BugReportSummary[]
  total: number
}

const BASE = '/bug-reports'

export const bugReportsAPI = {
  list: (
    params: { status?: BugReportStatus; limit?: number; offset?: number } = {},
  ): Promise<BugReportPage> => {
    const query = new URLSearchParams()
    if (params.status) query.set('status', params.status)
    query.set('limit', String(params.limit ?? 50))
    query.set('offset', String(params.offset ?? 0))
    return apiClient.get(`${BASE}?${query}`, { cache: 'no-store' })
  },
  get: (id: string): Promise<BugReportDetail> =>
    apiClient.get(`${BASE}/${encodeURIComponent(id)}`, { cache: 'no-store' }),
  redeliver: (id: string): Promise<BugReportDetail> =>
    apiClient.post(`${BASE}/${encodeURIComponent(id)}/redeliver`),
  /** Same-origin URL of the screenshot (the session cookie authorizes it). */
  screenshotUrl: (id: string): string =>
    `/api${BASE}/${encodeURIComponent(id)}/screenshot`,
}

export default bugReportsAPI

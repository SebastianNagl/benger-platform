'use client'

/**
 * Superadmin list of the problem reports sent with "Report a problem"
 * (`/admin/bug-reports`, flag `bug_reports`): newest first with a status
 * filter; one report opens below the list (`?report=<id>`, the link the
 * issue carries) with the text, the screenshot, the technical context and
 * the delivery state, and can be delivered again.
 */

import { ArrowPathIcon } from '@heroicons/react/24/outline'
import { useRouter, useSearchParams } from 'next/navigation'
import { useCallback, useEffect, useState } from 'react'

import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { Button } from '@/components/shared/Button'
import { Pagination } from '@/components/shared/Pagination'
import { ResponsiveContainer } from '@/components/shared/ResponsiveContainer'
import { useToast } from '@/components/shared/Toast'
import { useI18n } from '@/contexts/I18nContext'
import {
  BUG_REPORT_STATUSES,
  bugReportsAPI,
  type BugReportDetail,
  type BugReportStatus,
  type BugReportSummary,
} from '@/lib/api/bugReports'
import { intlTag } from '@/lib/i18n/locales'

const K = 'bugReport.admin'

const STATUS_STYLES: Record<BugReportStatus, string> = {
  pending:
    'bg-amber-50 text-amber-700 ring-amber-600/20 dark:bg-amber-400/10 dark:text-amber-300 dark:ring-amber-400/20',
  delivered:
    'bg-emerald-50 text-emerald-700 ring-emerald-600/20 dark:bg-emerald-400/10 dark:text-emerald-300 dark:ring-emerald-400/20',
  failed:
    'bg-red-50 text-red-700 ring-red-600/20 dark:bg-red-400/10 dark:text-red-300 dark:ring-red-400/20',
  stored:
    'bg-zinc-100 text-zinc-700 ring-zinc-600/20 dark:bg-zinc-400/10 dark:text-zinc-300 dark:ring-zinc-400/20',
}

function StatusBadge({ status }: { status: BugReportStatus }) {
  const { t } = useI18n()
  return (
    <span
      className={`inline-flex shrink-0 items-center rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${STATUS_STYLES[status]}`}
      data-testid={`bug-report-status-${status}`}
    >
      {t(`${K}.status.${status}`)}
    </span>
  )
}

function useFormatDate() {
  const { locale } = useI18n()
  return (value: string | null) =>
    value
      ? new Date(value).toLocaleString(intlTag(locale), {
          dateStyle: 'medium',
          timeStyle: 'short',
        })
      : ''
}

function ReportDetail({
  id,
  onChanged,
}: {
  id: string
  onChanged: () => void
}) {
  const { t } = useI18n()
  const { addToast } = useToast()
  const formatDate = useFormatDate()
  const [report, setReport] = useState<BugReportDetail | null>(null)
  const [failed, setFailed] = useState(false)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    // Keyed by id in the parent, so a new report starts from empty state.
    let alive = true
    bugReportsAPI
      .get(id)
      .then((data) => alive && setReport(data))
      .catch(() => alive && setFailed(true))
    return () => {
      alive = false
    }
  }, [id])

  if (failed)
    return (
      <p className="text-sm text-red-600 dark:text-red-400">
        {t(`${K}.loadFailed`)}
      </p>
    )
  if (!report)
    return (
      <p className="text-sm text-zinc-500 dark:text-zinc-400">
        {t('common.loading')}
      </p>
    )

  const redeliver = async () => {
    setBusy(true)
    try {
      setReport(await bugReportsAPI.redeliver(report.id))
      addToast(t(`${K}.redeliverQueued`), 'success')
      onChanged()
    } catch {
      addToast(t(`${K}.redeliverFailed`), 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <article
      className="space-y-4 rounded-lg border border-zinc-200 p-4 dark:border-zinc-700"
      data-testid="bug-report-detail"
    >
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-lg font-semibold break-words text-zinc-900 dark:text-white">
            {report.title}
          </h2>
          <p className="text-xs text-zinc-500 dark:text-zinc-400">
            {formatDate(report.created_at)} ·{' '}
            {report.reporter_id
              ? t(`${K}.reporterUser`, { id: report.reporter_id })
              : t(`${K}.reporterAnonymous`)}
          </p>
        </div>
        <StatusBadge status={report.status} />
      </header>

      <dl className="grid grid-cols-1 gap-x-6 gap-y-2 text-sm sm:grid-cols-[max-content_minmax(0,1fr)]">
        {report.issue_url && (
          <>
            <dt className="text-zinc-500 dark:text-zinc-400">
              {t(`${K}.issue`)}
            </dt>
            <dd>
              <a
                href={report.issue_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-emerald-600 hover:underline dark:text-emerald-400"
              >
                #{report.issue_number}
              </a>
            </dd>
          </>
        )}
        {report.contact_email && (
          <>
            <dt className="text-zinc-500 dark:text-zinc-400">
              {t(`${K}.contactEmail`)}
            </dt>
            <dd className="break-all">{report.contact_email}</dd>
          </>
        )}
        <dt className="text-zinc-500 dark:text-zinc-400">
          {t(`${K}.attempts`)}
        </dt>
        <dd>{report.delivery_attempts}</dd>
        {report.delivery_error && (
          <>
            <dt className="text-zinc-500 dark:text-zinc-400">
              {t(`${K}.deliveryError`)}
            </dt>
            <dd className="break-words text-red-600 dark:text-red-400">
              {report.delivery_error}
            </dd>
          </>
        )}
      </dl>

      <section>
        <h3 className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
          {t(`${K}.sections.description`)}
        </h3>
        <p className="mt-1 text-sm break-words whitespace-pre-wrap text-zinc-800 dark:text-zinc-200">
          {report.description}
        </p>
      </section>
      {report.expected && (
        <section>
          <h3 className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
            {t(`${K}.sections.expected`)}
          </h3>
          <p className="mt-1 text-sm break-words whitespace-pre-wrap text-zinc-800 dark:text-zinc-200">
            {report.expected}
          </p>
        </section>
      )}
      {report.has_screenshot && (
        <section>
          <h3 className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
            {t(`${K}.sections.screenshot`)}
          </h3>
          <a
            href={bugReportsAPI.screenshotUrl(report.id)}
            target="_blank"
            rel="noopener noreferrer"
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={bugReportsAPI.screenshotUrl(report.id)}
              alt={t('bugReport.screenshotPreview')}
              className="mt-2 max-h-96 max-w-full rounded border border-zinc-200 object-contain dark:border-zinc-700"
              data-testid="bug-report-screenshot"
            />
          </a>
        </section>
      )}
      <details className="text-sm">
        <summary className="cursor-pointer text-zinc-700 dark:text-zinc-300">
          {t(`${K}.context`)}
        </summary>
        <pre className="mt-2 max-h-96 overflow-auto rounded bg-zinc-100 p-2 text-xs break-all whitespace-pre-wrap text-zinc-700 dark:bg-zinc-900 dark:text-zinc-300">
          {JSON.stringify(report.context, null, 2)}
        </pre>
      </details>
      {report.status !== 'delivered' && (
        <div className="flex justify-end">
          <Button
            variant="outline"
            onClick={redeliver}
            disabled={busy}
            data-testid="bug-report-redeliver"
          >
            <ArrowPathIcon className="mr-1 h-4 w-4" />
            {t(`${K}.redeliver`)}
          </Button>
        </div>
      )}
    </article>
  )
}

export function BugReportsAdmin() {
  const { t } = useI18n()
  const router = useRouter()
  const searchParams = useSearchParams()
  const formatDate = useFormatDate()
  const selected = searchParams?.get('report') ?? null

  const [status, setStatus] = useState<BugReportStatus | ''>('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(25)
  const [data, setData] = useState<{
    items: BugReportSummary[]
    total: number
  } | null>(null)
  const [failed, setFailed] = useState(false)
  const [reload, setReload] = useState(0)

  const load = useCallback(() => setReload((n) => n + 1), [])

  useEffect(() => {
    let alive = true
    bugReportsAPI
      .list({
        status: status || undefined,
        limit: pageSize,
        offset: (page - 1) * pageSize,
      })
      .then((result) => {
        if (!alive) return
        setData(result)
        setFailed(false)
      })
      .catch(() => alive && setFailed(true))
    return () => {
      alive = false
    }
  }, [status, page, pageSize, reload])

  const select = (id: string | null) => {
    const params = new URLSearchParams(searchParams?.toString() ?? '')
    if (id) params.set('report', id)
    else params.delete('report')
    const query = params.toString()
    router.replace(`/admin/bug-reports${query ? `?${query}` : ''}`, {
      scroll: false,
    })
  }

  return (
    <ResponsiveContainer size="xl" className="pt-8 pb-10">
      <div className="mb-4">
        <Breadcrumb
          items={[
            { label: t('navigation.dashboard'), href: '/dashboard' },
            { label: t(`${K}.title`), href: '/admin/bug-reports' },
          ]}
        />
      </div>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-2xl font-bold text-zinc-900 dark:text-white">
            {t(`${K}.title`)}
          </h1>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
            {t(`${K}.description`)}
          </p>
        </div>
        <label className="flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
          {t(`${K}.filterStatus`)}
          <select
            value={status}
            onChange={(e) => {
              setStatus(e.target.value as BugReportStatus | '')
              setPage(1)
            }}
            className="ui-input w-auto"
            data-testid="bug-report-status-filter"
          >
            <option value="">{t(`${K}.allStatuses`)}</option>
            {BUG_REPORT_STATUSES.map((s) => (
              <option key={s} value={s}>
                {t(`${K}.status.${s}`)}
              </option>
            ))}
          </select>
        </label>
      </div>

      {failed && (
        <p className="text-sm text-red-600 dark:text-red-400">
          {t(`${K}.loadFailed`)}
        </p>
      )}
      {!failed && data && data.items.length === 0 && (
        <p className="text-sm text-zinc-500 dark:text-zinc-400">
          {t(`${K}.empty`)}
        </p>
      )}
      {!failed && data && data.items.length > 0 && (
        <ul
          className="divide-y divide-zinc-200 rounded-lg border border-zinc-200 dark:divide-zinc-700 dark:border-zinc-700"
          data-testid="bug-report-list"
        >
          {data.items.map((item) => (
            <li key={item.id}>
              <button
                type="button"
                onClick={() => select(item.id === selected ? null : item.id)}
                aria-expanded={item.id === selected}
                className={`flex w-full min-w-0 flex-col gap-1 px-4 py-3 text-left hover:bg-zinc-50 sm:flex-row sm:items-center sm:gap-4 dark:hover:bg-zinc-800/50 ${item.id === selected ? 'bg-zinc-50 dark:bg-zinc-800/50' : ''}`}
                data-testid="bug-report-row"
              >
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium text-zinc-900 dark:text-white">
                    {item.title}
                  </span>
                  <span className="block truncate text-xs text-zinc-500 dark:text-zinc-400">
                    {formatDate(item.created_at)}
                    {item.page ? ` · ${item.page}` : ''}
                    {item.has_screenshot
                      ? ` · ${t(`${K}.withScreenshot`)}`
                      : ''}
                  </span>
                </span>
                <span className="flex shrink-0 items-center gap-3">
                  {item.issue_url && (
                    <a
                      href={item.issue_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={(e) => e.stopPropagation()}
                      className="text-xs text-emerald-600 hover:underline dark:text-emerald-400"
                    >
                      #{item.issue_number}
                    </a>
                  )}
                  <StatusBadge status={item.status} />
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {data && data.total > pageSize && (
        <Pagination
          className="mt-4"
          currentPage={page}
          totalPages={Math.max(1, Math.ceil(data.total / pageSize))}
          totalItems={data.total}
          pageSize={pageSize}
          onPageChange={setPage}
          onPageSizeChange={(size) => {
            setPageSize(size)
            setPage(1)
          }}
        />
      )}

      {selected && (
        <div className="mt-6">
          <ReportDetail key={selected} id={selected} onChanged={load} />
        </div>
      )}
    </ResponsiveContainer>
  )
}

export default BugReportsAdmin

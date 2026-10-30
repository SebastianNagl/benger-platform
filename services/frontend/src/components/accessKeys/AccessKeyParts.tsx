'use client'

/**
 * Building blocks shared by the organization dialog, the profile section
 * and the superadmin page: status badge, scope chips, the revoke panel,
 * the show-once secret panel (copy, snippets, connection test) and the
 * usage panel.
 */

import { Button } from '@/components/shared/Button'
import { Textarea } from '@/components/shared/Textarea'
import { useI18n } from '@/contexts/I18nContext'
import { accessKeysAPI } from '@/lib/api/accessKeys'
import type {
  AccessKey,
  AccessKeyTestResult,
  AccessKeyUsagePoint,
  AccessKeyUsageSummary,
} from '@/lib/api/types'
import {
  CheckCircleIcon,
  ClipboardDocumentIcon,
  ExclamationTriangleIcon,
  XCircleIcon,
} from '@heroicons/react/24/outline'
import { type ReactNode, useEffect, useState } from 'react'

import {
  API_REFERENCE_PATHS,
  DAY_MS,
  apiErrorMessage,
  curlSnippet,
  describeTestFailure,
  pythonSnippet,
} from './accessKeyUtils'

const STATUS_STYLES: Record<AccessKey['status'], string> = {
  active:
    'bg-emerald-50 text-emerald-700 ring-emerald-600/20 dark:bg-emerald-950/40 dark:text-emerald-400',
  expired:
    'bg-amber-50 text-amber-700 ring-amber-600/20 dark:bg-amber-950/40 dark:text-amber-400',
  revoked:
    'bg-zinc-100 text-zinc-600 ring-zinc-500/20 dark:bg-zinc-800 dark:text-zinc-400',
}

export function AccessKeyStatusBadge({
  status,
}: {
  status: AccessKey['status']
}) {
  const { t } = useI18n()
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${STATUS_STYLES[status] ?? STATUS_STYLES.revoked}`}
      data-testid={`access-key-status-${status}`}
    >
      {t(`accessKeys.status.${status}`)}
    </span>
  )
}

export function ScopeChips({ scopes }: { scopes: string[] }) {
  return (
    <div className="flex flex-wrap gap-1">
      {scopes.map((scope) => (
        <span
          key={scope}
          className="rounded bg-zinc-100 px-1.5 py-0.5 font-mono text-[11px] text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300"
        >
          {scope}
        </span>
      ))}
    </div>
  )
}

interface RevokeKeyPanelProps {
  accessKey: AccessKey
  onConfirm: (reason: string) => Promise<void>
  onCancel: () => void
}

export function RevokeKeyPanel({
  accessKey,
  onConfirm,
  onCancel,
}: RevokeKeyPanelProps) {
  const { t } = useI18n()
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      await onConfirm(reason.trim())
    } catch (e) {
      setError(t('accessKeys.revoke.failed', { message: apiErrorMessage(e) }))
      setBusy(false)
    }
  }

  return (
    <div className="space-y-4" data-testid="access-key-revoke-panel">
      <h3 className="text-base font-semibold text-zinc-900 dark:text-white">
        {t('accessKeys.revoke.title')}
      </h3>
      <p className="text-sm text-zinc-600 dark:text-zinc-400">
        {t('accessKeys.revoke.description', {
          name: accessKey.name,
          prefix: accessKey.key_prefix,
        })}
      </p>
      <div>
        <label
          htmlFor="access-key-revoke-reason"
          className="block text-sm font-medium text-zinc-900 dark:text-zinc-100"
        >
          {t('accessKeys.revoke.reasonLabel')}
        </label>
        <Textarea
          id="access-key-revoke-reason"
          value={reason}
          maxLength={500}
          rows={2}
          onChange={(e) => setReason(e.target.value)}
          placeholder={t('accessKeys.revoke.reasonPlaceholder')}
          className="mt-1"
          data-testid="access-key-revoke-reason"
        />
      </div>
      {error && (
        <p className="text-sm text-red-600 dark:text-red-400" role="alert">
          {error}
        </p>
      )}
      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" onClick={onCancel}>
          {t('accessKeys.cancel')}
        </Button>
        <Button
          type="button"
          variant="filled"
          onClick={submit}
          disabled={busy}
          data-testid="access-key-revoke-confirm"
        >
          {busy
            ? t('accessKeys.revoke.revoking')
            : t('accessKeys.revoke.confirm')}
        </Button>
      </div>
    </div>
  )
}

function CodeBlock({ code, testId }: { code: string; testId: string }) {
  return (
    <pre
      className="overflow-x-auto rounded-md bg-zinc-900 p-3 font-mono text-xs leading-relaxed text-zinc-100"
      data-testid={testId}
    >
      {code}
    </pre>
  )
}

function publicBaseUrl(): string {
  if (typeof window === 'undefined') return ''
  return window.location.origin
}

interface SecretPanelProps {
  secret: string
  accessKey: AccessKey
  /** Extra content under the panel (renewal choices). */
  footer?: ReactNode
  onDone?: () => void
}

/** The full key, shown once, with copy, snippets and a connection test. */
export function AccessKeySecretPanel({
  secret,
  accessKey,
  footer,
  onDone,
}: SecretPanelProps) {
  const { t } = useI18n()
  const [copyState, setCopyState] = useState<'idle' | 'copied' | 'failed'>(
    'idle',
  )
  const [testing, setTesting] = useState(false)
  const [result, setResult] = useState<AccessKeyTestResult | null>(null)
  const baseUrl = publicBaseUrl()

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(secret)
      setCopyState('copied')
    } catch {
      setCopyState('failed')
    }
  }

  const test = async () => {
    setTesting(true)
    setResult(null)
    try {
      setResult(await accessKeysAPI.testConnection(secret))
    } finally {
      setTesting(false)
    }
  }

  return (
    <div className="space-y-4" data-testid="access-key-secret-panel">
      <h3 className="text-base font-semibold text-zinc-900 dark:text-white">
        {t('accessKeys.secret.title')}: {accessKey.name}
      </h3>
      <div
        className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-300"
        role="alert"
      >
        <ExclamationTriangleIcon className="mt-0.5 h-5 w-5 shrink-0" />
        <span>{t('accessKeys.secret.warning')}</span>
      </div>
      <div className="flex items-center gap-2">
        <code
          className="min-w-0 flex-1 overflow-x-auto rounded-md border border-zinc-300 bg-zinc-50 px-3 py-2 font-mono text-sm break-all text-zinc-900 select-all dark:border-zinc-600 dark:bg-zinc-900 dark:text-zinc-100"
          data-testid="access-key-secret"
        >
          {secret}
        </code>
        <Button
          type="button"
          variant="outline"
          onClick={copy}
          data-testid="access-key-copy"
        >
          <ClipboardDocumentIcon className="h-4 w-4" />
          {copyState === 'copied'
            ? t('accessKeys.secret.copied')
            : t('accessKeys.secret.copy')}
        </Button>
      </div>
      {copyState === 'failed' && (
        <p className="text-sm text-red-600 dark:text-red-400">
          {t('accessKeys.secret.copyFailed')}
        </p>
      )}

      <div>
        <Button
          type="button"
          variant="secondary"
          onClick={test}
          disabled={testing}
          data-testid="access-key-test"
        >
          {testing ? t('accessKeys.test.testing') : t('accessKeys.test.button')}
        </Button>
        {result && <TestResult result={result} />}
      </div>

      <div className="space-y-2">
        <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
          {t('accessKeys.secret.curlTitle')}
        </p>
        <CodeBlock
          code={curlSnippet(baseUrl, secret)}
          testId="access-key-curl"
        />
        <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
          {t('accessKeys.secret.pythonTitle')}
        </p>
        <CodeBlock
          code={pythonSnippet(baseUrl, secret)}
          testId="access-key-python"
        />
      </div>

      <div
        className="space-y-1 rounded-md border border-zinc-200 p-3 text-sm dark:border-zinc-700"
        data-testid="access-key-reference"
      >
        <p className="font-medium text-zinc-900 dark:text-zinc-100">
          {t('accessKeys.secret.referenceTitle')}
        </p>
        <p className="text-zinc-600 dark:text-zinc-400">
          {t('accessKeys.secret.referenceHint')}
        </p>
        <ul className="list-disc space-y-0.5 pl-5">
          <li>
            <a
              href={`${baseUrl}${API_REFERENCE_PATHS.full}`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-emerald-600 hover:underline dark:text-emerald-400"
              data-testid="access-key-reference-full"
            >
              {t('accessKeys.secret.referenceFull')}
            </a>{' '}
            <code className="font-mono text-xs text-zinc-500">
              {API_REFERENCE_PATHS.full}
            </code>
          </li>
          <li>
            <a
              href={`${baseUrl}${API_REFERENCE_PATHS.v1}`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-emerald-600 hover:underline dark:text-emerald-400"
              data-testid="access-key-reference-v1"
            >
              {t('accessKeys.secret.referenceV1')}
            </a>{' '}
            <code className="font-mono text-xs text-zinc-500">
              {API_REFERENCE_PATHS.v1}
            </code>
          </li>
        </ul>
      </div>

      {footer}
      {onDone && (
        <div className="flex justify-end">
          <Button
            type="button"
            variant="filled"
            onClick={onDone}
            data-testid="access-key-secret-done"
          >
            {t('accessKeys.secret.done')}
          </Button>
        </div>
      )}
    </div>
  )
}

function TestResult({ result }: { result: AccessKeyTestResult }) {
  const { t } = useI18n()
  if (result.ok) {
    const { principal, user } = result.me
    return (
      <div
        className="mt-2 rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300"
        data-testid="access-key-test-success"
      >
        <p className="flex items-center gap-2 font-medium">
          <CheckCircleIcon className="h-5 w-5" />
          {t('accessKeys.test.success')}
        </p>
        <ul className="mt-1 space-y-0.5 pl-7">
          {principal.organization && (
            <li>
              {t('accessKeys.test.organization', {
                name: principal.organization.name,
              })}
            </li>
          )}
          {principal.group && (
            <li>
              {t('accessKeys.test.group', { name: principal.group.name })}
            </li>
          )}
          {!principal.organization && user && (
            <li>
              {t('accessKeys.test.actsAs', {
                name: user.name || user.username || user.id,
              })}
            </li>
          )}
          <li>
            {t('accessKeys.test.scopes', {
              scopes: (principal.scopes ?? []).join(', '),
            })}
          </li>
        </ul>
      </div>
    )
  }
  const failure = describeTestFailure(result)
  return (
    <div
      className="mt-2 flex items-start gap-2 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950/40 dark:text-red-400"
      data-testid="access-key-test-error"
      role="alert"
    >
      <XCircleIcon className="mt-0.5 h-5 w-5 shrink-0" />
      <span>{t(failure.key, failure.vars)}</span>
    </div>
  )
}

/** The last `days` calendar days (UTC), oldest first, as YYYY-MM-DD. */
export function lastDays(days: number, now: number = Date.now()): string[] {
  const out: string[] = []
  for (let i = days - 1; i >= 0; i--) {
    out.push(new Date(now - i * DAY_MS).toISOString().slice(0, 10))
  }
  return out
}

interface UsagePanelProps {
  accessKey: AccessKey
  load: (granularity: 'day' | 'route') => Promise<AccessKeyUsageSummary>
  exportUrl?: string
  onClose: () => void
}

export function AccessKeyUsagePanel({
  accessKey,
  load,
  exportUrl,
  onClose,
}: UsagePanelProps) {
  const { t } = useI18n()
  const [days, setDays] = useState<AccessKeyUsageSummary | null>(null)
  const [routes, setRoutes] = useState<AccessKeyUsagePoint[]>([])
  const [error, setError] = useState(false)

  useEffect(() => {
    let cancelled = false
    Promise.all([load('day'), load('route')])
      .then(([byDay, byRoute]) => {
        if (cancelled) return
        setDays(byDay)
        setRoutes(byRoute?.items ?? [])
      })
      .catch(() => {
        if (!cancelled) setError(true)
      })
    return () => {
      cancelled = true
    }
    // The panel is mounted per key; reload only when the key changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessKey.id])

  const counts = new Map(
    (days?.items ?? []).map((item) => [item.day ?? '', item.requests]),
  )
  const series = lastDays(30).map((day) => ({
    day,
    requests: counts.get(day) ?? 0,
  }))
  const max = Math.max(1, ...series.map((s) => s.requests))

  return (
    <div className="space-y-4" data-testid="access-key-usage-panel">
      <h3 className="text-base font-semibold text-zinc-900 dark:text-white">
        {t('accessKeys.usage.title', { name: accessKey.name })}
      </h3>
      {error ? (
        <p className="text-sm text-red-600 dark:text-red-400" role="alert">
          {t('accessKeys.usage.loadFailed')}
        </p>
      ) : !days ? (
        <p className="text-sm text-zinc-500">{t('accessKeys.usage.loading')}</p>
      ) : days.total_requests === 0 ? (
        <p
          className="text-sm text-zinc-500"
          data-testid="access-key-usage-empty"
        >
          {t('accessKeys.usage.noUsage')}
        </p>
      ) : (
        <>
          <p className="text-sm text-zinc-700 dark:text-zinc-300">
            {t('accessKeys.usage.total', {
              requests: days.total_requests,
              errors: days.total_errors,
            })}
          </p>
          <div>
            <p className="mb-1 text-xs font-medium text-zinc-500 dark:text-zinc-400">
              {t('accessKeys.usage.perDay')}
            </p>
            <ul className="space-y-0.5" data-testid="access-key-usage-days">
              {series.map((point) => (
                <li
                  key={point.day}
                  className="flex items-center gap-2 text-[11px] text-zinc-500 dark:text-zinc-400"
                >
                  <span className="w-20 shrink-0 font-mono">{point.day}</span>
                  <span className="h-2 flex-1 rounded bg-zinc-100 dark:bg-zinc-800">
                    <span
                      className="block h-2 rounded bg-emerald-500"
                      style={{ width: `${(point.requests / max) * 100}%` }}
                    />
                  </span>
                  <span className="w-10 shrink-0 text-right tabular-nums">
                    {point.requests}
                  </span>
                </li>
              ))}
            </ul>
          </div>
          {routes.length > 0 && (
            <div>
              <p className="mb-1 text-xs font-medium text-zinc-500 dark:text-zinc-400">
                {t('accessKeys.usage.routes')}
              </p>
              <ul
                className="divide-y divide-zinc-100 text-xs dark:divide-zinc-800"
                data-testid="access-key-usage-routes"
              >
                {routes.map((r) => (
                  <li
                    key={`${r.method} ${r.route}`}
                    className="flex items-center justify-between gap-2 py-1"
                  >
                    <span className="min-w-0 truncate font-mono text-zinc-700 dark:text-zinc-300">
                      {r.method} {r.route}
                    </span>
                    <span className="shrink-0 text-zinc-500 tabular-nums">
                      {r.requests}
                      {r.errors > 0 && (
                        <span className="ml-2 text-red-600 dark:text-red-400">
                          {t('accessKeys.usage.errors', { errors: r.errors })}
                        </span>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
      <div className="flex items-center justify-between gap-2">
        {exportUrl ? (
          <a
            href={exportUrl}
            className="text-sm text-emerald-600 hover:underline dark:text-emerald-400"
            data-testid="access-key-usage-export"
          >
            {t('accessKeys.usage.export')}
          </a>
        ) : (
          <span />
        )}
        <Button type="button" variant="outline" onClick={onClose}>
          {t('accessKeys.close')}
        </Button>
      </div>
    </div>
  )
}

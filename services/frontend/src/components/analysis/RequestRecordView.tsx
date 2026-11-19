'use client'

/**
 * Request record view: exactly what the provider client sent for one
 * generation trial (messages, response format, parameters, every request
 * verbatim including a format retry) and its SHA-256, checked against the
 * record on the server (CORE 2.73). A mismatch means the stored hash does
 * not belong to the stored record.
 *
 * `RequestRecordView` renders a loaded view from its props;
 * `RequestRecordLoader` fetches one by trial id. The generation page and the
 * variant unit viewer both use them.
 */

import { useI18n } from '@/contexts/I18nContext'
import { MISSING } from '@/lib/analysis/results'
import {
  variantViewsAPI,
  type RequestRecord,
  type TrialRequestView,
} from '@/lib/api/variantViews'
import {
  CheckCircleIcon,
  ExclamationTriangleIcon,
  MinusCircleIcon,
} from '@heroicons/react/20/solid'
import { useEffect, useState } from 'react'
import { Notice, SystemName } from './viewParts'

function contentText(content: unknown): string {
  if (typeof content === 'string') return content
  return JSON.stringify(content, null, 2)
}

const PRE =
  'max-h-72 overflow-auto rounded-md border border-zinc-200 bg-zinc-50 p-3 font-mono text-xs whitespace-pre-wrap break-words text-zinc-800 dark:border-zinc-700 dark:bg-zinc-800/60 dark:text-zinc-200'
const LABEL = 'mb-1 text-xs font-medium text-zinc-600 dark:text-zinc-400'

/** Whether the stored hash belongs to the stored record. */
export function RequestHashStatus({ view }: { view: TrialRequestView }) {
  const { t } = useI18n()
  if (view.hash_matches === false && view.request_sha256) {
    return (
      <span
        className="inline-flex items-center gap-1 text-xs font-medium text-red-700 dark:text-red-400"
        data-testid="request-hash-mismatch"
      >
        <ExclamationTriangleIcon className="h-4 w-4" aria-hidden="true" />
        {t('generations.detail.request.hashMismatch')}
      </span>
    )
  }
  if (!view.request_record && view.request_sha256) {
    return (
      <span
        className="inline-flex items-center gap-1 text-xs font-medium text-zinc-500 dark:text-zinc-400"
        data-testid="request-hash-unverifiable"
      >
        <MinusCircleIcon className="h-4 w-4" aria-hidden="true" />
        {t('generations.detail.request.hashUnverifiable')}
      </span>
    )
  }
  if (!view.request_record) {
    return (
      <span className="inline-flex items-center gap-1 text-xs font-medium text-zinc-500 dark:text-zinc-400">
        <MinusCircleIcon className="h-4 w-4" aria-hidden="true" />
        {t('generations.detail.request.noRecord')}
      </span>
    )
  }
  if (view.hash_matches === undefined) return null
  if (view.hash_matches) {
    return (
      <span
        className="inline-flex items-center gap-1 text-xs font-medium text-emerald-700 dark:text-emerald-400"
        data-testid="request-hash-ok"
      >
        <CheckCircleIcon className="h-4 w-4" aria-hidden="true" />
        {t('generations.detail.request.hashOk')}
      </span>
    )
  }
  return (
    <span
      className="inline-flex items-center gap-1 text-xs font-medium text-red-700 dark:text-red-400"
      data-testid="request-hash-missing"
    >
      <ExclamationTriangleIcon className="h-4 w-4" aria-hidden="true" />
      {t('generations.detail.request.hashMissing')}
    </span>
  )
}

const isObject = (v: unknown): v is Record<string, unknown> =>
  !!v && typeof v === 'object' && !Array.isArray(v)
const text = (v: unknown) => (typeof v === 'string' ? v : null)

/**
 * The fields of a stored record in the shape the view renders, so no field
 * of a record of any other shape (e.g. a tampered one) can break it.
 */
function safeRecord(raw: unknown): RequestRecord | null {
  if (!isObject(raw)) return null
  return {
    provider: text(raw.provider),
    api: text(raw.api),
    capture: text(raw.capture),
    model: text(raw.model),
    messages: Array.isArray(raw.messages)
      ? raw.messages
          .filter(isObject)
          .map((m) => ({ role: text(m.role) ?? undefined, content: m.content }))
      : [],
    response_format: raw.response_format,
    parameters: isObject(raw.parameters) ? raw.parameters : null,
    requests: Array.isArray(raw.requests)
      ? (raw.requests as RequestRecord['requests'])
      : [],
  }
}

/** A request record with its hash check, from its data (no fetching). */
export function RequestRecordView({ view }: { view: TrialRequestView }) {
  const { t } = useI18n()
  const [showRaw, setShowRaw] = useState(false)
  const record = safeRecord(view.request_record)
  const requestCount = record?.requests?.length ?? 0
  return (
    <div className="min-w-0 space-y-3" data-testid="request-record-view">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-zinc-600 dark:text-zinc-400">
        <RequestHashStatus view={view} />
        {view.system_key &&
          view.system_key !== (record?.model ?? view.model_id) && (
            <SystemName systemKey={view.system_key} />
          )}
        {record?.model && (
          <span>
            {t('generations.detail.request.model')}:{' '}
            <span className="font-mono">{record.model}</span>
          </span>
        )}
        {view.structure_key && (
          <span>
            {t('generations.detail.request.structure')}:{' '}
            <span className="font-mono">{view.structure_key}</span>
          </span>
        )}
        {record?.provider && (
          <span>
            {t('generations.detail.request.provider')}:{' '}
            <span className="font-mono">
              {record.provider}
              {record.api ? ` · ${record.api}` : ''}
            </span>
          </span>
        )}
      </div>
      {(view.request_sha256 || view.computed_sha256) && (
        <dl className="grid gap-1 text-xs">
          <div className="flex min-w-0 flex-wrap gap-x-2">
            <dt className="text-zinc-500 dark:text-zinc-400">
              {t('generations.detail.request.storedHash')}
            </dt>
            <dd className="min-w-0 font-mono break-all text-zinc-800 dark:text-zinc-200">
              {view.request_sha256 ?? MISSING}
            </dd>
          </div>
          {view.computed_sha256 !== undefined && (
            <div className="flex min-w-0 flex-wrap gap-x-2">
              <dt className="text-zinc-500 dark:text-zinc-400">
                {t('generations.detail.request.computedHash')}
              </dt>
              <dd className="min-w-0 font-mono break-all text-zinc-800 dark:text-zinc-200">
                {view.computed_sha256 ?? MISSING}
              </dd>
            </div>
          )}
        </dl>
      )}
      {!record ? (
        <Notice>
          {view.request_sha256
            ? t('generations.detail.request.hashOnly')
            : t('generations.detail.request.none')}
        </Notice>
      ) : (
        <>
          {record.capture === 'worker_call' && (
            <Notice tone="warning">
              {t('generations.detail.request.workerCall')}
            </Notice>
          )}
          {(record.messages ?? []).map((message, i) => (
            <div key={i} className="min-w-0">
              <p className={LABEL}>
                {message.role === 'system'
                  ? t('generations.detail.request.roleSystem')
                  : message.role === 'assistant'
                    ? t('generations.detail.request.roleAssistant')
                    : t('generations.detail.request.roleUser')}
              </p>
              <pre className={PRE}>{contentText(message.content)}</pre>
            </div>
          ))}
          {record.response_format != null && (
            <div className="min-w-0">
              <p className={LABEL}>
                {t('generations.detail.request.responseFormat')}
              </p>
              <pre className={PRE}>
                {JSON.stringify(record.response_format, null, 2)}
              </pre>
            </div>
          )}
          {record.parameters && Object.keys(record.parameters).length > 0 && (
            <div className="min-w-0">
              <p className={LABEL}>
                {t('generations.detail.request.parameters')}
              </p>
              <pre className={PRE}>
                {JSON.stringify(record.parameters, null, 2)}
              </pre>
            </div>
          )}
          {view.retried && (
            <Notice tone="warning">
              <p className="font-medium">
                {t('generations.detail.request.retried', {
                  count: requestCount,
                })}
              </p>
              {view.first_response && (
                <p className="mt-1 break-words">
                  {t('generations.detail.request.firstAnswer')}:{' '}
                  {view.first_response}
                  {view.first_response_truncated ? '…' : ''}
                </p>
              )}
            </Notice>
          )}
          {requestCount > 0 && (
            <div>
              <button
                type="button"
                className="text-xs font-medium text-emerald-700 hover:underline dark:text-emerald-400"
                onClick={() => setShowRaw((v) => !v)}
                aria-expanded={showRaw}
              >
                {showRaw
                  ? t('generations.detail.request.hideRaw')
                  : t('generations.detail.request.showRaw', {
                      count: requestCount,
                    })}
              </button>
              {showRaw && (
                <pre className={`${PRE} mt-2`} data-testid="request-raw">
                  {JSON.stringify(record.requests ?? [], null, 2)}
                </pre>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}

/** One trial's request record and hash check, loaded by trial id. */
export function RequestRecordLoader({
  trialId,
  generationId,
}: {
  trialId: string
  /** The trial's generation run, when known (else the trial-only route). */
  generationId?: string | null
}) {
  const { t } = useI18n()
  const [view, setView] = useState<TrialRequestView | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setView(null)
    setError(null)
    variantViewsAPI
      .getTrialRequest(trialId, generationId)
      .then((v) => !cancelled && setView(v))
      .catch(
        (e: unknown) =>
          !cancelled &&
          setError(
            (e as Error)?.message || t('generations.detail.request.loadFailed'),
          ),
      )
    return () => {
      cancelled = true
    }
    // t is stable per locale; a locale switch need not reload the record.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [trialId, generationId])

  if (error) return <Notice tone="error">{error}</Notice>
  if (!view) {
    return (
      <p className="text-xs text-zinc-500 dark:text-zinc-400" role="status">
        {t('generations.detail.request.loading')}
      </p>
    )
  }
  return <RequestRecordView view={view} />
}

'use client'

/**
 * What an analysis run needs to be reproduced: the spec hash, the frame
 * hashes and size, the engine, spec and library versions, the lockfile
 * hash, the seed, the frame counts and the timings. Hashes are shown
 * shortened with a copy button for the full value.
 *
 * The layout shrinks to any width its container gives it (a phone, a side
 * panel, a narrow column of an overlay): a value keeps its place beside
 * its label while 8rem are left for it and moves under the label when
 * not, and values and list entries break instead of forcing one line, so
 * the component is never wider than its container.
 */

import { useI18n } from '@/contexts/I18nContext'
import { formatNumber, MISSING, shortHash } from '@/lib/analysis/results'
import type { AnalysisRun } from '@/lib/api/analysis'
import { intlTag } from '@/lib/i18n/locales'
import { CheckIcon, ClipboardIcon } from '@heroicons/react/24/outline'
import { useState, type ReactNode } from 'react'

export function CopyValueButton({
  value,
  label,
}: {
  value: string
  label: string
}) {
  const { t } = useI18n()
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    } catch {
      // Clipboard blocked: the value stays selectable in the title.
    }
  }
  return (
    <button
      type="button"
      onClick={copy}
      aria-label={copied ? t('analysis.provenance.copied') : label}
      title={copied ? t('analysis.provenance.copied') : label}
      className="rounded p-0.5 text-zinc-400 hover:text-zinc-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 dark:hover:text-zinc-200"
    >
      {copied ? (
        <CheckIcon className="h-3.5 w-3.5 text-emerald-600" />
      ) : (
        <ClipboardIcon className="h-3.5 w-3.5" />
      )}
    </button>
  )
}

function Hash({ value, label }: { value: string | null; label: string }) {
  const { t } = useI18n()
  if (!value) return <span className="text-zinc-400">{MISSING}</span>
  return (
    <span className="inline-flex max-w-full items-center gap-1">
      <code
        className="min-w-0 font-mono text-xs [overflow-wrap:anywhere] text-zinc-800 dark:text-zinc-200"
        title={value}
      >
        {shortHash(value)}
      </code>
      <CopyValueButton
        value={value}
        label={t('analysis.provenance.copy', { what: label })}
      />
    </span>
  )
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div
      className="flex min-w-0 flex-wrap items-baseline justify-between gap-x-3 gap-y-1 py-1.5"
      data-testid="run-provenance-row"
    >
      <dt className="min-w-0 text-xs [overflow-wrap:anywhere] text-zinc-500 dark:text-zinc-400">
        {label}
      </dt>
      <dd className="max-w-full min-w-0 flex-[1_1_8rem] text-right text-sm [overflow-wrap:anywhere] text-zinc-800 dark:text-zinc-200">
        {children}
      </dd>
    </div>
  )
}

function KeyValues({
  values,
  format,
  formatKey = (key) => key,
}: {
  values: Record<string, string | number> | null
  format: (value: string | number) => string
  formatKey?: (key: string) => string
}) {
  const entries = values ? Object.entries(values) : []
  if (entries.length === 0)
    return <span className="text-zinc-400">{MISSING}</span>
  return (
    <span className="flex min-w-0 flex-wrap justify-end gap-1.5">
      {entries.map(([key, value]) => (
        <span
          key={key}
          className="max-w-full rounded bg-zinc-100 px-1.5 py-0.5 font-mono text-[11px] [overflow-wrap:anywhere] text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300"
          data-testid="run-provenance-entry"
        >
          {formatKey(key)} {format(value)}
        </span>
      ))}
    </span>
  )
}

export function RunProvenance({ run }: { run: AnalysisRun }) {
  const { t, locale } = useI18n()
  const bytes =
    typeof run.frame_bytes === 'number'
      ? new Intl.NumberFormat(intlTag(locale), {
          style: 'unit',
          unit: run.frame_bytes >= 1e6 ? 'megabyte' : 'kilobyte',
          maximumFractionDigits: 1,
        }).format(run.frame_bytes / (run.frame_bytes >= 1e6 ? 1e6 : 1e3))
      : MISSING
  const count = (v: string | number) =>
    typeof v === 'number'
      ? new Intl.NumberFormat(intlTag(locale)).format(v)
      : String(v)
  const seconds = (v: string | number) =>
    typeof v === 'number' ? `${formatNumber(v, locale, 3)} s` : String(v)

  return (
    <div
      className="grid min-w-0 grid-cols-1 gap-x-10 md:grid-cols-2"
      data-testid="run-provenance"
    >
      <dl className="min-w-0 divide-y divide-zinc-100 dark:divide-zinc-800">
        <Row label={t('analysis.provenance.specHash')}>
          <Hash
            value={run.spec_hash}
            label={t('analysis.provenance.specHash')}
          />
        </Row>
        <Row label={t('analysis.provenance.frameHash')}>
          <Hash
            value={run.frame_hash}
            label={t('analysis.provenance.frameHash')}
          />
        </Row>
        <Row label={t('analysis.provenance.frameSha256')}>
          <Hash
            value={run.frame_sha256}
            label={t('analysis.provenance.frameSha256')}
          />
        </Row>
        <Row label={t('analysis.provenance.lockfile')}>
          <Hash
            value={run.lockfile_sha256}
            label={t('analysis.provenance.lockfile')}
          />
        </Row>
        <Row label={t('analysis.provenance.frameSize')}>
          {run.frame_rows === null || run.frame_rows === undefined
            ? MISSING
            : t('analysis.provenance.frameRows', {
                rows: count(run.frame_rows),
                size: bytes,
              })}
        </Row>
      </dl>
      <dl className="min-w-0 divide-y divide-zinc-100 dark:divide-zinc-800">
        <Row label={t('analysis.provenance.engine')}>
          <span className="font-mono text-xs">
            {t('analysis.provenance.engineVersions', {
              engine: run.engine_version,
              spec: run.spec_version,
            })}
          </span>
        </Row>
        <Row label={t('analysis.provenance.libraries')}>
          <KeyValues values={run.library_versions} format={String} />
        </Row>
        <Row label={t('analysis.provenance.seed')}>
          <span className="font-mono text-xs">
            {run.seed === null || run.seed === undefined
              ? t('analysis.provenance.noSeed')
              : String(run.seed)}
          </span>
        </Row>
        <Row label={t('analysis.provenance.counts')}>
          <KeyValues values={run.frame_counts} format={count} />
        </Row>
        <Row label={t('analysis.provenance.timings')}>
          <KeyValues
            values={run.timings}
            format={seconds}
            formatKey={(key) => key.replace(/_s$/, '')}
          />
        </Row>
      </dl>
    </div>
  )
}

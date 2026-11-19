'use client'

import { formatDate } from '@/lib/reports/format'
import {
  ArrowDownTrayIcon,
  CheckIcon,
  ClipboardIcon,
  PrinterIcon,
} from '@heroicons/react/24/outline'
import { useEffect, useRef, useState } from 'react'
import type { TranslateFn } from './chartTheme'
import { ReportSection } from './ReportSection'

interface CitationBlockProps {
  reportId: string
  title: string
  /** Absolute URL of the report page. */
  url: string
  publishedAt?: string | null
  snapshotSha256?: string | null
  locale: string
  t: TranslateFn
}

/** BibTeX entry key: "benger-report-<year>-<first 8 id chars>". */
function bibKey(reportId: string, year: string): string {
  return `benger-report-${year || 'nd'}-${reportId.replace(/[^a-z0-9]/gi, '').slice(0, 8)}`
}

/** Braces and backslashes would end or break a BibTeX field. */
function bibEscape(value: string): string {
  return value.replace(/[\\{}]/g, '')
}

export function buildBibtex({
  reportId,
  title,
  url,
  publishedAt,
  snapshotSha256,
}: Omit<CitationBlockProps, 'locale' | 't'>): string {
  const date = publishedAt ? new Date(publishedAt) : null
  const valid = date && !Number.isNaN(date.getTime())
  const year = valid ? String(date.getUTCFullYear()) : ''
  const lines = [
    `@misc{${bibKey(reportId, year)},`,
    `  title        = {${bibEscape(title)}},`,
    `  howpublished = {\\url{${url}}},`,
  ]
  if (valid) {
    lines.push(`  year         = {${year}},`)
    lines.push(`  date         = {${date.toISOString().slice(0, 10)}},`)
  }
  if (snapshotSha256) {
    lines.push(
      `  note         = {BenGER project report, snapshot SHA-256 ${snapshotSha256}},`,
    )
  } else {
    lines.push('  note         = {BenGER project report},')
  }
  lines.push('}')
  return lines.join('\n')
}

function CopyButton({
  value,
  label,
  copiedLabel,
  testId,
}: {
  value: string
  label: string
  copiedLabel: string
  testId: string
}) {
  const [copied, setCopied] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current)
    },
    [],
  )
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(true)
      if (timer.current) clearTimeout(timer.current)
      timer.current = setTimeout(() => setCopied(false), 1500)
    } catch {
      // Clipboard blocked: the text stays selectable on the page.
    }
  }
  return (
    <button
      type="button"
      onClick={copy}
      data-testid={testId}
      className={BUTTON}
    >
      {copied ? (
        <CheckIcon className="mr-1.5 h-4 w-4 text-emerald-600" />
      ) : (
        <ClipboardIcon className="mr-1.5 h-4 w-4" />
      )}
      {copied ? copiedLabel : label}
    </button>
  )
}

const BUTTON =
  'inline-flex h-8 items-center rounded-full border border-zinc-300 px-3 text-sm font-medium text-zinc-700 transition hover:bg-zinc-50 dark:border-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-800'

/** How to cite the report, with its data link and a print button. */
export function CitationBlock(props: CitationBlockProps) {
  const { reportId, title, url, publishedAt, snapshotSha256, locale, t } = props
  const date = formatDate(publishedAt, locale)
  const citation = t(
    snapshotSha256
      ? 'reports.view.records.citationText'
      : 'reports.view.records.citationTextNoHash',
    {
      title,
      date: date || t('reports.view.records.undated'),
      url,
      hash: snapshotSha256 ?? '',
    },
  )
  const bibtex = buildBibtex({
    reportId,
    title,
    url,
    publishedAt,
    snapshotSha256,
  })
  const dataHref = `/api/reports/${encodeURIComponent(reportId)}/data`

  return (
    <ReportSection title={t('reports.view.records.citeTitle')} id="cite">
      <p
        className="rounded-md bg-zinc-50 p-3 text-sm leading-6 break-words text-zinc-800 dark:bg-zinc-800/60 dark:text-zinc-200"
        data-testid="citation-text"
      >
        {citation}
      </p>
      <details className="mt-3 print:hidden">
        <summary className="cursor-pointer text-sm text-emerald-700 hover:underline dark:text-emerald-400">
          {t('reports.view.records.bibtex')}
        </summary>
        <pre
          className="mt-2 overflow-x-auto rounded-md bg-zinc-50 p-3 font-mono text-xs text-zinc-800 dark:bg-zinc-800/60 dark:text-zinc-200"
          data-testid="citation-bibtex"
        >
          {bibtex}
        </pre>
      </details>
      <div className="mt-4 flex flex-wrap gap-2 print:hidden">
        <CopyButton
          value={citation}
          label={t('reports.view.records.copyCitation')}
          copiedLabel={t('reports.view.records.copied')}
          testId="copy-citation"
        />
        <CopyButton
          value={bibtex}
          label={t('reports.view.records.copyBibtex')}
          copiedLabel={t('reports.view.records.copied')}
          testId="copy-bibtex"
        />
        <a
          href={dataHref}
          target="_blank"
          rel="noopener noreferrer"
          className={BUTTON}
          data-testid="report-data-link"
        >
          <ArrowDownTrayIcon className="mr-1.5 h-4 w-4" />
          {t('reports.view.records.dataJson')}
        </a>
        <button
          type="button"
          onClick={() => window.print()}
          className={BUTTON}
          data-testid="print-report"
        >
          <PrinterIcon className="mr-1.5 h-4 w-4" />
          {t('reports.view.records.print')}
        </button>
      </div>
    </ReportSection>
  )
}

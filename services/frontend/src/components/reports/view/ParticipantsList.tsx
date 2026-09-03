import { formatCount } from '@/lib/reports/format'
import type { ReportSnapshot } from '@/types/report'
import type { TranslateFn } from './chartTheme'

interface ParticipantsListProps {
  participants: ReportSnapshot['participants']
  locale: string
  t: TranslateFn
}

/** Collapsible pseudonym list with contribution counts. */
export function ParticipantsList({ participants, locale, t }: ParticipantsListProps) {
  if (participants.length === 0) return null
  return (
    <details
      className="group rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900"
      data-testid="participants-list"
    >
      <summary className="cursor-pointer select-none text-base font-semibold text-zinc-900 dark:text-white">
        {t('reports.view.participants', 'Teilnehmende')}{' '}
        <span className="text-sm font-normal text-zinc-500 dark:text-zinc-400">
          ({formatCount(participants.length, locale)})
        </span>
      </summary>
      <ul className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {participants.map((p) => (
          <li
            key={p.id}
            className="flex items-center justify-between rounded-md border border-zinc-100 px-3 py-2 text-sm dark:border-zinc-800"
          >
            <span className="font-medium text-zinc-800 dark:text-zinc-200">{p.label}</span>
            <span className="text-zinc-500 dark:text-zinc-400">
              {t('reports.view.submissions', '{count} Abgaben', { count: formatCount(p.annotation_count, locale) })}
            </span>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-xs text-zinc-500 dark:text-zinc-400">
        {t('reports.view.pseudonymHint', 'Teilnehmende werden ausschließlich unter Pseudonym angezeigt.')}
      </p>
    </details>
  )
}

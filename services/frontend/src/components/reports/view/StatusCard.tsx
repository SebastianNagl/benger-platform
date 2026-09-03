import Link from 'next/link'
import { Card } from '@/components/shared/Card'
import type { TranslateFn } from './chartTheme'

export type StatusKind = 'loading' | 'error' | 'forbidden'

interface StatusCardProps {
  kind: StatusKind
  /** Error detail from the API (error kind only). */
  message?: string | null
  onRetry?: () => void
  /** Where the login link points (forbidden kind). */
  loginHref?: string
  t: TranslateFn
}

/**
 * In-layout status card for the report reader: loading, failure and the
 * anonymous-visitor "not public" case. Never takes over the screen; the
 * breadcrumb and title stay above it.
 */
export function StatusCard({ kind, message, onRetry, loginHref = '/login', t }: StatusCardProps) {
  const backLink = (
    <Link
      href="/reports"
      className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm font-medium text-zinc-700 transition hover:bg-zinc-50 dark:border-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-800"
    >
      {t('reports.view.backToReports', 'Zurück zu den Berichten')}
    </Link>
  )

  if (kind === 'loading') {
    return (
      <Card className="p-8 text-center" data-testid="report-loading" aria-busy="true">
        <div className="mx-auto mb-3 h-6 w-6 animate-spin rounded-full border-2 border-zinc-300 border-t-emerald-600 dark:border-zinc-700 dark:border-t-emerald-400" />
        <p className="text-sm text-zinc-500 dark:text-zinc-400">
          {t('reports.view.loading', 'Bericht wird geladen …')}
        </p>
      </Card>
    )
  }

  if (kind === 'forbidden') {
    return (
      <Card className="p-8" data-testid="report-forbidden">
        <h2 className="text-lg font-semibold text-zinc-900 dark:text-white">
          {t('reports.view.notPublicTitle', 'Dieser Bericht ist nicht öffentlich.')}
        </h2>
        <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-300">
          {t(
            'reports.view.notPublicText',
            'Melden Sie sich an, um ihn zu sehen. Veröffentlichte Berichte sind für Mitglieder der beteiligten Organisationen sichtbar.',
          )}
        </p>
        <div className="mt-5 flex flex-wrap gap-3">
          <Link
            href={loginHref}
            className="rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white transition hover:bg-emerald-700 dark:bg-emerald-500 dark:text-zinc-950 dark:hover:bg-emerald-400"
          >
            {t('reports.view.signIn', 'Anmelden')}
          </Link>
          {backLink}
        </div>
      </Card>
    )
  }

  return (
    <Card className="border-red-200 p-8 dark:border-red-900/60" data-testid="report-error" role="alert">
      <h2 className="text-lg font-semibold text-zinc-900 dark:text-white">
        {t('reports.view.loadFailedTitle', 'Der Bericht konnte nicht geladen werden.')}
      </h2>
      <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-300">
        {message || t('reports.view.loadFailedText', 'Bitte versuchen Sie es in einem Moment erneut.')}
      </p>
      <div className="mt-5 flex flex-wrap gap-3">
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white transition hover:bg-emerald-700 dark:bg-emerald-500 dark:text-zinc-950 dark:hover:bg-emerald-400"
          >
            {t('reports.view.reload', 'Erneut laden')}
          </button>
        )}
        {backLink}
      </div>
    </Card>
  )
}

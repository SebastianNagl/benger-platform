'use client'

import { VertretbarMarkIcon } from '@/components/brand/VertretbarMark'
import { BugReportDialog } from '@/components/bugReport/BugReportDialog'
import { useI18n } from '@/contexts/I18nContext'
import { recordError } from '@/lib/bugReport/recorder'
import { getFeatureFlag } from '@/lib/featureFlags'
import { BUG_REPORTS } from '@/lib/featureFlags/platformFlags'
import { isStudentLockedHost } from '@/lib/utils/subdomain'
import { Component, ReactNode, useState, useSyncExternalStore } from 'react'

const subscribeNoop = () => () => {}

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
  error?: Error
}

/**
 * Last-resort crash card. This boundary wraps the ENTIRE provider tree
 * (app/providers.tsx), so when it trips there is no I18nProvider mounted —
 * useI18n falls back to a t() that echoes the inline German defaults below.
 * Every key therefore MUST carry its default, or the card renders raw
 * `errors.global.*` keys. Host branding uses the pure isStudentLockedHost()
 * util (no context) so vertretbar.net keeps its wordmark even on a crash.
 */
function GlobalErrorContent({ error }: { error?: Error }) {
  const { t } = useI18n()
  // The app's dialog host is gone with the crashed tree: this card renders
  // its own "Report a problem" dialog (flag bug_reports).
  const [reporting, setReporting] = useState(false)
  // Resolved after mount (same pattern as the auth pages) so the SSR/first
  // paint is deterministic and never hydration-mismatches.
  // Host resolved on the client only: the server snapshot stays neutral so
  // the first paint never hydration-mismatches (no state, no effect needed).
  const isVtr = useSyncExternalStore(
    subscribeNoop,
    isStudentLockedHost,
    () => false,
  )

  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-50 dark:bg-zinc-900">
      <div className="w-full max-w-md rounded-lg border border-zinc-200 bg-white p-6 shadow-lg dark:border-zinc-700 dark:bg-zinc-800">
        {isVtr && (
          <div
            className="mb-4 flex items-center gap-2"
            data-testid="error-brand-vertretbar"
          >
            <VertretbarMarkIcon className="h-6 w-6 text-emerald-500" />
            <span className="text-lg font-semibold text-zinc-900 dark:text-white">
              Vertretbar
            </span>
          </div>
        )}
        <h1 className="mb-4 text-2xl font-bold text-zinc-900 dark:text-white">
          {t('errors.global.applicationError')}
        </h1>
        <p className="mb-4 text-zinc-600 dark:text-zinc-300">
          {error?.message || t('errors.global.unexpectedError')}
        </p>
        <details className="mb-4">
          <summary className="cursor-pointer text-sm text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300">
            {t('errors.global.errorDetails')}
          </summary>
          <pre className="mt-2 overflow-auto rounded bg-zinc-100 p-3 text-xs text-zinc-600 dark:bg-zinc-900 dark:text-zinc-400">
            {error?.stack}
          </pre>
        </details>
        <button
          onClick={() => window.location.reload()}
          className="h-8 w-full rounded-full bg-zinc-900 px-4 text-sm font-medium text-white transition-colors hover:bg-zinc-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-2 dark:bg-emerald-500 dark:hover:bg-emerald-400 dark:focus-visible:ring-offset-zinc-900"
        >
          {t('errors.global.reloadPage')}
        </button>
        {/* No auth here, so the flag is read from the store as it was
            loaded before the crash. */}
        {getFeatureFlag(BUG_REPORTS) && (
          <button
            type="button"
            onClick={() => setReporting(true)}
            data-testid="error-report-problem"
            className="mt-3 h-8 w-full rounded-full px-4 text-sm font-medium text-zinc-700 ring-1 ring-zinc-900/10 transition ring-inset hover:bg-zinc-900/2.5 dark:text-zinc-300 dark:ring-white/10 dark:hover:bg-white/5"
          >
            {t('bugReport.entry')}
          </button>
        )}
      </div>
      {reporting && (
        <BugReportDialog
          open
          onClose={() => setReporting(false)}
          source="crash"
        />
      )}
    </div>
  )
}

export class GlobalErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('Module initialization error:', error, errorInfo)
    recordError(error, 'crash')

    // Log webpack-specific errors with more detail
    if (error.message?.includes('Cannot read properties of undefined')) {
      console.error('Webpack module loading error detected:', {
        message: error.message,
        stack: error.stack,
        componentStack: errorInfo.componentStack,
      })
    }
  }

  render() {
    if (this.state.hasError) {
      return <GlobalErrorContent error={this.state.error} />
    }

    return this.props.children
  }
}

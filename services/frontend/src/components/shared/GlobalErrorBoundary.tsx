'use client'

import { VertretbarMarkIcon } from '@/components/brand/VertretbarMark'
import { useI18n } from '@/contexts/I18nContext'
import { isStudentLockedHost } from '@/lib/utils/subdomain'
import { Component, ReactNode, useEffect, useState } from 'react'

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
function GlobalErrorContent({
  error,
}: {
  error?: Error
}) {
  const { t } = useI18n()
  // Resolved after mount (same pattern as the auth pages) so the SSR/first
  // paint is deterministic and never hydration-mismatches.
  const [isVtr, setIsVtr] = useState(false)
  useEffect(() => {
    setIsVtr(isStudentLockedHost())
  }, [])

  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-50 dark:bg-zinc-900">
      <div className="w-full max-w-md rounded-lg border border-zinc-200 bg-white p-6 shadow-lg dark:border-zinc-700 dark:bg-zinc-800">
        {isVtr && (
          <div className="mb-4 flex items-center gap-2" data-testid="error-brand-vertretbar">
            <VertretbarMarkIcon className="h-6 w-6 text-emerald-500" />
            <span className="text-lg font-semibold text-zinc-900 dark:text-white">
              Vertretbar
            </span>
          </div>
        )}
        <h1 className="mb-4 text-2xl font-bold text-zinc-900 dark:text-white">
          {t('errors.global.applicationError', 'Anwendungsfehler')}
        </h1>
        <p className="mb-4 text-zinc-600 dark:text-zinc-300">
          {error?.message ||
            t('errors.global.unexpectedError', 'Ein unerwarteter Fehler ist aufgetreten')}
        </p>
        <details className="mb-4">
          <summary className="cursor-pointer text-sm text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300">
            {t('errors.global.errorDetails', 'Fehlerdetails')}
          </summary>
          <pre className="mt-2 overflow-auto rounded bg-zinc-100 p-3 text-xs text-zinc-600 dark:bg-zinc-900 dark:text-zinc-400">
            {error?.stack}
          </pre>
        </details>
        <button
          onClick={() => window.location.reload()}
          className="w-full rounded-md bg-emerald-600 px-4 py-2 text-white transition-colors hover:bg-emerald-700 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-offset-2"
        >
          {t('errors.global.reloadPage', 'Seite neu laden')}
        </button>
      </div>
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

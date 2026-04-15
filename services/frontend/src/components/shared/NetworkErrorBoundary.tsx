import { useI18n } from '@/contexts/I18nContext'
import {
  ArrowPathIcon,
  ExclamationTriangleIcon,
} from '@heroicons/react/24/outline'
import React, { Component, ReactNode } from 'react'

interface Props {
  children: ReactNode
  fallback?: (error: Error, retry: () => void) => ReactNode
  onError?: (error: Error, errorInfo: React.ErrorInfo) => void
}

interface State {
  hasError: boolean
  error: Error | null
  isNetworkError: boolean
  retryCount: number
}

function NetworkErrorContent({
  isNetworkError,
  error,
  retryCount,
  onRetry,
}: {
  isNetworkError: boolean
  error: Error
  retryCount: number
  onRetry: () => void
}) {
  const { t } = useI18n()

  return (
    <div className="flex min-h-[400px] items-center justify-center p-4">
      <div className="w-full max-w-2xl rounded-lg bg-white p-6 shadow-lg dark:bg-gray-800">
        <div className="mb-4 flex items-center">
          <ExclamationTriangleIcon className="mr-3 h-8 w-8 text-red-500" />
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
            {isNetworkError
              ? t('errors.network.title')
              : t('errors.global.title')}
          </h2>
        </div>

        <div className="mb-6">
          <p className="mb-2 text-gray-600 dark:text-gray-300">
            {isNetworkError
              ? t('errors.network.connectionTrouble')
              : t('errors.global.description')}
          </p>

          {isNetworkError && (
            <ul className="list-inside list-disc space-y-1 text-sm text-gray-500 dark:text-gray-400">
              <li>{t('errors.network.networkIssue')}</li>
              <li>{t('errors.network.serverLoad')}</li>
              <li>{t('errors.network.tooManyRequests')}</li>
            </ul>
          )}

          {process.env.NODE_ENV === 'development' && (
            <details className="mt-4">
              <summary className="cursor-pointer text-sm text-gray-500 hover:text-gray-700">
                {t('errors.global.technicalDetails')}
              </summary>
              <pre className="mt-2 overflow-auto rounded bg-gray-100 p-2 text-xs dark:bg-gray-900">
                {error.stack || error.message}
              </pre>
            </details>
          )}
        </div>

        <div className="flex gap-3">
          <button
            onClick={onRetry}
            className="inline-flex flex-1 items-center justify-center rounded-md border border-transparent bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
          >
            <ArrowPathIcon className="mr-2 h-4 w-4" />
            {t('errors.global.tryAgain')}
            {retryCount > 0 && ` (${retryCount})`}
          </button>

          <button
            onClick={() => window.location.reload()}
            className="inline-flex flex-1 items-center justify-center rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-200 dark:hover:bg-gray-600"
          >
            {t('errors.global.reloadPage')}
          </button>
        </div>
      </div>
    </div>
  )
}

/**
 * Error boundary specifically designed to handle network-related errors
 * Provides retry functionality and user-friendly error messages
 */
export class NetworkErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = {
      hasError: false,
      error: null,
      isNetworkError: false,
      retryCount: 0,
    }
  }

  static getDerivedStateFromError(error: Error): Partial<State> {
    // Check if it's a network-related error
    const isNetworkError =
      error.message.includes('ERR_INSUFFICIENT_RESOURCES') ||
      error.message.includes('Network') ||
      error.message.includes('fetch') ||
      error.message.includes('Failed to fetch') ||
      error.message.includes('NetworkError') ||
      error.message.includes('TypeError: Failed to fetch') ||
      error.message.includes('AbortError')

    return {
      hasError: true,
      error,
      isNetworkError,
    }
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    // Log error details for debugging
    console.error('NetworkErrorBoundary caught error:', error, errorInfo)

    // Call optional error handler
    if (this.props.onError) {
      this.props.onError(error, errorInfo)
    }
  }

  retry = () => {
    this.setState((prevState) => ({
      hasError: false,
      error: null,
      isNetworkError: false,
      retryCount: prevState.retryCount + 1,
    }))
  }

  render() {
    if (this.state.hasError && this.state.error) {
      // Use custom fallback if provided
      if (this.props.fallback) {
        return this.props.fallback(this.state.error, this.retry)
      }

      // Default error UI
      return (
        <NetworkErrorContent
          isNetworkError={this.state.isNetworkError}
          error={this.state.error}
          retryCount={this.state.retryCount}
          onRetry={this.retry}
        />
      )
    }

    return this.props.children
  }
}

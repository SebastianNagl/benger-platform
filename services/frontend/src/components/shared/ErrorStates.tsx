'use client'

import { useI18n } from '@/contexts/I18nContext'
import { ModelError } from '@/hooks/useModels'
import Link from 'next/link'
import { Button } from './Button'

type ExtendedError =
  | ModelError
  | {
      type: 'TASK_NOT_FOUND' | 'ACCESS_DENIED' | 'CONFIG_ERROR'
      message: string
      details?: string
    }

interface ErrorStateProps {
  error: ExtendedError
  onRetry?: () => void
  className?: string
}

export function ErrorState({
  error,
  onRetry,
  className = '',
}: ErrorStateProps) {
  const { t } = useI18n()

  const renderErrorContent = () => {
    switch (error.type) {
      case 'NO_API_KEYS':
        return (
          <>
            <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-blue-100 dark:bg-blue-900/30">
              <svg
                className="h-8 w-8 text-blue-600 dark:text-blue-400"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1.5}
                  d="M15 7a2 2 0 012 2m4 0a6 6 0 01-6 6c-1.105 0-2.13-.275-3.03-.764M15 7a2 2 0 00-2 2m2-2c.973 0 1.865.32 2.625.86M15 7V5a2 2 0 00-2-2H9a2 2 0 00-2 2v2M9 7a2 2 0 012 2m0 0V9a2 2 0 012-2h2a2 2 0 012 2v2.93"
                />
              </svg>
            </div>
            <h3 className="mb-2 text-lg font-medium text-zinc-900 dark:text-white">
              {t('errors.states.noApiKeys.title')}
            </h3>
            <p className="mb-6 text-sm text-zinc-600 dark:text-zinc-400">
              {t('errors.states.noApiKeys.message')}
            </p>
            <Link href="/profile">
              <Button variant="filled" className="mx-auto mb-4">
                {t('errors.states.noApiKeys.configureKeys')}
              </Button>
            </Link>
            <div className="space-y-1 text-xs text-zinc-500 dark:text-zinc-400">
              <p>{t('errors.states.noApiKeys.supportedProviders')}</p>
              <div className="mt-2 flex flex-wrap justify-center gap-2">
                <span className="inline-flex items-center rounded bg-blue-100 px-2 py-1 text-xs text-blue-700 dark:bg-blue-900/30 dark:text-blue-300">
                  OpenAI
                </span>
                <span className="inline-flex items-center rounded bg-purple-100 px-2 py-1 text-xs text-purple-700 dark:bg-purple-900/30 dark:text-purple-300">
                  Anthropic
                </span>
                <span className="inline-flex items-center rounded bg-green-100 px-2 py-1 text-xs text-green-700 dark:bg-green-900/30 dark:text-green-300">
                  Google
                </span>
                <span className="inline-flex items-center rounded bg-red-100 px-2 py-1 text-xs text-red-700 dark:bg-red-900/30 dark:text-red-300">
                  DeepInfra
                </span>
              </div>
            </div>
          </>
        )

      case 'AUTH_FAILED':
        return (
          <>
            <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-red-100 dark:bg-red-900/30">
              <svg
                className="h-8 w-8 text-red-600 dark:text-red-400"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1.5}
                  d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z"
                />
              </svg>
            </div>
            <h3 className="mb-2 text-lg font-medium text-zinc-900 dark:text-white">
              {t('errors.states.authFailed.title')}
            </h3>
            <p className="mb-6 text-sm text-zinc-600 dark:text-zinc-400">
              {t('errors.states.authFailed.message')}
            </p>
            <Button
              variant="filled"
              className="mx-auto"
              onClick={() => window.location.reload()}
              data-testid="retry-button"
            >
              {t('errors.states.authFailed.refreshPage')}
            </Button>
          </>
        )

      case 'SERVER_ERROR':
        return (
          <>
            <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-orange-100 dark:bg-orange-900/30">
              <svg
                className="h-8 w-8 text-orange-600 dark:text-orange-400"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1.5}
                  d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                />
              </svg>
            </div>
            <h3 className="mb-2 text-lg font-medium text-zinc-900 dark:text-white">
              {t('errors.states.serverError.title')}
            </h3>
            <p
              data-testid="error-message"
              className="mb-6 text-sm text-zinc-600 dark:text-zinc-400"
            >
              {error.details ||
                t('errors.states.serverError.defaultMessage')}
            </p>
            {onRetry && (
              <Button
                variant="filled"
                onClick={onRetry}
                className="mx-auto"
                data-testid="retry-button"
              >
                {t('errors.states.serverError.tryAgain')}
              </Button>
            )}
          </>
        )

      case 'NETWORK_ERROR':
        return (
          <>
            <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-yellow-100 dark:bg-yellow-900/30">
              <svg
                className="h-8 w-8 text-yellow-600 dark:text-yellow-400"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1.5}
                  d="M8.111 16.404a5.5 5.5 0 017.778 0M12 20h.01m-7.08-7.071c3.904-3.905 10.236-3.905 14.141 0M1.394 9.393c5.857-5.857 15.355-5.857 21.213 0"
                />
              </svg>
            </div>
            <h3 className="mb-2 text-lg font-medium text-zinc-900 dark:text-white">
              {t('errors.states.networkError.title')}
            </h3>
            <p className="mb-6 text-sm text-zinc-600 dark:text-zinc-400">
              {t('errors.states.networkError.message')}
            </p>
            {onRetry && (
              <Button
                variant="filled"
                onClick={onRetry}
                className="mx-auto"
                data-testid="retry-button"
              >
                {t('errors.states.networkError.retryConnection')}
              </Button>
            )}
          </>
        )

      case 'TASK_NOT_FOUND':
        return (
          <>
            <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-blue-100 dark:bg-blue-900/30">
              <svg
                className="h-8 w-8 text-blue-600 dark:text-blue-400"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1.5}
                  d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                />
              </svg>
            </div>
            <h3 className="mb-2 text-lg font-medium text-zinc-900 dark:text-white">
              {t('errors.states.taskNotFound.title')}
            </h3>
            <p
              data-testid="error-message"
              className="mb-6 text-sm text-zinc-600 dark:text-zinc-400"
            >
              {error.details ||
                t('errors.states.taskNotFound.defaultMessage')}
            </p>
            <Link href="/projects">
              <Button variant="filled" className="mx-auto">
                {t('errors.states.taskNotFound.backToProjects')}
              </Button>
            </Link>
          </>
        )

      case 'ACCESS_DENIED':
        return (
          <>
            <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-red-100 dark:bg-red-900/30">
              <svg
                className="h-8 w-8 text-red-600 dark:text-red-400"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1.5}
                  d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728L5.636 5.636m12.728 12.728L18.364 5.636M5.636 18.364l12.728-12.728"
                />
              </svg>
            </div>
            <h3 className="mb-2 text-lg font-medium text-zinc-900 dark:text-white">
              {t('errors.states.accessDenied.title')}
            </h3>
            <p
              data-testid="error-message"
              className="mb-6 text-sm text-zinc-600 dark:text-zinc-400"
            >
              {error.details ||
                t('errors.states.accessDenied.defaultMessage')}
            </p>
            <Link href="/projects">
              <Button variant="filled" className="mx-auto">
                {t('errors.states.accessDenied.backToProjects')}
              </Button>
            </Link>
          </>
        )

      case 'CONFIG_ERROR':
        return (
          <>
            <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-orange-100 dark:bg-orange-900/30">
              <svg
                className="h-8 w-8 text-orange-600 dark:text-orange-400"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1.5}
                  d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z"
                />
              </svg>
            </div>
            <h3 className="mb-2 text-lg font-medium text-zinc-900 dark:text-white">
              {t('errors.states.configError.title')}
            </h3>
            <p
              data-testid="error-message"
              className="mb-6 text-sm text-zinc-600 dark:text-zinc-400"
            >
              {error.details ||
                error.message ||
                t('errors.states.configError.defaultMessage')}
            </p>
            {onRetry && (
              <Button
                variant="filled"
                onClick={onRetry}
                className="mx-auto"
                data-testid="retry-button"
              >
                {t('errors.states.configError.tryAgain')}
              </Button>
            )}
          </>
        )

      default:
        return (
          <>
            <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-zinc-100 dark:bg-zinc-800">
              <svg
                className="h-8 w-8 text-zinc-400 dark:text-zinc-500"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1.5}
                  d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
            </div>
            <h3 className="mb-2 text-lg font-medium text-zinc-900 dark:text-white">
              {t('errors.states.default.title')}
            </h3>
            <p
              data-testid="error-message"
              className="mb-6 text-sm text-zinc-600 dark:text-zinc-400"
            >
              {error.message || t('errors.states.default.defaultMessage')}
            </p>
            {onRetry && (
              <Button
                variant="filled"
                onClick={onRetry}
                className="mx-auto"
                data-testid="retry-button"
              >
                {t('errors.states.default.tryAgain')}
              </Button>
            )}
          </>
        )
    }
  }

  return (
    <div
      data-testid="error-state"
      className={`px-4 py-12 text-center ${className}`}
    >
      <div className="mx-auto max-w-md">{renderErrorContent()}</div>
    </div>
  )
}

interface AuthenticationErrorProps {
  className?: string
}

export function AuthenticationError({
  className = '',
}: AuthenticationErrorProps) {
  const { t } = useI18n()

  return (
    <ErrorState
      error={{
        type: 'AUTH_FAILED',
        message: t('errors.states.authenticationError.message'),
        details: t('errors.states.authenticationError.details'),
      }}
      className={className}
    />
  )
}

interface ServerErrorWithRetryProps {
  onRetry: () => void
  message?: string
  className?: string
}

export function ServerErrorWithRetry({
  onRetry,
  message,
  className = '',
}: ServerErrorWithRetryProps) {
  const { t } = useI18n()

  return (
    <ErrorState
      error={{
        type: 'SERVER_ERROR',
        message: t('errors.states.serverErrorWithRetry.message'),
        details:
          message || t('errors.states.serverErrorWithRetry.defaultDetails'),
      }}
      onRetry={onRetry}
      className={className}
    />
  )
}

export default ErrorState

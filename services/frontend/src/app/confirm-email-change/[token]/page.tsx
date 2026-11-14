'use client'

import { VertretbarMarkIcon } from '@/components/brand/VertretbarMark'
import { LanguageSwitcher, ThemeToggle } from '@/components/layout'
import { Button } from '@/components/shared/Button'
import { useI18n } from '@/contexts/I18nContext'
import { rateLimitMessage } from '@/lib/api/errors'
import { getHostBrandName, isStudentLockedHost } from '@/lib/utils/subdomain'
import Link from 'next/link'
import { useParams } from 'next/navigation'
import { useState, useSyncExternalStore } from 'react'

const subscribeNoop = () => () => {}

type Status = 'ready' | 'confirming' | 'success' | 'error'

/**
 * Target of the mail sent to a new address after an email change on the
 * profile page (`/confirm-email-change/<token>`). It is opened from a
 * mailbox, on any device and often without a session, so the route is public.
 * Loading the page changes nothing: the token is used only when the reader
 * presses the button, so mail scanners that fetch the link do not consume it.
 */
export default function ConfirmEmailChangePage() {
  const params = useParams<{ token: string }>()
  const token = params?.token ?? ''
  const { t } = useI18n()

  const brandName = useSyncExternalStore(
    subscribeNoop,
    getHostBrandName,
    () => 'BenGER',
  )
  const isVtr = useSyncExternalStore(
    subscribeNoop,
    isStudentLockedHost,
    () => false,
  )

  const [status, setStatus] = useState<Status>('ready')
  const [newEmail, setNewEmail] = useState('')
  const [error, setError] = useState('')

  const handleConfirm = async () => {
    setStatus('confirming')
    setError('')
    try {
      const response = await fetch('/api/auth/email-change/confirm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token }),
      })
      const data = await response.json().catch(() => ({}))
      if (response.ok) {
        setNewEmail(typeof data?.email === 'string' ? data.email : '')
        setStatus('success')
        return
      }
      const code = data?.detail?.code
      setError(
        code === 'email_taken'
          ? t('emailChange.taken')
          : (rateLimitMessage(response.status, t, data) ??
              t('emailChange.invalid')),
      )
      setStatus('error')
    } catch (err) {
      console.error('Error confirming email change:', err)
      setError(t('emailChange.invalid'))
      setStatus('error')
    }
  }

  return (
    <div className="min-h-screen bg-white dark:bg-zinc-900">
      <header className="relative z-10">
        <nav
          className="mx-auto flex max-w-7xl items-center justify-between p-6 lg:px-8"
          aria-label={t('layout.minimal.globalNav')}
        >
          <div className="flex lg:flex-1">
            <Link href="/" className="-m-1.5 p-1.5">
              <span className="sr-only">{brandName}</span>
              <div className="flex items-center gap-2 text-xl font-bold text-zinc-900 dark:text-white">
                {isVtr ? (
                  <VertretbarMarkIcon className="h-7 w-7 text-emerald-500" />
                ) : (
                  <span className="text-2xl">🤘</span>
                )}
                <span>{brandName}</span>
              </div>
            </Link>
          </div>
          <div className="flex items-center gap-2">
            <LanguageSwitcher />
            <ThemeToggle />
          </div>
        </nav>
      </header>

      <main className="flex min-h-[calc(100vh-80px)] items-center justify-center px-6 py-12 lg:px-8">
        <div className="w-full max-w-md space-y-8 text-center">
          {status === 'success' ? (
            <div data-testid="confirm-email-change-success">
              <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-emerald-100 dark:bg-emerald-900/20">
                <svg
                  className="h-6 w-6 text-emerald-600 dark:text-emerald-400"
                  fill="none"
                  viewBox="0 0 24 24"
                  strokeWidth="1.5"
                  stroke="currentColor"
                  aria-hidden="true"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M4.5 12.75l6 6 9-13.5"
                  />
                </svg>
              </div>
              <h1 className="mt-4 text-2xl font-bold text-zinc-900 dark:text-white">
                {t('emailChange.success')}
              </h1>
              <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
                {t('emailChange.successDescription', { email: newEmail })}
              </p>
              <div className="mt-6">
                <Link
                  href="/login"
                  className="inline-flex items-center justify-center gap-2 text-sm font-medium text-emerald-600 hover:text-emerald-500 dark:text-emerald-400 dark:hover:text-emerald-300"
                >
                  {t('emailChange.toLogin')}
                </Link>
              </div>
            </div>
          ) : (
            <div>
              <h1 className="text-2xl font-bold text-zinc-900 dark:text-white">
                {t('emailChange.title')}
              </h1>
              <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
                {t('emailChange.description')}
              </p>
              {status === 'error' && error && (
                <div className="mt-6 rounded-md bg-red-50 p-4 text-left dark:bg-red-900/20">
                  <p
                    className="text-sm text-red-800 dark:text-red-400"
                    role="alert"
                    data-testid="confirm-email-change-error"
                  >
                    {error}
                  </p>
                </div>
              )}
              <div className="mt-6">
                <Button
                  variant="filled"
                  className="w-full"
                  onClick={handleConfirm}
                  disabled={status === 'confirming' || !token}
                  data-testid="confirm-email-change-submit"
                >
                  {status === 'confirming'
                    ? t('emailChange.confirming')
                    : t('emailChange.confirm')}
                </Button>
              </div>
              <div className="mt-6">
                <Link
                  href="/login"
                  className="inline-flex items-center justify-center gap-2 text-sm font-medium text-emerald-600 hover:text-emerald-500 dark:text-emerald-400 dark:hover:text-emerald-300"
                >
                  ← {t('passwordReset.backToLogin')}
                </Link>
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  )
}

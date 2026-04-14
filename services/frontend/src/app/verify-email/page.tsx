'use client'

import { LanguageSwitcher, ThemeToggle } from '@/components/layout'
import { Button } from '@/components/shared/Button'
import { useI18n } from '@/contexts/I18nContext'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { useCallback, useEffect, useState } from 'react'

export default function VerifyEmailPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const token = searchParams?.get('token')
  const messageKey = searchParams?.get('messageKey')
  const { t } = useI18n()

  const [status, setStatus] = useState<
    'loading' | 'success' | 'error' | 'info'
  >('loading')
  const [message, setMessage] = useState('')
  const [email, setEmail] = useState('')

  const verifyEmail = useCallback(
    async (verificationToken: string) => {
      try {
        const response = await fetch('/api/auth/verify-email', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            token: verificationToken,
          }),
        })

        const data = await response.json()

        if (response.ok) {
          setStatus('success')
          setMessage(t('emailVerification.verifiedDescription'))
          setEmail(data.email || '')
          // Redirect to login after 3 seconds
          setTimeout(() => {
            router.push('/login')
          }, 3000)
        } else {
          setStatus('error')
          setMessage(data.detail || t('emailVerification.invalidDescription'))
        }
      } catch (error) {
        console.error('Error verifying email:', error)
        setStatus('error')
        setMessage(t('emailVerification.invalidDescription'))
      }
    },
    [t, router]
  )

  useEffect(() => {
    if (token) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- Intentional: verifyEmail updates state as part of async flow
      verifyEmail(token)
    } else if (messageKey) {
      // This is a redirect after registration with a message key
       
      setStatus('info')
      // Translate the message key (e.g., 'registrationSuccess' -> 'emailVerification.registrationSuccess')
      setMessage(t(`emailVerification.${messageKey}`))
    } else {
       
      setStatus('error')
      setMessage(t('emailVerification.noToken'))
    }
  }, [token, messageKey, t, verifyEmail])

  const handleResendVerification = async () => {
    if (!email) return

    try {
      const response = await fetch('/api/auth/resend-verification', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          email: email,
          language: 'en',
        }),
      })

      if (response.ok) {
        setMessage(t('emailVerification.resent'))
      }
    } catch (error) {
      console.error('Error resending verification:', error)
    }
  }

  return (
    <div className="min-h-screen bg-white dark:bg-zinc-900">
      {/* Minimal Header */}
      <header className="relative z-10">
        <nav
          className="mx-auto flex max-w-7xl items-center justify-between p-6 lg:px-8"
          aria-label="Global"
        >
          <div className="flex lg:flex-1">
            <Link href="/" className="-m-1.5 p-1.5">
              <span className="sr-only">BenGER</span>
              <div className="flex items-center gap-2 text-xl font-bold text-zinc-900 dark:text-white">
                <span className="text-2xl">🤘</span>
                <span>BenGER</span>
              </div>
            </Link>
          </div>

          {/* Controls */}
          <div className="flex items-center gap-2">
            <LanguageSwitcher />
            <ThemeToggle />
          </div>
        </nav>
      </header>

      {/* Main Content */}
      <main className="flex min-h-[calc(100vh-80px)] items-center justify-center px-6 py-12 lg:px-8">
        <div className="w-full max-w-md space-y-8">
          {status === 'loading' && (
            <div className="text-center">
              <div className="mx-auto flex h-12 w-12 items-center justify-center">
                <div className="h-8 w-8 animate-spin rounded-full border-b-2 border-emerald-600 dark:border-emerald-400"></div>
              </div>
              <h2 className="mt-4 text-2xl font-bold text-zinc-900 dark:text-white">
                {t('emailVerification.verifying')}
              </h2>
              <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
                {t('emailVerification.checkInboxDescription')}
              </p>
            </div>
          )}

          {status === 'success' && (
            <div className="text-center">
              <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-emerald-100 dark:bg-emerald-900/20">
                <svg
                  className="h-6 w-6 text-emerald-600 dark:text-emerald-400"
                  fill="none"
                  viewBox="0 0 24 24"
                  strokeWidth="1.5"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M4.5 12.75l6 6 9-13.5"
                  />
                </svg>
              </div>
              <h2 className="mt-4 text-2xl font-bold text-zinc-900 dark:text-white">
                {t('emailVerification.verified')}
              </h2>
              <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
                {message}
              </p>
              {email && (
                <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-500">
                  {t('emailVerification.emailLabel')} {email}
                </p>
              )}
              <p className="mt-4 text-sm text-zinc-600 dark:text-zinc-400">
                {t('login.redirecting')}
              </p>
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

          {status === 'info' && (
            <div className="text-center">
              <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-blue-100 dark:bg-blue-900/20">
                <svg
                  className="h-6 w-6 text-blue-600 dark:text-blue-400"
                  fill="none"
                  viewBox="0 0 24 24"
                  strokeWidth="1.5"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75"
                  />
                </svg>
              </div>
              <h2 className="mt-4 text-2xl font-bold text-zinc-900 dark:text-white">
                {t('emailVerification.checkInbox')}
              </h2>
              <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
                {message}
              </p>
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

          {status === 'error' && (
            <div className="text-center">
              <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-red-100 dark:bg-red-900/20">
                <svg
                  className="h-6 w-6 text-red-600 dark:text-red-400"
                  fill="none"
                  viewBox="0 0 24 24"
                  strokeWidth="1.5"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M6 18L18 6M6 6l12 12"
                  />
                </svg>
              </div>
              <h2 className="mt-4 text-2xl font-bold text-zinc-900 dark:text-white">
                {t('emailVerification.invalid')}
              </h2>
              <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
                {message}
              </p>

              <div className="mt-6 space-y-4">
                {email && (
                  <Button
                    onClick={handleResendVerification}
                    className="w-full bg-emerald-600 px-4 py-2 text-white shadow-sm hover:bg-emerald-700 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-offset-2 dark:focus:ring-offset-zinc-900"
                  >
                    {t('emailVerification.resend')}
                  </Button>
                )}

                <div>
                  <Link
                    href="/login"
                    className="inline-flex items-center justify-center gap-2 text-sm font-medium text-emerald-600 hover:text-emerald-500 dark:text-emerald-400 dark:hover:text-emerald-300"
                  >
                    ← {t('passwordReset.backToLogin')}
                  </Link>
                </div>
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  )
}

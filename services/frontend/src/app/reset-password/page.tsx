'use client'

import { LanguageSwitcher, ThemeToggle } from '@/components/layout'
import { Button } from '@/components/shared/Button'
import { useI18n } from '@/contexts/I18nContext'
import Link from 'next/link'
import { useState } from 'react'

export default function ResetPasswordPage() {
  const [email, setEmail] = useState('')
  const [isSubmitted, setIsSubmitted] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const { t } = useI18n()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsLoading(true)

    try {
      // Call the actual API endpoint
      const response = await fetch('/api/auth/request-password-reset', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          email: email,
          language: 'en', // You can detect this from the user's browser or preferences
        }),
      })

      if (!response.ok) {
        // Even if the API returns an error, we show success to prevent email enumeration
        console.error('Password reset request failed:', response.statusText)
      }

      setIsSubmitted(true)
    } catch (error) {
      console.error('Error requesting password reset:', error)
      // Show success message anyway to prevent email enumeration
      setIsSubmitted(true)
    } finally {
      setIsLoading(false)
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

          {/* Back to Login + Controls */}
          <div className="flex items-center gap-4">
            <Link
              href="/login"
              className="text-sm text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white"
            >
              {t('passwordReset.backToLogin')}
            </Link>
            <div className="ml-4 flex items-center gap-2">
              <LanguageSwitcher />
              <ThemeToggle />
            </div>
          </div>
        </nav>
      </header>

      {/* Main Content */}
      <main className="flex min-h-[calc(100vh-80px)] items-center justify-center px-6 py-12 lg:px-8">
        <div className="w-full max-w-md space-y-8">
          {!isSubmitted ? (
            <>
              {/* Header */}
              <div className="text-center">
                <h1 className="text-3xl font-bold tracking-tight text-zinc-900 dark:text-white">
                  {t('passwordReset.title')}
                </h1>
                <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
                  {t('passwordReset.description')}
                </p>
              </div>

              {/* Reset Form */}
              <form onSubmit={handleSubmit} className="space-y-6">
                <div>
                  <label
                    htmlFor="email"
                    className="block text-sm font-medium text-zinc-900 dark:text-white"
                  >
                    {t('passwordReset.emailLabel')}
                  </label>
                  <div className="mt-1">
                    <input
                      id="email"
                      name="email"
                      type="email"
                      autoComplete="email"
                      required
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      className="block w-full rounded-md border border-zinc-300 px-3 py-2 text-zinc-900 placeholder-zinc-500 focus:border-emerald-500 focus:outline-none focus:ring-emerald-500 dark:border-zinc-600 dark:bg-zinc-800 dark:text-white dark:placeholder-zinc-400 dark:focus:border-emerald-400 dark:focus:ring-emerald-400"
                      placeholder={t('passwordReset.emailPlaceholder')}
                    />
                  </div>
                </div>

                <div>
                  <Button
                    type="submit"
                    disabled={isLoading}
                    className="w-full bg-emerald-600 px-4 py-2 text-white shadow-sm hover:bg-emerald-700 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-offset-2 dark:focus:ring-offset-zinc-900"
                  >
                    {isLoading ? (
                      <div className="flex items-center justify-center">
                        <div className="mr-2 h-4 w-4 animate-spin rounded-full border-b-2 border-white"></div>
                        {t('passwordReset.sending')}
                      </div>
                    ) : (
                      t('passwordReset.send')
                    )}
                  </Button>
                </div>

                <div className="text-center">
                  <Link
                    href="/login"
                    className="text-sm font-medium text-emerald-600 hover:text-emerald-500 dark:text-emerald-400 dark:hover:text-emerald-300"
                  >
                    {t('passwordReset.backToLogin')}
                  </Link>
                </div>
              </form>
            </>
          ) : (
            /* Success Message */
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
                {t('passwordReset.sent')}
              </h2>
              <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
                {t('passwordReset.sentDescription')}
              </p>
              <p className="mt-4 text-xs text-zinc-500 dark:text-zinc-500">
                {t('emailVerification.didntReceive')}{' '}
                <button
                  onClick={() => setIsSubmitted(false)}
                  className="font-medium text-emerald-600 hover:text-emerald-500 dark:text-emerald-400 dark:hover:text-emerald-300"
                >
                  try again
                </button>
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
        </div>
      </main>
    </div>
  )
}

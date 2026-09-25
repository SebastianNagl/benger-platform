'use client'

import { AuthPageFrame } from '@/components/layout/AuthPageFrame'
import { Button } from '@/components/shared/Button'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { getHostBrandName } from '@/lib/utils/subdomain'
import { authRedirect } from '@/utils/authRedirect'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'

export default function LoginPage() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [nextUrl, setNextUrl] = useState<string | null>(null)
  // Host-aware product name for the subtitle (the frame draws the wordmark).
  // Resolved after mount so SSR stays neutral.
  const [brandName, setBrandName] = useState('BenGER')
  const { user, login } = useAuth()
  const { t } = useI18n()
  const router = useRouter()

  useEffect(() => {
    setBrandName(getHostBrandName())
  }, [])

  // Capture an optional ?next= return path (sanitized to an internal route).
  // Read from window.location to avoid a useSearchParams Suspense boundary,
  // matching the register page's convention (Issue #35).
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    setNextUrl(authRedirect.sanitizeNext(params.get('next')))
  }, [])

  // Redirect authenticated users to their intended destination (or dashboard).
  // (Dev auto-login is handled by the inline script in layout.tsx)
  useEffect(() => {
    if (user) {
      router.replace(nextUrl || authRedirect.defaultAuthedPath())
    }
  }, [user, router, nextUrl])

  // Prevent flash while redirecting
  if (user) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-white dark:bg-zinc-900">
        <div className="text-center">
          <div className="mx-auto mb-4 h-8 w-8 animate-spin rounded-full border-b-2 border-emerald-500"></div>
          <p className="text-zinc-600 dark:text-zinc-400">
            {t('login.redirecting')}
          </p>
        </div>
      </div>
    )
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsLoading(true)
    setError(null)

    try {
      await login(username, password)
      // Login success will trigger redirect via useEffect
    } catch (err) {
      setError(err instanceof Error ? err.message : t('login.failed'))
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <AuthPageFrame contentTestId="auth-login-area">
      {/* Header */}
      <div className="text-center">
        <h1 className="text-3xl font-bold tracking-tight text-zinc-900 dark:text-white">
          {t('login.title')}
        </h1>
        <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
          {t('login.subtitle').replace(/BenGER/g, brandName)}{' '}
          <Link
            href="/register"
            className="font-medium text-emerald-600 hover:text-emerald-500 dark:text-emerald-400 dark:hover:text-emerald-300"
            data-testid="auth-login-register-link"
          >
            {t('login.register')}
          </Link>
        </p>
      </div>

      {/* Login Form */}
      <form
        onSubmit={handleSubmit}
        className="space-y-6"
        data-testid="auth-login-form"
      >
        {error && (
          <div
            className="rounded-md bg-red-50 p-4 dark:bg-red-900/20"
            data-testid="auth-login-error-message"
          >
            <div className="text-sm text-red-700 dark:text-red-400">
              {error}
            </div>
          </div>
        )}

        <div>
          <label
            htmlFor="username"
            className="block text-sm font-medium text-zinc-900 dark:text-white"
          >
            {t('login.username')}
          </label>
          <div className="mt-1">
            <input
              id="username"
              name="username"
              type="text"
              autoComplete="username"
              required
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="block w-full rounded-md border border-zinc-300 px-3 py-2 text-zinc-900 placeholder-zinc-500 focus:border-emerald-500 focus:ring-emerald-500 focus:outline-none dark:border-zinc-600 dark:bg-zinc-800 dark:text-white dark:placeholder-zinc-400 dark:focus:border-emerald-400 dark:focus:ring-emerald-400"
              placeholder={t('login.usernamePlaceholder')}
              data-testid="auth-login-email-input"
            />
          </div>
        </div>

        <div>
          <label
            htmlFor="password"
            className="block text-sm font-medium text-zinc-900 dark:text-white"
          >
            {t('login.password')}
          </label>
          <div className="mt-1">
            <input
              id="password"
              name="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="block w-full rounded-md border border-zinc-300 px-3 py-2 text-zinc-900 placeholder-zinc-500 focus:border-emerald-500 focus:ring-emerald-500 focus:outline-none dark:border-zinc-600 dark:bg-zinc-800 dark:text-white dark:placeholder-zinc-400 dark:focus:border-emerald-400 dark:focus:ring-emerald-400"
              placeholder={t('login.passwordPlaceholder')}
              data-testid="auth-login-password-input"
            />
          </div>
        </div>

        <div className="flex items-center justify-between">
          <div className="text-sm">
            <Link
              href="/reset-password"
              className="font-medium text-emerald-600 hover:text-emerald-500 dark:text-emerald-400 dark:hover:text-emerald-300"
              data-testid="auth-login-forgot-password-link"
            >
              {t('login.forgotPassword')}
            </Link>
          </div>
        </div>

        <div>
          <Button
            type="submit"
            disabled={isLoading}
            className="w-full bg-emerald-600 px-4 py-2 text-white shadow-sm hover:bg-emerald-700 focus:ring-2 focus:ring-emerald-500 focus:ring-offset-2 focus:outline-none dark:focus:ring-offset-zinc-900"
            data-testid="auth-login-submit-button"
          >
            {isLoading ? (
              <div className="flex items-center justify-center">
                <div className="mr-2 h-4 w-4 animate-spin rounded-full border-b-2 border-white"></div>
                {t('login.loading')}
              </div>
            ) : (
              t('login.button')
            )}
          </Button>
        </div>
      </form>
    </AuthPageFrame>
  )
}

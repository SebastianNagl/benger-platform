'use client'

import { LanguageSwitcher, ThemeToggle } from '@/components/layout'
import { Button } from '@/components/shared/Button'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'

export default function LoginPage() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const { user, login } = useAuth()
  const { t } = useI18n()
  const router = useRouter()

  // Redirect authenticated users to dashboard
  // (Dev auto-login is handled by the inline script in layout.tsx)
  useEffect(() => {
    if (user) {
      router.replace('/dashboard')
    }
  }, [user, router])

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

          {/* Back to Landing + Controls */}
          <div
            className="flex items-center gap-4"
            data-testid="auth-navigation-safe-zone"
          >
            <Link
              href="/"
              className="text-sm text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white"
            >
              {t('login.backToLanding')}
            </Link>
            <div
              className="ml-4 flex items-center gap-2"
              data-testid="auth-ui-controls"
              data-automation="ignore"
            >
              <LanguageSwitcher />
              <ThemeToggle />
            </div>
          </div>
        </nav>
      </header>

      {/* Main Content */}
      <main className="flex min-h-[calc(100vh-80px)] items-center justify-center px-6 py-12 lg:px-8">
        <div
          className="w-full max-w-md space-y-8"
          data-testid="auth-login-area"
        >
          {/* Header */}
          <div className="text-center">
            <h1 className="text-3xl font-bold tracking-tight text-zinc-900 dark:text-white">
              {t('login.title')}
            </h1>
            <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
              {t('login.subtitle')}{' '}
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
                  className="block w-full rounded-md border border-zinc-300 px-3 py-2 text-zinc-900 placeholder-zinc-500 focus:border-emerald-500 focus:outline-none focus:ring-emerald-500 dark:border-zinc-600 dark:bg-zinc-800 dark:text-white dark:placeholder-zinc-400 dark:focus:border-emerald-400 dark:focus:ring-emerald-400"
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
                  className="block w-full rounded-md border border-zinc-300 px-3 py-2 text-zinc-900 placeholder-zinc-500 focus:border-emerald-500 focus:outline-none focus:ring-emerald-500 dark:border-zinc-600 dark:bg-zinc-800 dark:text-white dark:placeholder-zinc-400 dark:focus:border-emerald-400 dark:focus:ring-emerald-400"
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
                className="w-full bg-emerald-600 px-4 py-2 text-white shadow-sm hover:bg-emerald-700 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-offset-2 dark:focus:ring-offset-zinc-900"
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
        </div>
      </main>
    </div>
  )
}

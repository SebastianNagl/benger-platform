'use client'

import { LanguageSwitcher, ThemeToggle } from '@/components/layout'
import { Button } from '@/components/shared/Button'
import { useI18n } from '@/contexts/I18nContext'
import { getHostBrandName, isStudentLockedHost } from '@/lib/utils/subdomain'
import Link from 'next/link'
import { useParams, useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'

export default function ActivateAccountPage() {
  const params = useParams()
  const router = useRouter()
  const token = params?.token as string

  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [isSubmitted, setIsSubmitted] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')
  const [brandName, setBrandName] = useState('BenGER')
  const [isVtr, setIsVtr] = useState(false)
  const { t } = useI18n()

  useEffect(() => {
    setBrandName(getHostBrandName())
    setIsVtr(isStudentLockedHost())
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')

    if (newPassword !== confirmPassword) {
      setError(t('accountActivation.mismatch'))
      return
    }
    if (newPassword.length < 6) {
      setError(t('accountActivation.tooShort'))
      return
    }

    setIsLoading(true)
    try {
      const response = await fetch('/api/auth/activate-account', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          token: token,
          new_password: newPassword,
          confirm_password: confirmPassword,
        }),
      })

      const data = await response.json().catch(() => ({}))

      if (response.ok) {
        setIsSubmitted(true)
        setTimeout(() => {
          router.push('/login')
        }, 3000)
      } else {
        const code = data?.detail?.code
        if (code === 'email_taken') {
          setError(t('accountActivation.emailTaken'))
        } else {
          // invalid_or_expired and everything else: one message, no oracle.
          setError(t('accountActivation.expiredDescription'))
        }
      }
    } catch (err) {
      console.error('Error activating account:', err)
      setError(t('accountActivation.expiredDescription'))
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
              <span className="sr-only">{brandName}</span>
              <div className="flex items-center gap-2 text-xl font-bold text-zinc-900 dark:text-white">
                {!isVtr && <span className="text-2xl">🤘</span>}
                <span>{brandName}</span>
              </div>
            </Link>
          </div>

          <div className="flex items-center gap-4">
            <Link
              href="/login"
              className="text-sm text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white"
            >
              {t('accountActivation.backToLogin')}
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
              <div className="text-center">
                <h1 className="text-3xl font-bold tracking-tight text-zinc-900 dark:text-white">
                  {t('accountActivation.title')}
                </h1>
                <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
                  {t('accountActivation.description', { brand: brandName })}
                </p>
              </div>

              <form onSubmit={handleSubmit} className="space-y-6">
                {error && (
                  <div className="rounded-md bg-red-50 p-4 dark:bg-red-900/20">
                    <p
                      className="text-sm text-red-800 dark:text-red-400"
                      data-testid="activate-error"
                    >
                      {error}
                    </p>
                  </div>
                )}

                <div>
                  <label
                    htmlFor="new-password"
                    className="block text-sm font-medium text-zinc-900 dark:text-white"
                  >
                    {t('accountActivation.newPassword')}
                  </label>
                  <div className="mt-1">
                    <input
                      id="new-password"
                      name="new-password"
                      type="password"
                      autoComplete="new-password"
                      required
                      value={newPassword}
                      onChange={(e) => setNewPassword(e.target.value)}
                      data-testid="activate-password"
                      className="block w-full rounded-md border border-zinc-300 px-3 py-2 text-zinc-900 placeholder-zinc-500 focus:border-emerald-500 focus:outline-none focus:ring-emerald-500 dark:border-zinc-600 dark:bg-zinc-800 dark:text-white dark:placeholder-zinc-400 dark:focus:border-emerald-400 dark:focus:ring-emerald-400"
                      placeholder={t('accountActivation.newPassword')}
                    />
                  </div>
                </div>

                <div>
                  <label
                    htmlFor="confirm-password"
                    className="block text-sm font-medium text-zinc-900 dark:text-white"
                  >
                    {t('accountActivation.confirmPassword')}
                  </label>
                  <div className="mt-1">
                    <input
                      id="confirm-password"
                      name="confirm-password"
                      type="password"
                      autoComplete="new-password"
                      required
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      data-testid="activate-password-confirm"
                      className="block w-full rounded-md border border-zinc-300 px-3 py-2 text-zinc-900 placeholder-zinc-500 focus:border-emerald-500 focus:outline-none focus:ring-emerald-500 dark:border-zinc-600 dark:bg-zinc-800 dark:text-white dark:placeholder-zinc-400 dark:focus:border-emerald-400 dark:focus:ring-emerald-400"
                      placeholder={t('accountActivation.confirmPassword')}
                    />
                  </div>
                </div>

                <div>
                  <Button
                    type="submit"
                    disabled={isLoading}
                    data-testid="activate-submit"
                    className="w-full bg-emerald-600 px-4 py-2 text-white shadow-sm hover:bg-emerald-700 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-offset-2 dark:focus:ring-offset-zinc-900"
                  >
                    {isLoading ? (
                      <div className="flex items-center justify-center">
                        <div className="mr-2 h-4 w-4 animate-spin rounded-full border-b-2 border-white"></div>
                        {t('accountActivation.activating')}
                      </div>
                    ) : (
                      t('accountActivation.activate')
                    )}
                  </Button>
                </div>
              </form>
            </>
          ) : (
            <div className="text-center" data-testid="activate-success">
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
                {t('accountActivation.success')}
              </h2>
              <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
                {t('accountActivation.successDescription')}
              </p>
              <div className="mt-6">
                <Link
                  href="/login"
                  className="inline-flex items-center justify-center gap-2 text-sm font-medium text-emerald-600 hover:text-emerald-500 dark:text-emerald-400 dark:hover:text-emerald-300"
                >
                  ← {t('accountActivation.backToLogin')}
                </Link>
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  )
}

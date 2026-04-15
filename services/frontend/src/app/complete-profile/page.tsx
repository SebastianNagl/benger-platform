'use client'

import { Button } from '@/components/shared/Button'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { api } from '@/lib/api'
import {
  ArrowPathIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon,
  LockClosedIcon,
  UserIcon,
} from '@heroicons/react/24/outline'
import { useRouter } from 'next/navigation'
import { useCallback, useEffect, useState } from 'react'

export default function CompleteProfilePage() {
  const router = useRouter()
  const { user, refreshAuth } = useAuth()
  const { t } = useI18n()
  const [formData, setFormData] = useState({
    username: '',
    password: '',
    confirmPassword: '',
    name: '',
  })
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [profileStatus, setProfileStatus] = useState<any>(null)

  const checkProfileStatus = useCallback(async () => {
    if (!user) {
      router.push('/login')
      return
    }

    try {
      setLoading(true)
      const response = await api.get('/auth/check-profile-status')
      setProfileStatus(response.data)

      if (response.data.profile_completed) {
        // Profile already completed, redirect to dashboard
        router.push('/dashboard')
      } else if (!response.data.created_via_invitation) {
        // Not an invited user, redirect to dashboard
        router.push('/dashboard')
      } else {
        // Pre-fill form with user data
        setFormData({
          username: user.username || '',
          password: '',
          confirmPassword: '',
          name: user.name || '',
        })
      }
    } catch (err: any) {
      console.error('Failed to check profile status:', err)
      setError(t('completeProfile.failedToCheck'))
    } finally {
      setLoading(false)
    }
  }, [user, router, t])

  useEffect(() => {
    checkProfileStatus()
  }, [checkProfileStatus])

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFormData((prev) => ({
      ...prev,
      [e.target.name]: e.target.value,
    }))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    setError(null)

    // Validate passwords match
    if (formData.password !== formData.confirmPassword) {
      setError(t('completeProfile.passwordMismatch'))
      setSubmitting(false)
      return
    }

    // Validate password length
    if (formData.password.length < 8) {
      setError(t('completeProfile.passwordTooShort'))
      setSubmitting(false)
      return
    }

    try {
      const response = await api.post('/auth/complete-profile', {
        username: formData.username,
        password: formData.password,
        name: formData.name || undefined,
      })

      if (response.data.success) {
        // Refresh auth to get updated user data
        await refreshAuth()

        // Redirect to the appropriate page
        const redirectUrl = response.data.redirect_url || '/dashboard'
        router.push(redirectUrl)
      }
    } catch (err: any) {
      console.error('Failed to complete profile:', err)
      setError(err.response?.data?.detail || t('completeProfile.failedToComplete'))
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-50 dark:bg-zinc-900">
        <div className="text-center">
          <ArrowPathIcon className="mx-auto mb-4 h-8 w-8 animate-spin text-zinc-400" />
          <p className="text-zinc-600 dark:text-zinc-400">
            {t('completeProfile.loading')}
          </p>
        </div>
      </div>
    )
  }

  if (!user || (profileStatus && profileStatus.profile_completed)) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-50 dark:bg-zinc-900">
        <div className="text-center">
          <CheckCircleIcon className="mx-auto mb-4 h-12 w-12 text-green-500" />
          <p className="text-zinc-600 dark:text-zinc-400">
            {t('completeProfile.alreadyCompleted')}
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-50 dark:bg-zinc-900">
      <div className="mx-auto w-full max-w-md">
        <div className="overflow-hidden rounded-lg bg-white shadow-sm ring-1 ring-zinc-900/5 dark:bg-zinc-800 dark:ring-white/10">
          {/* Header */}
          <div className="border-b border-emerald-200 bg-emerald-50 px-6 py-4 dark:border-emerald-800 dark:bg-emerald-900/20">
            <div className="flex items-center">
              <UserIcon className="mr-3 h-6 w-6 text-emerald-600 dark:text-emerald-400" />
              <h1 className="text-lg font-semibold text-emerald-900 dark:text-emerald-100">
                {t('completeProfile.title')}
              </h1>
            </div>
          </div>

          {/* Content */}
          <div className="p-6">
            <div className="mb-6 text-center">
              <h2 className="mb-2 text-xl font-semibold text-zinc-900 dark:text-white">
                {t('completeProfile.welcome')}
              </h2>
              <p className="text-sm text-zinc-600 dark:text-zinc-400">
                {t('completeProfile.description')}
              </p>
            </div>

            {/* Error Message */}
            {error && (
              <div className="mb-6 rounded-lg border border-red-200 bg-red-50 p-4 dark:border-red-800 dark:bg-red-900/20">
                <div className="flex">
                  <ExclamationTriangleIcon className="mr-2 mt-0.5 h-5 w-5 flex-shrink-0 text-red-400" />
                  <div className="text-red-800 dark:text-red-200">{error}</div>
                </div>
              </div>
            )}

            {/* Form */}
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label
                  htmlFor="username"
                  className="block text-sm font-medium text-zinc-700 dark:text-zinc-300"
                >
                  {t('completeProfile.username')}
                </label>
                <div className="mt-1">
                  <input
                    id="username"
                    name="username"
                    type="text"
                    autoComplete="username"
                    required
                    value={formData.username}
                    onChange={handleChange}
                    className="block w-full rounded-md border-zinc-300 px-3 py-2 shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-emerald-500 dark:border-zinc-600 dark:bg-zinc-700 dark:text-white sm:text-sm"
                    placeholder={t('completeProfile.usernamePlaceholder')}
                  />
                </div>
              </div>

              <div>
                <label
                  htmlFor="name"
                  className="block text-sm font-medium text-zinc-700 dark:text-zinc-300"
                >
                  {t('completeProfile.displayName')}
                </label>
                <div className="mt-1">
                  <input
                    id="name"
                    name="name"
                    type="text"
                    autoComplete="name"
                    value={formData.name}
                    onChange={handleChange}
                    className="block w-full rounded-md border-zinc-300 px-3 py-2 shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-emerald-500 dark:border-zinc-600 dark:bg-zinc-700 dark:text-white sm:text-sm"
                    placeholder={t('completeProfile.displayNamePlaceholder')}
                  />
                </div>
              </div>

              <div>
                <label
                  htmlFor="password"
                  className="block text-sm font-medium text-zinc-700 dark:text-zinc-300"
                >
                  {t('completeProfile.password')}
                </label>
                <div className="mt-1">
                  <input
                    id="password"
                    name="password"
                    type="password"
                    autoComplete="new-password"
                    required
                    value={formData.password}
                    onChange={handleChange}
                    className="block w-full rounded-md border-zinc-300 px-3 py-2 shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-emerald-500 dark:border-zinc-600 dark:bg-zinc-700 dark:text-white sm:text-sm"
                    placeholder={t('completeProfile.passwordPlaceholder')}
                  />
                </div>
              </div>

              <div>
                <label
                  htmlFor="confirmPassword"
                  className="block text-sm font-medium text-zinc-700 dark:text-zinc-300"
                >
                  {t('completeProfile.confirmPassword')}
                </label>
                <div className="mt-1">
                  <input
                    id="confirmPassword"
                    name="confirmPassword"
                    type="password"
                    autoComplete="new-password"
                    required
                    value={formData.confirmPassword}
                    onChange={handleChange}
                    className="block w-full rounded-md border-zinc-300 px-3 py-2 shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-emerald-500 dark:border-zinc-600 dark:bg-zinc-700 dark:text-white sm:text-sm"
                    placeholder={t('completeProfile.confirmPasswordPlaceholder')}
                  />
                </div>
              </div>

              <div className="pt-4">
                <Button type="submit" disabled={submitting} className="w-full">
                  {submitting ? (
                    <>
                      <ArrowPathIcon className="mr-2 h-4 w-4 animate-spin" />
                      {t('completeProfile.submitting')}
                    </>
                  ) : (
                    <>
                      <LockClosedIcon className="mr-2 h-4 w-4" />
                      {t('completeProfile.submit')}
                    </>
                  )}
                </Button>
              </div>
            </form>

            <div className="mt-6 border-t border-zinc-200 pt-6 text-center text-sm text-zinc-600 dark:border-zinc-700 dark:text-zinc-400">
              <p>{t('completeProfile.notice')}</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

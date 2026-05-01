'use client'

import { Button } from '@/components/shared/Button'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { api } from '@/lib/api'
import { apiClient } from '@/lib/api/client'
import { InvitationDetails } from '@/lib/api/invitations'
import { getOrgUrl } from '@/lib/utils/subdomain'
import { useNotificationStore } from '@/stores/notificationStore'
import {
  ArrowPathIcon,
  BuildingOfficeIcon,
  CheckCircleIcon,
  ClockIcon,
  ExclamationTriangleIcon,
  UserPlusIcon,
} from '@heroicons/react/24/outline'
import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'

export default function AcceptInvitationPage({
  params,
}: {
  params: Promise<{ token: string }>
}) {
  const router = useRouter()
  const { user, refreshAuth, signup, isLoading: authLoading } = useAuth()
  const { t } = useI18n()
  const [invitation, setInvitation] = useState<InvitationDetails | null>(null)
  const [loading, setLoading] = useState(true)
  const [accepting, setAccepting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)
  const [token, setToken] = useState<string | null>(null)

  // Form state for new user account creation
  const [showAccountSetup, setShowAccountSetup] = useState(false)
  const [formData, setFormData] = useState({
    username: '',
    name: '',
    password: '',
    confirmPassword: '',
  })

  useEffect(() => {
    params?.then(({ token }) => {
      setToken(token)
    })
  }, [params])

  useEffect(() => {
    const loadInvitation = async () => {
      if (!token) return

      try {
        setLoading(true)
        setError(null)

        const data = await api.getInvitationByToken(token)
        setInvitation(data)
      } catch (err: any) {
        console.error('Failed to load invitation:', err)
        setError(err.response?.data?.detail || t('invitation.loadFailed'))
      } finally {
        setLoading(false)
      }
    }

    if (token && !authLoading) {
      loadInvitation()
    }
  }, [token, authLoading])

  const handleAcceptInvitation = async () => {
    if (!token) return

    if (!user) {
      // Redirect new users to full registration with invitation token
      router.push(`/register?invitation=${token}&email=${encodeURIComponent(invitation!.email)}`)
      return
    }

    try {
      setAccepting(true)
      setError(null)

      await api.acceptInvitation(token)
      setSuccess(true)

      // Refresh user data to get new organization membership
      await refreshAuth()

      // Fetch fresh orgs to find the accepted org's slug for redirect
      const orgId = invitation?.organization_id
      setTimeout(async () => {
        try {
          const orgs = await apiClient.getOrganizations()
          const acceptedOrg = orgs.find((o: any) => o.id === orgId)
          if (acceptedOrg?.slug) {
            const targetUrl = getOrgUrl(acceptedOrg.slug, '/dashboard')
            // Cross-subdomain redirect — encode the success message on the
            // URL so the destination's ToastProvider can show it on mount.
            window.location.href = useNotificationStore
              .getState()
              .flashRedirect(
                targetUrl,
                t('invitation.accepted', {
                  organizationName:
                    acceptedOrg.name ?? invitation?.organization_name ?? '',
                }),
                'success'
              )
          } else {
            useNotificationStore
              .getState()
              .flash(
                t('invitation.accepted', {
                  organizationName: invitation?.organization_name ?? '',
                }),
                'success'
              )
            router.push('/dashboard')
          }
        } catch {
          router.push('/dashboard')
        }
      }, 2000)
    } catch (err: any) {
      console.error('Failed to accept invitation:', err)
      setError(err.response?.data?.detail || t('invitation.acceptFailed'))
    } finally {
      setAccepting(false)
    }
  }

  const handleAccountSetup = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)

    // Validate passwords match
    if (formData.password !== formData.confirmPassword) {
      setError(t('invitation.passwordMismatch'))
      return
    }

    // Validate password length
    if (formData.password.length < 6) {
      setError(t('invitation.passwordTooShort'))
      return
    }

    try {
      setAccepting(true)

      // Create account with invitation token
      await signup(
        formData.username,
        invitation!.email,
        formData.name,
        formData.password,
        undefined, // no legal expertise data for invitation signup
        token!
      )

      // Success handled by AuthContext (will redirect to dashboard)
      setSuccess(true)
    } catch (err: any) {
      console.error('Failed to create account:', err)
      setError(err.message || t('invitation.createAccountFailed'))
      setAccepting(false)
    }
  }

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFormData((prev) => ({
      ...prev,
      [e.target.name]: e.target.value,
    }))
  }

  const formatExpiryDate = (dateString: string) => {
    const date = new Date(dateString)
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  }

  const isExpired = (dateString: string) => {
    return new Date(dateString) < new Date()
  }

  if (loading || authLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-50 dark:bg-zinc-900">
        <div className="text-center">
          <ArrowPathIcon className="mx-auto mb-4 h-8 w-8 animate-spin text-zinc-400" />
          <p className="text-zinc-600 dark:text-zinc-400">
            {t('invitation.loading')}
          </p>
        </div>
      </div>
    )
  }

  if (error || !invitation) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-50 dark:bg-zinc-900">
        <div className="mx-auto w-full max-w-md">
          <div className="rounded-lg bg-white p-8 text-center shadow-sm ring-1 ring-zinc-900/5 dark:bg-zinc-800 dark:ring-white/10">
            <ExclamationTriangleIcon className="mx-auto mb-4 h-12 w-12 text-red-500" />
            <h1 className="mb-2 text-xl font-semibold text-zinc-900 dark:text-white">
              {t('invitation.invalidTitle')}
            </h1>
            <p className="mb-6 text-zinc-600 dark:text-zinc-400">
              {error || t('invitation.invalidDescription')}
            </p>
            <Button onClick={() => router.push('/')} variant="outline">
              {t('invitation.returnHome')}
            </Button>
          </div>
        </div>
      </div>
    )
  }

  if (success) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-50 dark:bg-zinc-900">
        <div className="mx-auto w-full max-w-md">
          <div className="rounded-lg bg-white p-8 text-center shadow-sm ring-1 ring-zinc-900/5 dark:bg-zinc-800 dark:ring-white/10">
            <CheckCircleIcon className="mx-auto mb-4 h-12 w-12 text-green-500" />
            <h1 className="mb-2 text-xl font-semibold text-zinc-900 dark:text-white">
              {t('invitation.welcomeTo', {
                organizationName: invitation.organization_name,
              })}
            </h1>
            <p className="mb-6 text-zinc-600 dark:text-zinc-400">
              {t('invitation.joinedSuccess', { role: invitation.role })}
            </p>
            <p className="text-sm text-zinc-500 dark:text-zinc-400">
              {t('invitation.redirectingToOrg')}
            </p>
          </div>
        </div>
      </div>
    )
  }

  const expired = isExpired(invitation.expires_at)

  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-50 dark:bg-zinc-900">
      <div className="mx-auto w-full max-w-lg">
        <div className="overflow-hidden rounded-lg bg-white shadow-sm ring-1 ring-zinc-900/5 dark:bg-zinc-800 dark:ring-white/10">
          {/* Header */}
          <div className="border-b border-emerald-200 bg-emerald-50 px-6 py-4 dark:border-emerald-800 dark:bg-emerald-900/20">
            <div className="flex items-center">
              <UserPlusIcon className="mr-3 h-6 w-6 text-emerald-600 dark:text-emerald-400" />
              <h1 className="text-lg font-semibold text-emerald-900 dark:text-emerald-100">
                {t('invitation.title')}
              </h1>
            </div>
          </div>

          {/* Content */}
          <div className="p-6">
            <div className="mb-6 text-center">
              <h2 className="mb-2 text-xl font-semibold text-zinc-900 dark:text-white">
                {t('invitation.youreInvited')}
              </h2>
              <div className="mb-4 flex items-center justify-center space-x-2">
                <BuildingOfficeIcon className="h-5 w-5 text-zinc-400" />
                <span className="text-xl font-bold text-emerald-600 dark:text-emerald-400">
                  {invitation.organization_name}
                </span>
              </div>
            </div>

            {/* Invitation Details */}
            <div className="mb-6 rounded-lg bg-zinc-50 p-4 dark:bg-zinc-700/50">
              <div className="space-y-3">
                <div className="flex justify-between">
                  <span className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                    {t('invitation.invitedBy')}
                  </span>
                  <span className="text-sm text-zinc-900 dark:text-white">
                    {invitation.inviter_name}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                    {t('invitation.role')}
                  </span>
                  <span className="text-sm capitalize text-zinc-900 dark:text-white">
                    {invitation.role.replace('_', ' ')}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                    {t('invitation.email')}
                  </span>
                  <span className="text-sm text-zinc-900 dark:text-white">
                    {invitation.email}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                    {t('invitation.expires')}
                  </span>
                  <div className="flex items-center space-x-1">
                    <ClockIcon
                      className={`h-3 w-3 ${expired ? 'text-red-500' : 'text-zinc-400'}`}
                    />
                    <span
                      className={`text-sm ${expired ? 'text-red-600 dark:text-red-400' : 'text-zinc-900 dark:text-white'}`}
                    >
                      {formatExpiryDate(invitation.expires_at)}
                    </span>
                  </div>
                </div>
              </div>
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

            {/* Expiry Warning */}
            {expired && (
              <div className="mb-6 rounded-lg border border-red-200 bg-red-50 p-4 dark:border-red-800 dark:bg-red-900/20">
                <div className="flex">
                  <ExclamationTriangleIcon className="mr-2 mt-0.5 h-5 w-5 flex-shrink-0 text-red-400" />
                  <div className="text-red-800 dark:text-red-200">
                    {t('invitation.expired')}
                  </div>
                </div>
              </div>
            )}

            {/* Email Mismatch Warning */}
            {user && user.email !== invitation.email && (
              <div className="mb-6 rounded-lg border border-yellow-200 bg-yellow-50 p-4 dark:border-yellow-800 dark:bg-yellow-900/20">
                <div className="flex">
                  <ExclamationTriangleIcon className="mr-2 mt-0.5 h-5 w-5 flex-shrink-0 text-yellow-400" />
                  <div className="text-yellow-800 dark:text-yellow-200">
                    {t('invitation.emailMismatch', {
                      invitedEmail: invitation.email,
                      currentEmail: user.email,
                    })}
                  </div>
                </div>
              </div>
            )}

            {/* Actions */}
            {showAccountSetup ? (
              // Account Setup Form
              <form onSubmit={handleAccountSetup} className="space-y-4">
                <div>
                  <label className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
                    {t('invitation.emailLabel')}
                  </label>
                  <input
                    type="email"
                    value={invitation.email}
                    disabled
                    className="w-full rounded-md border border-zinc-300 bg-zinc-100 px-3 py-2 text-zinc-900 dark:border-zinc-600 dark:bg-zinc-700 dark:text-zinc-100"
                  />
                </div>

                <div>
                  <label className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
                    {t('invitation.fullName')}
                  </label>
                  <input
                    type="text"
                    name="name"
                    value={formData.name}
                    onChange={handleInputChange}
                    required
                    className="w-full rounded-md border border-zinc-300 px-3 py-2 text-zinc-900 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500 dark:border-zinc-600 dark:bg-zinc-700 dark:text-zinc-100"
                    placeholder={t('invitation.fullNamePlaceholder')}
                  />
                </div>

                <div>
                  <label className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
                    {t('invitation.username')}
                  </label>
                  <input
                    type="text"
                    name="username"
                    value={formData.username}
                    onChange={handleInputChange}
                    required
                    className="w-full rounded-md border border-zinc-300 px-3 py-2 text-zinc-900 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500 dark:border-zinc-600 dark:bg-zinc-700 dark:text-zinc-100"
                    placeholder={t('invitation.usernamePlaceholder')}
                  />
                </div>

                <div>
                  <label className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
                    {t('invitation.password')}
                  </label>
                  <input
                    type="password"
                    name="password"
                    value={formData.password}
                    onChange={handleInputChange}
                    required
                    minLength={6}
                    className="w-full rounded-md border border-zinc-300 px-3 py-2 text-zinc-900 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500 dark:border-zinc-600 dark:bg-zinc-700 dark:text-zinc-100"
                    placeholder={t('invitation.passwordPlaceholder')}
                  />
                </div>

                <div>
                  <label className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
                    {t('invitation.confirmPassword')}
                  </label>
                  <input
                    type="password"
                    name="confirmPassword"
                    value={formData.confirmPassword}
                    onChange={handleInputChange}
                    required
                    className="w-full rounded-md border border-zinc-300 px-3 py-2 text-zinc-900 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500 dark:border-zinc-600 dark:bg-zinc-700 dark:text-zinc-100"
                    placeholder={t('invitation.confirmPasswordPlaceholder')}
                  />
                </div>

                <div className="flex flex-col space-y-3">
                  <Button
                    type="submit"
                    disabled={accepting || expired}
                    className="w-full"
                  >
                    {accepting ? (
                      <>
                        <ArrowPathIcon className="mr-2 h-4 w-4 animate-spin" />
                        {t('invitation.creatingAccount')}
                      </>
                    ) : (
                      t('invitation.createAndJoin')
                    )}
                  </Button>

                  <Button
                    type="button"
                    onClick={() => setShowAccountSetup(false)}
                    variant="outline"
                    className="w-full"
                  >
                    {t('invitation.back')}
                  </Button>
                </div>
              </form>
            ) : (
              <div className="flex flex-col space-y-3">
                {!user ? (
                  <>
                    <Button
                      onClick={handleAcceptInvitation}
                      disabled={expired}
                      className="w-full"
                    >
                      {t('invitation.acceptAndCreate')}
                    </Button>
                    <div className="relative">
                      <div className="absolute inset-0 flex items-center">
                        <div className="w-full border-t border-zinc-300 dark:border-zinc-600" />
                      </div>
                      <div className="relative flex justify-center text-sm">
                        <span className="bg-white px-2 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400">
                          {t('invitation.alreadyHaveAccount')}
                        </span>
                      </div>
                    </div>
                    <Button
                      onClick={() =>
                        router.push(
                          `/login?redirect=/accept-invitation/${token}`
                        )
                      }
                      variant="outline"
                      className="w-full"
                    >
                      {t('invitation.loginToAccept')}
                    </Button>
                  </>
                ) : (
                  <Button
                    onClick={handleAcceptInvitation}
                    disabled={
                      accepting || expired || user.email !== invitation.email
                    }
                    className="w-full"
                  >
                    {accepting ? (
                      <>
                        <ArrowPathIcon className="mr-2 h-4 w-4 animate-spin" />
                        {t('invitation.accepting')}
                      </>
                    ) : (
                      t('invitation.accept')
                    )}
                  </Button>
                )}

                <Button
                  onClick={() => router.push('/')}
                  variant="outline"
                  className="w-full"
                >
                  {t('invitation.cancel')}
                </Button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

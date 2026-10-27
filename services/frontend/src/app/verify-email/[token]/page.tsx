'use client'

import { Alert } from '@/components/shared/Alert'
import { Button } from '@/components/shared/Button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/shared/Card'
import { useI18n } from '@/contexts/I18nContext'
import { CheckCircle, Loader2, XCircle } from 'lucide-react'
import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'

interface VerifyTokenPageProps {
  params: Promise<{
    token: string
  }>
}

export default function VerifyTokenPage({ params }: VerifyTokenPageProps) {
  const [isVerifying, setIsVerifying] = useState(true)
  const [isSuccess, setIsSuccess] = useState(false)
  const [message, setMessage] = useState('')
  const [token, setToken] = useState<string | null>(null)
  const router = useRouter()
  const { t } = useI18n()

  useEffect(() => {
    const getToken = async () => {
      const resolvedParams = await params
      setToken(resolvedParams.token)
    }
    getToken()
  }, [params])

  useEffect(() => {
    if (!token) return

    const verifyEmail = async () => {
      try {
        // Try enhanced verification endpoint first
        let response = await fetch(`/api/auth/verify-email-enhanced/${token}`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
        })

        let useEnhanced = true
        let data = await response.json()

        // Fall back to standard endpoint if enhanced is not available
        if (response.status === 403 || response.status === 404) {
          useEnhanced = false
          response = await fetch('/api/auth/verify-email', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({ token }),
          })
          data = await response.json()
        }

        if (response.ok && data.success) {
          setIsSuccess(true)
          setMessage(data.message || t('emailVerification.verifiedDescription'))

          // Handle different user types
          if (useEnhanced && data.redirect_url) {
            // Enhanced response with redirect URL
            setTimeout(() => {
              router.push(data.redirect_url)
            }, 3000)
          } else if (
            useEnhanced &&
            data.user_type === 'invited' &&
            !data.profile_completed
          ) {
            // Invited user needs profile completion
            setTimeout(() => {
              router.push('/complete-profile')
            }, 3000)
          } else {
            // Standard redirect to login
            setTimeout(() => {
              router.push('/login?message=Email verified! You can now log in.')
            }, 3000)
          }
        } else {
          setIsSuccess(false)
          setMessage(
            data.detail ||
              data.message ||
              t('emailVerification.invalidDescription'),
          )
        }
      } catch (error) {
        setIsSuccess(false)
        setMessage(t('emailVerification.invalidDescription'))
      } finally {
        setIsVerifying(false)
      }
    }

    verifyEmail()
  }, [token, router, t])

  if (isVerifying) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-50 px-4 py-12 sm:px-6 lg:px-8">
        <div className="w-full max-w-md">
          <Card>
            <CardHeader className="text-center">
              <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-emerald-100 dark:bg-emerald-900/20">
                <Loader2 className="h-6 w-6 animate-spin text-emerald-600 dark:text-emerald-400" />
              </div>
              <CardTitle className="text-2xl font-bold text-zinc-900">
                {t('emailVerification.verifying')}
              </CardTitle>
              <CardDescription className="text-zinc-600">
                {t('emailVerification.checkInboxDescription')}
              </CardDescription>
            </CardHeader>
          </Card>
        </div>
      </div>
    )
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-50 px-4 py-12 sm:px-6 lg:px-8">
      <div className="w-full max-w-md">
        <Card>
          <CardHeader className="text-center">
            <div
              className={`mx-auto flex h-12 w-12 items-center justify-center rounded-full ${
                isSuccess ? 'bg-emerald-100' : 'bg-red-100'
              }`}
            >
              {isSuccess ? (
                <CheckCircle className="h-6 w-6 text-emerald-600" />
              ) : (
                <XCircle className="h-6 w-6 text-red-600" />
              )}
            </div>
            <CardTitle className="text-2xl font-bold text-zinc-900">
              {isSuccess
                ? t('emailVerification.verified')
                : t('emailVerification.invalid')}
            </CardTitle>
            <CardDescription className="text-zinc-600">
              {isSuccess
                ? t('emailVerification.verifiedDescription')
                : t('emailVerification.invalidDescription')}
            </CardDescription>
          </CardHeader>

          <CardContent className="space-y-4">
            <Alert variant={isSuccess ? 'success' : 'error'}>
              <p
                className={`text-sm ${isSuccess ? 'text-emerald-700' : 'text-red-700'}`}
              >
                {message}
              </p>
            </Alert>

            {isSuccess ? (
              <div className="text-center text-sm text-zinc-600">
                <p>{t('emailVerification.redirectingToLogin')}</p>
                <p className="mt-2">{t('emailVerification.canNowLogIn')}</p>
              </div>
            ) : (
              <div className="text-center text-sm text-zinc-600">
                <p>{t('emailVerification.expiredDescription')}</p>
              </div>
            )}
          </CardContent>

          <div className="p-6 pt-0">
            {isSuccess ? (
              <Button
                variant="filled"
                onClick={() =>
                  router.push(
                    '/login?message=Email verified! You can now log in.',
                  )
                }
                className="w-full"
              >
                {t('passwordReset.backToLogin')}
              </Button>
            ) : (
              <div className="space-y-3">
                <Button
                  variant="filled"
                  onClick={() => router.push('/verify-email')}
                  className="w-full"
                >
                  {t('emailVerification.resend')}
                </Button>
                <Button
                  onClick={() => router.push('/register')}
                  variant="outline"
                  className="w-full"
                >
                  {t('passwordReset.backToLogin')}
                </Button>
              </div>
            )}
          </div>
        </Card>
      </div>
    </div>
  )
}

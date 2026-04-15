'use client'

import { LoginModal } from '@/components/auth/LoginModal'
import { Button } from '@/components/shared/Button'
import { useAuth } from '@/contexts/AuthContext'
import { Dialog, DialogBackdrop, DialogPanel } from '@headlessui/react'
import { useI18n } from '@/contexts/I18nContext'
import { useRouter } from 'next/navigation'
import React, { useState } from 'react'

interface AuthGuardProps {
  children: React.ReactNode
  requireAuth?: boolean
}

export function AuthGuard({ children, requireAuth = true }: AuthGuardProps) {
  const { t } = useI18n()
  const { user, isLoading } = useAuth()
  const router = useRouter()
  const [showLoginModal, setShowLoginModal] = useState(false)
  const [dialogDismissed, setDialogDismissed] = useState(false)

  // Derive dialog visibility from auth state
  const showAuthDialog = requireAuth && !isLoading && !user && !dialogDismissed

  const handleCloseDialog = () => {
    // Only close dialog if navigation is successful or if router is available
    if (router?.push) {
      setDialogDismissed(true)
      router.push('/')
    } else {
      // If router.push is not available, keep dialog open but don't throw error
      // This handles the graceful degradation case
    }
  }

  const handleSignIn = () => {
    setDialogDismissed(true)
    setShowLoginModal(true)
  }

  const handleLoginSuccess = () => {
    setShowLoginModal(false)
    // AuthGuard will automatically re-render when user state changes
  }

  // Show loading while auth is being checked
  if (isLoading) {
    return (
      <div
        className="flex min-h-screen items-center justify-center bg-white dark:bg-zinc-900"
        data-testid="loading-container"
      >
        <div className="text-center">
          <div className="mx-auto mb-4 h-8 w-8 animate-spin rounded-full border-b-2 border-emerald-500"></div>
          <p className="text-zinc-600 dark:text-zinc-400">{t('auth.guard.loading')}</p>
        </div>
      </div>
    )
  }

  // If authentication is required but user is not authenticated, show dialog
  if (requireAuth && !user) {
    return (
      <>
        {/* Render children in background (blurred/disabled state) */}
        <div className="pointer-events-none opacity-50 blur-sm">{children}</div>

        {/* Authentication Required Dialog */}
        <Dialog
          open={showAuthDialog}
          onClose={handleCloseDialog}
          className="relative z-50"
          data-testid="auth-dialog"
        >
          <DialogBackdrop className="fixed inset-0 bg-black/50" />

          <div className="fixed inset-0 flex items-center justify-center p-4">
            <DialogPanel className="mx-auto max-w-md rounded-lg border border-zinc-200 bg-white p-6 shadow-xl dark:border-zinc-700 dark:bg-zinc-800">
              <div className="text-center">
                <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-emerald-100 dark:bg-emerald-900/20">
                  <svg
                    className="h-6 w-6 text-emerald-600 dark:text-emerald-400"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
                    />
                  </svg>
                </div>

                <h3 className="mb-2 text-lg font-semibold text-zinc-900 dark:text-white">
                  {t('auth.guard.authRequired')}
                </h3>

                <p className="mb-6 text-sm text-zinc-600 dark:text-zinc-400">
                  {t('auth.guard.authRequiredDescription')}
                </p>

                <div className="flex justify-center gap-3">
                  <Button onClick={handleSignIn} className="flex-1">
                    {t('auth.guard.goToSignIn')}
                  </Button>
                  <Button
                    variant="outline"
                    onClick={handleCloseDialog}
                    className="flex-1"
                  >
                    {t('auth.guard.cancel')}
                  </Button>
                </div>
              </div>
            </DialogPanel>
          </div>
        </Dialog>

        {/* Login Modal */}
        <LoginModal isOpen={showLoginModal} onClose={handleLoginSuccess} />
      </>
    )
  }

  // User is authenticated or auth is not required, render children normally
  return <div data-testid="auth-guard">{children}</div>
}

'use client'

import { SessionValidator } from '@/components/auth/SessionValidator'
import { GlobalErrorBoundary } from '@/components/shared/GlobalErrorBoundary'
import { ToastProvider } from '@/components/shared/Toast'
import { AuthProvider } from '@/contexts/AuthContext'
import { FeatureFlagProvider } from '@/contexts/FeatureFlagContext'
import { HydrationProvider } from '@/contexts/HydrationContext'
import { I18nProvider } from '@/contexts/I18nContext'
import { ProgressProvider } from '@/contexts/ProgressContext'
import { DialogProvider } from '@/hooks/useDialogs'
import { ThemeProvider } from 'next-themes'

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <GlobalErrorBoundary>
      <HydrationProvider>
        <ThemeProvider
          attribute="class"
          defaultTheme="light"
          enableSystem={false}
          disableTransitionOnChange={true}
          storageKey="theme"
        >
          <AuthProvider>
            <SessionValidator />
            <FeatureFlagProvider>
              <I18nProvider>
                <ToastProvider>
                  <ProgressProvider>
                    <DialogProvider>{children}</DialogProvider>
                  </ProgressProvider>
                </ToastProvider>
              </I18nProvider>
            </FeatureFlagProvider>
          </AuthProvider>
        </ThemeProvider>
      </HydrationProvider>
    </GlobalErrorBoundary>
  )
}

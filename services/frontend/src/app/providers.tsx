'use client'

import { useEffect, useState } from 'react'
import { SessionValidator } from '@/components/auth/SessionValidator'
import { GlobalErrorBoundary } from '@/components/shared/GlobalErrorBoundary'
import { ToastProvider } from '@/components/shared/Toast'
import { AuthProvider } from '@/contexts/AuthContext'
import { FeatureFlagProvider } from '@/contexts/FeatureFlagContext'
import { HydrationProvider } from '@/contexts/HydrationContext'
import { I18nProvider } from '@/contexts/I18nContext'
import { ProgressProvider } from '@/contexts/ProgressContext'
import { DialogProvider } from '@/hooks/useDialogs'
import { loadExtended } from '@/lib/extensions'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ThemeProvider } from 'next-themes'

export function Providers({ children }: { children: React.ReactNode }) {
  // One QueryClient per mount. Defaults tuned for the dashboard pattern:
  // a 60 s `staleTime` makes back-nav feel instant (cached `/api/projects`
  // and `/api/dashboard/stats` serve from memory until the user actually
  // pauses for a minute), and `refetchOnWindowFocus` is off because Tab-switch
  // refetches were the noisiest source of redundant requests before.
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 60_000,
            gcTime: 5 * 60_000,
            refetchOnWindowFocus: false,
            retry: 1,
          },
        },
      })
  )

  useEffect(() => {
    loadExtended()
  }, [])
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
          <QueryClientProvider client={queryClient}>
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
          </QueryClientProvider>
        </ThemeProvider>
      </HydrationProvider>
    </GlobalErrorBoundary>
  )
}

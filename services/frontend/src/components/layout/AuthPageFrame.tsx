'use client'

import { VertretbarMarkIcon } from '@/components/brand/VertretbarMark'
import { LanguageSwitcher } from '@/components/layout/LanguageSwitcher'
import { ThemeToggle } from '@/components/layout/ThemeToggle'
import { useI18n } from '@/contexts/I18nContext'
import { getHostBrandName, isStudentLockedHost } from '@/lib/utils/subdomain'
import Link from 'next/link'
import { useSyncExternalStore, type ReactNode } from 'react'

interface AuthPageFrameProps {
  children: ReactNode
  /** Show the "back to the start page" link next to the controls. */
  showBackLink?: boolean
  /** Width of the centered content column. */
  width?: 'md' | 'lg'
  /** Test id of the centered content column. */
  contentTestId?: string
}

// The host never changes while a page is open: nothing to subscribe to.
const noSubscription = () => () => {}

/**
 * Frame of the pages people see before they have a session: login and the
 * LMS launch steps (consent, account choice, launch errors). A minimal
 * header with the host's wordmark (BenGER, or Vertretbar on its host) and
 * the language and theme controls, and the content centered below.
 *
 * The wordmark follows the hostname. The server renders the BenGER name;
 * the browser reads the host (useSyncExternalStore, no hydration mismatch).
 */
export function AuthPageFrame({
  children,
  showBackLink = true,
  width = 'md',
  contentTestId,
}: AuthPageFrameProps) {
  const { t } = useI18n()
  const brandName = useSyncExternalStore(
    noSubscription,
    () => getHostBrandName(),
    () => 'BenGER',
  )
  const isVtr = useSyncExternalStore(
    noSubscription,
    () => isStudentLockedHost(),
    () => false,
  )

  return (
    <div className="min-h-screen bg-white dark:bg-zinc-900">
      <header className="relative z-10">
        <nav
          className="mx-auto flex max-w-7xl items-center justify-between p-6 lg:px-8"
          aria-label="Global"
        >
          <div className="flex lg:flex-1">
            <Link href="/" className="-m-1.5 p-1.5">
              <span className="sr-only">{brandName}</span>
              <div
                className="flex items-center gap-2 text-xl font-bold text-zinc-900 dark:text-white"
                data-testid="auth-brand"
              >
                {isVtr ? (
                  <VertretbarMarkIcon className="h-7 w-7 text-emerald-500" />
                ) : (
                  <span className="text-2xl">🤘</span>
                )}
                <span>{brandName}</span>
              </div>
            </Link>
          </div>

          <div
            className="flex items-center gap-4"
            data-testid="auth-navigation-safe-zone"
          >
            {showBackLink && (
              <Link
                href="/"
                className="text-sm text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white"
              >
                {t('login.backToLanding')}
              </Link>
            )}
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

      <main className="flex min-h-[calc(100vh-80px)] items-center justify-center px-6 py-12 lg:px-8">
        <div
          className={`w-full space-y-8 ${width === 'lg' ? 'max-w-2xl' : 'max-w-md'}`}
          data-testid={contentTestId}
        >
          {children}
        </div>
      </main>
    </div>
  )
}

export default AuthPageFrame

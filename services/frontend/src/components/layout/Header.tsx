'use client'

import clsx from 'clsx'
import { motion } from 'framer-motion'
import Link from 'next/link'
import { forwardRef } from 'react'

import { AuthButton } from '@/components/auth/AuthButton'
import { LanguageSwitcher } from '@/components/layout/LanguageSwitcher'
import { Logo } from '@/components/layout/Logo'
import { MobileNavigation } from '@/components/layout/MobileNavigation'
import { NotificationBell } from '@/components/layout/NotificationBell'
import {
  useIsPublicShell,
  useShellSidebar,
} from '@/components/layout/ShellVariant'
import { ThemeToggle } from '@/components/layout/ThemeToggle'
import { MobileSearch, Search } from '@/components/shared/Search'
import { useI18n } from '@/contexts/I18nContext'
import { CloseButton } from '@headlessui/react'

// Hamburger menu button component
function HamburgerMenu() {
  const { t } = useI18n()
  const { showSidebar, toggle } = useShellSidebar()

  return (
    <button
      type="button"
      onClick={toggle}
      aria-expanded={showSidebar}
      className="flex h-8 w-8 items-center justify-center rounded-md text-zinc-600 transition-colors hover:bg-zinc-100 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-white"
      aria-label={
        showSidebar ? t('header.hideSidebar') : t('header.showSidebar')
      }
    >
      <svg
        className="h-4 w-4"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        {/* Always show hamburger icon (three horizontal lines) */}
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M3 6h18M3 12h18M3 18h18"
        />
      </svg>
    </button>
  )
}

export const Header = forwardRef<
  React.ElementRef<'div'>,
  React.ComponentPropsWithoutRef<typeof motion.div>
>(function Header({ className, ...props }, ref) {
  // Visitors get the same header without the parts that need a session:
  // search (its index and project lookup are the workspace's) and the
  // notification bell. The logo leads home instead of to the dashboard.
  const isPublic = useIsPublicShell()
  const homeHref = isPublic ? '/' : '/dashboard'
  const homeLabel = isPublic ? 'BenGER' : 'Dashboard'

  return (
    <motion.div
      {...props}
      ref={ref}
      className={clsx(
        className,
        'fixed top-0 z-50 flex h-14 items-center gap-2 transition sm:px-6 lg:z-40 lg:gap-12 lg:px-8',
        // Mobile: items start from left, Desktop: space between items
        'justify-start lg:justify-between',
        // Full width header
        'right-0 left-0 pr-3 pl-1 lg:pl-8',
        // Opaque background (no transparency)
        'bg-white dark:bg-zinc-900',
        // Bottom border matching sidebar style
        'border-b border-zinc-900/10 dark:border-white/10',
      )}
    >
      <div className="hidden items-center gap-3 lg:flex lg:max-w-xl lg:flex-1">
        {/* BenGer Logo - Desktop only */}
        <Link
          href={homeHref}
          aria-label={homeLabel}
          className="flex items-center"
        >
          <Logo className="h-6" />
        </Link>

        {/* Hamburger Menu - Desktop only */}
        <HamburgerMenu />

        {!isPublic && (
          <div className="hidden flex-1 lg:ml-16 lg:block">
            <Search />
          </div>
        )}
      </div>
      <div className="flex items-center gap-2 min-[360px]:gap-3 sm:gap-5 lg:hidden">
        <MobileNavigation />
        <CloseButton as={Link} href={homeHref} aria-label={homeLabel}>
          <Logo className="h-6" />
        </CloseButton>
      </div>
      <div className="ml-auto flex items-center gap-2 min-[360px]:gap-3 sm:gap-5 lg:ml-0">
        <div className="flex gap-2 min-[360px]:gap-3 sm:gap-4">
          {!isPublic && <MobileSearch />}
          <LanguageSwitcher />
          <ThemeToggle />
          {!isPublic && <NotificationBell />}
        </div>
        {/* Signed in, the account menu (a compact pill on phones) is the
            only way to profile and sign-out, so it always shows. A visitor's
            two buttons do not fit a phone header; the sidebar and the hero
            offer sign-in and sign-up there. */}
        <div className={isPublic ? 'hidden min-[416px]:contents' : 'contents'}>
          <AuthButton />
        </div>
      </div>
    </motion.div>
  )
})

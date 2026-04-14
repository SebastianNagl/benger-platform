'use client'

import { useHydration } from '@/hooks/useHydration'
import { useUIStore } from '@/stores'
import clsx from 'clsx'
import { motion } from 'framer-motion'
import Link from 'next/link'
import { forwardRef } from 'react'

import { AuthButton } from '@/components/auth/AuthButton'
import { useI18n } from '@/contexts/I18nContext'
import { LanguageSwitcher } from '@/components/layout/LanguageSwitcher'
import { Logo } from '@/components/layout/Logo'
import {
  MobileNavigation,
  useIsInsideMobileNavigation,
  useMobileNavigationStore,
} from '@/components/layout/MobileNavigation'
import { NotificationBell } from '@/components/layout/NotificationBell'
import { ThemeToggle } from '@/components/layout/ThemeToggle'
import { MobileSearch, Search } from '@/components/shared/Search'
import { CloseButton } from '@headlessui/react'

// Hamburger menu button component
function HamburgerMenu() {
  const { t } = useI18n()
  const { isSidebarHidden, toggleSidebar } = useUIStore()
  const isHydrated = useHydration()

  // During SSR or before hydration, show the sidebar to prevent layout shift
  // After hydration, use the actual state
  const showSidebar = isHydrated ? !isSidebarHidden : true

  return (
    <button
      type="button"
      onClick={toggleSidebar}
      className="flex h-8 w-8 items-center justify-center rounded-md text-zinc-600 transition-colors hover:bg-zinc-100 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-white"
      aria-label={showSidebar ? t('header.hideSidebar') : t('header.showSidebar')}
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
  let { isOpen: mobileNavIsOpen } = useMobileNavigationStore()
  let isInsideMobileNavigation = useIsInsideMobileNavigation()
  const { isSidebarHidden } = useUIStore()
  const isHydrated = useHydration()

  // During SSR or before hydration, show the sidebar to prevent layout shift
  // After hydration, use the actual state
  const showSidebar = isHydrated ? !isSidebarHidden : true

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
        'left-0 right-0 pl-1 pr-4 lg:pl-8',
        // Opaque background (no transparency)
        'bg-white dark:bg-zinc-900',
        // Bottom border matching sidebar style
        'border-b border-zinc-900/10 dark:border-white/10'
      )}
    >
      <div className="hidden items-center gap-3 lg:flex lg:max-w-xl lg:flex-1">
        {/* BenGer Logo - Desktop only */}
        <Link
          href="/dashboard"
          aria-label="Dashboard"
          className="flex items-center"
        >
          <Logo className="h-6" />
        </Link>

        {/* Hamburger Menu - Desktop only */}
        <HamburgerMenu />

        <div className="hidden flex-1 lg:ml-16 lg:block">
          <Search />
        </div>
      </div>
      <div className="flex items-center gap-5 lg:hidden">
        <MobileNavigation />
        <CloseButton as={Link} href="/dashboard" aria-label="Dashboard">
          <Logo className="h-6" />
        </CloseButton>
      </div>
      <div className="ml-auto flex items-center gap-5 lg:ml-0">
        <div className="flex gap-4">
          <MobileSearch />
          <LanguageSwitcher />
          <ThemeToggle />
          <NotificationBell />
        </div>
        <div className="hidden min-[416px]:contents">
          <AuthButton />
        </div>
      </div>
    </motion.div>
  )
})

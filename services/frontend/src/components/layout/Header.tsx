'use client'

import clsx from 'clsx'
import { motion } from 'framer-motion'
import Link from 'next/link'
import { forwardRef, useRef } from 'react'

import { AuthButton } from '@/components/auth/AuthButton'
import { LanguageSwitcher } from '@/components/layout/LanguageSwitcher'
import { Logo } from '@/components/layout/Logo'
import { MobileNavigation } from '@/components/layout/MobileNavigation'
import { NotificationBell } from '@/components/layout/NotificationBell'
import { usePublicNavigation } from '@/components/layout/PublicNavigation'
import {
  isHoverPointer,
  SIDEBAR_ID,
  SIDEBAR_TOGGLE_ID,
  useIsPublicShell,
  useShellSidebar,
  useSidebarPeekStore,
} from '@/components/layout/ShellVariant'
import { ThemeToggle } from '@/components/layout/ThemeToggle'
import { MobileSearch, Search } from '@/components/shared/Search'
import { useI18n } from '@/contexts/I18nContext'
import { CloseButton } from '@headlessui/react'

/**
 * The hamburger of the signed-in top bar. A click pins the sidebar open or
 * collapses it. While it is collapsed, pointing at the hamburger peeks it:
 * the sidebar floats above the page until the pointer leaves both.
 */
function HamburgerMenu() {
  const { t } = useI18n()
  const { showSidebar, toggle } = useShellSidebar()
  const { show, hideSoon, hide } = useSidebarPeekStore()
  // Right after collapsing the sidebar with a click the pointer is still on
  // the hamburger; it must leave once before hovering peeks again.
  const suppressPeek = useRef(false)

  return (
    <button
      type="button"
      id={SIDEBAR_TOGGLE_ID}
      onClick={() => {
        if (showSidebar) suppressPeek.current = true
        hide()
        toggle()
      }}
      onPointerEnter={(event) => {
        if (!showSidebar && !suppressPeek.current && isHoverPointer(event))
          show()
      }}
      onPointerLeave={(event) => {
        suppressPeek.current = false
        if (!showSidebar && isHoverPointer(event)) hideSoon()
      }}
      aria-expanded={showSidebar}
      aria-controls={SIDEBAR_ID}
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
        aria-hidden="true"
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

/** Container shared by both versions of the top bar. */
const BAR_CLASSES = clsx(
  'fixed top-0 right-0 left-0 z-50 flex h-14 items-center transition lg:z-40',
  // Opaque background (no transparency)
  'bg-white dark:bg-zinc-900',
  // Bottom border matching sidebar style
  'border-b border-zinc-900/10 dark:border-white/10',
)

/**
 * The visitor top bar (landing page and public pages): logo, the visitor
 * navigation as items of the bar (a compact menu when they do not fit),
 * language, theme, sign in and sign up. No hamburger and no sidebar.
 */
function PublicHeader({
  className,
  ...props
}: React.ComponentPropsWithRef<typeof motion.div>) {
  const { inline, menu } = usePublicNavigation()

  return (
    <motion.div
      {...props}
      className={clsx(
        className,
        BAR_CLASSES,
        'gap-3 px-4 sm:gap-6 sm:px-6 lg:gap-8 lg:px-8',
      )}
      data-shell="public"
    >
      <Link href="/" aria-label="BenGER" className="flex shrink-0 items-center">
        <Logo className="h-6" />
      </Link>
      {inline}
      <div className="ml-auto flex shrink-0 items-center gap-3 sm:gap-5">
        <div className="flex items-center gap-3 sm:gap-4">
          <LanguageSwitcher />
          <ThemeToggle />
        </div>
        {/* Two buttons do not fit a small phone's bar; the menu and the hero
            offer sign-in and sign-up there. */}
        <div className="hidden min-[416px]:contents">
          <AuthButton />
        </div>
        {menu}
      </div>
    </motion.div>
  )
}

export const Header = forwardRef<
  React.ElementRef<'div'>,
  React.ComponentPropsWithoutRef<typeof motion.div>
>(function Header({ className, ...props }, ref) {
  const isPublic = useIsPublicShell()
  if (isPublic)
    return <PublicHeader {...props} ref={ref} className={className} />

  return (
    <motion.div
      {...props}
      ref={ref}
      className={clsx(
        className,
        BAR_CLASSES,
        'gap-2 pr-3 pl-1 sm:px-6 lg:gap-12 lg:px-8 lg:pl-8',
        // Mobile: items start from left, Desktop: space between items
        'justify-start lg:justify-between',
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
      <div className="flex items-center gap-2 min-[360px]:gap-3 sm:gap-5 lg:hidden">
        <MobileNavigation />
        <CloseButton as={Link} href="/dashboard" aria-label="Dashboard">
          <Logo className="h-6" />
        </CloseButton>
      </div>
      <div className="ml-auto flex items-center gap-2 min-[360px]:gap-3 sm:gap-5 lg:ml-0">
        <div className="flex gap-2 min-[360px]:gap-3 sm:gap-4">
          <MobileSearch />
          <LanguageSwitcher />
          <ThemeToggle />
          <NotificationBell />
        </div>
        {/* The account menu (a compact pill on phones) is the only way to
            profile and sign-out, so it always shows. */}
        <AuthButton />
      </div>
    </motion.div>
  )
})

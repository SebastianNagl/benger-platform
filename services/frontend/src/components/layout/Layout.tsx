'use client'

import { useAuth } from '@/contexts/AuthContext'
import { useHydration } from '@/hooks/useHydration'
import { isExtendedEdition, useResolvedUiMode } from '@/hooks/useResolvedUiMode'
import { useSlot } from '@/lib/extensions/slots'
import { useActiveExtensionsReady } from '@/lib/featureFlags'
import { sebNavigationTarget } from '@/lib/seb'
import { isExpertOnlyRoute } from '@/lib/utils/routeSurface'
import { motion } from 'framer-motion'
import { usePathname, useRouter } from 'next/navigation'
import { useEffect, useState, type FocusEvent } from 'react'

import { Footer } from '@/components/layout/Footer'
import { Header } from '@/components/layout/Header'
import { Navigation } from '@/components/layout/Navigation'
import {
  SectionProvider,
  type Section,
} from '@/components/layout/SectionProvider'
import {
  isHoverPointer,
  ShellVariantProvider,
  SIDEBAR_ID,
  SIDEBAR_TOGGLE_ID,
  useShellSidebar,
  useSidebarPeekStore,
  type ShellVariant,
} from '@/components/layout/ShellVariant'
import clsx from 'clsx'

export function Layout({
  children,
  allSections,
  variant = 'app',
}: {
  children: React.ReactNode
  allSections: Record<string, Array<Section>>
  /**
   * `public` renders the same shell for visitors (the landing page and the
   * public pages): no sidebar, the visitor navigation sits in the top bar.
   * See ShellVariant.tsx.
   */
  variant?: ShellVariant
}) {
  return (
    <ShellVariantProvider value={variant}>
      <ShellLayout allSections={allSections} variant={variant}>
        {children}
      </ShellLayout>
    </ShellVariantProvider>
  )
}

function ShellLayout({
  children,
  allSections,
  variant,
}: {
  children: React.ReactNode
  allSections: Record<string, Array<Section>>
  variant: ShellVariant
}) {
  let pathname = usePathname()
  const isHydrated = useHydration()
  const [isInitialRender, setIsInitialRender] = useState(true)
  const { isLoading } = useAuth()
  const resolvedUiMode = useResolvedUiMode()
  // Whether the runtime switch of the extended overlay is known for this
  // viewer (server answer or the last known value of this browser).
  const extensionsReady = useActiveExtensionsReady()
  const StudentShell = useSlot('StudentShell')
  // First-visit setup modal + role tour (extended). Mounted in both shells;
  // the slot decides itself whether there is anything to show.
  const GlobalOnboarding = useSlot('GlobalOnboarding')
  const router = useRouter()

  // Inside Safe Exam Browser the session stays on its exam page.
  useEffect(() => {
    const target = sebNavigationTarget(pathname)
    if (target && target !== pathname) router.replace(target)
  }, [pathname, router])

  const { showSidebar } = useShellSidebar()
  const isPublic = variant === 'public'

  // Track when initial render is complete
  useEffect(() => {
    if (isHydrated) {
      // Small delay to ensure layout is stable before enabling animations
      const timer = setTimeout(() => {
        setIsInitialRender(false)
      }, 100)
      return () => clearTimeout(timer)
    }
  }, [isHydrated])

  // Student/expert shell branch (Issue #35). Only the extended edition can ever
  // render the student shell — short-circuit entirely in community so the
  // expert layout never pays for the resolution dance. The visitor shell has
  // no session and therefore no mode to resolve.
  if (!isPublic && isExtendedEdition()) {
    // Until hydration completes or auth resolves, the resolved mode is not yet
    // trustworthy. Render a neutral skeleton rather than flashing the expert
    // layout to a student on first paint. The same holds until this viewer's
    // runtime extension switch is known (lib/featureFlags).
    if (!isHydrated || isLoading || !extensionsReady) {
      return (
        <div
          className="flex h-full w-full items-center justify-center"
          data-testid="ui-shell-skeleton"
          aria-hidden="true"
        >
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-zinc-300 border-t-emerald-500 dark:border-zinc-600 dark:border-t-emerald-400" />
        </div>
      )
    }

    // Student mode + a registered StudentShell slot → hand the whole app shell
    // to the extended package. If the slot is missing (community-style overlay
    // not loaded), fall through to the normal expert layout — never crash.
    // Expert-workbench routes keep the expert layout even for a user in
    // student mode: the student sidebar has no way back to them, and a
    // project page inside student chrome reads as the wrong product.
    if (
      resolvedUiMode === 'student' &&
      StudentShell &&
      !isExpertOnlyRoute(pathname)
    ) {
      return (
        <SectionProvider sections={allSections[pathname || '/'] ?? []}>
          {/* eslint-disable-next-line react-hooks/static-components */}
          <StudentShell>{children}</StudentShell>
          {/* eslint-disable-next-line react-hooks/static-components */}
          {GlobalOnboarding && <GlobalOnboarding shell="student" />}
        </SectionProvider>
      )
    }
  }

  return (
    <SectionProvider sections={allSections[pathname || '/'] ?? []}>
      <div className="flex h-full w-full">
        {/* Header/Navbar - Always visible */}
        <Header />

        {/* Sidebar: the visitor shell has none, its navigation lives in
            the top bar. */}
        {!isPublic && <Sidebar isInitialRender={isInitialRender} />}

        {/* Main content area */}
        <div className="min-w-0 flex-1">
          <div
            className={`relative flex h-full flex-col pt-14 print:ml-0 print:pt-0 ${showSidebar ? 'lg:ml-64 xl:ml-72 2xl:ml-80' : ''}`}
          >
            <main className={`w-full min-w-0 flex-auto`}>{children}</main>
            <Footer />
          </div>
        </div>
      </div>
      {/* eslint-disable-next-line react-hooks/static-components */}
      {GlobalOnboarding && !isPublic && <GlobalOnboarding shell="expert" />}
    </SectionProvider>
  )
}

/**
 * The desktop sidebar of the signed-in shell. Pinned open it pushes the
 * content aside; collapsed it can still be peeked (see useSidebarPeekStore):
 * it then floats above the page with a shadow and the content stays put.
 */
function Sidebar({ isInitialRender }: { isInitialRender: boolean }) {
  const { showSidebar } = useShellSidebar()
  const { isPeeking, show, hideSoon, hide } = useSidebarPeekStore()
  const isPeeked = isPeeking && !showSidebar
  const isVisible = showSidebar || isPeeked

  // Pinning the sidebar ends a peek, so unpinning it later does not leave
  // it floating.
  useEffect(() => {
    if (showSidebar) hide()
  }, [showSidebar, hide])

  // Peeking only matters while collapsed; pinned, these handlers do nothing.
  const peekHandlers = showSidebar
    ? {}
    : {
        onPointerEnter: (event: React.PointerEvent) => {
          if (isHoverPointer(event)) show()
        },
        onPointerLeave: (event: React.PointerEvent) => {
          if (isHoverPointer(event)) hideSoon()
        },
        // Tabbing into the collapsed sidebar reveals it, so keyboard focus
        // never lands on links nobody can see.
        onFocus: show,
        onBlur: (event: FocusEvent<HTMLElement>) => {
          if (!event.currentTarget.contains(event.relatedTarget as Node | null))
            hideSoon()
        },
        onKeyDown: (event: React.KeyboardEvent) => {
          if (event.key !== 'Escape') return
          hide()
          document.getElementById(SIDEBAR_TOGGLE_ID)?.focus()
        },
      }

  return (
    <motion.aside
      className="lg:pointer-events-none lg:fixed lg:inset-0 lg:z-30 lg:flex print:hidden"
      suppressHydrationWarning
    >
      <motion.div
        id={SIDEBAR_ID}
        data-testid="app-sidebar"
        data-sidebar-state={
          showSidebar ? 'pinned' : isPeeked ? 'peeked' : 'collapsed'
        }
        className={clsx(
          'lg:pointer-events-auto lg:w-64 lg:overflow-y-auto lg:border-r lg:border-zinc-900/10 lg:bg-white lg:px-6 lg:pt-4 lg:pb-8 xl:w-72 2xl:w-80 lg:dark:border-white/10 lg:dark:bg-zinc-900',
          // Floating above the page while peeked.
          isPeeked &&
            'lg:shadow-2xl lg:shadow-zinc-900/20 lg:dark:shadow-black/60',
        )}
        initial={false}
        animate={{
          x: isVisible ? 0 : -320,
          opacity: isVisible ? 1 : 0,
        }}
        transition={
          isInitialRender
            ? { duration: 0 } // No animation on initial render
            : {
                type: 'spring',
                stiffness: 300,
                damping: 30,
              }
        }
        {...peekHandlers}
      >
        <Navigation className="hidden lg:mt-16 lg:block" />
      </motion.div>
    </motion.aside>
  )
}

'use client'

import { useAuth } from '@/contexts/AuthContext'
import { useHydration } from '@/hooks/useHydration'
import { isExtendedEdition, useResolvedUiMode } from '@/hooks/useResolvedUiMode'
import { useSlot } from '@/lib/extensions/slots'
import { useUIStore } from '@/stores'
import { motion } from 'framer-motion'
import { usePathname } from 'next/navigation'
import { useEffect, useState } from 'react'

import { Footer } from '@/components/layout/Footer'
import { Header } from '@/components/layout/Header'
import { Navigation } from '@/components/layout/Navigation'
import {
  SectionProvider,
  type Section,
} from '@/components/layout/SectionProvider'

export function Layout({
  children,
  allSections,
}: {
  children: React.ReactNode
  allSections: Record<string, Array<Section>>
}) {
  let pathname = usePathname()
  const { isSidebarHidden } = useUIStore()
  const isHydrated = useHydration()
  const [isInitialRender, setIsInitialRender] = useState(true)
  const { isLoading } = useAuth()
  const resolvedUiMode = useResolvedUiMode()
  const StudentShell = useSlot('StudentShell')

  // During SSR or before hydration, show the sidebar to prevent layout shift
  // After hydration, use the actual state
  const showSidebar = isHydrated ? !isSidebarHidden : true

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
  // expert layout never pays for the resolution dance.
  if (isExtendedEdition()) {
    // Until hydration completes or auth resolves, the resolved mode is not yet
    // trustworthy. Render a neutral skeleton rather than flashing the expert
    // layout to a student on first paint.
    if (!isHydrated || isLoading) {
      return (
        <div
          className="flex h-full w-full items-center justify-center"
          data-testid="ui-shell-skeleton"
          aria-hidden="true"
        >
          <div className="h-8 w-8 animate-spin rounded-full border-b-2 border-emerald-500" />
        </div>
      )
    }

    // Student mode + a registered StudentShell slot → hand the whole app shell
    // to the extended package. If the slot is missing (community-style overlay
    // not loaded), fall through to the normal expert layout — never crash.
    if (resolvedUiMode === 'student' && StudentShell) {
      return (
        <SectionProvider sections={allSections[pathname || '/'] ?? []}>
          {/* eslint-disable-next-line react-hooks/static-components */}
          <StudentShell>{children}</StudentShell>
        </SectionProvider>
      )
    }
  }

  return (
    <SectionProvider sections={allSections[pathname || '/'] ?? []}>
      <div className="flex h-full w-full">
        {/* Header/Navbar - Always visible */}
        <Header />

        {/* Sidebar - Can be hidden */}
        <motion.aside
          className="lg:pointer-events-none lg:fixed lg:inset-0 lg:z-30 lg:flex"
          suppressHydrationWarning
        >
          <motion.div
            className="lg:pointer-events-auto lg:w-64 lg:overflow-y-auto lg:border-r lg:border-zinc-900/10 lg:bg-white lg:px-6 lg:pb-8 lg:pt-4 lg:dark:border-white/10 lg:dark:bg-zinc-900 xl:w-72 2xl:w-80"
            initial={false}
            animate={{
              x: showSidebar ? 0 : -320,
              opacity: showSidebar ? 1 : 0,
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
          >
            <Navigation className="hidden lg:mt-16 lg:block" />
          </motion.div>
        </motion.aside>

        {/* Main content area */}
        <div className="min-w-0 flex-1">
          <div
            className={`relative flex h-full flex-col pt-14 ${showSidebar ? 'lg:ml-64 xl:ml-72 2xl:ml-80' : ''}`}
          >
            <main className={`w-full min-w-0 flex-auto`}>{children}</main>
            <Footer />
          </div>
        </div>
      </div>
    </SectionProvider>
  )
}

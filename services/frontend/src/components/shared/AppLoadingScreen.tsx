'use client'

import { useShellSidebar } from '@/components/layout/ShellVariant'

import { LoadingSpinner } from './LoadingSpinner'

interface AppLoadingScreenProps {
  /** Line under the spinner; without one the line stays empty. */
  label?: string
  testId?: string
  /**
   * Whether the screen covers the app. A page's own loading state passes
   * false: the shell stays visible and usable, and the spinner sits exactly
   * where the full-viewport screen had it, so the hand-over does not move it.
   */
  covering?: boolean
}

/**
 * The full-viewport loading screen of the app's start: checking the session
 * (ConditionalLayout), waiting for the shell's inputs (Layout) and the
 * redirect to the login (ProtectedRoute). One component, so the spinner
 * stays in the same place when one of these waits hands over to the next;
 * the label line is always there, empty or not, for the same reason.
 *
 * Where the shell will show the pinned desktop sidebar, the spinner centers
 * on the content area next to it (the same offset as Layout's main column),
 * so it does not jump sideways when a page's own spinner takes over.
 */
export function AppLoadingScreen({
  label,
  testId,
  covering = true,
}: AppLoadingScreenProps) {
  const { showSidebar } = useShellSidebar()
  return (
    <div
      className={`fixed inset-0 flex items-center justify-center ${covering ? 'z-50 bg-white dark:bg-zinc-900' : 'pointer-events-none'} ${showSidebar ? 'lg:pl-64 xl:pl-72 2xl:pl-80' : ''}`}
      data-testid={testId}
      data-sidebar-offset={showSidebar ? 'true' : undefined}
      role="status"
      aria-busy="true"
    >
      <div className="text-center">
        <LoadingSpinner className="mx-auto mb-4" />
        <p className="min-h-6 text-zinc-600 dark:text-zinc-400">{label}</p>
      </div>
    </div>
  )
}

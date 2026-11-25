import { LoadingSpinner } from './LoadingSpinner'

interface AppLoadingScreenProps {
  /** Line under the spinner; without one the line stays empty. */
  label?: string
  testId?: string
}

/**
 * The full-viewport loading screen of the app's start: checking the session
 * (ConditionalLayout), waiting for the shell's inputs (Layout) and the
 * redirect to the login (ProtectedRoute). One component, so the spinner
 * stays in the same place when one of these waits hands over to the next;
 * the label line is always there, empty or not, for the same reason.
 */
export function AppLoadingScreen({ label, testId }: AppLoadingScreenProps) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-white dark:bg-zinc-900"
      data-testid={testId}
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

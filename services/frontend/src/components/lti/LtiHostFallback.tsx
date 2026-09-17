/**
 * Community-edition notice for the public LMS host routes (consent, account
 * linking, link confirmation).
 *
 * Those routes are standalone (no app layout), so the notice centres itself
 * in the viewport. The LMS flows themselves ship in the extended package.
 */
export function LtiHostFallback({ message }: { message: string }) {
  return (
    <div
      className="flex min-h-screen items-center justify-center px-4"
      data-testid="lti-host-fallback"
    >
      <p className="max-w-md text-center text-zinc-500 dark:text-zinc-400">
        {message}
      </p>
    </div>
  )
}

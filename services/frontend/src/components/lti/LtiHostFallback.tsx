/**
 * Community-edition notice for the public LMS host routes (consent, account
 * linking, link confirmation).
 *
 * Those routes are standalone; app/lti/layout.tsx frames and centres them.
 * The LMS flows themselves ship in the extended package.
 */
export function LtiHostFallback({ message }: { message: string }) {
  return (
    <div className="flex justify-center" data-testid="lti-host-fallback">
      <p className="max-w-md text-center text-zinc-500 dark:text-zinc-400">
        {message}
      </p>
    </div>
  )
}

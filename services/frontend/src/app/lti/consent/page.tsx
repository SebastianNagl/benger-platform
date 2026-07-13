'use client'

import { useSlot } from '@/lib/extensions/slots'

/**
 * Host route for the LTI account-linking consent step.
 *
 * Students arriving from a Moodle launch pass through here when their LTI
 * identity is not yet linked to a platform account. The consent flow itself
 * lives in the proprietary extended package; the open-core platform only
 * provides the route and a graceful fallback.
 */
export default function LtiConsentPage() {
  const LtiConsentGate = useSlot('LtiConsentGate')

  if (!LtiConsentGate) {
    return (
      <div className="flex min-h-[400px] items-center justify-center">
        <p className="text-zinc-500 dark:text-zinc-400">
          LTI account linking requires the extended edition.
        </p>
      </div>
    )
  }

  // eslint-disable-next-line react-hooks/static-components
  return <LtiConsentGate />
}

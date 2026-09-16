'use client'

import { LtiHostFallback } from '@/components/lti/LtiHostFallback'
import { useI18n } from '@/contexts/I18nContext'
import { useSlot } from '@/lib/extensions/slots'
import { Suspense } from 'react'

/**
 * Host route for the LMS consent step.
 *
 * Consent comes first: a launch without current consent parks the verified
 * launch on the server and sends the browser here (`?rl=<link>&p=<handle>`).
 * No account or session exists yet, so the route is public and standalone
 * (see authRedirect.publicRoutes and ConditionalLayout.standalonePages). The
 * consent form ships in the extended package as the LtiConsentGate slot; it
 * reads its query parameters itself. The community edition renders a
 * neutral notice.
 */
export default function LtiConsentPage() {
  const LtiConsentGate = useSlot('LtiConsentGate')
  const { t } = useI18n()

  if (!LtiConsentGate) {
    return <LtiHostFallback message={t('ltiHost.fallback.consent')} />
  }

  // useSearchParams inside the slot needs a Suspense boundary for static
  // prerendering in the App Router.
  return (
    <Suspense fallback={null}>
      {/* eslint-disable-next-line react-hooks/static-components */}
      <LtiConsentGate />
    </Suspense>
  )
}

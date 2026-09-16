'use client'

import { LtiHostFallback } from '@/components/lti/LtiHostFallback'
import { useI18n } from '@/contexts/I18nContext'
import { useSlot } from '@/lib/extensions/slots'
import { Suspense } from 'react'

/**
 * Host route for the existing-account step of an LMS launch.
 *
 * After consent, when an account with the LMS address already exists, the
 * browser lands here (`?p=<handle>`) to prove ownership (password login or
 * an emailed confirmation link) or to continue with a separate account.
 * Nothing is linked yet and no session exists, so the route is public and
 * standalone. The choice UI ships in the extended package as the
 * LtiIdentityChoice slot, bound to the parked launch; it reads its query
 * parameters itself. The community edition renders a neutral notice.
 */
export default function LtiLinkAccountPage() {
  const LtiIdentityChoice = useSlot('LtiIdentityChoice')
  const { t } = useI18n()

  if (!LtiIdentityChoice) {
    return <LtiHostFallback message={t('ltiHost.fallback.linkAccount')} />
  }

  // useSearchParams inside the slot needs a Suspense boundary for static
  // prerendering in the App Router.
  return (
    <Suspense fallback={null}>
      {/* eslint-disable-next-line react-hooks/static-components */}
      <LtiIdentityChoice />
    </Suspense>
  )
}

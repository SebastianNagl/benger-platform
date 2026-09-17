'use client'

import { LtiHostFallback } from '@/components/lti/LtiHostFallback'
import { useI18n } from '@/contexts/I18nContext'
import { useSlot } from '@/lib/extensions/slots'
import { useParams } from 'next/navigation'

/**
 * Host route for the mailed account-link confirmation
 * (`/lti/link-confirm/<token>`).
 *
 * The link is opened from a mailbox, on any device and usually without a
 * session, so the route is public and standalone. Loading the page changes
 * nothing: the LtiLinkConfirm slot (extended package) uses the token only
 * when the reader presses its button, so mail scanners that fetch the link
 * do not consume it. The community edition renders a neutral notice.
 */
export default function LtiLinkConfirmPage() {
  const params = useParams<{ token: string }>()
  const token = params?.token ?? ''
  const LtiLinkConfirm = useSlot('LtiLinkConfirm')
  const { t } = useI18n()

  if (!LtiLinkConfirm) {
    return <LtiHostFallback message={t('ltiHost.fallback.linkConfirm')} />
  }

  // eslint-disable-next-line react-hooks/static-components
  return <LtiLinkConfirm token={token} />
}

'use client'

import { StudentSlotFallback } from '@/components/student/StudentSlotFallback'
import { useSlot } from '@/lib/extensions/slots'
import { useParams } from 'next/navigation'

/**
 * Host route for the exam-share join page (Issue #35).
 *
 * An invitee opens /shares/<token> from a share link. The proprietary join UI
 * (preview, password, GDPR consent) ships in the extended package as the
 * StudentShareJoin slot; the community edition renders the neutral fallback.
 *
 * Registered as a public + standalone route (see authRedirect.publicRoutes and
 * ConditionalLayout.standalonePages) so a logged-out invitee lands here instead
 * of being bounced to /login with the token lost — the slot itself routes them
 * through login/sign-up with a ?next back to this page.
 */
export default function ShareJoinPage() {
  const params = useParams<{ token: string }>()
  const token = params!.token
  const StudentShareJoin = useSlot('StudentShareJoin')

  if (!StudentShareJoin) {
    return <StudentSlotFallback />
  }

  // eslint-disable-next-line react-hooks/static-components
  return <StudentShareJoin token={token} />
}

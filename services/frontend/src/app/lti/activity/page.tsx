'use client'

import { useSlot } from '@/lib/extensions/slots'
import { useSearchParams } from 'next/navigation'
import { Suspense, type ComponentType } from 'react'

/** Props the activity view slot receives, read from the launch redirect. */
interface LtiActivityViewProps {
  /** `rl`: the LMS activity (resource link) the view shows. */
  resourceLinkId: string
  /** `lti_u`: the account the launch signed in (session guard). */
  expectedUserId: string
  /**
   * `lti_ui`: the UI mode the launch asked for, as it was on the first
   * render. The layout already applies it (StudentModeRedirect removes it
   * from the address bar afterwards), so views should follow the resolved
   * UI mode and treat this as informational.
   */
  requestedUiMode: 'student' | 'expert' | null
}

function readUiMode(value: string | null): 'student' | 'expert' | null {
  return value === 'student' || value === 'expert' ? value : null
}

function ActivityViewWithQuery({
  View,
}: {
  View: ComponentType<LtiActivityViewProps>
}) {
  const params = useSearchParams()
  return (
    <View
      resourceLinkId={params?.get('rl') ?? ''}
      expectedUserId={params?.get('lti_u') ?? ''}
      requestedUiMode={readUiMode(params?.get('lti_ui') ?? null)}
    />
  )
}

/**
 * Host route for the teacher view of one LMS activity.
 *
 * An instructor who launches an activity that already points at an exam
 * lands here (`?rl=<link>&lti_u=<user>&lti_ui=<mode>`): every consented
 * participant with the grades the tool holds and what was sent to the
 * learning platform. The route needs a session and keeps the app layout, so
 * it renders in the expert shell on the main host and in the student shell
 * on a student host (the one-shot `lti_ui` decides, see
 * StudentModeRedirect). The view ships in the extended package as the
 * LtiActivityView slot; the open-core platform only provides the route and
 * a graceful fallback, like the link picker route (/lti/link).
 */
export default function LtiActivityPage() {
  const LtiActivityView = useSlot('LtiActivityView')

  if (!LtiActivityView) {
    return (
      <div className="flex min-h-[400px] items-center justify-center">
        <p className="text-zinc-500 dark:text-zinc-400">
          The LMS activity view requires the extended edition.
        </p>
      </div>
    )
  }

  // useSearchParams needs a Suspense boundary for static prerendering in
  // the App Router.
  return (
    <Suspense fallback={null}>
      <ActivityViewWithQuery View={LtiActivityView} />
    </Suspense>
  )
}

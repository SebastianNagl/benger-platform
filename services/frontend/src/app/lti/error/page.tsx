'use client'

import { useSlot } from '@/lib/extensions/slots'
import { useSearchParams } from 'next/navigation'
import { Suspense } from 'react'

/**
 * Host route for LTI launch errors.
 *
 * The API's LTI endpoints redirect the browser here with ?code=<reason>
 * whenever a launch cannot complete. Unlike the other LTI host routes, the
 * community fallback is fully functional: launches can fail on a community
 * install too (misconfigured registration, blocked cookies, ...), so the
 * platform must render a human-readable explanation without the extended
 * package. The extended edition may register a richer 'LtiLaunchError' slot
 * (retry actions, support links) that replaces this fallback.
 */

const ERROR_MESSAGES: Record<string, string> = {
  invalid_request:
    'The launch request from your learning platform was incomplete or malformed. Go back to your learning platform and open the activity again.',
  registration_not_found:
    'This learning platform is not registered with the platform. Ask an administrator to create the LTI registration first.',
  registration_disabled:
    'The LTI registration for this learning platform is disabled. Ask an administrator to re-enable it.',
  org_inactive:
    'The organization that runs this connection is deactivated. Contact the operator of this platform.',
  tool_not_configured:
    'The tool is not set up on this platform yet. Contact the operator of this platform.',
  deployment_disabled:
    'This activity (deployment) is switched off in the connection. Ask the organization admin to enable it again.',
  state_unavailable:
    'The launch could not be stored right now because of a temporary server problem. This is not caused by your browser. Try again in a few minutes.',
  invalid_state:
    'This launch link has expired or was already used. Go back to your learning platform and click the activity again.',
  invalid_token:
    'The identity token from your learning platform could not be verified. Go back and try again; if this keeps happening, the registration keys may be out of date.',
  nonce_mismatch:
    'The launch could not be verified because it did not match the login it started from. Go back to your learning platform and click the activity again.',
  nonce_reused:
    'This launch link has expired or was already used. Go back to your learning platform and click the activity again.',
  unknown_deployment:
    'This course connection is not known to the platform. Ask an administrator to add the deployment to the LTI registration.',
  unsupported_message:
    'This type of LTI message is not supported by the platform.',
  not_linked: 'Your instructor has not connected this activity to an exam yet.',
  exam_unavailable:
    'The exam linked to this activity no longer exists. Contact your instructor.',
  user_inactive:
    'Your account on this platform is deactivated. Contact your instructor or an administrator.',
  membership_removed:
    'Your membership in the organization of this connection was removed. Contact the organization admin.',
  launch_expired:
    'This sign-in has expired or was already completed. Go back to your learning platform and open the activity again.',
  launch_mismatch:
    'This page belongs to another sign-in or another browser. Go back to your learning platform and open the activity again.',
  link_proof_failed:
    'The confirmation link is invalid, expired or already used. Open the activity again and request a new link.',
  account_not_linkable:
    'This account cannot be linked to a learning platform. Open the activity again and continue with a separate account.',
  internal:
    'Something went wrong on our side while processing the launch. Please try again in a moment.',
}

const DEFAULT_MESSAGE =
  'The launch could not be completed. Go back to your learning platform and click the activity again; if the problem persists, contact your instructor.'

function LtiErrorFallback() {
  const searchParams = useSearchParams()
  const code = searchParams?.get('code') ?? ''
  const message = ERROR_MESSAGES[code] ?? DEFAULT_MESSAGE

  return (
    <div className="flex min-h-[400px] items-center justify-center px-4">
      <div className="max-w-md text-center">
        <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">
          Launch failed
        </h1>
        <p className="mt-2 text-zinc-600 dark:text-zinc-400">{message}</p>
        {code ? (
          <p className="mt-4 text-xs text-zinc-400 dark:text-zinc-500">
            Error code: {code}
          </p>
        ) : null}
      </div>
    </div>
  )
}

export default function LtiErrorPage() {
  const LtiLaunchError = useSlot('LtiLaunchError')

  // useSearchParams (used by the fallback, and likely by slot implementations)
  // requires a Suspense boundary for static prerendering in the App Router.
  if (LtiLaunchError) {
    return (
      <Suspense fallback={null}>
        {/* eslint-disable-next-line react-hooks/static-components */}
        <LtiLaunchError />
      </Suspense>
    )
  }

  return (
    <Suspense fallback={null}>
      <LtiErrorFallback />
    </Suspense>
  )
}

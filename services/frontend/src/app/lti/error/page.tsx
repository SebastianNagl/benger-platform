'use client'

import { ExclamationTriangleIcon } from '@heroicons/react/24/outline'
import { useSearchParams } from 'next/navigation'
import { Suspense } from 'react'

import { useI18n } from '@/contexts/I18nContext'
import { useSlot } from '@/lib/extensions/slots'
import {
  isLtiLaunchErrorCode,
  ltiErrorActions,
  type LtiErrorAction,
} from '@/lib/lti/launchErrors'

/**
 * Host route for LTI launch errors.
 *
 * The LTI endpoints redirect the browser here with ?code=<reason> (and
 * &ref=<id> for unexpected server errors) whenever a launch from a learning
 * platform cannot complete. The consent and account pages forward their
 * errors here too. Unlike the other LTI host routes, the community fallback
 * is a working page: it explains every code of lib/lti/launchErrors.ts in
 * the UI language and says who can fix the problem. The route is public and
 * standalone (see authRedirect.publicRoutes and ConditionalLayout). The
 * extended edition may register a richer 'LtiLaunchError' slot that
 * replaces this fallback.
 */

/** Actions that someone other than the person at the browser takes. */
const STAFF_ACTIONS: ReadonlySet<LtiErrorAction> = new Set<LtiErrorAction>([
  'orgAdmin',
  'lmsAdmin',
  'support',
])

// The page repeats both query values verbatim. Only well-formed values are
// shown, so a crafted link cannot place arbitrary text on the page.
const CODE_PATTERN = /^[a-z0-9_]{1,64}$/
const REF_PATTERN = /^[0-9a-f]{4,32}$/i

function LtiErrorFallback() {
  const { t } = useI18n()
  const searchParams = useSearchParams()
  const rawCode = searchParams?.get('code') ?? ''
  const rawRef = searchParams?.get('ref') ?? ''
  const code = CODE_PATTERN.test(rawCode) ? rawCode : ''
  const ref = REF_PATTERN.test(rawRef) ? rawRef : ''

  const message = isLtiLaunchErrorCode(code)
    ? t(`lti.error.codes.${code}`)
    : t('lti.error.default')
  const actions = ltiErrorActions(code)
  const showStudentHint = actions.some((action) => STAFF_ACTIONS.has(action))

  return (
    <div
      className="flex min-h-screen items-center justify-center px-4 py-10"
      data-testid="lti-error-fallback"
    >
      <div className="w-full max-w-md space-y-4 text-center">
        <ExclamationTriangleIcon
          aria-hidden="true"
          className="mx-auto h-10 w-10 text-amber-500"
        />
        <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">
          {t('lti.error.title')}
        </h1>
        <p
          className="text-zinc-600 dark:text-zinc-400"
          data-testid="lti-error-message"
        >
          {message}
        </p>
        <div className="rounded-lg bg-zinc-50 p-4 text-left dark:bg-zinc-800/60">
          <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
            {t('lti.error.actionsTitle')}
          </h2>
          <ul
            className="mt-2 list-disc space-y-1 pl-5 text-sm text-zinc-700 dark:text-zinc-300"
            data-testid="lti-error-actions"
          >
            {actions.map((action) => (
              <li key={action} data-testid={`lti-error-action-${action}`}>
                {t(`lti.error.actions.${action}`)}
              </li>
            ))}
          </ul>
          {showStudentHint ? (
            <p
              className="mt-2 text-sm text-zinc-500 dark:text-zinc-400"
              data-testid="lti-error-student-hint"
            >
              {t('lti.error.studentHint')}
            </p>
          ) : null}
        </div>
        {code ? (
          <p
            className="text-xs text-zinc-500 dark:text-zinc-400"
            data-testid="lti-error-code"
          >
            {t('lti.error.codeLabel')}:{' '}
            <span className="font-mono">{code}</span>
          </p>
        ) : null}
        {ref ? (
          <p
            className="text-xs text-zinc-500 dark:text-zinc-400"
            data-testid="lti-error-ref"
          >
            {t('lti.error.refLabel')}: <span className="font-mono">{ref}</span>
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

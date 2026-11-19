'use client'

/**
 * Host side of the compliance overlay's slots.
 *
 * The platform owns the routes under /compliance and the places where
 * compliance content appears on generic pages; the overlay
 * (`@benger/compliance`) registers the components. A compliance slot renders
 * only while the overlay's master flag `extension.compliance` is on for the
 * viewer (lib/extensions/active.ts) AND a component is registered for the
 * slot. The registry already hides the registrations of an inactive owner;
 * this gate checks the compliance flag itself as well, so a component
 * registered under the same name by another owner never shows while the
 * compliance overlay is off.
 *
 * Slots (CORE 2.63):
 *  - `ComplianceDashboard` on /compliance, no props.
 *  - `AssessmentDetail` on /compliance/assessments/[assessmentId], props
 *    `{ assessmentId }`.
 *  - `AnalysisRunFindings` on the analysis run page, props
 *    `{ projectId, run, estimates }` (the findings that cite the run).
 */

import { useI18n } from '@/contexts/I18nContext'
import { isExtensionLoaded } from '@/lib/extensions'
import { isExtensionEnabled } from '@/lib/extensions/enabled'
import { useSlot } from '@/lib/extensions/slots'
import {
  useActiveExtensionsReady,
  useExtensionActive,
} from '@/lib/featureFlags'
import type { ComponentType } from 'react'

/** Overlay id of the compliance package (master flag `extension.compliance`). */
export const COMPLIANCE_EXTENSION = 'compliance'

/** Slot names the compliance overlay fills. */
export const COMPLIANCE_SLOTS = {
  dashboard: 'ComplianceDashboard',
  assessmentDetail: 'AssessmentDetail',
  analysisRunFindings: 'AnalysisRunFindings',
} as const

export type ComplianceSlotName =
  (typeof COMPLIANCE_SLOTS)[keyof typeof COMPLIANCE_SLOTS]

export type ComplianceSlotState =
  | { status: 'loading'; Component: null }
  | { status: 'off'; Component: null }
  | { status: 'on'; Component: ComponentType<any> }

/**
 * The compliance component for `name`, or why there is none: `loading`
 * while the viewer's active overlays are not known yet (or the overlay this
 * build includes has not registered yet), `off` when the overlay is not
 * active for the viewer or registers no such slot.
 */
export function useComplianceSlot(
  name: ComplianceSlotName,
): ComplianceSlotState {
  const ready = useActiveExtensionsReady()
  const active = useExtensionActive(COMPLIANCE_EXTENSION)
  const Component = useSlot(name)
  if (!active) {
    return ready
      ? { status: 'off', Component: null }
      : { status: 'loading', Component: null }
  }
  if (Component) return { status: 'on', Component }
  if (
    isExtensionEnabled(COMPLIANCE_EXTENSION) &&
    !isExtensionLoaded(COMPLIANCE_EXTENSION)
  ) {
    return { status: 'loading', Component: null }
  }
  return { status: 'off', Component: null }
}

/** Notice shown on a /compliance route when the overlay is not available. */
export function ComplianceUnavailable() {
  const { t } = useI18n()
  return (
    <div
      className="flex min-h-[400px] flex-col items-center justify-center gap-2 px-4 text-center"
      data-testid="compliance-unavailable"
    >
      <h1 className="text-lg font-semibold text-zinc-900 dark:text-white">
        {t('compliance.unavailable.title')}
      </h1>
      <p className="max-w-md text-sm text-zinc-500 dark:text-zinc-400">
        {t('compliance.unavailable.description')}
      </p>
    </div>
  )
}

function ComplianceLoading() {
  const { t } = useI18n()
  return (
    <div
      className="flex min-h-[400px] items-center justify-center"
      data-testid="compliance-loading"
      role="status"
    >
      <p className="text-sm text-zinc-500 dark:text-zinc-400">
        {t('compliance.loading')}
      </p>
    </div>
  )
}

/**
 * A /compliance route: the overlay's page component, a loading state while
 * the viewer's overlays load, else the unavailable notice.
 */
export function ComplianceRouteShell({
  slot,
  props,
}: {
  slot: ComplianceSlotName
  props?: Record<string, unknown>
}) {
  const state = useComplianceSlot(slot)
  if (state.status === 'loading') return <ComplianceLoading />
  if (state.status === 'off') return <ComplianceUnavailable />
  const Component = state.Component
  return <Component {...(props ?? {})} />
}

/**
 * An inline compliance slot on a generic page: the overlay's component
 * while it is active, nothing otherwise (no placeholder, no loading state).
 */
export function ComplianceInlineSlot({
  slot,
  props,
}: {
  slot: ComplianceSlotName
  props?: Record<string, unknown>
}) {
  const state = useComplianceSlot(slot)
  if (state.status !== 'on') return null
  const Component = state.Component
  return <Component {...(props ?? {})} />
}

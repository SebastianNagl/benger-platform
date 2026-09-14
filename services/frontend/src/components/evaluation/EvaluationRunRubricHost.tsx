/**
 * Extension slot around the evaluation run page's content.
 *
 * A metric detail renderer (for a Bewertungsbogen, the filled sheet with step
 * titles and sections) may need to know which project the run belongs to in
 * order to resolve what a result references. The run page has no such context
 * of its own, so an edition that needs one registers a provider under
 * `EvaluationRunRubricHost`. Without a registration the children render
 * unchanged.
 *
 * Contract: slot name `EvaluationRunRubricHost`, props
 * `{ projectId: string; children: React.ReactNode }`.
 */

'use client'

import { useSlot } from '@/lib/extensions/slots'
import type { ReactNode } from 'react'

export const EVALUATION_RUN_RUBRIC_HOST_SLOT = 'EvaluationRunRubricHost'

export interface EvaluationRunRubricHostProps {
  projectId: string
  children: ReactNode
}

export function EvaluationRunRubricHost({
  projectId,
  children,
}: EvaluationRunRubricHostProps) {
  const Host = useSlot(EVALUATION_RUN_RUBRIC_HOST_SLOT)
  if (!Host) return <>{children}</>
  // The slot registry returns a module-level component, not one made here.
  // eslint-disable-next-line react-hooks/static-components
  return <Host projectId={projectId}>{children}</Host>
}

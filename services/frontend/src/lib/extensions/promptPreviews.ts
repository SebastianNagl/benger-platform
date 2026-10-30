/**
 * Per-metric prompt preview registry — the extension point for showing the
 * prompts of a proprietary evaluation method in the project page's Prompts
 * card, next to the generic judge prompts the platform resolves itself.
 *
 * Extended packages call `registerPromptPreview('korrektur_falloesung', C)`.
 * The Prompts card asks `getPromptPreview(metric)` for every configured
 * method and renders the component in that method's entry. Methods without
 * a preview fall back to the generic judge prompt (llm_judge_*) or a note
 * that the method assembles its prompt at grading time. Same owner and
 * precedence rules as ./metricEditors.ts.
 */

import type { ComponentType } from 'react'
import { isOwnerActive } from './active'
import {
  type RegistrationOwners,
  type RegistrationStacks,
  pushRegistration,
  recordRegistration,
  resolveRegistration,
} from './owner'

export interface PromptPreviewProps {
  /** Metric name the preview is rendered for. */
  metric: string
  /** The metric_parameters saved on this evaluation config. */
  parameters: Record<string, unknown>
  /** Sibling evaluation_configs on the same project. */
  siblingConfigs?: Array<{
    metric: string
    metric_parameters?: Record<string, unknown>
  }>
  /** Project the evaluation config belongs to. */
  projectId?: string
}

const previews: RegistrationStacks<ComponentType<PromptPreviewProps>> =
  new Map()
const previewOwners: RegistrationOwners = new Map()

export function registerPromptPreview(
  metric: string,
  component: ComponentType<PromptPreviewProps>,
) {
  recordRegistration(previewOwners, 'prompt preview', metric)
  pushRegistration(previews, metric, component)
}

export function getPromptPreview(
  metric: string,
): ComponentType<PromptPreviewProps> | null {
  return resolveRegistration(previews, metric, isOwnerActive) ?? null
}

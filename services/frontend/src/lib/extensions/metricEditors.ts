/**
 * Per-metric editor registry — the public extension point for surfacing
 * proprietary parameter UIs inside the Evaluation Configuration card without
 * the platform builder hardcoding metric names.
 *
 * Extended packages call `registerMetricEditor('korrektur_falloesung', Comp)`.
 * The platform's EvaluationBuilder asks `getMetricEditor(metricName)` and, if
 * a component is registered, renders it inside the metric's expansion area.
 * Each owner keeps one editor per metric; the newest one whose owner is
 * active counts (see ./active.ts), and a different owner registering a
 * metric logs a warning (see ./owner.ts).
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

export interface MetricEditorProps {
  /** The metric_parameters JSONB blob currently saved on this metric. */
  parameters: Record<string, unknown>
  /** Callback to merge a partial update into parameters. */
  onChange: (patch: Record<string, unknown>) => void
  /**
   * Metric name this editor instance is bound to. Editors registered for
   * multiple metrics (e.g. KorrekturMetricConfigEditor handles _classic /
   * _falloesung / _custom) can branch off this. Optional for backwards
   * compatibility with editors registered for a single metric.
   */
  metric?: string
  /**
   * Sibling evaluation_configs on the same project. Editors that mirror
   * configuration from another metric (e.g. korrektur_custom reading the
   * llm_judge_custom rubric) read this to find the source config.
   */
  siblingConfigs?: Array<{
    metric: string
    metric_parameters?: Record<string, unknown>
  }>
  /**
   * Project the evaluation config belongs to. Editors that fetch
   * project-scoped resources (e.g. the llm_judge_rubric editor listing
   * generation-config prompt structures) need this. Optional for backwards
   * compatibility with editors that don't fetch.
   */
  projectId?: string
}

const editors: RegistrationStacks<ComponentType<MetricEditorProps>> = new Map()
const editorOwners: RegistrationOwners = new Map()

export function registerMetricEditor(
  metric: string,
  component: ComponentType<MetricEditorProps>,
) {
  recordRegistration(editorOwners, 'metric editor', metric)
  pushRegistration(editors, metric, component)
}

export function getMetricEditor(
  metric: string,
): ComponentType<MetricEditorProps> | null {
  return resolveRegistration(editors, metric, isOwnerActive) ?? null
}

export function hasMetricEditor(metric: string): boolean {
  return getMetricEditor(metric) !== null
}

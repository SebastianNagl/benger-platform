/**
 * Per-metric editor registry — the public extension point for surfacing
 * proprietary parameter UIs inside the Evaluation Configuration card without
 * the platform builder hardcoding metric names.
 *
 * Extended packages call `registerMetricEditor('korrektur_falloesung', Comp)`.
 * The platform's EvaluationBuilder asks `getMetricEditor(metricName)` and, if
 * a component is registered, renders it inside the metric's expansion area.
 */

import type { ComponentType } from 'react'

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
}

const editors: Record<string, ComponentType<MetricEditorProps>> = {}

export function registerMetricEditor(
  metric: string,
  component: ComponentType<MetricEditorProps>,
) {
  editors[metric] = component
}

export function getMetricEditor(
  metric: string,
): ComponentType<MetricEditorProps> | null {
  return editors[metric] ?? null
}

export function hasMetricEditor(metric: string): boolean {
  return metric in editors
}

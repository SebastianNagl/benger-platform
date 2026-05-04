/**
 * Per-metric cell + detail renderer registry — the public extension point
 * for surfacing proprietary score-rendering UIs inside the platform's
 * evaluation tables and detail modals without the platform code knowing
 * about extended-only metrics.
 *
 * Mirrors `metricEditors.ts` (parameter UI editors) — same shape, different
 * surface.
 *
 * Extended packages call:
 *   registerMetricCell('korrektur_falloesung', (v) => v?.value ?? null)
 *   registerMetricDetail('korrektur_falloesung', KorrekturFalloesungDetail)
 *
 * The platform's table reads getMetricCell(metric); the platform's detail
 * modal reads getMetricDetail(metric). When a renderer is registered, it
 * overrides the generic display path. When none is registered, the platform
 * falls back to its built-in rendering.
 */

import type { ComponentType, ReactNode } from 'react'

/**
 * Pure cell renderer: receives the metric's value blob (typically the
 * `{value, method, details, error}` dict the workers persist) and returns
 * what the table cell should display. Returning `null` defers to the
 * platform's generic numeric-or-empty rendering.
 */
export type MetricCellRenderer = (value: unknown) => ReactNode

export interface MetricDetailProps {
  /** The metric's value blob (e.g. {value, method, details, error}). */
  value: unknown
  /** The full TaskEvaluation row, in case the detail view needs context
   *  (task_id, field_name, created_by, etc.). Optional — most renderers
   *  only need `value`. */
  evaluation?: Record<string, unknown>
}

const cellRenderers: Record<string, MetricCellRenderer> = {}
const detailRenderers: Record<string, ComponentType<MetricDetailProps>> = {}

export function registerMetricCell(metric: string, renderer: MetricCellRenderer) {
  cellRenderers[metric] = renderer
}

export function getMetricCell(metric: string): MetricCellRenderer | null {
  return cellRenderers[metric] ?? null
}

export function registerMetricDetail(
  metric: string,
  component: ComponentType<MetricDetailProps>,
) {
  detailRenderers[metric] = component
}

export function getMetricDetail(
  metric: string,
): ComponentType<MetricDetailProps> | null {
  return detailRenderers[metric] ?? null
}

export function hasMetricCell(metric: string): boolean {
  return metric in cellRenderers
}

export function hasMetricDetail(metric: string): boolean {
  return metric in detailRenderers
}

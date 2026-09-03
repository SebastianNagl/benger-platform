/**
 * Shared chart tokens for the report viewer.
 *
 * Series colors live in CSS custom properties set by `CHART_WRAPPER_CLASS`
 * so the same recharts markup adapts to dark mode. The pairs were checked
 * with the dataviz palette validator (light: emerald-500 / indigo-500,
 * dark: emerald-600 / indigo-500) for CVD separation and surface contrast.
 */
export const SERIES_COLOR = {
  model: 'var(--rv-model)',
  human: 'var(--rv-human)',
} as const

/** Put this on the element wrapping a recharts chart. `currentColor` drives axes and grid. */
export const CHART_WRAPPER_CLASS =
  '[--rv-model:#10b981] [--rv-human:#6366f1] dark:[--rv-model:#059669] dark:[--rv-human:#6366f1] text-zinc-500 dark:text-zinc-400'

export const AXIS_TICK = { fill: 'currentColor', fontSize: 12 } as const
export const AXIS_LINE = { stroke: 'currentColor', strokeOpacity: 0.3 } as const
export const GRID_STROKE_OPACITY = 0.15

/** Swatch classes for HTML legends (mirrors SERIES_COLOR). */
export const LEGEND_SWATCH_CLASS = {
  model: 'bg-emerald-500 dark:bg-emerald-600',
  human: 'bg-indigo-500',
} as const

/** Translation function shape used by every view component. */
export type TranslateFn = (
  key: string,
  fallback?: string,
  vars?: Record<string, string | number>,
) => string

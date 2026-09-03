import type { TranslateFn } from '../chartTheme'

/** Fallback-returning translate stub with {var} interpolation. */
export const t: TranslateFn = (key, fallback, vars) => {
  const base = fallback ?? key
  if (!vars) return base
  return base.replace(/\{(\w+)\}/g, (m, name) => (vars[name] !== undefined ? String(vars[name]) : m))
}

/** Recharts stand-in: renders enough DOM to assert series/keys. */
export function rechartsMock() {
  const React = require('react')
  const passthrough = (testId: string) =>
    function Mock({ children, ...props }: any) {
      const attrs: Record<string, string> = {}
      for (const [k, v] of Object.entries(props)) {
        if (typeof v === 'string' || typeof v === 'number') attrs[`data-${k.toLowerCase()}`] = String(v)
      }
      return React.createElement('div', { 'data-testid': testId, ...attrs }, children)
    }
  return {
    ResponsiveContainer: ({ children }: any) =>
      React.createElement('div', { 'data-testid': 'responsive-container', style: { width: 600, height: 300 } }, children),
    BarChart: ({ children, data, layout }: any) =>
      React.createElement(
        'div',
        { 'data-testid': 'bar-chart', 'data-layout': layout ?? 'horizontal', 'data-rows': String(data?.length ?? 0) },
        children,
      ),
    Bar: ({ children, dataKey, name, fill }: any) =>
      React.createElement('div', { 'data-testid': 'bar', 'data-key': String(dataKey), 'data-name': name, 'data-fill': fill }, children),
    ErrorBar: passthrough('error-bar'),
    CartesianGrid: passthrough('cartesian-grid'),
    XAxis: passthrough('x-axis'),
    YAxis: passthrough('y-axis'),
    Tooltip: ({ content }: any) => React.createElement('div', { 'data-testid': 'tooltip' }, content ?? null),
  }
}

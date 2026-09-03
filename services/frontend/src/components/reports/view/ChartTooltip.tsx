import type { ReactNode } from 'react'

export interface TooltipLine {
  label: string
  value: string
  swatchClass?: string
}

/** Theme-aware tooltip body shared by the report charts. */
export function ChartTooltipBox({ title, lines }: { title: ReactNode; lines: TooltipLine[] }) {
  return (
    <div
      className="rounded-md border border-zinc-200 bg-white px-3 py-2 text-xs shadow-md dark:border-zinc-700 dark:bg-zinc-900"
      data-testid="chart-tooltip"
    >
      <div className="mb-1 font-medium text-zinc-900 dark:text-white">{title}</div>
      <ul className="space-y-0.5">
        {lines.map((line) => (
          <li key={line.label} className="flex items-center gap-2 text-zinc-600 dark:text-zinc-300">
            {line.swatchClass && (
              <span className={`inline-block h-2.5 w-2.5 rounded-sm ${line.swatchClass}`} aria-hidden="true" />
            )}
            <span>{line.label}</span>
            <span className="ml-auto pl-3 tabular-nums text-zinc-900 dark:text-white">{line.value}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

/** HTML legend: identity never depends on color alone (swatch + text). */
export function ChartLegend({ items }: { items: Array<{ label: string; swatchClass: string }> }) {
  return (
    <ul className="mt-2 flex flex-wrap gap-4 text-xs text-zinc-600 dark:text-zinc-300" data-testid="chart-legend">
      {items.map((item) => (
        <li key={item.label} className="flex items-center gap-1.5">
          <span className={`inline-block h-2.5 w-2.5 rounded-sm ${item.swatchClass}`} aria-hidden="true" />
          {item.label}
        </li>
      ))}
    </ul>
  )
}

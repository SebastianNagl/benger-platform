import type { ReportConfigRef } from '@/types/report'
import clsx from 'clsx'
import type { TranslateFn } from './chartTheme'

interface ConfigSelectorProps {
  options: ReportConfigRef[]
  value: string | null
  onChange: (configId: string) => void
  t: TranslateFn
}

export function configOptionLabel(
  config: ReportConfigRef,
  siblings: ReportConfigRef[] = [],
): string {
  const judge = config.judge_label
  // Several configurations can use the same judge model (e.g. ×3 runs vs a
  // single run, or a multi-judge ensemble led by the same model). A bare
  // judge name would then repeat across buttons, so fall back to the
  // configuration's own name whenever another option carries the same judge.
  const judgeShared =
    !!judge &&
    siblings.some(
      (other) => other.id !== config.id && other.judge_label === judge,
    )
  if (judge && !judgeShared) return judge
  return config.name || judge || config.id || config.metric
}

/** Segmented control to switch between configs (judges) sharing the primary metric. */
export function ConfigSelector({
  options,
  value,
  onChange,
  t,
}: ConfigSelectorProps) {
  if (options.length < 2) return null
  return (
    <div
      className="flex items-center gap-2 text-sm"
      data-testid="config-selector"
    >
      <span className="text-zinc-500 dark:text-zinc-400">
        {t('reports.view.judge')}:
      </span>
      <div
        role="radiogroup"
        aria-label={t('reports.view.judge')}
        className="inline-flex max-w-full items-center gap-0.5 overflow-x-auto rounded-full bg-zinc-100 p-0.5 dark:bg-zinc-800"
      >
        {options.map((option) => {
          const active = option.id === value
          return (
            <button
              key={option.id}
              type="button"
              role="radio"
              aria-checked={active}
              onClick={() => onChange(option.id)}
              title={option.name ? `${option.name} (n=${option.n})` : undefined}
              className={clsx(
                'h-7 rounded-full px-3 text-sm font-medium whitespace-nowrap transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500',
                active
                  ? 'bg-white text-zinc-900 shadow-sm dark:bg-zinc-700 dark:text-white'
                  : 'text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white',
              )}
            >
              {configOptionLabel(option, options)}
            </button>
          )
        })}
      </div>
    </div>
  )
}

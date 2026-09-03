import clsx from 'clsx'
import type { ReportConfigRef } from '@/types/report'
import type { TranslateFn } from './chartTheme'

interface ConfigSelectorProps {
  options: ReportConfigRef[]
  value: string | null
  onChange: (configId: string) => void
  t: TranslateFn
}

export function configOptionLabel(config: ReportConfigRef, siblings: ReportConfigRef[] = []): string {
  const judge = config.judge_label
  // Several configurations can use the same judge model (e.g. ×3 runs vs a
  // single run, or a multi-judge ensemble led by the same model). A bare
  // judge name would then repeat across buttons, so fall back to the
  // configuration's own name whenever another option carries the same judge.
  const judgeShared =
    !!judge && siblings.some((other) => other.id !== config.id && other.judge_label === judge)
  if (judge && !judgeShared) return judge
  return config.name || judge || config.id || config.metric
}

/** Segmented control to switch between configs (judges) sharing the primary metric. */
export function ConfigSelector({ options, value, onChange, t }: ConfigSelectorProps) {
  if (options.length < 2) return null
  return (
    <div className="flex items-center gap-2 text-sm" data-testid="config-selector">
      <span className="text-zinc-500 dark:text-zinc-400">
        {t('reports.view.judge', 'Judge')}:
      </span>
      <div
        role="radiogroup"
        aria-label={t('reports.view.judge', 'Judge')}
        className="inline-flex flex-wrap overflow-hidden rounded-md border border-zinc-300 dark:border-zinc-700"
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
                'px-3 py-1.5 text-sm transition focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500',
                active
                  ? 'bg-emerald-600 font-medium text-white dark:bg-emerald-500 dark:text-zinc-950'
                  : 'bg-white text-zinc-700 hover:bg-zinc-50 dark:bg-zinc-900 dark:text-zinc-200 dark:hover:bg-zinc-800',
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

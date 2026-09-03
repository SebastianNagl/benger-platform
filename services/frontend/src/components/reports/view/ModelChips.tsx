import type { ReportSubject } from '@/types/report'
import type { TranslateFn } from './chartTheme'

interface ModelChipsProps {
  models: ReportSubject[]
  t: TranslateFn
}

function Chip({ model }: { model: ReportSubject }) {
  const tooltip = [model.id, model.provider].filter(Boolean).join(' · ')
  return (
    <li
      className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-sm font-medium text-emerald-800 dark:border-emerald-900/60 dark:bg-emerald-900/20 dark:text-emerald-300"
      title={tooltip}
      data-testid="model-chip"
    >
      {model.label}
    </li>
  )
}

/** Evaluated models as chips; custom (BYOM) models grouped under their own hint. */
export function ModelChips({ models, t }: ModelChipsProps) {
  if (models.length === 0) return null
  const official = models.filter((m) => !m.is_custom)
  const custom = models.filter((m) => m.is_custom)
  return (
    <div className="space-y-3" data-testid="model-chips">
      {official.length > 0 && (
        <ul className="flex flex-wrap gap-2">
          {official.map((m) => (
            <Chip key={m.id} model={m} />
          ))}
        </ul>
      )}
      {custom.length > 0 && (
        <div>
          <div className="mb-1 text-xs font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
            {t('reports.view.customModels', 'Eigene Modelle')}
          </div>
          <ul className="flex flex-wrap gap-2">
            {custom.map((m) => (
              <Chip key={m.id} model={m} />
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

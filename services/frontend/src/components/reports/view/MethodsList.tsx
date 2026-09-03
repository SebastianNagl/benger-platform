import { formatCount, scaleLabel } from '@/lib/reports/format'
import type { ReportConfigRef, ReportMethod } from '@/types/report'
import type { TranslateFn } from './chartTheme'
import { SubHeading } from './ReportSection'

interface MethodsListProps {
  /** Methods actually used by the visible configs (non-derived). */
  methods: ReportMethod[]
  configs: ReportConfigRef[]
  labelFor: (metricId: string) => string
  locale: string
  t: TranslateFn
}

/** Explains how the numbers were produced: metrics + scales, and judge configs. */
export function MethodsList({ methods, configs, labelFor, locale, t }: MethodsListProps) {
  if (methods.length === 0 && configs.length === 0) return null
  return (
    <div className="mb-6" data-testid="methods-list">
      <SubHeading>{t('reports.view.methods', 'Bewertungsverfahren')}</SubHeading>
      <ul className="grid gap-2 sm:grid-cols-2">
        {methods.map((m) => (
          <li
            key={m.id}
            className="rounded-md border border-zinc-200 px-3 py-2 text-sm dark:border-zinc-700"
          >
            <div className="font-medium text-zinc-900 dark:text-white">{labelFor(m.id)}</div>
            <div className="text-xs text-zinc-500 dark:text-zinc-400">
              {t('reports.view.scale', 'Skala')}: {scaleLabel(m.scale)}
              {' · '}
              {categoryLabel(m.category, t)}
            </div>
          </li>
        ))}
      </ul>
      {configs.length > 0 && (
        <ul className="mt-3 flex flex-wrap gap-2 text-xs text-zinc-600 dark:text-zinc-300">
          {configs.map((c) => (
            <li
              key={c.id || c.metric}
              className="rounded-full bg-zinc-100 px-3 py-1 dark:bg-zinc-800"
              data-testid="config-chip"
            >
              {c.judge_label
                ? t('reports.view.judgeConfig', 'Judge: {judge}', { judge: c.judge_label })
                : c.name || labelFor(c.metric)}
              {' · '}
              {t('reports.view.samples', 'n = {n}', { n: formatCount(c.n, locale) })}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function categoryLabel(category: string, t: TranslateFn): string {
  switch (category) {
    case 'llm_judge':
      return t('reports.view.category.llmJudge', 'LLM-Bewertung')
    case 'human':
      return t('reports.view.category.human', 'Menschliche Korrektur')
    case 'lexical':
      return t('reports.view.category.lexical', 'Lexikalische Metrik')
    case 'semantic':
      return t('reports.view.category.semantic', 'Semantische Metrik')
    case 'classification':
      return t('reports.view.category.classification', 'Klassifikation')
    default:
      return category
  }
}

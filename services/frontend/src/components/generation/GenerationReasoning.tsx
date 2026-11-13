'use client'

import { useI18n } from '@/contexts/I18nContext'

interface ReasoningEntry {
  label: string | null
  text: string
}

/**
 * Reasoning entries of a generation result (`/generation-result`).
 *
 * A single run carries `reasoning` beside `generated_text`; a result with
 * several runs carries a `generations` list, each with its own `reasoning`.
 * Runs without reasoning are left out, so a model that returned none yields
 * an empty list.
 */
export function reasoningEntries(
  data: Record<string, any> | undefined,
  runLabel: (index: number) => string,
): ReasoningEntry[] {
  if (!data) return []
  if (Array.isArray(data.generations)) {
    return data.generations.flatMap((gen: any, index: number) =>
      typeof gen?.reasoning === 'string' && gen.reasoning
        ? [{ label: runLabel(index + 1), text: gen.reasoning }]
        : [],
    )
  }
  return typeof data.reasoning === 'string' && data.reasoning
    ? [{ label: null, text: data.reasoning }]
    : []
}

/**
 * Collapsed section with the reasoning a model returned beside its answer.
 * Renders nothing when the result carries no reasoning.
 */
export function GenerationReasoning({
  result,
  className = 'rounded-lg border p-4',
}: {
  result: Record<string, any> | undefined
  className?: string
}) {
  const { t } = useI18n()
  const entries = reasoningEntries(result, (index) =>
    t('generation.resultModal.reasoningRun', { index }),
  )
  if (entries.length === 0) return null
  return (
    <details className={className} data-testid="generation-reasoning">
      <summary className="cursor-pointer text-sm font-medium text-zinc-700 dark:text-zinc-300">
        {t('generation.resultModal.viewReasoning')}
      </summary>
      <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
        {t('generation.resultModal.reasoningHint')}
      </p>
      <div className="mt-2 space-y-3">
        {entries.map((entry, index) => (
          <div key={index}>
            {entry.label && (
              <p className="text-xs font-medium text-zinc-500 uppercase dark:text-zinc-400">
                {entry.label}
              </p>
            )}
            <pre className="mt-1 max-h-96 overflow-y-auto text-sm whitespace-pre-wrap text-zinc-600 dark:text-zinc-400">
              {entry.text}
            </pre>
          </div>
        ))}
      </div>
    </details>
  )
}

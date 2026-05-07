'use client'

/**
 * Reusable max-tokens input for judge model parameters. Mirrors
 * TemperatureInput: surfaces the provider-recommended value (eval mode)
 * with a "Zurücksetzen auf Empfohlen" link when the user has deviated.
 */

import { useI18n } from '@/contexts/I18nContext'
import { useModels } from '@/hooks/useModels'
import { getRecommendedParam, hasRecommendations } from '@/lib/modelConstraints'

interface Props {
  judgeModelId: string
  value: number | undefined
  onChange: (next: number) => void
  min?: number
  max?: number
  fallback?: number
}

export function MaxTokensInput({
  judgeModelId,
  value,
  onChange,
  min = 100,
  max = 4000,
  fallback = 500,
}: Props) {
  const { t } = useI18n()
  const { models } = useModels()
  const model = models.find((m) => m.id === judgeModelId)
  const recommended = getRecommendedParam(model, 'max_tokens', 'evaluation')
  const recNumber = typeof recommended === 'number' ? recommended : undefined
  const modelHasRec = hasRecommendations(model)
  const current = value ?? fallback

  return (
    <div>
      <label className="mb-2 block text-xs font-medium text-gray-700 dark:text-gray-300">
        {t('evaluationBuilder.parameters.maxTokens', 'Max Tokens')}
      </label>
      <input
        type="number"
        min={min}
        max={max}
        value={current}
        onChange={(e) => onChange(parseInt(e.target.value) || fallback)}
        className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800"
      />
      <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
        {t(
          'evaluationBuilder.parameters.maxTokensDescription',
          `Maximum tokens for judge response (${min}-${max})`,
        )}
      </p>
      <div className="mt-1 text-xs">
        {recNumber !== undefined ? (
          <span className="text-zinc-600 dark:text-zinc-400">
            {t('evaluationBuilder.parameters.recommended', 'Empfehlung')}: {recNumber}
            {current !== recNumber && (
              <button
                type="button"
                onClick={() => onChange(recNumber)}
                className="ml-2 text-blue-600 hover:underline"
              >
                {t('evaluationBuilder.parameters.resetToRecommended', 'Zurücksetzen auf Empfohlen')}
              </button>
            )}
          </span>
        ) : modelHasRec ? (
          <span className="text-zinc-400 dark:text-zinc-500">
            {t('evaluationBuilder.parameters.noRecommendationForKey', 'Keine Empfehlung für max_tokens')}
          </span>
        ) : (
          <span className="text-zinc-400 dark:text-zinc-500">
            {t('evaluationBuilder.parameters.noRecommendation', 'Keine Empfehlung')}
          </span>
        )}
      </div>
    </div>
  )
}

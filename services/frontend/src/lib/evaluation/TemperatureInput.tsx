'use client'

/**
 * Reusable temperature input that enforces per-model constraints from
 * useJudgeModelHelpers. Used by both core LLM-Judge branches and any
 * extended metric editor that calls the same helpers.
 */

import { useI18n } from '@/contexts/I18nContext'
import { useModels } from '@/hooks/useModels'
import { getRecommendedParam, hasRecommendations } from '@/lib/modelConstraints'
import { useJudgeModelHelpers } from './judgeModelHelpers'

interface Props {
  judgeModelId: string
  value: number | undefined
  onChange: (next: number | undefined) => void
}

export function TemperatureInput({ judgeModelId, value, onChange }: Props) {
  const { t } = useI18n()
  const { getModelConstraints, getTemperatureValidation } = useJudgeModelHelpers()
  const { models } = useModels()
  const constraints = getModelConstraints(judgeModelId)
  const tempValidation = getTemperatureValidation(judgeModelId, value)
  const model = models.find((m) => m.id === judgeModelId)
  const recommended = getRecommendedParam(model, 'temperature', 'evaluation')
  const recNumber = typeof recommended === 'number' ? recommended : undefined
  const modelHasRec = hasRecommendations(model)

  return (
    <div>
      <label className="mb-2 block text-xs font-medium text-gray-700 dark:text-gray-300">
        {t('evaluationBuilder.parameters.temperature', 'Temperature')}
        {constraints.temperature.fixed && (
          <span className="ml-2 rounded bg-blue-100 px-1.5 py-0.5 text-xs text-blue-700 dark:bg-blue-900/30 dark:text-blue-300">
            {t(
              'evaluationBuilder.validation.fixed',
              `Fixed at ${constraints.temperature.fixedValue}`,
            )}
          </span>
        )}
      </label>
      <input
        type="number"
        min={constraints.temperature.min}
        max={constraints.temperature.max}
        step={0.1}
        value={value ?? ''}
        placeholder="0.0"
        disabled={constraints.temperature.fixed}
        onChange={(e) =>
          onChange(e.target.value ? parseFloat(e.target.value) : undefined)
        }
        className={`w-full rounded-md border px-3 py-2 text-sm ${
          constraints.temperature.fixed
            ? 'cursor-not-allowed bg-gray-100 dark:bg-gray-700'
            : ''
        } ${
          tempValidation.type === 'error'
            ? 'border-red-500 dark:border-red-400'
            : 'border-gray-300 dark:border-gray-600'
        } dark:bg-gray-800`}
      />
      {tempValidation.type && (
        <p
          className={`mt-1 text-xs ${
            tempValidation.type === 'error'
              ? 'text-red-600 dark:text-red-400'
              : 'text-amber-600 dark:text-amber-400'
          }`}
        >
          {tempValidation.message}
        </p>
      )}
      {!tempValidation.type && (
        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
          {constraints.temperature.fixed
            ? t(
                'evaluationBuilder.validation.temperatureFixedDescription',
                'This model requires a fixed temperature value.',
              )
            : t(
                'evaluationBuilder.parameters.temperatureDescription',
                `Response randomness (${constraints.temperature.min} - ${constraints.temperature.max} for this provider)`,
              )}
        </p>
      )}
      {!constraints.temperature.fixed && (
        <div className="mt-1 text-xs">
          {recNumber !== undefined ? (
            <span className="text-zinc-600 dark:text-zinc-400">
              {t('evaluationBuilder.parameters.recommended', 'Empfehlung')}: {recNumber}
              {value !== undefined && value !== recNumber && (
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
              {t('evaluationBuilder.parameters.noRecommendationForKey', 'Keine Empfehlung für temperature')}
            </span>
          ) : (
            <span className="text-zinc-400 dark:text-zinc-500">
              {t('evaluationBuilder.parameters.noRecommendation', 'Keine Empfehlung')}
            </span>
          )}
        </div>
      )}
    </div>
  )
}

/**
 * Evaluation-defaults configuration block for the project detail page.
 *
 * Renders the "Evaluation Defaults" SubSection: the 3-mode strategy picker
 * (recommended / minimum / custom) plus the per-project default temperature
 * and max-tokens inputs with their recommended-value consensus badges. Mirrors
 * GenerationDefaultsCard but with eval-specific i18n keys and bounds.
 *
 * Extracted verbatim from ProjectDetailPage as a behavior-preserving
 * presentational sub-component — the rendered DOM/text/classNames are
 * identical to the inline version. All state lives in the parent and is
 * prop-drilled here.
 */

'use client'

import { DefaultParamInput } from '@/components/projects/DefaultParamInput'
import { SubSection } from '@/components/projects/SubSection'
import type {
  DefaultsMode,
  RecommendedConsensus,
} from '@/components/projects/GenerationDefaultsCard'

interface EvaluationDefaultsCardProps {
  t: (key: string, params?: any) => string
  evalDefaultsMode: DefaultsMode
  setEvalDefaultsMode: (mode: DefaultsMode) => void
  evalDefaultTemperature: number | undefined
  setEvalDefaultTemperature: (value: number | undefined) => void
  evalDefaultMaxTokens: number | undefined
  setEvalDefaultMaxTokens: (value: number | undefined) => void
  selectedModelIds: string[]
  evalRecConsensus: RecommendedConsensus
  cardEditingEvaluation: boolean
  beginEditEvaluation: () => void
}

export function EvaluationDefaultsCard({
  t,
  evalDefaultsMode,
  setEvalDefaultsMode,
  evalDefaultTemperature,
  setEvalDefaultTemperature,
  evalDefaultMaxTokens,
  setEvalDefaultMaxTokens,
  selectedModelIds,
  evalRecConsensus,
  cardEditingEvaluation,
  beginEditEvaluation,
}: EvaluationDefaultsCardProps) {
  return (
    <div className="mb-6">
      <SubSection title={t('project.evaluationDefaults.title')}>
        <p className="-mt-2 mb-3 text-xs text-zinc-500 dark:text-zinc-400">
          {t('project.evaluationDefaults.description')}
        </p>
        {/* 3-mode picker — controls per-judge pre-fill when a
            new llm_judge_* metric is configured. Same shape
            as the generation-side picker. */}
        <div className="mb-4 rounded-md border border-zinc-200 bg-zinc-50 p-3 dark:border-zinc-700 dark:bg-zinc-800/40">
          <div className="mb-2 text-xs font-medium text-zinc-700 dark:text-zinc-300">
            {t('project.evaluationDefaults.modeLabel', 'Standard-Strategie')}
          </div>
          <div className="space-y-2">
            {([
              ['recommended', t('project.evaluationDefaults.modeRecommended', 'Empfohlene Werte (pro Judge-Modell)'),
                t('project.evaluationDefaults.modeRecommendedDesc', 'Verwende die vom Anbieter empfohlenen Eval-Werte für jedes neu hinzugefügte Judge-Modell.')],
              ['minimum', t('project.evaluationDefaults.modeMinimum', 'Minimal-Werte (pro Judge-Modell)'),
                t('project.evaluationDefaults.modeMinimumDesc', 'Verwende die niedrigste vom Anbieter zulässige Temperatur für jedes neu hinzugefügte Judge-Modell.')],
              ['custom', t('project.evaluationDefaults.modeCustom', 'Benutzerdefiniert'),
                t('project.evaluationDefaults.modeCustomDesc', 'Verwende die unten eingegebenen Werte einheitlich für alle neu hinzugefügten Judge-Konfigurationen (Min/Max-Constraints werden weiterhin durchgesetzt).')],
            ] as const).map(([modeKey, label, desc]) => (
              <label key={modeKey} className="flex items-start gap-2 cursor-pointer">
                <input
                  type="radio"
                  name="eval-defaults-mode"
                  value={modeKey}
                  checked={evalDefaultsMode === modeKey}
                  onChange={() => {
                    setEvalDefaultsMode(modeKey)
                    if (!cardEditingEvaluation) beginEditEvaluation()
                  }}
                  className="mt-0.5"
                />
                <span className="flex-1">
                  <span className="block text-xs font-medium text-zinc-900 dark:text-zinc-100">{label}</span>
                  <span className="block text-xs text-zinc-500 dark:text-zinc-400">{desc}</span>
                </span>
              </label>
            ))}
          </div>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-medium text-zinc-600 dark:text-zinc-400">
              {t('project.evaluationDefaults.defaultTemperature')}
            </label>
            <DefaultParamInput
              value={evalDefaultTemperature}
              fallback={0}
              min={0}
              max={2}
              step={0.1}
              placeholder="0.0"
              disabled={evalDefaultsMode !== 'custom'}
              onChange={(e) => {
                if (!cardEditingEvaluation) beginEditEvaluation()
                setEvalDefaultTemperature(
                  e.target.value ? parseFloat(e.target.value) : undefined
                )
              }}
            />
            <p className="mt-1 text-xs text-zinc-400 dark:text-zinc-500">
              {evalDefaultsMode === 'custom'
                ? t('project.evaluationDefaults.temperatureHelp')
                : t('project.evaluationDefaults.temperatureHelpModeOverride',
                    'Wird ignoriert: aktive Strategie befüllt Temperatur pro Judge-Modell.')}
            </p>
            {selectedModelIds.length > 0 && (
              <div className="mt-1 text-xs">
                {evalRecConsensus.temperature.uniform &&
                evalRecConsensus.temperature.value !== undefined ? (
                  <span className="text-zinc-600 dark:text-zinc-400">
                    {t('generation.controlModal.recommended', 'Empfehlung')}: {evalRecConsensus.temperature.value}
                    {(evalDefaultTemperature ?? 0) !== evalRecConsensus.temperature.value && (
                      <button
                        type="button"
                        onClick={() => setEvalDefaultTemperature(evalRecConsensus.temperature.value)}
                        className="ml-2 text-blue-600 hover:underline"
                      >
                        {t('generation.controlModal.resetToRecommended', 'Zurücksetzen auf Empfohlen')}
                      </button>
                    )}
                  </span>
                ) : evalRecConsensus.temperature.anyRec ? (
                  <span
                    className="text-amber-600 dark:text-amber-400"
                    title={evalRecConsensus.temperature.perModel
                      .map((m) => `${m.model}: ${m.value ?? '—'}`)
                      .join('\n')}
                  >
                    {t('generation.controlModal.divergentRecommendations', 'Verschiedene Empfehlungen pro Modell')}
                  </span>
                ) : (
                  <span className="text-zinc-400 dark:text-zinc-500">
                    {t('generation.controlModal.noRecommendation', 'Keine Empfehlung')}
                  </span>
                )}
              </div>
            )}
          </div>
          <div>
            <label className="block text-xs font-medium text-zinc-600 dark:text-zinc-400">
              {t('project.evaluationDefaults.defaultMaxTokens')}
            </label>
            <DefaultParamInput
              value={evalDefaultMaxTokens}
              fallback={500}
              min={100}
              max={16000}
              step={100}
              placeholder="500"
              disabled={evalDefaultsMode !== 'custom'}
              onChange={(e) => {
                if (!cardEditingEvaluation) beginEditEvaluation()
                setEvalDefaultMaxTokens(
                  e.target.value ? parseInt(e.target.value) : undefined
                )
              }}
            />
            <p className="mt-1 text-xs text-zinc-400 dark:text-zinc-500">
              {evalDefaultsMode === 'custom'
                ? t('project.evaluationDefaults.maxTokensHelp')
                : t('project.evaluationDefaults.maxTokensHelpModeOverride',
                    'Wird ignoriert: aktive Strategie befüllt Max Tokens pro Judge-Modell.')}
            </p>
            {selectedModelIds.length > 0 && (
              <div className="mt-1 text-xs">
                {evalRecConsensus.max_tokens.uniform &&
                evalRecConsensus.max_tokens.value !== undefined ? (
                  <span className="text-zinc-600 dark:text-zinc-400">
                    {t('generation.controlModal.recommended', 'Empfehlung')}: {evalRecConsensus.max_tokens.value}
                    {(evalDefaultMaxTokens ?? 500) !== evalRecConsensus.max_tokens.value && (
                      <button
                        type="button"
                        onClick={() => setEvalDefaultMaxTokens(evalRecConsensus.max_tokens.value)}
                        className="ml-2 text-blue-600 hover:underline"
                      >
                        {t('generation.controlModal.resetToRecommended', 'Zurücksetzen auf Empfohlen')}
                      </button>
                    )}
                  </span>
                ) : evalRecConsensus.max_tokens.anyRec ? (
                  <span
                    className="text-amber-600 dark:text-amber-400"
                    title={evalRecConsensus.max_tokens.perModel
                      .map((m) => `${m.model}: ${m.value ?? '—'}`)
                      .join('\n')}
                  >
                    {t('generation.controlModal.divergentRecommendations', 'Verschiedene Empfehlungen pro Modell')}
                  </span>
                ) : (
                  <span className="text-zinc-400 dark:text-zinc-500">
                    {t('generation.controlModal.noRecommendation', 'Keine Empfehlung')}
                  </span>
                )}
              </div>
            )}
          </div>
        </div>
      </SubSection>
    </div>
  )
}

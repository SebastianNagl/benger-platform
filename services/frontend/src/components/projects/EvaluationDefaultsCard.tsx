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
import type {
  DefaultsMode,
  RecommendedConsensus,
} from '@/components/projects/GenerationDefaultsCard'
import {
  SettingField,
  SettingRow,
  SettingsGroup,
  SettingsGroupStack,
} from '@/components/projects/SettingsGroup'
import { SubSection } from '@/components/projects/SubSection'
import { Checkbox } from '@/components/shared/Checkbox'
import { Input } from '@/components/shared/Input'
import { Label } from '@/components/shared/Label'
import type { ReactNode } from 'react'

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
  /** Default judge runs per task (group "Läufe"). */
  runsPerTask?: number
  setRunsPerTask?: (value: number | undefined) => void
  /** Sofortige Evaluation (group "Zeitpunkt"). */
  immediateEvaluation?: boolean
  onImmediateEvaluationChange?: (enabled: boolean) => void
  /** Extension content shown as its own group (e.g. Korrektur policy). */
  korrekturSettings?: ReactNode
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
  runsPerTask,
  setRunsPerTask,
  immediateEvaluation,
  onImmediateEvaluationChange,
  korrekturSettings,
}: EvaluationDefaultsCardProps) {
  return (
    <SubSection
      title={t('project.evaluationSettings.title')}
      data-testid="evaluation-settings-section"
    >
      <SettingsGroupStack>
        <SettingsGroup
          title={t('project.settings.groups.parameters')}
          description={t('project.evaluationDefaults.description')}
        >
          {/* 3-mode picker — controls per-judge pre-fill when a
            new llm_judge_* metric is configured. Same shape
            as the generation-side picker. */}
          <div className="mb-4 rounded-md border border-zinc-200 bg-zinc-50 p-3 dark:border-zinc-700 dark:bg-zinc-800/40">
            <div className="mb-2 text-xs font-medium text-zinc-700 dark:text-zinc-300">
              {t('project.evaluationDefaults.modeLabel')}
            </div>
            <div className="space-y-2">
              {(
                [
                  [
                    'recommended',
                    t('project.evaluationDefaults.modeRecommended'),
                    t('project.evaluationDefaults.modeRecommendedDesc'),
                  ],
                  [
                    'minimum',
                    t('project.evaluationDefaults.modeMinimum'),
                    t('project.evaluationDefaults.modeMinimumDesc'),
                  ],
                  [
                    'custom',
                    t('project.evaluationDefaults.modeCustom'),
                    t('project.evaluationDefaults.modeCustomDesc'),
                  ],
                ] as const
              ).map(([modeKey, label, desc]) => (
                <label
                  key={modeKey}
                  className="flex cursor-pointer items-start gap-2"
                >
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
                    <span className="block text-xs font-medium text-zinc-900 dark:text-zinc-100">
                      {label}
                    </span>
                    <span className="block text-xs text-zinc-500 dark:text-zinc-400">
                      {desc}
                    </span>
                  </span>
                </label>
              ))}
            </div>
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <Label>
                {t('project.evaluationDefaults.defaultTemperature')}
              </Label>
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
                    e.target.value ? parseFloat(e.target.value) : undefined,
                  )
                }}
              />
              <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                {evalDefaultsMode === 'custom'
                  ? t('project.evaluationDefaults.temperatureHelp')
                  : t('project.evaluationDefaults.temperatureHelpModeOverride')}
              </p>
              {selectedModelIds.length > 0 && (
                <div className="mt-1 text-xs">
                  {evalRecConsensus.temperature.uniform &&
                  evalRecConsensus.temperature.value !== undefined ? (
                    <span className="text-zinc-600 dark:text-zinc-400">
                      {t('generation.controlModal.recommended')}:{' '}
                      {evalRecConsensus.temperature.value}
                      {(evalDefaultTemperature ?? 0) !==
                        evalRecConsensus.temperature.value && (
                        <button
                          type="button"
                          onClick={() => {
                            if (!cardEditingEvaluation) beginEditEvaluation()
                            setEvalDefaultTemperature(
                              evalRecConsensus.temperature.value,
                            )
                          }}
                          className="ml-2 text-emerald-600 hover:underline dark:text-emerald-400"
                        >
                          {t('generation.controlModal.resetToRecommended')}
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
                      {t('generation.controlModal.divergentRecommendations')}
                    </span>
                  ) : (
                    <span className="text-zinc-400 dark:text-zinc-500">
                      {t('generation.controlModal.noRecommendation')}
                    </span>
                  )}
                </div>
              )}
            </div>
            <div>
              <Label>{t('project.evaluationDefaults.defaultMaxTokens')}</Label>
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
                    e.target.value ? parseInt(e.target.value) : undefined,
                  )
                }}
              />
              <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                {evalDefaultsMode === 'custom'
                  ? t('project.evaluationDefaults.maxTokensHelp')
                  : t('project.evaluationDefaults.maxTokensHelpModeOverride')}
              </p>
              {selectedModelIds.length > 0 && (
                <div className="mt-1 text-xs">
                  {evalRecConsensus.max_tokens.uniform &&
                  evalRecConsensus.max_tokens.value !== undefined ? (
                    <span className="text-zinc-600 dark:text-zinc-400">
                      {t('generation.controlModal.recommended')}:{' '}
                      {evalRecConsensus.max_tokens.value}
                      {(evalDefaultMaxTokens ?? 500) !==
                        evalRecConsensus.max_tokens.value && (
                        <button
                          type="button"
                          onClick={() => {
                            if (!cardEditingEvaluation) beginEditEvaluation()
                            setEvalDefaultMaxTokens(
                              evalRecConsensus.max_tokens.value,
                            )
                          }}
                          className="ml-2 text-emerald-600 hover:underline dark:text-emerald-400"
                        >
                          {t('generation.controlModal.resetToRecommended')}
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
                      {t('generation.controlModal.divergentRecommendations')}
                    </span>
                  ) : (
                    <span className="text-zinc-400 dark:text-zinc-500">
                      {t('generation.controlModal.noRecommendation')}
                    </span>
                  )}
                </div>
              )}
            </div>
          </div>
        </SettingsGroup>
        {setRunsPerTask ? (
          <SettingsGroup
            title={t('project.settings.groups.runs')}
            description={t('project.evaluationDefaults.runsDescription')}
            data-testid="evaluation-runs-group"
          >
            <SettingField
              label={t('project.evaluationDefaults.defaultRunsPerTask')}
              htmlFor="evaluation-runs-per-task"
              help={t('project.evaluationDefaults.runsPerTaskHelp')}
              className="max-w-xs"
            >
              <Input
                id="evaluation-runs-per-task"
                type="number"
                min={1}
                max={25}
                step={1}
                value={runsPerTask ?? 1}
                placeholder="1"
                onChange={(e) => {
                  if (!cardEditingEvaluation) beginEditEvaluation()
                  setRunsPerTask(
                    e.target.value ? parseInt(e.target.value) : undefined,
                  )
                }}
              />
            </SettingField>
          </SettingsGroup>
        ) : null}
        {onImmediateEvaluationChange ? (
          <SettingsGroup
            title={t('project.settings.groups.timing')}
            data-testid="evaluation-timing-group"
          >
            <SettingRow
              label={t('projects.creation.wizard.step7.immediateEvaluation')}
              htmlFor="immediate_evaluation_enabled"
              help={t('projects.creation.wizard.step7.immediateEvaluationHint')}
              control={
                <Checkbox
                  id="immediate_evaluation_enabled"
                  checked={!!immediateEvaluation}
                  onChange={(e) =>
                    onImmediateEvaluationChange(e.target.checked)
                  }
                />
              }
            />
          </SettingsGroup>
        ) : null}
        {korrekturSettings ? (
          <SettingsGroup
            title={t('project.settings.groups.korrektur')}
            data-testid="evaluation-korrektur-group"
          >
            {korrekturSettings}
          </SettingsGroup>
        ) : null}
      </SettingsGroupStack>
    </SubSection>
  )
}

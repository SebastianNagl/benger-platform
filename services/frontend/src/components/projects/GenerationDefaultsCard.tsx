/**
 * Generation-defaults configuration block for the project detail page.
 *
 * Renders the "Generation Defaults" SubSection: the 3-mode strategy picker
 * (recommended / minimum / custom) plus the per-project default temperature
 * and max-tokens inputs with their recommended-value consensus badges.
 *
 * Extracted verbatim from ProjectDetailPage as a behavior-preserving
 * presentational sub-component — the rendered DOM/text/classNames are
 * identical to the inline version. All state lives in the parent and is
 * prop-drilled here.
 */

'use client'

import { type MutableRefObject } from 'react'
import { DefaultParamInput } from '@/components/projects/DefaultParamInput'
import { SubSection } from '@/components/projects/SubSection'

export type DefaultsMode = 'recommended' | 'minimum' | 'custom'

export interface RecommendedConsensusEntry {
  value: number | undefined
  uniform: boolean
  anyRec: boolean
  perModel: Array<{ model: string; value: number | undefined }>
}

export interface RecommendedConsensus {
  temperature: RecommendedConsensusEntry
  max_tokens: RecommendedConsensusEntry
}

interface GenerationDefaultsCardProps {
  t: (key: string, params?: any) => string
  genDefaultsMode: DefaultsMode
  setGenDefaultsMode: (mode: DefaultsMode) => void
  genDefaultsModeRef: MutableRefObject<DefaultsMode>
  genDefaultTemperature: number | undefined
  setGenDefaultTemperature: (value: number | undefined) => void
  genDefaultMaxTokens: number | undefined
  setGenDefaultMaxTokens: (value: number | undefined) => void
  selectedModelIds: string[]
  genRecConsensus: RecommendedConsensus
  cardEditingGeneration: boolean
  beginEditGeneration: () => void
}

export function GenerationDefaultsCard({
  t,
  genDefaultsMode,
  setGenDefaultsMode,
  genDefaultsModeRef,
  genDefaultTemperature,
  setGenDefaultTemperature,
  genDefaultMaxTokens,
  setGenDefaultMaxTokens,
  selectedModelIds,
  genRecConsensus,
  cardEditingGeneration,
  beginEditGeneration,
}: GenerationDefaultsCardProps) {
  return (
    <div className="mb-6">
      <SubSection title={t('project.generationDefaults.title')}>
        <p className="-mt-2 mb-3 text-xs text-zinc-500 dark:text-zinc-400">
          {t('project.generationDefaults.description')}
        </p>
        {/* 3-mode picker — controls per-model pre-fill when a
            model is added. recommended/minimum read each model's
            catalog metadata; custom uses the inputs below. */}
        <div className="mb-4 rounded-md border border-zinc-200 bg-zinc-50 p-3 dark:border-zinc-700 dark:bg-zinc-800/40">
          <div className="mb-2 text-xs font-medium text-zinc-700 dark:text-zinc-300">
            {t('project.generationDefaults.modeLabel', 'Standard-Strategie')}
          </div>
          <div className="space-y-2">
            {([
              ['recommended', t('project.generationDefaults.modeRecommended', 'Empfohlene Werte (pro Modell)'),
                t('project.generationDefaults.modeRecommendedDesc', 'Verwende die vom Anbieter empfohlenen Werte für jedes neu hinzugefügte Modell.')],
              ['minimum', t('project.generationDefaults.modeMinimum', 'Minimal-Werte (pro Modell)'),
                t('project.generationDefaults.modeMinimumDesc', 'Verwende die niedrigste vom Anbieter zulässige Temperatur für jedes neu hinzugefügte Modell.')],
              ['custom', t('project.generationDefaults.modeCustom', 'Benutzerdefiniert'),
                t('project.generationDefaults.modeCustomDesc', 'Verwende die unten eingegebenen Werte einheitlich für alle neu hinzugefügten Modelle (Min/Max-Constraints werden weiterhin durchgesetzt).')],
            ] as const).map(([modeKey, label, desc]) => (
              <label key={modeKey} className="flex items-start gap-2 cursor-pointer">
                <input
                  type="radio"
                  name="gen-defaults-mode"
                  value={modeKey}
                  checked={genDefaultsMode === modeKey}
                  onChange={() => {
                    // Sync ref + state. handleModelToggle reads
                    // the ref, so this guarantees a model toggle
                    // in the same tick sees the new mode without
                    // waiting for React to re-render.
                    genDefaultsModeRef.current = modeKey
                    setGenDefaultsMode(modeKey)
                    if (!cardEditingGeneration) beginEditGeneration()
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
              {t('project.generationDefaults.defaultTemperature')}
            </label>
            <DefaultParamInput
              value={genDefaultTemperature}
              fallback={0}
              min={0}
              max={2}
              step={0.1}
              placeholder="0.0"
              disabled={genDefaultsMode !== 'custom'}
              onChange={(e) => {
                if (!cardEditingGeneration) beginEditGeneration()
                setGenDefaultTemperature(
                  e.target.value ? parseFloat(e.target.value) : undefined
                )
              }}
            />
            <p className="mt-1 text-xs text-zinc-400 dark:text-zinc-500">
              {genDefaultsMode === 'custom'
                ? t('project.generationDefaults.temperatureHelp')
                : t('project.generationDefaults.temperatureHelpModeOverride',
                    'Wird ignoriert: aktive Strategie befüllt Temperatur pro Modell.')}
            </p>
            {/* Recommended-value badge for the project Generation
                Defaults — consensus across the project's selected
                models. Same UX as the run-trigger modal so the user
                sees the same signal regardless of where they edit. */}
            {selectedModelIds.length > 0 && (
              <div className="mt-1 text-xs">
                {genRecConsensus.temperature.uniform &&
                genRecConsensus.temperature.value !== undefined ? (
                  <span className="text-zinc-600 dark:text-zinc-400">
                    {t('generation.controlModal.recommended', 'Empfehlung')}: {genRecConsensus.temperature.value}
                    {(genDefaultTemperature ?? 0) !== genRecConsensus.temperature.value && (
                      <button
                        type="button"
                        onClick={() => setGenDefaultTemperature(genRecConsensus.temperature.value)}
                        className="ml-2 text-blue-600 hover:underline"
                      >
                        {t('generation.controlModal.resetToRecommended', 'Zurücksetzen auf Empfohlen')}
                      </button>
                    )}
                  </span>
                ) : genRecConsensus.temperature.anyRec ? (
                  <span
                    className="text-amber-600 dark:text-amber-400"
                    title={genRecConsensus.temperature.perModel
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
              {t('project.generationDefaults.defaultMaxTokens')}
            </label>
            <DefaultParamInput
              value={genDefaultMaxTokens}
              fallback={4000}
              min={100}
              max={128000}
              step={100}
              placeholder="4000"
              disabled={genDefaultsMode !== 'custom'}
              onChange={(e) => {
                if (!cardEditingGeneration) beginEditGeneration()
                setGenDefaultMaxTokens(
                  e.target.value ? parseInt(e.target.value) : undefined
                )
              }}
            />
            <p className="mt-1 text-xs text-zinc-400 dark:text-zinc-500">
              {genDefaultsMode === 'custom'
                ? t('project.generationDefaults.maxTokensHelp')
                : t('project.generationDefaults.maxTokensHelpModeOverride',
                    'Wird ignoriert: aktive Strategie befüllt Max Tokens pro Modell.')}
            </p>
            {selectedModelIds.length > 0 && (
              <div className="mt-1 text-xs">
                {genRecConsensus.max_tokens.uniform &&
                genRecConsensus.max_tokens.value !== undefined ? (
                  <span className="text-zinc-600 dark:text-zinc-400">
                    {t('generation.controlModal.recommended', 'Empfehlung')}: {genRecConsensus.max_tokens.value}
                    {(genDefaultMaxTokens ?? 4000) !== genRecConsensus.max_tokens.value && (
                      <button
                        type="button"
                        onClick={() => setGenDefaultMaxTokens(genRecConsensus.max_tokens.value)}
                        className="ml-2 text-blue-600 hover:underline"
                      >
                        {t('generation.controlModal.resetToRecommended', 'Zurücksetzen auf Empfohlen')}
                      </button>
                    )}
                  </span>
                ) : genRecConsensus.max_tokens.anyRec ? (
                  <span
                    className="text-amber-600 dark:text-amber-400"
                    title={genRecConsensus.max_tokens.perModel
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

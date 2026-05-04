'use client'

/**
 * Shared judge-model lookup helpers for any evaluation parameter UI that
 * needs the LLM-Judge model picker, temperature constraints, max-tokens
 * defaults, or thinking-config detection.
 *
 * Extracted from EvaluationBuilder so the same helpers drive (a) the
 * Classic and Custom LLM-Judge branches in core and (b) any extended-
 * registered metric editors (e.g. Falllösung) that opt into the same UX
 * without the platform hardcoding extended metric names.
 */

import { useCallback } from 'react'
import { useI18n } from '@/contexts/I18nContext'
import { useModels, type Model } from '@/hooks/useModels'
import {
  getDefaultMaxTokens,
  getTemperatureConstraints,
} from '@/lib/modelConstraints'

export interface JudgeModelDefaults {
  temperature?: number
  max_tokens?: number
  temperatureFixed?: boolean
}

export interface ModelConstraints {
  temperature: { min: number; max: number; fixed?: boolean; fixedValue?: number }
  maxTokens: { min: number; max: number }
}

export type ThinkingConfig =
  | { type: 'budget' | 'effort'; default?: number }
  | undefined

export type TemperatureValidation = {
  type: 'error' | 'warning' | null
  message: string
}

// Provider temperature ranges used as fallback when a model has no
// parameter_constraints declared in the catalog.
export const PROVIDER_TEMPERATURE_RANGES: Record<
  string,
  { min: number; max: number }
> = {
  openai: { min: 0, max: 2 },
  anthropic: { min: 0, max: 1 },
  google: { min: 0, max: 2 },
  deepinfra: { min: 0, max: 2 },
  grok: { min: 0, max: 2 },
  mistral: { min: 0, max: 1 },
  cohere: { min: 0, max: 1 },
}

export interface JudgeModelHelpers {
  /** Available judge models, fetched once via useModels(). */
  judgeModels: Model[]
  /** Detect thinking-config shape for a model id, or undefined if not a thinking model. */
  getThinkingConfig: (modelId: string) => ThinkingConfig
  /** Recommended defaults (temperature + max_tokens) for a freshly-picked model. */
  getJudgeModelDefaults: (modelId: string) => JudgeModelDefaults
  /** Numeric constraints to enforce on the temperature/max-tokens inputs. */
  getModelConstraints: (modelId: string) => ModelConstraints
  /** Validate a candidate temperature value against the model's constraints. */
  getTemperatureValidation: (
    modelId: string,
    value: number | undefined,
  ) => TemperatureValidation
}

export function useJudgeModelHelpers(): JudgeModelHelpers {
  const { t } = useI18n()
  const { models: judgeModels } = useModels()

  const getThinkingConfig = useCallback(
    (modelId: string): ThinkingConfig => {
      const model = judgeModels.find((m) => m.id === modelId)
      const rc = model?.default_config?.reasoning_config
      if (rc) {
        if (rc.parameter === 'reasoning_effort') return { type: 'effort' }
        if (
          rc.parameter === 'thinking_budget' ||
          rc.parameter === 'thinking_token_budget'
        ) {
          return { type: 'budget', default: rc.default as number }
        }
      }
      return undefined
    },
    [judgeModels],
  )

  const getJudgeModelDefaults = useCallback(
    (modelId: string): JudgeModelDefaults => {
      const model = judgeModels.find((m) => m.id === modelId)
      const tc = getTemperatureConstraints(model, PROVIDER_TEMPERATURE_RANGES)
      const defaultMaxTokens = getDefaultMaxTokens(model)
      return {
        temperature: tc.default,
        max_tokens: defaultMaxTokens ?? 500,
        temperatureFixed: tc.fixed,
      }
    },
    [judgeModels],
  )

  const getModelConstraints = useCallback(
    (modelId: string): ModelConstraints => {
      const model = judgeModels.find((m) => m.id === modelId)
      const tc = getTemperatureConstraints(model, PROVIDER_TEMPERATURE_RANGES)
      return {
        temperature: tc.fixed
          ? {
              min: tc.fixedValue!,
              max: tc.fixedValue!,
              fixed: true,
              fixedValue: tc.fixedValue,
            }
          : { min: tc.min, max: tc.max },
        maxTokens: { min: 100, max: 16000 },
      }
    },
    [judgeModels],
  )

  const getTemperatureValidation = useCallback(
    (modelId: string, value: number | undefined): TemperatureValidation => {
      if (value === undefined || value === null) return { type: null, message: '' }
      const constraints = getModelConstraints(modelId)
      if (constraints.temperature.fixed) {
        if (value !== constraints.temperature.fixedValue) {
          return {
            type: 'error',
            message: t(
              'evaluationBuilder.validation.temperatureFixed',
              `This model requires temperature = ${constraints.temperature.fixedValue}. The API will reject other values.`,
            ),
          }
        }
        return { type: null, message: '' }
      }
      if (value < constraints.temperature.min) {
        return {
          type: 'error',
          message: t(
            'evaluationBuilder.validation.temperatureTooLow',
            `Temperature must be at least ${constraints.temperature.min} for this provider.`,
          ),
        }
      }
      if (value > constraints.temperature.max) {
        return {
          type: 'error',
          message: t(
            'evaluationBuilder.validation.temperatureTooHigh',
            `Temperature must be at most ${constraints.temperature.max} for this provider. The API will reject higher values.`,
          ),
        }
      }
      return { type: null, message: '' }
    },
    [getModelConstraints, t],
  )

  return {
    judgeModels,
    getThinkingConfig,
    getJudgeModelDefaults,
    getModelConstraints,
    getTemperatureValidation,
  }
}

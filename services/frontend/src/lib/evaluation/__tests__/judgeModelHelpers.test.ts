/**
 * @jest-environment jsdom
 *
 * Branch + function coverage for useJudgeModelHelpers — the shared judge-model
 * lookup hook (thinking-config detection, recommended/minimum/custom defaults,
 * fixed-temperature clamping, numeric constraints, temperature validation).
 *
 * Mocks useModels + useI18n directly (mirrors src/hooks/__tests__/useModels.test.ts)
 * so the hook resolves a deterministic catalog. modelConstraints.ts is exercised
 * for real (not mocked) so the constraint-derivation branches are covered too.
 */

import { renderHook } from '@testing-library/react'
import type { Model } from '@/hooks/useModels'
import {
  PROVIDER_TEMPERATURE_RANGES,
  useJudgeModelHelpers,
} from '../judgeModelHelpers'

// I18n: identity translator with a fallback param honored (the hook passes a
// default message as the 2nd arg to t()).
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (_key: string, fallback?: string) => fallback ?? _key,
    locale: 'en',
    changeLocale: jest.fn(),
    isReady: true,
  }),
}))

// useModels: return a stable, controllable catalog.
let mockModels: Model[] = []
jest.mock('@/hooks/useModels', () => ({
  useModels: () => ({ models: mockModels }),
}))

const baseModel = (overrides: Partial<Model> = {}): Model => ({
  id: 'm',
  name: 'Model',
  provider: 'anthropic',
  model_type: 'chat',
  capabilities: [],
  is_active: true,
  created_at: null,
  ...overrides,
})

describe('useJudgeModelHelpers', () => {
  const setup = (models: Model[]) => {
    mockModels = models
    return renderHook(() => useJudgeModelHelpers()).result
  }

  describe('getThinkingConfig', () => {
    it('detects reasoning_effort models as effort type', () => {
      const { current } = setup([
        baseModel({
          id: 'gpt-5',
          default_config: {
            reasoning_config: {
              parameter: 'reasoning_effort',
              type: 'select',
              default: 'medium',
            },
          },
        }),
      ])
      expect(current.getThinkingConfig('gpt-5')).toEqual({ type: 'effort' })
    })

    it('detects thinking_budget models as budget type with default', () => {
      const { current } = setup([
        baseModel({
          id: 'claude-budget',
          default_config: {
            reasoning_config: {
              parameter: 'thinking_budget',
              type: 'number',
              default: 4096,
            },
          },
        }),
      ])
      expect(current.getThinkingConfig('claude-budget')).toEqual({
        type: 'budget',
        default: 4096,
      })
    })

    it('treats thinking_token_budget as budget type', () => {
      const { current } = setup([
        baseModel({
          id: 'gemini-budget',
          default_config: {
            reasoning_config: {
              parameter: 'thinking_token_budget',
              type: 'number',
              default: 8192,
            },
          },
        }),
      ])
      expect(current.getThinkingConfig('gemini-budget')).toEqual({
        type: 'budget',
        default: 8192,
      })
    })

    it('returns undefined for a model without reasoning_config', () => {
      const { current } = setup([baseModel({ id: 'plain' })])
      expect(current.getThinkingConfig('plain')).toBeUndefined()
    })

    it('returns undefined for an unknown reasoning parameter', () => {
      const { current } = setup([
        baseModel({
          id: 'weird',
          default_config: {
            reasoning_config: {
              parameter: 'something_else' as any,
              type: 'number',
              default: 1,
            },
          },
        }),
      ])
      expect(current.getThinkingConfig('weird')).toBeUndefined()
    })

    it('returns undefined for a model id not in the catalog', () => {
      const { current } = setup([baseModel({ id: 'a' })])
      expect(current.getThinkingConfig('missing')).toBeUndefined()
    })
  })

  describe('getJudgeModelDefaults — fixed-temperature models', () => {
    const fixedModel = baseModel({
      id: 'gpt-5-fixed',
      provider: 'openai',
      parameter_constraints: {
        temperature: { supported: false, required_value: 1 },
      },
    })

    it('clamps temperature to the required value and marks fixed (recommended mode)', () => {
      const { current } = setup([fixedModel])
      const d = current.getJudgeModelDefaults('gpt-5-fixed', 'recommended')
      expect(d.temperature).toBe(1)
      expect(d.temperatureFixed).toBe(true)
    })

    it('uses recommended evaluation max_tokens when present (fixed model)', () => {
      const { current } = setup([
        baseModel({
          ...fixedModel,
          recommended_parameters: { evaluation: { max_tokens: 1234 } },
        }),
      ])
      const d = current.getJudgeModelDefaults('gpt-5-fixed', 'recommended')
      expect(d.max_tokens).toBe(1234)
      expect(d.temperatureFixed).toBe(true)
    })

    it('falls back to constraint default max_tokens for fixed model with no recommendation', () => {
      const { current } = setup([
        baseModel({
          ...fixedModel,
          parameter_constraints: {
            temperature: { supported: false, required_value: 1 },
            max_tokens: { default: 999 },
          },
        }),
      ])
      const d = current.getJudgeModelDefaults('gpt-5-fixed', 'recommended')
      expect(d.max_tokens).toBe(999)
    })

    it('honors custom max_tokens for fixed model in custom mode', () => {
      const { current } = setup([fixedModel])
      const d = current.getJudgeModelDefaults('gpt-5-fixed', 'custom', 0.2, 777)
      expect(d.temperature).toBe(1) // still clamped
      expect(d.max_tokens).toBe(777)
    })

    it('falls back to 500 max_tokens for fixed model in custom mode with nothing supplied', () => {
      const { current } = setup([fixedModel])
      const d = current.getJudgeModelDefaults('gpt-5-fixed', 'custom')
      expect(d.max_tokens).toBe(500)
    })
  })

  describe('getJudgeModelDefaults — non-fixed models', () => {
    it('recommended mode reads catalog recommended evaluation params', () => {
      const { current } = setup([
        baseModel({
          id: 'rec',
          recommended_parameters: {
            evaluation: { temperature: 0.3, max_tokens: 2000 },
          },
        }),
      ])
      const d = current.getJudgeModelDefaults('rec', 'recommended')
      expect(d.temperature).toBe(0.3)
      expect(d.max_tokens).toBe(2000)
      expect(d.temperatureFixed).toBe(false)
    })

    it('recommended mode falls back to constraint default + 500 when no recommendation', () => {
      const { current } = setup([
        baseModel({
          id: 'norec',
          provider: 'anthropic',
          parameter_constraints: {
            temperature: { supported: true, default: 0.5, min: 0, max: 1 },
          },
        }),
      ])
      const d = current.getJudgeModelDefaults('norec', 'recommended')
      expect(d.temperature).toBe(0.5)
      expect(d.max_tokens).toBe(500)
    })

    it('minimum mode uses constraint min temperature and default max_tokens', () => {
      const { current } = setup([
        baseModel({
          id: 'minmodel',
          provider: 'openai',
          parameter_constraints: {
            temperature: { supported: true, default: 0.7, min: 0.1, max: 2 },
            max_tokens: { default: 4096 },
          },
        }),
      ])
      const d = current.getJudgeModelDefaults('minmodel', 'minimum')
      expect(d.temperature).toBe(0.1)
      expect(d.max_tokens).toBe(4096)
    })

    it('custom mode uses supplied temperature and max_tokens', () => {
      const { current } = setup([baseModel({ id: 'cust' })])
      const d = current.getJudgeModelDefaults('cust', 'custom', 0.42, 321)
      expect(d.temperature).toBe(0.42)
      expect(d.max_tokens).toBe(321)
    })

    it('custom mode falls back to provider default temperature when none supplied', () => {
      const { current } = setup([
        baseModel({ id: 'cust2', provider: 'anthropic' }),
      ])
      // No parameter_constraints → provider fallback default temperature is 0.
      const d = current.getJudgeModelDefaults('cust2', 'custom')
      expect(d.temperature).toBe(0)
      expect(d.max_tokens).toBe(500)
    })

    it('defaults to recommended mode when mode arg omitted', () => {
      const { current } = setup([
        baseModel({
          id: 'defmode',
          recommended_parameters: { evaluation: { temperature: 0.9 } },
        }),
      ])
      const d = current.getJudgeModelDefaults('defmode')
      expect(d.temperature).toBe(0.9)
    })
  })

  describe('getModelConstraints', () => {
    it('returns a fixed temperature window for fixed models', () => {
      const { current } = setup([
        baseModel({
          id: 'fx',
          provider: 'openai',
          parameter_constraints: {
            temperature: { supported: false, required_value: 1 },
          },
        }),
      ])
      const c = current.getModelConstraints('fx')
      expect(c.temperature).toMatchObject({
        min: 1,
        max: 1,
        fixed: true,
        fixedValue: 1,
      })
      expect(c.maxTokens).toEqual({ min: 100, max: 16000 })
    })

    it('returns provider min/max for non-fixed models', () => {
      const { current } = setup([
        baseModel({ id: 'an', provider: 'anthropic' }),
      ])
      const c = current.getModelConstraints('an')
      // anthropic provider range is 0..1
      expect(c.temperature).toEqual({ min: 0, max: 1 })
    })
  })

  describe('getTemperatureValidation', () => {
    const nonFixed = baseModel({ id: 'nf', provider: 'anthropic' }) // range 0..1

    it('returns null type for undefined / null values', () => {
      const { current } = setup([nonFixed])
      expect(current.getTemperatureValidation('nf', undefined)).toEqual({
        type: null,
        message: '',
      })
      expect(
        current.getTemperatureValidation('nf', null as unknown as number)
      ).toEqual({ type: null, message: '' })
    })

    it('flags a value below the provider minimum as an error', () => {
      const { current } = setup([
        baseModel({
          id: 'lo',
          provider: 'anthropic',
          parameter_constraints: {
            temperature: { supported: true, default: 0.5, min: 0.2, max: 1 },
          },
        }),
      ])
      const v = current.getTemperatureValidation('lo', 0.1)
      expect(v.type).toBe('error')
      expect(v.message).toContain('0.2')
    })

    it('flags a value above the provider maximum as an error', () => {
      const { current } = setup([nonFixed])
      const v = current.getTemperatureValidation('nf', 1.5)
      expect(v.type).toBe('error')
      expect(v.message).toContain('1')
    })

    it('accepts an in-range value with no error', () => {
      const { current } = setup([nonFixed])
      expect(current.getTemperatureValidation('nf', 0.5)).toEqual({
        type: null,
        message: '',
      })
    })

    it('errors when a fixed model receives a non-required value', () => {
      const { current } = setup([
        baseModel({
          id: 'fxv',
          provider: 'openai',
          parameter_constraints: {
            temperature: { supported: false, required_value: 1 },
          },
        }),
      ])
      const v = current.getTemperatureValidation('fxv', 0.5)
      expect(v.type).toBe('error')
      expect(v.message).toContain('1')
    })

    it('passes when a fixed model receives exactly the required value', () => {
      const { current } = setup([
        baseModel({
          id: 'fxok',
          provider: 'openai',
          parameter_constraints: {
            temperature: { supported: false, required_value: 1 },
          },
        }),
      ])
      expect(current.getTemperatureValidation('fxok', 1)).toEqual({
        type: null,
        message: '',
      })
    })
  })

  it('exposes the provider temperature ranges table', () => {
    expect(PROVIDER_TEMPERATURE_RANGES.anthropic).toEqual({ min: 0, max: 1 })
    expect(PROVIDER_TEMPERATURE_RANGES.openai).toEqual({ min: 0, max: 2 })
  })

  it('passes through the catalog as judgeModels', () => {
    const models = [baseModel({ id: 'x' }), baseModel({ id: 'y' })]
    const { current } = setup(models)
    expect(current.judgeModels).toHaveLength(2)
    expect(current.judgeModels[0].id).toBe('x')
  })
})

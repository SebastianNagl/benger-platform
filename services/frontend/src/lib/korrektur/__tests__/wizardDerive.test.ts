import {
  deriveKorrekturProjectFields,
  type KorrekturProjectFields,
} from '../wizardDerive'
import type { EvaluationConfig } from '@/lib/api/evaluation-types'

function cfg(metric: string, params?: Record<string, any>): EvaluationConfig {
  return {
    id: `${metric}-id`,
    metric,
    display_name: metric,
    prediction_fields: [],
    reference_fields: [],
    enabled: true,
    metric_parameters: params,
  } as EvaluationConfig
}

describe('deriveKorrekturProjectFields', () => {
  it('returns empty object when neither korrektur metric is selected', () => {
    const out = deriveKorrekturProjectFields([cfg('rouge'), cfg('llm_judge_classic')])
    expect(out).toEqual({})
  })

  it('sets korrektur_enabled when korrektur_classic is selected', () => {
    const out = deriveKorrekturProjectFields([cfg('korrektur_classic')])
    expect(out.korrektur_enabled).toBe(true)
  })

  it('sets korrektur_enabled when korrektur_falloesung is selected (without classic)', () => {
    const out = deriveKorrekturProjectFields([cfg('korrektur_falloesung')])
    expect(out.korrektur_enabled).toBe(true)
  })

  it('sets korrektur_enabled when both are selected', () => {
    const out = deriveKorrekturProjectFields([
      cfg('korrektur_classic'),
      cfg('korrektur_falloesung'),
    ])
    expect(out.korrektur_enabled).toBe(true)
  })

  it('copies highlight_labels from korrektur_classic into korrektur_config', () => {
    const labels = [
      { value: 'Error', background: '#ff0000' },
      { value: 'Suggestion', background: '#ffff00' },
    ]
    const out = deriveKorrekturProjectFields([
      cfg('korrektur_classic', { highlight_labels: labels }),
    ])
    expect(out.korrektur_config).toEqual(labels)
  })

  it('omits korrektur_config when no highlight_labels are configured', () => {
    const out: KorrekturProjectFields = deriveKorrekturProjectFields([
      cfg('korrektur_classic'),
    ])
    expect(out.korrektur_enabled).toBe(true)
    expect(out.korrektur_config).toBeUndefined()
  })

  it('omits korrektur_config when highlight_labels is an empty array', () => {
    const out = deriveKorrekturProjectFields([
      cfg('korrektur_classic', { highlight_labels: [] }),
    ])
    expect(out.korrektur_config).toBeUndefined()
  })

  it('ignores highlight_labels coming from korrektur_falloesung (not its concern)', () => {
    const out = deriveKorrekturProjectFields([
      cfg('korrektur_falloesung', { highlight_labels: [{ value: 'X', background: '#000' }] }),
    ])
    expect(out.korrektur_enabled).toBe(true)
    expect(out.korrektur_config).toBeUndefined()
  })

  it('does not touch unrelated metrics in the input list', () => {
    const out = deriveKorrekturProjectFields([
      cfg('rouge'),
      cfg('llm_judge_falloesung'),
      cfg('korrektur_classic', {
        highlight_labels: [{ value: 'A', background: '#fff' }],
      }),
    ])
    expect(out).toEqual({
      korrektur_enabled: true,
      korrektur_config: [{ value: 'A', background: '#fff' }],
    })
  })

  it('handles a malformed highlight_labels (not an array) by ignoring it', () => {
    const out = deriveKorrekturProjectFields([
      cfg('korrektur_classic', { highlight_labels: 'not an array' as any }),
    ])
    expect(out.korrektur_enabled).toBe(true)
    expect(out.korrektur_config).toBeUndefined()
  })
})

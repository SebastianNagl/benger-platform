import type { EvaluationConfig } from '@/lib/api/evaluation-types'
import { refreshEvaluationConfigs } from '../refreshEvaluationConfigs'

const cfg = (id: string, extra: Partial<EvaluationConfig> = {}) =>
  ({
    id,
    metric: 'korrektur',
    prediction_fields: ['answer'],
    reference_fields: ['solution'],
    enabled: true,
    ...extra,
  }) as EvaluationConfig

describe('refreshEvaluationConfigs', () => {
  it('takes the server list when the buffer has no unsaved edits', () => {
    const baseline = [cfg('a', { metric_parameters: { x: 1 } })]
    const fresh = [cfg('a', { metric_parameters: { x: 1, blind: true } })]
    expect(
      refreshEvaluationConfigs(
        baseline,
        JSON.parse(JSON.stringify(baseline)),
        fresh,
      ),
    ).toBe(fresh)
  })

  it('merges server parameter keys the user did not edit', () => {
    const baseline = [cfg('a', { metric_parameters: { x: 1, y: 'old' } })]
    const local = [cfg('a', { metric_parameters: { x: 2, y: 'old' } })]
    const fresh = [
      cfg('a', { metric_parameters: { x: 1, y: 'new', blind: true } }),
    ]
    expect(refreshEvaluationConfigs(baseline, local, fresh)).toEqual([
      cfg('a', { metric_parameters: { x: 2, y: 'new', blind: true } }),
    ])
  })

  it('keeps a parameter key the user removed removed', () => {
    const baseline = [cfg('a', { metric_parameters: { x: 1, y: 2 } })]
    const local = [cfg('a', { metric_parameters: { x: 1 } })]
    const fresh = [cfg('a', { metric_parameters: { x: 1, y: 2, z: 3 } })]
    expect(
      refreshEvaluationConfigs(baseline, local, fresh)[0].metric_parameters,
    ).toEqual({ x: 1, z: 3 })
  })

  it('keeps edited top-level fields and takes the rest from the server', () => {
    const baseline = [cfg('a', { display_name: 'A' })]
    const local = [cfg('a', { display_name: 'Mine' })]
    const fresh = [
      cfg('a', {
        display_name: 'A',
        enabled: false,
        metric_parameters: { blind: true },
      }),
    ]
    expect(refreshEvaluationConfigs(baseline, local, fresh)).toEqual([
      cfg('a', {
        display_name: 'Mine',
        enabled: false,
        metric_parameters: { blind: true },
      }),
    ])
  })

  it('keeps added and removed configs and appends ones added elsewhere', () => {
    const baseline = [cfg('a'), cfg('b')]
    const local = [cfg('a'), cfg('new')]
    const fresh = [cfg('a'), cfg('b'), cfg('other')]
    expect(
      refreshEvaluationConfigs(baseline, local, fresh).map((c) => c.id),
    ).toEqual(['a', 'new', 'other'])
  })

  it('drops an unedited config deleted on the server, keeps an edited one', () => {
    const baseline = [cfg('a'), cfg('b')]
    const local = [cfg('a', { display_name: 'edited' }), cfg('b')]
    expect(
      refreshEvaluationConfigs(baseline, local, []).map((c) => c.id),
    ).toEqual(['a'])
  })

  it('compares values regardless of key order', () => {
    const baseline = [cfg('a', { metric_parameters: { x: 1, y: 2 } })]
    const local = [
      { ...cfg('a'), metric_parameters: { y: 2, x: 1 } } as EvaluationConfig,
    ]
    const fresh = [cfg('a', { metric_parameters: { x: 1, y: 2, z: [1] } })]
    expect(refreshEvaluationConfigs(baseline, local, fresh)).toBe(fresh)
  })

  it('leaves metric_parameters out when no side has it', () => {
    const baseline = [cfg('a')]
    const local = [cfg('a', { display_name: 'x' })]
    const fresh = [cfg('a')]
    expect(
      refreshEvaluationConfigs(baseline, local, fresh)[0],
    ).not.toHaveProperty('metric_parameters')
  })
})

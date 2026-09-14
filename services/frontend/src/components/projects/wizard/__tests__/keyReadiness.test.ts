/**
 * The key-readiness rule: which provider keys a project being created will
 * lack. Each case mirrors a backend rule named in keyReadiness.ts, and the
 * rule may only warn where the answer is provable.
 */

import type { EvaluationConfig } from '@/lib/api/evaluation-types'
import { DEFAULT_MODEL_ID } from '@/lib/modelDefaults'
import {
  decideKeyWarnings,
  evaluationKeyRoute,
  hasNeededModels,
  judgeModelIds,
  type KeyReadinessInput,
  neededModels,
  organizationsToCheck,
  projectOrganizationIds,
} from '../keyReadiness'
import { INITIAL_WIZARD_DATA } from '../types'

const params = (value: Record<string, unknown> | null) =>
  value as unknown as EvaluationConfig['metric_parameters']

const judge = (
  overrides: Partial<EvaluationConfig> = {},
): EvaluationConfig => ({
  id: 'cfg-1',
  metric: 'llm_judge_classic',
  prediction_fields: ['__all_model__'],
  reference_fields: ['answer'],
  enabled: true,
  ...overrides,
})

const CATALOG = [
  { id: 'gpt-4o', provider: 'OpenAI' },
  { id: 'gpt-5.4-mini', provider: 'OpenAI' },
  { id: 'claude-sonnet', provider: 'Anthropic' },
]

const input = (
  overrides: Partial<KeyReadinessInput> = {},
): KeyReadinessInput => ({
  needed: { evaluation: ['gpt-4o'], generation: [] },
  catalog: CATALOG,
  personalProviders: [],
  visibility: 'private',
  organizationIds: [],
  organizationGroupIds: {},
  memberships: {},
  isSuperadmin: false,
  organizations: {},
  ...overrides,
})

describe('judgeModelIds', () => {
  it('ignores a metric that calls no model', () => {
    expect(judgeModelIds(judge({ metric: 'bleu' }))).toEqual([])
  })

  it('ignores a disabled config, as the worker does', () => {
    expect(judgeModelIds(judge({ enabled: false }))).toEqual([])
  })

  it('keeps a config without an enabled flag, as the worker does', () => {
    const config = { ...judge(), enabled: undefined }
    expect(judgeModelIds(config as unknown as EvaluationConfig)).toEqual([
      DEFAULT_MODEL_ID,
    ])
  })

  it('runs on the worker fallback when no judge model is named', () => {
    expect(judgeModelIds(judge())).toEqual([DEFAULT_MODEL_ID])
    expect(judgeModelIds(judge({ metric_parameters: params(null) }))).toEqual([
      DEFAULT_MODEL_ID,
    ])
    expect(
      judgeModelIds(judge({ metric_parameters: params({ judge_model: '' }) })),
    ).toEqual([DEFAULT_MODEL_ID])
  })

  it('uses the judge model the config names', () => {
    expect(
      judgeModelIds(
        judge({ metric_parameters: params({ judge_model: 'claude-sonnet' }) }),
      ),
    ).toEqual(['claude-sonnet'])
  })

  it('resolves every entry of a judge ensemble, which wins over judge_model', () => {
    expect(
      judgeModelIds(
        judge({
          metric_parameters: params({
            judge_model: 'gpt-5.4-mini',
            judges: [
              { judge_model_id: 'claude-sonnet', runs: 2 },
              { runs: 1 },
              null,
            ],
          }),
        }),
      ),
    ).toEqual(['claude-sonnet', DEFAULT_MODEL_ID, DEFAULT_MODEL_ID])
  })

  it('falls back to judge_model when the ensemble is empty', () => {
    expect(
      judgeModelIds(
        judge({
          metric_parameters: params({
            judges: [],
            judge_model: 'claude-sonnet',
          }),
        }),
      ),
    ).toEqual(['claude-sonnet'])
  })
})

describe('neededModels', () => {
  const configs = [
    judge(),
    judge({ id: 'cfg-2' }),
    judge({
      id: 'cfg-3',
      metric_parameters: params({ judge_model: 'claude-sonnet' }),
    }),
    judge({ id: 'cfg-4', metric: 'bleu' }),
  ]

  it('needs nothing while evaluation and generation are off', () => {
    const needed = neededModels({
      features: INITIAL_WIZARD_DATA.features,
      evaluationConfigs: configs,
      selectedModelIds: ['gpt-5.4-mini'],
    })
    expect(needed).toEqual({ evaluation: [], generation: [] })
    expect(hasNeededModels(needed)).toBe(false)
  })

  it('collects each judge model once, and the generation models', () => {
    const needed = neededModels({
      features: {
        ...INITIAL_WIZARD_DATA.features,
        evaluation: true,
        llmGeneration: true,
      },
      evaluationConfigs: configs,
      selectedModelIds: ['gpt-5.4-mini', 'gpt-5.4-mini'],
    })
    expect(needed).toEqual({
      evaluation: [DEFAULT_MODEL_ID, 'claude-sonnet'],
      generation: ['gpt-5.4-mini'],
    })
    expect(hasNeededModels(needed)).toBe(true)
  })

  it('counts generation alone as a need', () => {
    expect(
      hasNeededModels({ evaluation: [], generation: ['claude-sonnet'] }),
    ).toBe(true)
  })
})

describe('projectOrganizationIds', () => {
  it('attaches no organization to a private or public project', () => {
    expect(
      projectOrganizationIds({ visibility: 'private', organizationIds: ['a'] }),
    ).toEqual([])
    expect(
      projectOrganizationIds({ visibility: 'public', organizationIds: ['a'] }),
    ).toEqual([])
  })

  it('attaches exactly the selected organizations, once each', () => {
    expect(
      projectOrganizationIds({
        visibility: 'organization',
        organizationIds: ['a', 'b', 'a'],
      }),
    ).toEqual(['a', 'b'])
  })
})

describe('evaluationKeyRoute', () => {
  it('uses the personal key for a project without organizations', () => {
    expect(evaluationKeyRoute(input())).toEqual({
      kind: 'personal',
      reason: 'no_organization',
    })
    expect(evaluationKeyRoute(input({ visibility: 'organization' }))).toEqual({
      kind: 'personal',
      reason: 'no_organization',
    })
  })

  it('uses the organizations the creator is a member of', () => {
    expect(
      evaluationKeyRoute(
        input({
          visibility: 'organization',
          organizationIds: ['org-a', 'org-b', 'org-c'],
          memberships: { 'org-b': [], 'org-c': [], 'org-z': [] },
        }),
      ),
    ).toEqual({ kind: 'organizations', organizationIds: ['org-b', 'org-c'] })
  })

  it("falls back to all of the project's organizations for a superadmin", () => {
    expect(
      evaluationKeyRoute(
        input({
          visibility: 'organization',
          organizationIds: ['org-a', 'org-b'],
          isSuperadmin: true,
        }),
      ),
    ).toEqual({ kind: 'organizations', organizationIds: ['org-a', 'org-b'] })
  })

  it('uses the personal key for anyone else', () => {
    expect(
      evaluationKeyRoute(
        input({ visibility: 'organization', organizationIds: ['org-a'] }),
      ),
    ).toEqual({ kind: 'personal', reason: 'not_member' })
  })
})

describe('organizationsToCheck', () => {
  const member = {
    visibility: 'organization' as const,
    organizationIds: ['org-a'],
    memberships: { 'org-a': [], 'org-b': [] },
  }

  it('checks nothing when no model is needed', () => {
    expect(
      organizationsToCheck(
        input({ ...member, needed: { evaluation: [], generation: [] } }),
      ),
    ).toEqual([])
  })

  it('checks the possible organizations of an evaluation', () => {
    expect(organizationsToCheck(input(member))).toEqual(['org-a'])
  })

  it('checks nothing for an evaluation on the personal key', () => {
    expect(organizationsToCheck(input())).toEqual([])
  })

  it('checks every membership for a generation, without duplicates', () => {
    expect(
      organizationsToCheck(
        input({
          ...member,
          needed: { evaluation: ['gpt-4o'], generation: ['claude-sonnet'] },
        }),
      ),
    ).toEqual(['org-a', 'org-b'])
  })

  it('checks no membership for a superadmin generation', () => {
    expect(
      organizationsToCheck(
        input({
          ...member,
          isSuperadmin: true,
          needed: { evaluation: [], generation: ['claude-sonnet'] },
        }),
      ),
    ).toEqual([])
  })
})

describe('decideKeyWarnings: evaluation', () => {
  it('says nothing until the catalog has loaded', () => {
    expect(decideKeyWarnings(input({ catalog: null }))).toEqual([])
  })

  it('skips a model outside the official catalog', () => {
    expect(
      decideKeyWarnings(
        input({ needed: { evaluation: ['my-custom-model'], generation: [] } }),
      ),
    ).toEqual([])
  })

  it('warns when a project without organizations meets no personal key', () => {
    expect(decideKeyWarnings(input())).toEqual([
      {
        purpose: 'evaluation',
        provider: 'OpenAI',
        models: ['gpt-4o'],
        reason: 'no_organization',
        organizationIds: [],
        requiresPrivateKeys: null,
      },
    ])
  })

  it('groups the models of one provider into one warning', () => {
    const warnings = decideKeyWarnings(
      input({
        needed: {
          evaluation: ['gpt-4o', 'claude-sonnet', 'gpt-5.4-mini'],
          generation: [],
        },
      }),
    )
    expect(warnings.map((w) => [w.provider, w.models])).toEqual([
      ['OpenAI', ['gpt-4o', 'gpt-5.4-mini']],
      ['Anthropic', ['claude-sonnet']],
    ])
  })

  it('matches a personal key whatever the spelling of the provider', () => {
    expect(decideKeyWarnings(input({ personalProviders: ['openai'] }))).toEqual(
      [],
    )
  })

  it('stays silent while the personal key status is unknown', () => {
    expect(decideKeyWarnings(input({ personalProviders: null }))).toEqual([])
  })

  it('names the route of a creator outside every selected organization', () => {
    const [warning] = decideKeyWarnings(
      input({ visibility: 'organization', organizationIds: ['org-a'] }),
    )
    expect(warning.reason).toBe('not_member')
    expect(warning.organizationIds).toEqual([])
  })

  const twoOrganizations = (
    a: { providers: string[] | null; requiresPrivateKeys: boolean | null },
    b: { providers: string[] | null; requiresPrivateKeys: boolean | null },
  ) =>
    input({
      personalProviders: ['OpenAI'],
      visibility: 'organization',
      organizationIds: ['org-a', 'org-b'],
      memberships: { 'org-a': [], 'org-b': [] },
      organizations: { 'org-a': a, 'org-b': b },
    })

  it('warns when every possible organization lacks the key, whatever the personal keys', () => {
    expect(
      decideKeyWarnings(
        twoOrganizations(
          { providers: ['Anthropic'], requiresPrivateKeys: false },
          { providers: [], requiresPrivateKeys: false },
        ),
      ),
    ).toEqual([
      {
        purpose: 'evaluation',
        provider: 'OpenAI',
        models: ['gpt-4o'],
        reason: 'organization_without_key',
        organizationIds: ['org-a', 'org-b'],
        requiresPrivateKeys: false,
      },
    ])
  })

  it('reports whether the organizations require private keys', () => {
    const setting = (a: boolean | null, b: boolean | null) =>
      decideKeyWarnings(
        twoOrganizations(
          { providers: [], requiresPrivateKeys: a },
          { providers: [], requiresPrivateKeys: b },
        ),
      )[0].requiresPrivateKeys
    expect(setting(true, true)).toBe(true)
    expect(setting(false, false)).toBe(false)
    expect(setting(true, false)).toBeNull()
    expect(setting(null, null)).toBeNull()
  })

  it('stays silent when one possible organization has the key', () => {
    expect(
      decideKeyWarnings(
        twoOrganizations(
          { providers: [], requiresPrivateKeys: false },
          { providers: ['openai'], requiresPrivateKeys: false },
        ),
      ),
    ).toEqual([])
  })

  it('stays silent when an organization could not be checked', () => {
    expect(
      decideKeyWarnings(
        twoOrganizations(
          { providers: [], requiresPrivateKeys: false },
          { providers: null, requiresPrivateKeys: false },
        ),
      ),
    ).toEqual([])
    expect(
      decideKeyWarnings(
        input({
          visibility: 'organization',
          organizationIds: ['org-a'],
          memberships: { 'org-a': [] },
        }),
      ),
    ).toEqual([])
  })

  describe('a project attached through a group', () => {
    const grouped = (
      memberGroups: string[],
      requiresPrivateKeys: boolean | null,
    ) =>
      input({
        visibility: 'organization',
        organizationIds: ['org-a'],
        organizationGroupIds: { 'org-a': 'group-x' },
        memberships: { 'org-a': memberGroups },
        organizations: { 'org-a': { providers: [], requiresPrivateKeys } },
      })

    it('cannot see the key of a group the creator is not in', () => {
      expect(decideKeyWarnings(grouped([], false))).toEqual([])
      expect(decideKeyWarnings(grouped([], null))).toEqual([])
    })

    it('can when the organization requires private keys', () => {
      expect(decideKeyWarnings(grouped([], true))).toHaveLength(1)
    })

    it('can when the creator belongs to the group', () => {
      expect(decideKeyWarnings(grouped(['group-x'], false))).toHaveLength(1)
    })
  })

  it("reads a superadmin's group-scoped organization only when it requires private keys", () => {
    const superadminGrouped = (requiresPrivateKeys: boolean) =>
      input({
        isSuperadmin: true,
        visibility: 'organization',
        organizationIds: ['org-a'],
        organizationGroupIds: { 'org-a': 'group-x' },
        organizations: { 'org-a': { providers: [], requiresPrivateKeys } },
      })
    expect(decideKeyWarnings(superadminGrouped(true))).toHaveLength(1)
    expect(decideKeyWarnings(superadminGrouped(false))).toEqual([])
  })

  it('checks every organization of the project for a superadmin', () => {
    expect(
      decideKeyWarnings(
        input({
          isSuperadmin: true,
          visibility: 'organization',
          organizationIds: ['org-a'],
          organizations: {
            'org-a': { providers: [], requiresPrivateKeys: false },
          },
        }),
      ),
    ).toEqual([
      expect.objectContaining({
        reason: 'organization_without_key',
        organizationIds: ['org-a'],
      }),
    ])
  })
})

describe('decideKeyWarnings: generation', () => {
  const generation = (overrides: Partial<KeyReadinessInput> = {}) =>
    input({
      needed: { evaluation: [], generation: ['claude-sonnet'] },
      memberships: { 'org-a': [] },
      organizations: {
        'org-a': { providers: ['OpenAI'], requiresPrivateKeys: false },
      },
      ...overrides,
    })

  it('warns when neither the personal keys nor any membership provide the key', () => {
    expect(decideKeyWarnings(generation())).toEqual([
      {
        purpose: 'generation',
        provider: 'Anthropic',
        models: ['claude-sonnet'],
        reason: 'no_key_anywhere',
        organizationIds: ['org-a'],
        requiresPrivateKeys: null,
      },
    ])
  })

  it('lets the personal keys decide for a creator without memberships', () => {
    expect(
      decideKeyWarnings(generation({ memberships: {}, organizations: {} })),
    ).toEqual([
      expect.objectContaining({
        reason: 'no_key_anywhere',
        organizationIds: [],
      }),
    ])
  })

  it('stays silent when a membership provides the key', () => {
    expect(
      decideKeyWarnings(
        generation({
          organizations: {
            'org-a': { providers: ['Anthropic'], requiresPrivateKeys: false },
          },
        }),
      ),
    ).toEqual([])
  })

  it('stays silent when the creator holds the key', () => {
    expect(
      decideKeyWarnings(generation({ personalProviders: ['anthropic'] })),
    ).toEqual([])
  })

  it('stays silent when a membership could not be checked', () => {
    expect(decideKeyWarnings(generation({ organizations: {} }))).toEqual([])
  })

  it('stays silent for a superadmin, whose run may start from any organization', () => {
    expect(decideKeyWarnings(generation({ isSuperadmin: true }))).toEqual([])
  })

  it('ignores a group choice left over for an organization the project does not use', () => {
    expect(
      decideKeyWarnings(
        generation({
          organizationGroupIds: { 'org-a': 'group-x' },
          organizations: {
            'org-a': { providers: [], requiresPrivateKeys: false },
          },
        }),
      ),
    ).toHaveLength(1)
  })

  it('reports the evaluation before the generation', () => {
    const warnings = decideKeyWarnings(
      generation({
        needed: { evaluation: ['gpt-4o'], generation: ['claude-sonnet'] },
      }),
    )
    expect(warnings.map((w) => `${w.purpose}:${w.provider}`)).toEqual([
      'evaluation:OpenAI',
      'generation:Anthropic',
    ])
  })
})

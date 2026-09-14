/**
 * Which AI provider keys a project being created will need, and which of them
 * its creator provably will not have once grading or generation runs.
 *
 * The decision mirrors the backend and only reports a key as missing when the
 * client can prove it. Whatever it cannot see stays silent: a wrong warning
 * would send people after the wrong fix.
 *
 * Evaluation: `resolve_dispatch_org_for_project` (services/shared/
 * org_resolution.py) picks the organization, then `resolve_api_key`
 * (services/shared/shared_org_api_key_service.py) picks the key. The
 * dispatching user's active membership among the project's organizations
 * wins, a superadmin without one falls back to the project's first
 * organization, and everyone else spends their personal key, as does anyone
 * on a project without organizations.
 *
 * Generation: the organization tab a run is started from wins once membership
 * validates it (services/api/routers/generation_task_list.py), so the key can
 * come from any organization the user belongs to or from the personal keys. A
 * warning needs the provider to be missing from all of them.
 *
 * Per organization, `GET /organizations/{id}/api-keys/available-models`
 * resolves providers the way `resolve_api_key` does for the caller, with one
 * blind spot: a project attached through a group the caller is not in spends
 * that group's own key first, and the endpoint does not report it. Absence is
 * only provable there when the organization requires private keys.
 */

import type { EvaluationConfig } from '@/lib/api/evaluation-types'
import { DEFAULT_MODEL_ID } from '@/lib/modelDefaults'
import type { WizardData, WizardVisibility } from './types'

export type KeyPurpose = 'evaluation' | 'generation'

export interface NeededModels {
  evaluation: string[]
  generation: string[]
}

/** What the client learned about one organization; null where it could not. */
export interface OrganizationKeyFacts {
  /** Providers the creator can run there, from available-models. */
  providers: string[] | null
  /** The organization's `require_private_keys` setting. */
  requiresPrivateKeys: boolean | null
}

export interface KeyReadinessInput {
  needed: NeededModels
  /** The official model catalog; null until it loaded. */
  catalog: Array<{ id: string; provider: string }> | null
  /** Providers the creator holds a personal key for; null when unknown. */
  personalProviders: string[] | null
  visibility: WizardVisibility
  organizationIds: string[]
  organizationGroupIds: Record<string, string | null>
  /** The creator's active memberships: organization id to the ids of the
   * groups they belong to in it. */
  memberships: Record<string, string[]>
  isSuperadmin: boolean
  organizations: Record<string, OrganizationKeyFacts>
}

export type EvaluationKeyRoute =
  | { kind: 'personal'; reason: 'no_organization' | 'not_member' }
  | { kind: 'organizations'; organizationIds: string[] }

export type KeyWarningReason =
  | 'no_organization'
  | 'not_member'
  | 'organization_without_key'
  | 'no_key_anywhere'

export interface KeyWarning {
  purpose: KeyPurpose
  /** The provider as the catalog names it, e.g. "OpenAI". */
  provider: string
  models: string[]
  reason: KeyWarningReason
  /** The organizations that were checked: the possible organizations for an
   * evaluation, every membership for a generation. Empty when the personal
   * key alone decides. */
  organizationIds: string[]
  /** For an organization without the key: true when every checked
   * organization requires private keys, false when none does, null when that
   * is mixed or unknown. */
  requiresPrivateKeys: boolean | null
}

const unique = (values: string[]): string[] => Array.from(new Set(values))

const normalizeProvider = (provider: string): string =>
  provider.trim().toLowerCase()

const hasOwn = (record: object, key: string): boolean =>
  Object.prototype.hasOwnProperty.call(record, key)

/** The model ids an evaluation config sends to an LLM, as the worker resolves
 * them. A judge the config does not name runs on DEFAULT_MODEL_ID, the
 * worker's DEFAULT_JUDGE_MODEL_ID (services/shared/model_defaults.py); a
 * drift test pins the two together. */
export function judgeModelIds(config: EvaluationConfig): string[] {
  // The worker keeps a config unless `enabled` is present and falsy.
  if (config.enabled !== undefined && !config.enabled) return []
  if (!config.metric?.startsWith('llm_judge_')) return []
  const params: Record<string, unknown> = { ...config.metric_parameters }
  const judges = params.judges
  if (Array.isArray(judges) && judges.length > 0) {
    return judges.map((entry) => {
      const id = (entry as { judge_model_id?: unknown } | null)?.judge_model_id
      return typeof id === 'string' && id ? id : DEFAULT_MODEL_ID
    })
  }
  const model = params.judge_model
  return [typeof model === 'string' && model ? model : DEFAULT_MODEL_ID]
}

export function neededModels(
  data: Pick<WizardData, 'features' | 'evaluationConfigs' | 'selectedModelIds'>,
): NeededModels {
  return {
    evaluation: data.features.evaluation
      ? unique(data.evaluationConfigs.flatMap(judgeModelIds))
      : [],
    generation: data.features.llmGeneration
      ? unique(data.selectedModelIds)
      : [],
  }
}

export function hasNeededModels(needed: NeededModels): boolean {
  return needed.evaluation.length > 0 || needed.generation.length > 0
}

/** The organizations the project will be attached to. The wizard's
 * visibility update replaces the attachments with exactly the selected ones,
 * and a private or public project gets none. */
export function projectOrganizationIds(
  input: Pick<KeyReadinessInput, 'visibility' | 'organizationIds'>,
): string[] {
  return input.visibility === 'organization'
    ? unique(input.organizationIds)
    : []
}

/** Where an evaluation dispatched by the creator takes its key from. */
export function evaluationKeyRoute(
  input: Pick<
    KeyReadinessInput,
    'visibility' | 'organizationIds' | 'memberships' | 'isSuperadmin'
  >,
): EvaluationKeyRoute {
  const projectOrganizations = projectOrganizationIds(input)
  if (projectOrganizations.length === 0) {
    return { kind: 'personal', reason: 'no_organization' }
  }
  // The server takes the first matching membership in no defined order, so
  // every candidate has to lack the key before a warning is provable.
  const memberOrganizations = projectOrganizations.filter((id) =>
    hasOwn(input.memberships, id),
  )
  if (memberOrganizations.length > 0) {
    return { kind: 'organizations', organizationIds: memberOrganizations }
  }
  // A superadmin falls back to the project's first organization, whose order
  // is not known here either.
  if (input.isSuperadmin) {
    return { kind: 'organizations', organizationIds: projectOrganizations }
  }
  return { kind: 'personal', reason: 'not_member' }
}

/** The organizations whose facts the decision needs. */
export function organizationsToCheck(
  input: Pick<
    KeyReadinessInput,
    'needed' | 'visibility' | 'organizationIds' | 'memberships' | 'isSuperadmin'
  >,
): string[] {
  const ids: string[] = []
  if (input.needed.evaluation.length > 0) {
    const route = evaluationKeyRoute(input)
    if (route.kind === 'organizations') ids.push(...route.organizationIds)
  }
  if (input.needed.generation.length > 0 && !input.isSuperadmin) {
    ids.push(...Object.keys(input.memberships))
  }
  return unique(ids)
}

function personalKeyProvablyMissing(
  provider: string,
  input: KeyReadinessInput,
): boolean {
  return (
    input.personalProviders !== null &&
    !input.personalProviders.some((p) => normalizeProvider(p) === provider)
  )
}

function providerProvablyAbsentIn(
  organizationId: string,
  provider: string,
  input: KeyReadinessInput,
): boolean {
  const facts = hasOwn(input.organizations, organizationId)
    ? input.organizations[organizationId]
    : undefined
  if (!facts || facts.providers === null) return false
  if (facts.providers.some((p) => normalizeProvider(p) === provider)) {
    return false
  }
  const group = projectOrganizationIds(input).includes(organizationId)
    ? (input.organizationGroupIds[organizationId] ?? null)
    : null
  if (!group) return true
  const memberGroups = hasOwn(input.memberships, organizationId)
    ? input.memberships[organizationId]
    : []
  if (memberGroups.includes(group)) return true
  return facts.requiresPrivateKeys === true
}

/** True when every organization requires private keys, false when none
 * does, null when that is mixed or unknown. */
function commonPrivateKeySetting(
  settings: Array<boolean | null>,
): boolean | null {
  if (settings.every((setting) => setting === true)) return true
  if (settings.every((setting) => setting === false)) return false
  return null
}

function evaluationWarning(
  provider: string,
  entry: { provider: string; models: string[] },
  input: KeyReadinessInput,
): KeyWarning | null {
  const route = evaluationKeyRoute(input)
  if (route.kind === 'personal') {
    if (!personalKeyProvablyMissing(provider, input)) return null
    return {
      purpose: 'evaluation',
      provider: entry.provider,
      models: entry.models,
      reason: route.reason,
      organizationIds: [],
      requiresPrivateKeys: null,
    }
  }
  const absentEverywhere = route.organizationIds.every((id) =>
    providerProvablyAbsentIn(id, provider, input),
  )
  if (!absentEverywhere) return null
  // Absence was only provable because every candidate's facts were loaded.
  return {
    purpose: 'evaluation',
    provider: entry.provider,
    models: entry.models,
    reason: 'organization_without_key',
    organizationIds: route.organizationIds,
    requiresPrivateKeys: commonPrivateKeySetting(
      route.organizationIds.map(
        (id) => input.organizations[id].requiresPrivateKeys,
      ),
    ),
  }
}

function generationWarning(
  provider: string,
  entry: { provider: string; models: string[] },
  input: KeyReadinessInput,
): KeyWarning | null {
  // Any organization tab is honoured for a superadmin, so which key a run
  // will spend cannot be known in advance.
  if (input.isSuperadmin) return null
  if (!personalKeyProvablyMissing(provider, input)) return null
  const memberOrganizations = Object.keys(input.memberships)
  const absentEverywhere = memberOrganizations.every((id) =>
    providerProvablyAbsentIn(id, provider, input),
  )
  if (!absentEverywhere) return null
  return {
    purpose: 'generation',
    provider: entry.provider,
    models: entry.models,
    reason: 'no_key_anywhere',
    organizationIds: memberOrganizations,
    requiresPrivateKeys: null,
  }
}

/** One warning per purpose and provider the creator provably lacks a key for. */
export function decideKeyWarnings(input: KeyReadinessInput): KeyWarning[] {
  if (!input.catalog) return []
  const providerOf = new Map(input.catalog.map((m) => [m.id, m.provider]))
  const warnings: KeyWarning[] = []
  for (const purpose of ['evaluation', 'generation'] as const) {
    const byProvider = new Map<string, { provider: string; models: string[] }>()
    for (const modelId of input.needed[purpose]) {
      // A model outside the official catalog, such as a custom model, gets
      // its credential another way, so nothing is provable about it here.
      const provider = providerOf.get(modelId)
      if (!provider) continue
      const key = normalizeProvider(provider)
      const entry = byProvider.get(key) ?? { provider, models: [] }
      entry.models.push(modelId)
      byProvider.set(key, entry)
    }
    for (const [provider, entry] of byProvider) {
      const warning =
        purpose === 'evaluation'
          ? evaluationWarning(provider, entry, input)
          : generationWarning(provider, entry, input)
      if (warning) warnings.push(warning)
    }
  }
  return warnings
}

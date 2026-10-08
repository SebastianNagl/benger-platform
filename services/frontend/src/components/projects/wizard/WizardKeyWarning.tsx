'use client'

/**
 * Warns before a project is created when grading or generation will need an
 * AI provider key that its creator will not have. The rule itself lives in
 * `keyReadiness.ts`. This component only gathers what the rule needs and says
 * what to do. It never blocks creation, and it stays silent whenever a fact
 * could not be loaded.
 */

import { Alert } from '@/components/shared/Alert'
import { useOptionalAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import apiClient from '@/lib/api'
import { organizationsAPI } from '@/lib/api/organizations'
import Link from 'next/link'
import { useEffect, useMemo, useRef, useState } from 'react'
import {
  decideKeyWarnings,
  hasNeededModels,
  type KeyWarning,
  neededModels,
  type OrganizationKeyFacts,
  organizationsToCheck,
  projectGroupId,
} from './keyReadiness'
import type { WizardData } from './types'

// A missing method, a 403 or a network error all mean "unknown", and an
// unknown fact must silence the warning, never break the wizard.
async function attempt<T>(load: () => Promise<T>): Promise<T | null> {
  try {
    return await load()
  } catch {
    return null
  }
}

export function parseCatalog(
  value: unknown,
): Array<{ id: string; provider: string }> | null {
  if (!Array.isArray(value)) return null
  return value
    .filter(
      (model): model is { id: string; provider: string } =>
        typeof model?.id === 'string' && typeof model?.provider === 'string',
    )
    .map(({ id, provider }) => ({ id, provider }))
}

export function parsePersonalProviders(value: unknown): string[] | null {
  const status = (value as { api_key_status?: unknown } | null)?.api_key_status
  if (!status || typeof status !== 'object' || Array.isArray(status)) {
    return null
  }
  const entries = Object.entries(status as Record<string, unknown>)
  // The endpoint answers `{}` when it could not read the user, which says
  // nothing about their keys.
  if (entries.length === 0) return null
  return entries
    .filter(([, hasKey]) => hasKey === true)
    .map(([provider]) => provider)
}

export function parseProviders(value: unknown): string[] | null {
  if (!Array.isArray(value)) return null
  return Array.from(
    new Set(
      value
        .map((model) => (model as { provider?: unknown } | null)?.provider)
        .filter((provider): provider is string => typeof provider === 'string'),
    ),
  )
}

export function parseRequiresPrivateKeys(value: unknown): boolean | null {
  const flag = (value as { require_private_keys?: unknown } | null)
    ?.require_private_keys
  return typeof flag === 'boolean' ? flag : null
}

/** Facts are per organization and the project's group there: the "who
 * pays" setting is the group's effective one. */
const factsKey = (organizationId: string, groupId: string | null): string =>
  `${organizationId}::${groupId ?? ''}`

async function loadOrganizationFacts(
  organizationId: string,
  groupId: string | null,
): Promise<[string, OrganizationKeyFacts]> {
  const [models, settings] = await Promise.all([
    attempt(() => organizationsAPI.getOrgAvailableModels(organizationId)),
    attempt(() =>
      groupId
        ? organizationsAPI.getOrgApiKeySettings(organizationId, groupId)
        : organizationsAPI.getOrgApiKeySettings(organizationId),
    ),
  ])
  return [
    factsKey(organizationId, groupId),
    {
      providers: parseProviders(models),
      requiresPrivateKeys: parseRequiresPrivateKeys(settings),
    },
  ]
}

interface WizardKeyWarningProps {
  data: WizardData
}

export function WizardKeyWarning({ data }: WizardKeyWarningProps) {
  const { t } = useI18n()
  const auth = useOptionalAuth()
  // Memberships and the superadmin flag decide which key a run spends. The
  // auth context sets them together with the signed-in user, so until that
  // user is known nothing is provable and the warning stays silent.
  const signedIn = Boolean(auth?.user)
  const isSuperadmin = Boolean(auth?.user?.is_superadmin)
  const authOrganizations = auth?.organizations

  // /auth/me/contexts lists every organization for a superadmin; only a role
  // marks an actual membership.
  const memberships = useMemo(() => {
    const result: Record<string, string[]> = {}
    for (const organization of authOrganizations ?? []) {
      if (!organization.role) continue
      result[organization.id] = (organization.groups ?? []).map((g) => g.id)
    }
    return result
  }, [authOrganizations])

  const needed = useMemo(
    () =>
      neededModels({
        features: data.features,
        evaluationConfigs: data.evaluationConfigs,
        selectedModelIds: data.selectedModelIds,
      }),
    [data.features, data.evaluationConfigs, data.selectedModelIds],
  )
  const active = signedIn && hasNeededModels(needed)

  const [catalog, setCatalog] = useState<Array<{
    id: string
    provider: string
  }> | null>(null)
  const [personalProviders, setPersonalProviders] = useState<string[] | null>(
    null,
  )
  const [organizationFacts, setOrganizationFacts] = useState<
    Record<string, OrganizationKeyFacts>
  >({})

  useEffect(() => {
    if (!active) return
    let cancelled = false
    void attempt(() => apiClient.evaluations.getPublicModelCatalog()).then(
      (value) => {
        if (!cancelled) setCatalog(parseCatalog(value))
      },
    )
    void attempt(() => apiClient.evaluations.getUserApiKeys()).then((value) => {
      if (!cancelled) setPersonalProviders(parsePersonalProviders(value))
    })
    return () => {
      cancelled = true
    }
  }, [active])

  const toCheck = useMemo(
    () =>
      active
        ? organizationsToCheck({
            needed,
            visibility: data.visibility,
            organizationIds: data.organizationIds,
            memberships,
            isSuperadmin,
          })
        : [],
    [
      active,
      needed,
      data.visibility,
      data.organizationIds,
      memberships,
      isSuperadmin,
    ],
  )

  // Each organization with the group the project gets there.
  const toCheckScoped = useMemo(
    () =>
      toCheck.map((id) => ({
        id,
        groupId: projectGroupId(
          {
            visibility: data.visibility,
            organizationIds: data.organizationIds,
            organizationGroupIds: data.organizationGroupIds,
          },
          id,
        ),
      })),
    [toCheck, data.visibility, data.organizationIds, data.organizationGroupIds],
  )

  // (Organization, group) pairs already requested, so a re-render never
  // fetches twice. The set lives for the component's lifetime; a dropped
  // request is taken out again so the next selection asks anew.
  const requested = useRef(new Set<string>())
  useEffect(() => {
    const requestedKeys = requested.current
    const missing = toCheckScoped.filter(
      ({ id, groupId }) => !requestedKeys.has(factsKey(id, groupId)),
    )
    if (missing.length === 0) return
    missing.forEach(({ id, groupId }) =>
      requestedKeys.add(factsKey(id, groupId)),
    )
    let cancelled = false
    void Promise.all(
      missing.map(({ id, groupId }) => loadOrganizationFacts(id, groupId)),
    ).then((entries) => {
      if (cancelled) return
      setOrganizationFacts((previous) => ({
        ...previous,
        ...Object.fromEntries(entries),
      }))
    })
    return () => {
      cancelled = true
      missing.forEach(({ id, groupId }) =>
        requestedKeys.delete(factsKey(id, groupId)),
      )
    }
  }, [toCheckScoped])

  // The facts for the current selection, keyed by organization.
  const currentFacts = useMemo(() => {
    const result: Record<string, OrganizationKeyFacts> = {}
    for (const { id, groupId } of toCheckScoped) {
      const facts = organizationFacts[factsKey(id, groupId)]
      if (facts) result[id] = facts
    }
    return result
  }, [toCheckScoped, organizationFacts])

  const warnings = useMemo(
    () =>
      active
        ? decideKeyWarnings({
            needed,
            catalog,
            personalProviders,
            visibility: data.visibility,
            organizationIds: data.organizationIds,
            organizationGroupIds: data.organizationGroupIds,
            memberships,
            isSuperadmin,
            organizations: currentFacts,
          })
        : [],
    [
      active,
      needed,
      catalog,
      personalProviders,
      data.visibility,
      data.organizationIds,
      data.organizationGroupIds,
      memberships,
      isSuperadmin,
      currentFacts,
    ],
  )

  if (warnings.length === 0) return null

  const organizationNames = (ids: string[]): string =>
    ids
      .map((id) => {
        const organization = authOrganizations?.find((o) => o.id === id)
        return organization?.display_name || organization?.name || id
      })
      .join(', ')

  const purposeText = (warning: KeyWarning): string => {
    const models = warning.models.join(', ')
    return warning.purpose === 'evaluation'
      ? t(
          'projects.creation.wizard.keyWarning.purpose.evaluation',
          'Bewertung mit {models}',
          { models },
        )
      : t(
          'projects.creation.wizard.keyWarning.purpose.generation',
          'Generierung mit {models}',
          { models },
        )
  }

  const reasonText = (warning: KeyWarning): string => {
    const provider = warning.provider
    switch (warning.reason) {
      case 'no_organization':
        return t(
          'projects.creation.wizard.keyWarning.reason.noOrganization',
          'Das Projekt gehört keiner Organisation an, daher wird mit Ihrem eigenen {provider}-Schlüssel bewertet, und Sie haben keinen hinterlegt.',
          { provider },
        )
      case 'not_member':
        return t(
          'projects.creation.wizard.keyWarning.reason.notMember',
          'Sie sind in keiner der gewählten Organisationen Mitglied, daher wird mit Ihrem eigenen {provider}-Schlüssel bewertet, und Sie haben keinen hinterlegt.',
          { provider },
        )
      case 'organization_without_key':
        return t(
          'projects.creation.wizard.keyWarning.reason.organizationWithoutKey',
          'In {organizations} steht Ihnen kein {provider}-Schlüssel zur Verfügung.',
          {
            provider,
            organizations: organizationNames(warning.organizationIds),
          },
        )
      default:
        return warning.organizationIds.length === 0
          ? t(
              'projects.creation.wizard.keyWarning.reason.noPersonalKey',
              'Sie haben keinen eigenen {provider}-Schlüssel hinterlegt und gehören keiner Organisation an.',
              { provider },
            )
          : t(
              'projects.creation.wizard.keyWarning.reason.noKeyAnywhere',
              'Weder Ihre eigenen Schlüssel noch Ihre Organisationen stellen einen {provider}-Schlüssel bereit.',
              { provider },
            )
    }
  }

  const actionText = (warning: KeyWarning): string => {
    const provider = warning.provider
    switch (warning.reason) {
      case 'no_organization':
        return t(
          'projects.creation.wizard.keyWarning.action.noOrganization',
          'Wählen Sie im ersten Schritt eine Organisation mit {provider}-Schlüssel, oder hinterlegen Sie einen eigenen Schlüssel im Profil.',
          { provider },
        )
      case 'not_member':
        return t(
          'projects.creation.wizard.keyWarning.action.notMember',
          'Wählen Sie eine Organisation, in der Sie Mitglied sind, oder hinterlegen Sie einen eigenen Schlüssel im Profil.',
          { provider },
        )
      case 'organization_without_key':
        if (warning.requiresPrivateKeys === true) {
          return t(
            'projects.creation.wizard.keyWarning.action.requiresPrivateKeys',
            'Die Organisation verlangt eigene Schlüssel. Hinterlegen Sie einen {provider}-Schlüssel im Profil.',
            { provider },
          )
        }
        if (warning.requiresPrivateKeys === false) {
          return t(
            'projects.creation.wizard.keyWarning.action.askAdmin',
            'Bitten Sie die Administration der Organisation, einen {provider}-Schlüssel zu hinterlegen.',
            { provider },
          )
        }
        return t(
          'projects.creation.wizard.keyWarning.action.askAdminOrPersonal',
          'Bitten Sie die Administration der Organisation um einen {provider}-Schlüssel, oder hinterlegen Sie einen eigenen im Profil, falls die Organisation eigene Schlüssel verlangt.',
          { provider },
        )
      default:
        return warning.organizationIds.length === 0
          ? t(
              'projects.creation.wizard.keyWarning.action.addPersonalKey',
              'Hinterlegen Sie einen eigenen {provider}-Schlüssel im Profil.',
              { provider },
            )
          : t(
              'projects.creation.wizard.keyWarning.action.noKeyAnywhere',
              'Hinterlegen Sie einen eigenen Schlüssel im Profil, oder bitten Sie die Administration Ihrer Organisation um einen {provider}-Schlüssel.',
              { provider },
            )
    }
  }

  return (
    <Alert variant="warning" className="mb-8">
      <div className="space-y-3 text-sm" data-testid="wizard-key-warning">
        <p className="font-medium text-zinc-900 dark:text-white">
          {t(
            'projects.creation.wizard.keyWarning.title',
            'Für dieses Projekt fehlt ein API-Schlüssel',
          )}
        </p>
        <ul className="list-disc space-y-2 pl-5 text-zinc-700 dark:text-zinc-300">
          {warnings.map((warning) => (
            <li
              key={`${warning.purpose}-${warning.provider}`}
              data-testid={`wizard-key-warning-${warning.purpose}-${warning.provider.toLowerCase()}`}
            >
              <span className="font-medium text-zinc-900 dark:text-white">
                {purposeText(warning)}
              </span>
              {': '}
              {reasonText(warning)} {actionText(warning)}
            </li>
          ))}
        </ul>
        <p className="text-zinc-600 dark:text-zinc-400">
          <Link
            href="/profile"
            className="font-medium text-emerald-600 hover:text-emerald-700 dark:text-emerald-400 dark:hover:text-emerald-300"
            data-testid="wizard-key-warning-profile-link"
          >
            {t(
              'projects.creation.wizard.keyWarning.manageKeys',
              'API-Schlüssel im Profil verwalten',
            )}
          </Link>{' '}
          {t(
            'projects.creation.wizard.keyWarning.nonBlocking',
            'Sie können das Projekt trotzdem erstellen.',
          )}
        </p>
      </div>
    </Alert>
  )
}

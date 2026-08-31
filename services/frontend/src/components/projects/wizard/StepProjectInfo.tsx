'use client'

import { Input } from '@/components/shared/Input'
import { Label } from '@/components/shared/Label'
import { Textarea } from '@/components/shared/Textarea'
import { useI18n } from '@/contexts/I18nContext'
import {
  organizationsAPI,
  type OrganizationGroup,
} from '@/lib/api/organizations'
import { useSlot } from '@/lib/extensions/slots'
import { cn } from '@/lib/utils'
import { IconPickerModal, ProjectTypeSelector } from './ProjectTypeAndIcon'
import { defaultIconForKind } from '@/lib/projectKind'
import { useEffect, useState } from 'react'
import {
  WizardData,
  WizardFeatures,
  WizardPublicRole,
  WizardVisibility,
} from './types'


interface StepProjectInfoProps {
  data: WizardData
  onChange: (partial: Partial<WizardData>) => void
  errors: Record<string, string>
}

const FEATURE_CHECKBOXES: {
  key: keyof WizardFeatures
  labelKey: string
  descriptionKey: string
}[] = [
  {
    key: 'dataImport',
    labelKey: 'projects.creation.wizard.features.dataImport',
    descriptionKey: 'projects.creation.wizard.features.dataImportDescription',
  },
  {
    key: 'annotation',
    labelKey: 'projects.creation.wizard.features.annotation',
    descriptionKey: 'projects.creation.wizard.features.annotationDescription',
  },
  {
    key: 'llmGeneration',
    labelKey: 'projects.creation.wizard.features.llmGeneration',
    descriptionKey:
      'projects.creation.wizard.features.llmGenerationDescription',
  },
  {
    key: 'evaluation',
    labelKey: 'projects.creation.wizard.features.evaluation',
    descriptionKey: 'projects.creation.wizard.features.evaluationDescription',
  },
]

export function StepProjectInfo({
  data,
  onChange,
  errors,
}: StepProjectInfoProps) {
  const { t } = useI18n()
  const [iconPickerOpen, setIconPickerOpen] = useState(false)
  const [orgs, setOrgs] = useState<
    Array<{
      id: string
      name: string
      role?: 'ORG_ADMIN' | 'CONTRIBUTOR' | 'ANNOTATOR'
    }>
  >([])
  // Organization groups per org id (undefined = not fetched yet, [] =
  // fetched and empty / fetch failed). Fetched lazily for checked orgs.
  const [groupsByOrg, setGroupsByOrg] = useState<
    Record<string, OrganizationGroup[]>
  >({})
  // Extended-edition feature row rendered below the core feature checkboxes:
  // the experimental KI-Generator, styled like the rows above and toggling
  // `features.synthetic` (which adds the synthetic step to the wizard). Null
  // in the community edition.
  const SyntheticEntry = useSlot('ProjectWizardSyntheticEntry')
  // Extended-edition feature row: the experimental AI-Bewertungsbogen step
  // (per-task rubric generation as a second evaluation method). Null in the
  // community edition.
  const RubricEntry = useSlot('ProjectWizardRubricEntry')

  useEffect(() => {
    let cancelled = false
    if (data.visibility !== 'organization') return
    let p: Promise<unknown>
    try {
      p = Promise.resolve(organizationsAPI.getOrganizations())
    } catch {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setOrgs([])
      return
    }
    p.then((rows) => {
      if (cancelled) return
      setOrgs(Array.isArray(rows) ? rows : [])
    }).catch(() => {
      if (!cancelled) setOrgs([])
    })
    return () => {
      cancelled = true
    }
  }, [data.visibility])

  // Fetch the group list of every checked org once (mirrors the defensive
  // orgs fetch above: a failing/absent groups endpoint yields no groups).
  useEffect(() => {
    let cancelled = false
    if (data.visibility !== 'organization') return
    const missing = data.organizationIds.filter(
      (orgId) => groupsByOrg[orgId] === undefined
    )
    if (missing.length === 0) return
    missing.forEach((orgId) => {
      let p: Promise<unknown>
      try {
        p = Promise.resolve(organizationsAPI.getGroups(orgId))
      } catch {
        // eslint-disable-next-line react-hooks/set-state-in-effect
        setGroupsByOrg((prev) => ({ ...prev, [orgId]: [] }))
        return
      }
      p.then((rows) => {
        if (cancelled) return
        setGroupsByOrg((prev) => ({
          ...prev,
          [orgId]: Array.isArray(rows) ? (rows as OrganizationGroup[]) : [],
        }))
      }).catch(() => {
        if (!cancelled) {
          setGroupsByOrg((prev) => ({ ...prev, [orgId]: [] }))
        }
      })
    })
    return () => {
      cancelled = true
    }
  }, [data.visibility, data.organizationIds, groupsByOrg])

  // Default group scope: when the user belongs to exactly one group of a
  // checked org, preselect it; otherwise the org stays org-wide (implicit
  // null). Only fires while the org has no explicit choice yet.
  useEffect(() => {
    if (data.visibility !== 'organization') return
    const defaults: Record<string, string | null> = {}
    for (const orgId of data.organizationIds) {
      if (data.organizationGroupIds[orgId] !== undefined) continue
      const groups = groupsByOrg[orgId]
      if (groups === undefined) continue
      const memberGroups = groups.filter(
        (group) => group.is_active && group.is_member
      )
      if (memberGroups.length === 1) {
        defaults[orgId] = memberGroups[0].id
      }
    }
    if (Object.keys(defaults).length > 0) {
      onChange({
        organizationGroupIds: { ...data.organizationGroupIds, ...defaults },
      })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data.visibility, data.organizationIds, data.organizationGroupIds, groupsByOrg])

  const toggleFeature = (key: keyof WizardFeatures) => {
    onChange({
      features: { ...data.features, [key]: !data.features[key] },
    })
  }

  const toggleOrg = (orgId: string) => {
    const next = data.organizationIds.includes(orgId)
      ? data.organizationIds.filter((id) => id !== orgId)
      : [...data.organizationIds, orgId]
    onChange({ organizationIds: next })
  }

  const setOrgGroup = (orgId: string, groupId: string | null) => {
    onChange({
      organizationGroupIds: { ...data.organizationGroupIds, [orgId]: groupId },
    })
  }

  // Groups offered for one org: org admins pick any active group, everyone
  // else only active groups they belong to.
  const groupOptionsFor = (org: {
    id: string
    role?: 'ORG_ADMIN' | 'CONTRIBUTOR' | 'ANNOTATOR'
  }): OrganizationGroup[] => {
    const groups = groupsByOrg[org.id] ?? []
    const isOrgAdmin = org.role === 'ORG_ADMIN'
    return groups.filter(
      (group) => group.is_active && (isOrgAdmin || group.is_member)
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="mb-2 text-2xl font-semibold text-zinc-900 dark:text-white">
            {t('projects.creation.wizard.step1.title')}
          </h2>
          <p className="text-zinc-600 dark:text-zinc-400">
            {t('projects.creation.wizard.step1.subtitle')}
          </p>
        </div>
        {/* Project icon: pre-filled with the type default; click to pick. */}
        <div className="flex shrink-0 flex-col items-center gap-1">
          <button
            type="button"
            onClick={() => setIconPickerOpen(true)}
            title={t('projects.creation.wizard.step1.icon.title', 'Symbol wählen')}
            data-testid="project-icon-button"
            className="flex h-14 w-14 items-center justify-center rounded-xl border border-zinc-200 text-3xl transition-colors hover:border-emerald-400 hover:bg-emerald-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 dark:border-zinc-700 dark:hover:bg-emerald-900/20"
          >
            {data.icon ||
              defaultIconForKind(data.projectKind === 'generic' ? null : data.projectKind)}
          </button>
          <span className="text-[11px] text-zinc-500 dark:text-zinc-400">
            {t('projects.creation.wizard.step1.icon.clickToEdit', 'Klicken zum Bearbeiten')}
          </span>
        </div>
        <IconPickerModal
          isOpen={iconPickerOpen}
          onClose={() => setIconPickerOpen(false)}
          icon={data.icon}
          projectKind={data.projectKind}
          onPick={(icon) => onChange({ icon })}
        />
      </div>

      <div className="space-y-4">
        <div>
          <Label htmlFor="title">
            {t('projects.creation.wizard.step1.projectName')}{' '}
            <span className="text-red-600 dark:text-red-400">*</span>
          </Label>
          <Input
            id="title"
            placeholder={t(
              'projects.creation.wizard.step1.projectNamePlaceholder'
            )}
            value={data.title}
            onChange={(e) => onChange({ title: e.target.value })}
            className={cn(errors.title && 'border-red-500 dark:border-red-400')}
            data-testid="project-create-name-input"
          />
          {errors.title && (
            <p className="mt-1 text-sm text-red-600 dark:text-red-400">
              {errors.title}
            </p>
          )}
        </div>

        <div>
          <Label htmlFor="description">
            {t('projects.creation.wizard.step1.description')}
            <span className="ml-2 text-sm text-zinc-500 dark:text-zinc-400">
              {t('projects.creation.wizard.step1.optional')}
            </span>
          </Label>
          <Textarea
            id="description"
            placeholder={t(
              'projects.creation.wizard.step1.descriptionPlaceholder'
            )}
            value={data.description}
            onChange={(e) => onChange({ description: e.target.value })}
            rows={4}
            data-testid="project-create-description-textarea"
          />
        </div>

        <ProjectTypeSelector projectKind={data.projectKind} onChange={onChange} />
      </div>

      <hr className="border-zinc-200 dark:border-zinc-700" />

      {/* Feature Checkboxes */}
      <div className="space-y-3">
        <Label>
          {t('projects.creation.wizard.features.title')}{' '}
          <span className="font-normal text-zinc-500 dark:text-zinc-400">
            ({t('projects.creation.wizard.features.editLater')})
          </span>
        </Label>

        <div className="space-y-4">
          {FEATURE_CHECKBOXES.map(({ key, labelKey, descriptionKey }) => (
            <div
              key={key}
              className="flex items-center justify-between"
              data-testid={`wizard-feature-${key}`}
            >
              <div>
                <Label>
                  {t(labelKey)}
                </Label>
                <p className="text-sm text-zinc-500 dark:text-zinc-400">
                  {t(descriptionKey)}
                </p>
              </div>
              <input
                type="checkbox"
                checked={data.features[key]}
                onChange={() => toggleFeature(key)}
                className="h-4 w-4 rounded border-zinc-300 accent-emerald-600 focus:ring-emerald-500 dark:border-zinc-600 dark:accent-emerald-500"
              />
            </div>
          ))}

          {SyntheticEntry && (
            // eslint-disable-next-line react-hooks/static-components
            <SyntheticEntry
              checked={data.features.synthetic}
              onToggle={() => toggleFeature('synthetic')}
            />
          )}

          {RubricEntry && (
            // eslint-disable-next-line react-hooks/static-components
            <RubricEntry
              checked={data.features.rubric}
              onToggle={() => toggleFeature('rubric')}
            />
          )}
        </div>
      </div>

      <hr className="border-zinc-200 dark:border-zinc-700" />

      {/* Visibility */}
      <div className="space-y-3">
        <Label>
          {t('projects.creation.wizard.step1.visibilityLabel')}
        </Label>
        <p className="text-sm text-zinc-500 dark:text-zinc-400">
          {t('projects.creation.wizard.step1.visibilityDescription')}
        </p>
        <div className="space-y-2">
          {(
            [
              {
                value: 'private',
                labelKey: 'projects.creation.wizard.step1.visibility.private',
                descKey:
                  'projects.creation.wizard.step1.visibility.privateDescription',
              },
              {
                value: 'organization',
                labelKey:
                  'projects.creation.wizard.step1.visibility.organization',
                descKey:
                  'projects.creation.wizard.step1.visibility.organizationDescription',
              },
              {
                value: 'public',
                labelKey: 'projects.creation.wizard.step1.visibility.public',
                descKey:
                  'projects.creation.wizard.step1.visibility.publicDescription',
              },
            ] as Array<{
              value: WizardVisibility
              labelKey: string
              descKey: string
            }>
          ).map(({ value, labelKey, descKey }) => (
            <label
              key={value}
              className="flex cursor-pointer items-center justify-between"
              data-testid={`wizard-visibility-${value}-option`}
            >
              <div>
                <Label>{t(labelKey)}</Label>
                <p className="text-sm text-zinc-500 dark:text-zinc-400">
                  {t(descKey)}
                </p>
              </div>
              <input
                type="radio"
                name="wizard-visibility"
                checked={data.visibility === value}
                onChange={() => onChange({ visibility: value })}
                className="h-4 w-4 border-zinc-300 accent-emerald-600 focus:ring-emerald-500 dark:border-zinc-600 dark:accent-emerald-500"
                data-testid={`wizard-visibility-${value}-radio`}
              />
            </label>
          ))}
        </div>

        {data.visibility === 'organization' && (
          <div
            className="ml-6 space-y-2"
            data-testid="wizard-organization-section"
          >
            <Label>
              {t('projects.creation.wizard.step1.assignedOrganizations')}
              <span className="ml-2 text-sm text-red-600 dark:text-red-400">
                *
              </span>
            </Label>
            <p className="text-sm text-zinc-500 dark:text-zinc-400">
              {t('projects.creation.wizard.step1.assignedOrganizationsHelp')}
            </p>
            {orgs.length === 0 ? (
              <p className="text-sm text-zinc-500 dark:text-zinc-400">
                {t(
                  'projects.creation.wizard.step1.noOrganizationsAvailable',
                  'No organizations available.'
                )}
              </p>
            ) : (
              <div
                className="space-y-2"
                data-testid="wizard-organization-list"
              >
                {orgs.map((org) => {
                  const isChecked = data.organizationIds.includes(org.id)
                  const groupOptions = isChecked ? groupOptionsFor(org) : []
                  return (
                    <div key={org.id}>
                      <label
                        className="flex cursor-pointer items-center space-x-3 rounded-lg border border-zinc-200 p-3 transition-colors hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800/50"
                        data-testid={`wizard-organization-${org.id}-option`}
                      >
                        <input
                          type="checkbox"
                          checked={isChecked}
                          onChange={() => toggleOrg(org.id)}
                          className="h-4 w-4 rounded border-zinc-300 accent-emerald-600 focus:ring-emerald-500 dark:border-zinc-600 dark:accent-emerald-500"
                          data-testid={`wizard-organization-${org.id}-checkbox`}
                        />
                        <span className="text-sm font-medium text-zinc-900 dark:text-white">
                          {org.name}
                        </span>
                      </label>
                      {isChecked && groupOptions.length > 0 && (
                        <div
                          className="ml-7 mt-2"
                          data-testid={`wizard-organization-group-section-${org.id}`}
                        >
                          <label
                            htmlFor={`wizard-organization-group-${org.id}`}
                            className="block text-xs font-medium text-zinc-600 dark:text-zinc-400"
                          >
                            {t('projects.creation.wizard.step1.groupScopeLabel')}
                          </label>
                          <select
                            id={`wizard-organization-group-${org.id}`}
                            value={data.organizationGroupIds[org.id] ?? ''}
                            onChange={(e) =>
                              setOrgGroup(org.id, e.target.value || null)
                            }
                            data-testid={`wizard-organization-group-select-${org.id}`}
                            className="mt-1 w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 dark:border-zinc-600 dark:bg-zinc-700 dark:text-zinc-100"
                          >
                            <option value="">
                              {t(
                                'projects.creation.wizard.step1.groupScopeOrgWide'
                              )}
                            </option>
                            {groupOptions.map((group) => (
                              <option key={group.id} value={group.id}>
                                {group.name}
                              </option>
                            ))}
                          </select>
                          <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                            {t(
                              'projects.creation.wizard.step1.groupScopeHelp'
                            )}
                          </p>
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
            {errors.organizationIds && (
              <p className="text-sm text-red-600 dark:text-red-400">
                {errors.organizationIds}
              </p>
            )}
          </div>
        )}

        {data.visibility === 'public' && (
          <div
            className="ml-6 space-y-2"
            data-testid="wizard-public-role-section"
          >
            <Label>
              {t('projects.creation.wizard.step1.publicRoleLabel')}
            </Label>
            <p className="text-sm text-zinc-500 dark:text-zinc-400">
              {t('projects.creation.wizard.step1.publicRoleDescription')}
            </p>
            <div className="space-y-2">
              {(['ANNOTATOR', 'CONTRIBUTOR'] as WizardPublicRole[]).map(
                (role) => (
                  <label
                    key={role}
                    className="flex cursor-pointer items-center justify-between"
                    data-testid={`wizard-public-role-${role.toLowerCase()}-option`}
                  >
                    <div>
                      <Label>
                        {t(
                          `projects.creation.wizard.step1.publicRole.${role.toLowerCase()}`
                        )}
                      </Label>
                      <p className="text-sm text-zinc-500 dark:text-zinc-400">
                        {t(
                          `projects.creation.wizard.step1.publicRole.${role.toLowerCase()}Description`
                        )}
                      </p>
                    </div>
                    <input
                      type="radio"
                      name="wizard-public-role"
                      checked={data.publicRole === role}
                      onChange={() => onChange({ publicRole: role })}
                      className="h-4 w-4 border-zinc-300 accent-emerald-600 focus:ring-emerald-500 dark:border-zinc-600 dark:accent-emerald-500"
                      data-testid={`wizard-public-role-${role.toLowerCase()}-radio`}
                    />
                  </label>
                )
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

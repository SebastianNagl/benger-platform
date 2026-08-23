'use client'

import { Input } from '@/components/shared/Input'
import { Label } from '@/components/shared/Label'
import { Textarea } from '@/components/shared/Textarea'
import { useI18n } from '@/contexts/I18nContext'
import { organizationsAPI } from '@/lib/api/organizations'
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
  const [orgs, setOrgs] = useState<Array<{ id: string; name: string }>>([])
  // Extended-edition feature row rendered below the core feature checkboxes:
  // the experimental KI-Generator, styled like the rows above and toggling
  // `features.synthetic` (which adds the synthetic step to the wizard). Null
  // in the community edition.
  const SyntheticEntry = useSlot('ProjectWizardSyntheticEntry')

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
            className="flex h-14 w-14 items-center justify-center rounded-xl border border-zinc-200 text-3xl transition-colors hover:border-emerald-400 hover:bg-emerald-50 dark:border-zinc-700 dark:hover:bg-emerald-900/20"
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
                {orgs.map((org) => (
                  <label
                    key={org.id}
                    className="flex cursor-pointer items-center space-x-3 rounded-lg border border-zinc-200 p-3 transition-colors hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800/50"
                    data-testid={`wizard-organization-${org.id}-option`}
                  >
                    <input
                      type="checkbox"
                      checked={data.organizationIds.includes(org.id)}
                      onChange={() => toggleOrg(org.id)}
                      className="h-4 w-4 rounded border-zinc-300 accent-emerald-600 focus:ring-emerald-500 dark:border-zinc-600 dark:accent-emerald-500"
                      data-testid={`wizard-organization-${org.id}-checkbox`}
                    />
                    <span className="text-sm font-medium text-zinc-900 dark:text-white">
                      {org.name}
                    </span>
                  </label>
                ))}
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

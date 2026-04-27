'use client'

import { Input } from '@/components/shared/Input'
import { Label } from '@/components/shared/Label'
import { Textarea } from '@/components/shared/Textarea'
import { useI18n } from '@/contexts/I18nContext'
import { cn } from '@/lib/utils'
import { WizardData, WizardFeatures } from './types'


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

  const toggleFeature = (key: keyof WizardFeatures) => {
    onChange({
      features: { ...data.features, [key]: !data.features[key] },
    })
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="mb-2 text-2xl font-semibold text-zinc-900 dark:text-white">
          {t('projects.creation.wizard.step1.title')}
        </h2>
        <p className="text-zinc-600 dark:text-zinc-400">
          {t('projects.creation.wizard.step1.subtitle')}
        </p>
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
      </div>

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
                className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
              />
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

'use client'

import { Alert } from '@/components/shared/Alert'
import { Badge } from '@/components/shared/Badge'
import { Card } from '@/components/shared/Card'
import { Label } from '@/components/shared/Label'
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/shared/Tabs'
import { Textarea } from '@/components/shared/Textarea'
import { useI18n } from '@/contexts/I18nContext'
import { cn } from '@/lib/utils'
import { LabelingTemplate } from './types'

interface StepLabelingSetupProps {
  labelingConfig: LabelingTemplate | null
  onChange: (config: LabelingTemplate | null) => void
  nlpTemplates: LabelingTemplate[]
}

export function StepLabelingSetup({
  labelingConfig,
  onChange,
  nlpTemplates,
}: StepLabelingSetupProps) {
  const { t } = useI18n()

  return (
    <div className="space-y-6">
      <div>
        <h2 className="mb-2 text-2xl font-semibold text-zinc-900 dark:text-white">
          {t('projects.creation.wizard.step3.title')}
        </h2>
        <p className="text-zinc-600 dark:text-zinc-400">
          {t('projects.creation.wizard.step3.subtitle')}
        </p>
      </div>

      <Tabs
        defaultValue="templates"
        className="w-full"
        data-testid="project-create-labeling-tabs"
      >
        <TabsList className="grid w-full grid-cols-2">
          <TabsTrigger
            value="templates"
            data-testid="project-create-templates-tab"
          >
            {t('projects.creation.wizard.step3.tabs.templates')}
          </TabsTrigger>
          <TabsTrigger value="custom" data-testid="project-create-custom-tab">
            {t('projects.creation.wizard.step3.tabs.custom')}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="templates" className="mt-6">
          <div className="space-y-4">
            <div>
              <Label>
                {t('projects.creation.wizard.step3.templates.label')}
              </Label>
              <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
                {t('projects.creation.wizard.step3.templates.description')}
              </p>
            </div>

            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
              {nlpTemplates.map((template) => (
                <Card
                  key={template.id}
                  className={cn(
                    'cursor-pointer transition-colors hover:border-emerald-600',
                    labelingConfig?.id === template.id &&
                      'border-emerald-600 bg-emerald-50 dark:bg-emerald-900/20'
                  )}
                  onClick={() => onChange(template)}
                  data-testid={`project-create-template-${template.id}`}
                >
                  <div className="p-4">
                    <div className="mb-3 flex items-start gap-3">
                      <div className="text-2xl">{template.icon}</div>
                      <div className="flex-1">
                        <h4 className="mb-1 font-medium text-zinc-900 dark:text-white">
                          {template.name}
                        </h4>
                        <p className="text-sm text-zinc-600 dark:text-zinc-400">
                          {template.description}
                        </p>
                      </div>
                    </div>
                    {labelingConfig?.id === template.id && (
                      <div className="border-t border-emerald-200 pt-2 dark:border-emerald-800">
                        <Badge variant="default" className="text-xs">
                          {t(
                            'projects.creation.wizard.step3.templates.selected'
                          )}
                        </Badge>
                      </div>
                    )}
                  </div>
                </Card>
              ))}
            </div>
          </div>
        </TabsContent>

        <TabsContent value="custom" className="mt-6">
          <div className="space-y-4">
            <div>
              <Label>{t('projects.creation.wizard.step3.custom.label')}</Label>
              <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
                {t('projects.creation.wizard.step3.custom.description')}
              </p>
            </div>

            <Textarea
              placeholder={`<View>
  <Text name="text" value="$text"/>
  <Labels name="label" toName="text">
    <Label value="Category1" background="red"/>
    <Label value="Category2" background="blue"/>
  </Labels>
</View>`}
              rows={12}
              className="font-mono text-sm"
              value={labelingConfig?.config || ''}
              onChange={(e) =>
                onChange({
                  id: 'custom',
                  name: t('projects.wizard.customConfigName'),
                  description: t('projects.wizard.customConfigDescription'),
                  icon: '',
                  category: 'Custom',
                  config: e.target.value,
                })
              }
              data-testid="project-create-custom-config-textarea"
            />

            <Alert variant="info">
              <p className="mb-1 text-sm font-medium">
                {t('projects.creation.wizard.step3.custom.helpTitle')}
              </p>
              <p className="text-sm">
                {t('projects.creation.wizard.step3.custom.helpText')}{' '}
                <a
                  href="https://labelstud.io/tags/"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline hover:no-underline"
                >
                  {t('projects.wizard.labelStudioDocs')}
                </a>
                .
              </p>
            </Alert>
          </div>
        </TabsContent>
      </Tabs>

      {/* Preview */}
      {labelingConfig && (
        <div>
          <Label>{t('projects.creation.wizard.step3.preview.title')}</Label>
          <Card className="mt-2">
            <div className="p-4">
              <div className="mb-3 flex items-center gap-3">
                <span className="text-2xl">{labelingConfig.icon}</span>
                <div>
                  <h4 className="font-medium text-zinc-900 dark:text-white">
                    {labelingConfig.name}
                  </h4>
                  <p className="text-sm text-zinc-600 dark:text-zinc-400">
                    {labelingConfig.description}
                  </p>
                </div>
              </div>
              <details className="group">
                <summary className="cursor-pointer text-sm font-medium text-zinc-700 hover:text-emerald-600 dark:text-zinc-300 dark:hover:text-emerald-400">
                  {t('projects.creation.wizard.step3.preview.viewXml')}
                </summary>
                <pre className="mt-2 overflow-x-auto rounded-md bg-zinc-100 p-3 text-xs text-zinc-800 dark:bg-zinc-800 dark:text-zinc-200">
                  {labelingConfig.config}
                </pre>
              </details>
            </div>
          </Card>
        </div>
      )}
    </div>
  )
}

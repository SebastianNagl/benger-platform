/**
 * Label Configuration Editor
 *
 * Simple editor for Label Studio XML configurations
 */

import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Textarea } from '@/components/ui/textarea'
import { TaskFieldReferencePanel } from '@/components/shared/TaskFieldReferencePanel'
import { CheckIcon, XMarkIcon } from '@heroicons/react/24/outline'
import { useMemo, useState } from 'react'
import { useI18n } from '@/contexts/I18nContext'

interface LabelConfigEditorProps {
  initialConfig?: string
  onSave: (config: string) => void
  onCancel?: () => void
  projectId?: string
}

export function LabelConfigEditor({
  initialConfig = '',
  onSave,
  onCancel,
  projectId,
}: LabelConfigEditorProps) {
  const { t } = useI18n()
  const [config, setConfig] = useState(initialConfig)

  // Derive error from config using useMemo (pure validation)
  const error = useMemo<string | null>(() => {
    if (!config.trim()) {
      return t('projects.labelConfig.errorEmpty')
    }

    try {
      // Basic check for balanced tags
      const parser = new DOMParser()
      const doc = parser.parseFromString(config, 'text/xml')
      const parseError = doc.querySelector('parsererror')

      if (parseError) {
        return t('projects.labelConfig.errorInvalidXml') + parseError.textContent
      }

      // Check for required View element
      if (!config.includes('<View>') || !config.includes('</View>')) {
        return t('projects.labelConfig.errorMissingView')
      }

      return null
    } catch {
      return t('projects.labelConfig.errorInvalidFormat')
    }
  }, [config, t])

  const handleSave = () => {
    if (!error) {
      onSave(config)
    }
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>{t('projects.labelConfig.title')}</CardTitle>
          <CardDescription>
            {t('projects.labelConfig.description')}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Available task fields reference */}
          {projectId && (
            <TaskFieldReferencePanel
              projectId={projectId}
              defaultExpanded={false}
              description={t(
                'project.labelConfiguration.fieldReferenceHelp',
                'Reference task data fields in your XML using $fieldname syntax (e.g., $text, $question).'
              )}
            />
          )}

          <Textarea
            value={config}
            onChange={(e) => setConfig(e.target.value)}
            placeholder={t('projects.labelConfig.placeholder')}
            className="font-mono text-sm"
            rows={15}
          />

          {error && (
            <Alert variant="destructive">
              <XMarkIcon className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {!error && config && (
            <Alert>
              <CheckIcon className="h-4 w-4" />
              <AlertDescription>{t('projects.labelConfig.valid')}</AlertDescription>
            </Alert>
          )}

          <div className="flex justify-end gap-2">
            {onCancel && (
              <Button variant="outline" onClick={onCancel}>
                {t('common.cancel')}
              </Button>
            )}
            <Button onClick={handleSave} disabled={!config || !!error}>
              {t('projects.labelConfig.saveButton')}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

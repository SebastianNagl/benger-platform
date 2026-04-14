/**
 * Field Mapping Settings - Allow users to reconfigure field mappings after import
 *
 * This component allows users to modify the annotation template and field mappings
 * at any time, similar to Label Studio's flexible approach.
 */

'use client'

import { useToast } from '@/components/shared/Toast'
import { useI18n } from '@/contexts/I18nContext'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { projectsAPI } from '@/lib/api/projects'
import {
  ArrowPathIcon,
  CheckCircleIcon,
  CogIcon,
  ExclamationTriangleIcon,
} from '@heroicons/react/24/outline'
import { useEffect, useState } from 'react'

interface FieldMappingSettingsProps {
  projectId: string
  currentTemplate: string
  availableFields: string[]
  onTemplateUpdate?: (newTemplate: string) => void
}

export function FieldMappingSettings({
  projectId,
  currentTemplate,
  availableFields,
  onTemplateUpdate,
}: FieldMappingSettingsProps) {
  const [templateFields, setTemplateFields] = useState<string[]>([])
  const [isEditing, setIsEditing] = useState(false)
  const [newTemplate, setNewTemplate] = useState(currentTemplate)
  const [loading, setLoading] = useState(false)
  const { addToast } = useToast()
  const { t } = useI18n()

  useEffect(() => {
    // Extract fields from current template
    const fieldRegex = /\$([a-zA-Z_][a-zA-Z0-9_]*)/g
    const matches = currentTemplate.matchAll(fieldRegex)
    const fields = Array.from(matches, (m) => m[1])
    const uniqueFields = [...new Set(fields)]
    setTemplateFields(uniqueFields)
  }, [currentTemplate])

  const validateFieldMapping = () => {
    const missingFields = templateFields.filter(
      (field) => !availableFields.includes(field)
    )
    const unusedFields = availableFields.filter(
      (field) => !templateFields.includes(field)
    )

    return {
      valid: missingFields.length === 0,
      missingFields,
      unusedFields,
    }
  }

  const handleTemplateUpdate = async () => {
    setLoading(true)
    try {
      await projectsAPI.update(projectId, {
        label_config: newTemplate,
      })

      addToast(t('toasts.template.annotationUpdated'), 'success')

      onTemplateUpdate?.(newTemplate)
      setIsEditing(false)
    } catch (error: any) {
      addToast(
        t('projects.fieldMapping.updateFailed', { error: error.message || t('projects.fieldMapping.failedUpdateTemplate') }),
        'error'
      )
    } finally {
      setLoading(false)
    }
  }

  const generateSuggestedTemplate = () => {
    // Generate a simple template based on available fields
    const suggestions = availableFields
      .map((field) => {
        if (
          field.toLowerCase().includes('text') ||
          field.toLowerCase().includes('question')
        ) {
          return `  <Text name="${field}" value="$${field}"/>`
        } else if (field.toLowerCase().includes('image')) {
          return `  <Image name="${field}" value="$${field}"/>`
        } else {
          return `  <Text name="${field}" value="$${field}"/>`
        }
      })
      .join('\n')

    return `<View>\n${suggestions}\n  <Choices name="label" toName="${availableFields[0] || 'text'}">\n    <Choice value="Label1"/>\n    <Choice value="Label2"/>\n  </Choices>\n</View>`
  }

  const validation = validateFieldMapping()

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <CogIcon className="h-5 w-5" />
            <CardTitle>{t('projects.fieldMapping.title')}</CardTitle>
          </div>
          <Button variant="outline" onClick={() => setIsEditing(!isEditing)}>
            {isEditing ? t('common.cancel') : t('projects.fieldMapping.editTemplate')}
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Current field mapping status */}
        <div className="space-y-2">
          <h4 className="text-sm font-medium">{t('projects.fieldMapping.fieldMappingStatus')}</h4>
          <div className="flex flex-wrap gap-2">
            {templateFields.map((field) => (
              <Badge
                key={field}
                variant={
                  availableFields.includes(field) ? 'default' : 'destructive'
                }
                className="text-xs"
              >
                ${field}
                {availableFields.includes(field) ? (
                  <CheckCircleIcon className="ml-1 h-3 w-3" />
                ) : (
                  <ExclamationTriangleIcon className="ml-1 h-3 w-3" />
                )}
              </Badge>
            ))}
          </div>
        </div>

        {/* Validation status */}
        {!validation.valid && (
          <Alert>
            <ExclamationTriangleIcon className="h-4 w-4" />
            <AlertDescription>
              <strong>
                {t('projects.fieldMapping.validationError')}
              </strong>{' '}
              {validation.missingFields.join(', ')}
              <br />
              <span className="text-xs">
                {t('projects.fieldMapping.validationErrorHint')}
              </span>
            </AlertDescription>
          </Alert>
        )}

        {validation.unusedFields.length > 0 && (
          <Alert>
            <AlertDescription>
              <strong>{t('projects.fieldMapping.unusedFields')}</strong>{' '}
              {validation.unusedFields.join(', ')}
              <br />
              <span className="text-xs">
                {t('projects.fieldMapping.unusedFieldsHint')}
              </span>
            </AlertDescription>
          </Alert>
        )}

        {/* Template editor */}
        {isEditing && (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h4 className="text-sm font-medium">{t('projects.fieldMapping.labelingConfiguration')}</h4>
              <Button
                variant="ghost"
                onClick={() => setNewTemplate(generateSuggestedTemplate())}
                className="text-xs"
              >
                <ArrowPathIcon className="mr-1 h-3 w-3" />
                {t('projects.fieldMapping.generateFromData')}
              </Button>
            </div>
            <textarea
              value={newTemplate}
              onChange={(e) => setNewTemplate(e.target.value)}
              className="h-48 w-full rounded border p-3 font-mono text-sm"
              placeholder={t('projects.fieldMapping.placeholder')}
            />
            <div className="flex justify-end space-x-2">
              <Button variant="outline" onClick={() => setIsEditing(false)}>
                {t('common.cancel')}
              </Button>
              <Button onClick={handleTemplateUpdate} loading={loading}>
                {t('projects.fieldMapping.updateTemplate')}
              </Button>
            </div>
          </div>
        )}

        {/* Quick actions */}
        <div className="flex gap-2 border-t pt-2">
          <Button
            variant="ghost"
            onClick={() => setNewTemplate(generateSuggestedTemplate())}
            disabled={availableFields.length === 0}
          >
            {t('projects.fieldMapping.autoConfigureTemplate')}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

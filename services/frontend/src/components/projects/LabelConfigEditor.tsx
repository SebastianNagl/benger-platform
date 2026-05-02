/**
 * Label Configuration Editor
 *
 * Simple editor for Label Studio XML configurations.
 *
 * Two consumption modes:
 *  1. Standalone (default): renders its own Save/Cancel buttons.
 *  2. Card-driven: parent passes a `ref` and `hideInternalControls`; the
 *     parent's card-level Save calls `ref.current.save()` to flush this
 *     editor in lockstep with sibling sub-sections. The imperative
 *     `save()` resolves on success and rejects on validation error so a
 *     parent's `Promise.all([...])` short-circuits with a useful message.
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
import { forwardRef, useImperativeHandle, useMemo, useState } from 'react'
import { useI18n } from '@/contexts/I18nContext'

interface LabelConfigEditorProps {
  initialConfig?: string
  onSave: (config: string) => void | Promise<void>
  onCancel?: () => void
  projectId?: string
  /** Suppress the editor's own Save/Cancel buttons. The parent owns the
   *  lifecycle and calls `save()` via the ref. */
  hideInternalControls?: boolean
}

export interface LabelConfigEditorHandle {
  /** Flush the current XML through the onSave callback. Rejects if invalid. */
  save: () => Promise<void>
  isDirty: () => boolean
  hasErrors: () => boolean
}

export const LabelConfigEditor = forwardRef<
  LabelConfigEditorHandle,
  LabelConfigEditorProps
>(function LabelConfigEditor(
  { initialConfig = '', onSave, onCancel, projectId, hideInternalControls },
  ref,
) {
  const { t } = useI18n()
  const [config, setConfig] = useState(initialConfig)

  const error = useMemo<string | null>(() => {
    if (!config.trim()) {
      return t('projects.labelConfig.errorEmpty')
    }
    try {
      const parser = new DOMParser()
      const doc = parser.parseFromString(config, 'text/xml')
      const parseError = doc.querySelector('parsererror')
      if (parseError) {
        return t('projects.labelConfig.errorInvalidXml') + parseError.textContent
      }
      if (!config.includes('<View>') || !config.includes('</View>')) {
        return t('projects.labelConfig.errorMissingView')
      }
      return null
    } catch {
      return t('projects.labelConfig.errorInvalidFormat')
    }
  }, [config, t])

  const handleSave = async () => {
    if (error) throw new Error(error)
    if (!config) throw new Error(t('projects.labelConfig.errorEmpty'))
    await onSave(config)
  }

  useImperativeHandle(
    ref,
    () => ({
      save: handleSave,
      isDirty: () => config !== initialConfig,
      hasErrors: () => !!error,
    }),
    [config, initialConfig, error, onSave, t],
  )

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

          {!hideInternalControls && (
            <div className="flex justify-end gap-2">
              {onCancel && (
                <Button variant="outline" onClick={onCancel}>
                  {t('common.cancel')}
                </Button>
              )}
              <Button
                onClick={() => {
                  void handleSave().catch(() => {
                    /* error already surfaced by the inline alert */
                  })
                }}
                disabled={!config || !!error}
              >
                {t('projects.labelConfig.saveButton')}
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
})

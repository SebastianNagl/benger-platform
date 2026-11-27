'use client'

/**
 * The project's questionnaires ("Fragebögen" card of the project page): one
 * block per moment, all alike:
 *
 *   before_task    after the instructions, before the task (never timed)
 *   after_submit   right after a submission is final (never timed)
 *   korrektur      the grader's, after saving a Korrektur
 *
 * Each block: on/off, must-answer or skippable, how often, a template or an
 * uploaded .xml file, the XML (the annotation interface's label-config
 * syntax) with a live preview rendered by the annotation interface itself,
 * server validation while typing and on save, and the answers as CSV.
 *
 * A block saves itself with its own button: the XML is free text that is
 * only saved once it validates, and its version counts saved edits.
 */

import { ArrowDownTrayIcon, ArrowUpTrayIcon } from '@heroicons/react/24/outline'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { DynamicAnnotationInterface } from '@/components/labeling/DynamicAnnotationInterface'
import { Alert } from '@/components/shared/Alert'
import { Button } from '@/components/shared/Button'
import { Checkbox } from '@/components/shared/Checkbox'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/shared/Select'
import { Textarea } from '@/components/shared/Textarea'
import { useToast } from '@/components/shared/Toast'
import { useI18n } from '@/contexts/I18nContext'
import {
  QUESTIONNAIRE_TRIGGERS,
  questionnairesAPI,
  type ProjectQuestionnaire,
  type QuestionnaireFrequency,
  type QuestionnaireTrigger,
} from '@/lib/api/questionnaires'

import {
  SettingField,
  SettingRow,
  SettingsGroup,
  SettingsGroupStack,
} from '@/components/projects/SettingsGroup'
import { SubSection } from '@/components/projects/SubSection'
import { QUESTIONNAIRE_TEMPLATES } from './templates'

const NO_TASK_DATA = {}
const VALIDATE_DELAY_MS = 600

interface Draft {
  enabled: boolean
  required: boolean
  frequency: QuestionnaireFrequency
  config: string
}

function draftOf(q: ProjectQuestionnaire): Draft {
  return {
    enabled: q.enabled,
    required: q.required,
    frequency: q.frequency,
    config: q.config || '',
  }
}

function sameDraft(a: Draft, b: Draft): boolean {
  return (
    a.enabled === b.enabled &&
    a.required === b.required &&
    a.frequency === b.frequency &&
    a.config === b.config
  )
}

function serverErrors(err: any): string[] {
  const detail = err?.response?.data?.detail
  if (detail && Array.isArray(detail.errors) && detail.errors.length) {
    return detail.errors.map(String)
  }
  if (detail && typeof detail.message === 'string') return [detail.message]
  if (typeof err?.message === 'string' && err.message) return [err.message]
  return []
}

interface BlockProps {
  projectId: string
  questionnaire: ProjectQuestionnaire
  canEdit: boolean
  onSaved: (q: ProjectQuestionnaire) => void
}

function QuestionnaireBlock({
  projectId,
  questionnaire,
  canEdit,
  onSaved,
}: BlockProps) {
  const { t } = useI18n()
  const { addToast } = useToast()
  const trigger = questionnaire.trigger
  const saved = useMemo(() => draftOf(questionnaire), [questionnaire])
  const [draft, setDraft] = useState<Draft>(saved)
  const [errors, setErrors] = useState<string[]>([])
  // Why the last save failed; any change to the draft clears it.
  const [saveErrors, setSaveErrors] = useState<string[]>([])
  const [checking, setChecking] = useState(false)
  const [saving, setSaving] = useState(false)
  const [preview, setPreview] = useState(saved.config)
  const fileInput = useRef<HTMLInputElement>(null)
  const id = (name: string) => `questionnaire-${trigger}-${name}`

  // A save (or a reload) replaces the draft with what the server holds.
  useEffect(() => {
    setDraft(saved)
    setPreview(saved.config)
    setErrors([])
  }, [saved])

  useEffect(() => {
    setSaveErrors([])
  }, [draft])

  const dirty = !sameDraft(draft, saved)
  const configChanged = draft.config !== saved.config

  // Validate the XML a moment after the last keystroke, with the rules a
  // save applies, and refresh the preview with it.
  useEffect(() => {
    const config = draft.config
    const timer = setTimeout(() => {
      setPreview(config)
      if (!canEdit || !config.trim() || !configChanged) {
        setErrors([])
        return
      }
      setChecking(true)
      questionnairesAPI
        .validate(projectId, config)
        .then((r) => setErrors(r.valid ? [] : r.errors))
        .catch(() => setErrors([]))
        .finally(() => setChecking(false))
    }, VALIDATE_DELAY_MS)
    return () => clearTimeout(timer)
  }, [draft.config, configChanged, canEdit, projectId])

  const update = (patch: Partial<Draft>) =>
    setDraft((prev) => ({ ...prev, ...patch }))

  const handleUpload = async (file: File | undefined) => {
    if (!file) return
    try {
      update({ config: await file.text() })
    } catch {
      addToast(t('questionnaires.settings.uploadFailed'), 'error')
    } finally {
      if (fileInput.current) fileInput.current.value = ''
    }
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      const result = await questionnairesAPI.save(projectId, trigger, draft)
      onSaved(result)
      addToast(t('questionnaires.settings.saved'), 'success')
    } catch (err) {
      const messages = serverErrors(err)
      setSaveErrors(
        messages.length ? messages : [t('questionnaires.settings.saveFailed')],
      )
    } finally {
      setSaving(false)
    }
  }

  const templates = QUESTIONNAIRE_TEMPLATES[trigger]
  const badge = questionnaire.active
    ? t('questionnaires.settings.badgeActive', {
        version: questionnaire.version,
      })
    : t('questionnaires.settings.badgeOff')
  const canSave =
    canEdit &&
    dirty &&
    !saving &&
    errors.length === 0 &&
    !(draft.enabled && !draft.config.trim())

  return (
    <SubSection
      title={t(`questionnaires.moments.${trigger}.title`)}
      description={t(`questionnaires.moments.${trigger}.description`)}
      badge={badge}
      data-testid={`questionnaire-block-${trigger}`}
    >
      <SettingsGroupStack>
        <SettingsGroup title={t('questionnaires.settings.groupBehaviour')}>
          <SettingRow
            label={t('questionnaires.settings.enabled')}
            htmlFor={id('enabled')}
            help={t(`questionnaires.moments.${trigger}.enabledHelp`)}
            control={
              <Checkbox
                id={id('enabled')}
                data-testid={id('enabled')}
                checked={draft.enabled}
                onChange={(e) => update({ enabled: e.target.checked })}
                disabled={!canEdit}
              />
            }
          />
          <SettingRow
            label={t('questionnaires.settings.required')}
            htmlFor={id('required')}
            help={t('questionnaires.settings.requiredHelp')}
            control={
              <Checkbox
                id={id('required')}
                data-testid={id('required')}
                checked={draft.required}
                onChange={(e) => update({ required: e.target.checked })}
                disabled={!canEdit}
              />
            }
          />
          <SettingRow
            label={t('questionnaires.settings.frequency')}
            htmlFor={id('frequency')}
            help={t(`questionnaires.moments.${trigger}.frequencyHelp`)}
            control={
              <Select
                value={draft.frequency}
                onValueChange={(v) =>
                  update({ frequency: v as QuestionnaireFrequency })
                }
                disabled={!canEdit}
              >
                <SelectTrigger id={id('frequency')} className="w-56">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {questionnaire.allowed_frequencies.map((f) => (
                    <SelectItem key={f} value={f}>
                      {t(`questionnaires.frequencies.${trigger}.${f}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            }
          />
        </SettingsGroup>

        <SettingsGroup
          title={t('questionnaires.settings.groupQuestions')}
          description={t('questionnaires.settings.questionsHelp')}
        >
          {canEdit && (
            <div className="flex flex-wrap items-center gap-2">
              <Select
                value=""
                onValueChange={(v) => {
                  const template = templates.find((tpl) => tpl.id === v)
                  if (template) update({ config: template.xml })
                }}
              >
                <SelectTrigger id={id('template')} className="w-72">
                  <SelectValue
                    placeholder={t('questionnaires.settings.template')}
                  />
                </SelectTrigger>
                <SelectContent>
                  {templates.map((tpl) => (
                    <SelectItem key={tpl.id} value={tpl.id}>
                      {t(`questionnaires.templates.${tpl.id}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <input
                ref={fileInput}
                type="file"
                accept=".xml,application/xml,text/xml"
                className="hidden"
                data-testid={id('upload')}
                onChange={(e) => handleUpload(e.target.files?.[0])}
              />
              <Button
                variant="outline"
                onClick={() => fileInput.current?.click()}
                className="flex items-center gap-2"
              >
                <ArrowUpTrayIcon className="h-4 w-4" />
                {t('questionnaires.settings.upload')}
              </Button>
            </div>
          )}
          <div className="grid min-w-0 gap-4">
            <SettingField
              label={t('questionnaires.settings.xml')}
              htmlFor={id('xml')}
              className="min-w-0"
            >
              <Textarea
                id={id('xml')}
                data-testid={id('xml')}
                value={draft.config}
                onChange={(e) => update({ config: e.target.value })}
                disabled={!canEdit}
                rows={12}
                spellCheck={false}
                className="font-mono text-xs"
                placeholder={t('questionnaires.settings.xmlPlaceholder')}
              />
            </SettingField>
            <SettingField
              label={t('questionnaires.settings.preview')}
              className="min-w-0"
            >
              <div
                className="max-h-[28rem] min-h-[10rem] overflow-y-auto rounded-lg border border-zinc-200 p-4 dark:border-zinc-700"
                data-testid={id('preview')}
              >
                {errors.length > 0 ? (
                  <p className="text-sm text-zinc-500 dark:text-zinc-400">
                    {t('questionnaires.settings.previewInvalid')}
                  </p>
                ) : preview.trim() ? (
                  <DynamicAnnotationInterface
                    key={preview}
                    labelConfig={preview}
                    taskData={NO_TASK_DATA}
                    onSubmit={() => {}}
                    showSubmitButton={false}
                    hostOwnsSubmit
                    enableAutoSave={false}
                  />
                ) : (
                  <p className="text-sm text-zinc-500 dark:text-zinc-400">
                    {t('questionnaires.settings.previewEmpty')}
                  </p>
                )}
              </div>
            </SettingField>
          </div>
          {errors.length > 0 && (
            <Alert variant="error">
              <p className="font-medium">
                {t('questionnaires.settings.invalid')}
              </p>
              <ul className="mt-1 list-disc pl-5" data-testid={id('errors')}>
                {errors.map((e) => (
                  <li key={e}>{e}</li>
                ))}
              </ul>
            </Alert>
          )}
          {saveErrors.length > 0 && (
            <Alert variant="error">
              <ul className="list-disc pl-5" data-testid={id('save-errors')}>
                {saveErrors.map((e) => (
                  <li key={e}>{e}</li>
                ))}
              </ul>
            </Alert>
          )}
        </SettingsGroup>

        {canEdit && (
          <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-4 dark:border-zinc-700">
            <a
              href={questionnairesAPI.csvUrl(projectId, trigger)}
              className="flex items-center gap-2 text-sm text-emerald-700 hover:underline dark:text-emerald-400"
              data-testid={id('csv')}
            >
              <ArrowDownTrayIcon className="h-4 w-4" />
              {t('questionnaires.settings.downloadCsv')}
            </a>
            <div className="flex items-center gap-2">
              {checking && (
                <span className="text-xs text-zinc-500 dark:text-zinc-400">
                  {t('questionnaires.settings.checking')}
                </span>
              )}
              <Button
                variant="outline"
                onClick={() => {
                  setDraft(saved)
                  setErrors([])
                }}
                disabled={!dirty || saving}
              >
                {t('questionnaires.settings.discard')}
              </Button>
              <Button
                onClick={handleSave}
                disabled={!canSave}
                data-testid={id('save')}
              >
                {saving
                  ? t('questionnaires.settings.saving')
                  : t('questionnaires.settings.save')}
              </Button>
            </div>
          </div>
        )}
      </SettingsGroupStack>
    </SubSection>
  )
}

export interface QuestionnairesSettingsProps {
  projectId: string
  canEdit: boolean
  /** Called with the number of switched-on questionnaires once known. */
  onActiveCount?: (count: number) => void
}

export function QuestionnairesSettings({
  projectId,
  canEdit,
  onActiveCount,
}: QuestionnairesSettingsProps) {
  const { t } = useI18n()
  const [items, setItems] = useState<ProjectQuestionnaire[] | null>(null)
  const [loadError, setLoadError] = useState(false)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let cancelled = false
    questionnairesAPI
      .list(projectId)
      .then((r) => {
        if (cancelled) return
        setLoadError(false)
        setItems(r.questionnaires)
      })
      .catch(() => {
        if (!cancelled) setLoadError(true)
      })
    return () => {
      cancelled = true
    }
  }, [projectId, attempt])

  useEffect(() => {
    if (items) onActiveCount?.(items.filter((q) => q.active).length)
  }, [items, onActiveCount])

  const handleSaved = useCallback((q: ProjectQuestionnaire) => {
    setItems((prev) =>
      prev ? prev.map((item) => (item.trigger === q.trigger ? q : item)) : prev,
    )
  }, [])

  if (loadError) {
    return (
      <Alert variant="error">
        <div className="flex items-center justify-between gap-3">
          <span>{t('questionnaires.settings.loadFailed')}</span>
          <Button
            variant="outline"
            onClick={() => {
              setLoadError(false)
              setAttempt((n) => n + 1)
            }}
          >
            {t('questionnaires.settings.retry')}
          </Button>
        </div>
      </Alert>
    )
  }
  if (!items) {
    return (
      <div className="flex justify-center py-6">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-zinc-300 border-t-emerald-500 dark:border-zinc-600 dark:border-t-emerald-400" />
      </div>
    )
  }
  const byTrigger = new Map(items.map((q) => [q.trigger, q]))
  return (
    <div
      className="divide-y divide-zinc-200 dark:divide-zinc-700 [&>*]:py-4 [&>*:first-child]:pt-0"
      data-testid="questionnaires-settings"
    >
      {QUESTIONNAIRE_TRIGGERS.map((trigger: QuestionnaireTrigger) => {
        const q = byTrigger.get(trigger)
        return q ? (
          <QuestionnaireBlock
            key={trigger}
            projectId={projectId}
            questionnaire={q}
            canEdit={canEdit}
            onSaved={handleSaved}
          />
        ) : null
      })}
      {canEdit && (
        <div className="flex justify-end pt-2">
          <a
            href={questionnairesAPI.csvUrl(projectId, 'all')}
            className="flex items-center gap-2 text-sm text-emerald-700 hover:underline dark:text-emerald-400"
            data-testid="questionnaire-csv-all"
          >
            <ArrowDownTrayIcon className="h-4 w-4" />
            {t('questionnaires.settings.downloadCsvAll')}
          </a>
        </div>
      )}
    </div>
  )
}

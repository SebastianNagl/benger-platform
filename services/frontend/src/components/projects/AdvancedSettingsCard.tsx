/**
 * The "Annotationsablauf & -verhalten" sub-collapsible of the project
 * page's annotation card, in groups that follow an annotator's way through
 * a project:
 *
 *   Zuteilung        who gets which items
 *   Bearbeitung      what the annotator may do while working (time limit,
 *                    pasting; extension slots: file upload, handwriting,
 *                    draft checkpoints)
 *   Überspringen     the skip button and what skipping does
 *   Abgabe           submitting
 *   Nach der Abgabe  what annotators see afterwards (questionnaires have
 *                    their own card, components/questionnaires)
 *   Überprüfung      extension slot (review stage)
 *
 * The instruction display switches live with the instructions themselves
 * (`InstructionDisplaySettings`, rendered in "Annotationsanweisungen").
 *
 * Presentational: all state lives in the page and arrives through
 * `advancedSettings` / `setAdvancedSettings`; the page auto-saves the
 * buffer.
 */

'use client'

import { Checkbox } from '@/components/shared/Checkbox'
import { Input } from '@/components/shared/Input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/shared/Select'
import { Textarea } from '@/components/shared/Textarea'
import { useState, type ComponentType, type SetStateAction } from 'react'
import {
  SettingField,
  SettingRow,
  SettingsGroup,
  SettingsGroupStack,
} from './SettingsGroup'

export interface AdvancedSettings {
  show_instruction: boolean
  instructions_always_visible: boolean
  show_skip_button: boolean
  show_submit_button: boolean
  require_comment_on_skip: boolean
  require_confirm_before_submit: boolean
  // false = annotators can only paste text they copied inside BenGER
  allow_external_paste: boolean
  // false = the writer cannot hand in a file as the answer (overlay upload)
  allow_solution_upload: boolean
  // handwritten uploads (overlay setting): switch + model override
  // (null = the organization's default)
  handwriting_ocr_enabled: boolean
  handwriting_ocr_model: string | null
  skip_queue: 'requeue_for_me' | 'requeue_for_others' | 'ignore_skipped'
  maximum_annotations: number
  min_annotations_per_task: number
  assignment_mode: 'open' | 'manual' | 'auto'
  randomize_task_order: boolean
  annotator_full_visibility_after_submit: boolean
  // null = follow annotator_full_visibility_after_submit (server default)
  annotator_step_detail_after_submit: boolean | null
  review_enabled: boolean
  review_mode: 'in_place' | 'independent' | 'both'
  allow_self_review: boolean
  korrektur_enabled: boolean
  korrektur_config: Array<{ value: string; background: string }>
  annotation_time_limit_enabled: boolean
  annotation_time_limit_seconds: number | null
  strict_timer_enabled: boolean
  restorable_checkpoints_enabled: boolean
}

/**
 * Setter for the settings buffer. `deferSave` marks a free-text edit that
 * saves on blur instead of after the usual delay.
 * `onCancel` runs when a risky change is cancelled in its confirmation, for
 * controls that already show the new value.
 */
export type AdvancedSettingsSetter = (
  value: SetStateAction<AdvancedSettings>,
  options?: { deferSave?: boolean; onCancel?: () => void },
) => void

type Translate = (key: string, params?: any) => string

interface AdvancedSettingsCardProps {
  t: Translate
  canEditProject: () => boolean
  getReadOnlyMessage: (sectionTitle: string) => string
  advancedSettings: AdvancedSettings
  setAdvancedSettings: AdvancedSettingsSetter
  editing: boolean
  /** Extension slot: the review stage, rendered as the last group. */
  ProjectSettingsExtended: ComponentType<any> | null
  /** Extension slot: settings right below the paste switch (uploads). */
  ProjectSettingsInterfaceExtra?: ComponentType<any> | null
  /** Extension slot: further settings of the "Bearbeitung" group. */
  ProjectSettingsAnnotationWork?: ComponentType<any> | null
}

export function AdvancedSettingsCard({
  t,
  canEditProject,
  getReadOnlyMessage,
  advancedSettings,
  setAdvancedSettings,
  editing,
  ProjectSettingsExtended,
  ProjectSettingsInterfaceExtra = null,
  ProjectSettingsAnnotationWork = null,
}: AdvancedSettingsCardProps) {
  if (!canEditProject()) {
    return (
      <div className="py-6 text-center">
        <p className="text-sm text-zinc-500 dark:text-zinc-400">
          {getReadOnlyMessage(t('project.settings.title'))}
        </p>
      </div>
    )
  }

  const set = <K extends keyof AdvancedSettings>(
    field: K,
    value: AdvancedSettings[K],
  ) => setAdvancedSettings((prev) => ({ ...prev, [field]: value }))

  const toggle = (
    id: string,
    field: keyof AdvancedSettings,
    checked: boolean,
    testId?: string,
  ) => (
    <Checkbox
      id={id}
      data-testid={testId}
      checked={checked}
      onChange={(e) => set(field, e.target.checked as never)}
      disabled={!editing}
    />
  )

  const slotProps = {
    settings: advancedSettings,
    onSettingsChange: setAdvancedSettings,
    editing,
  }
  const skipQueue = advancedSettings.skip_queue || 'requeue_for_others'
  const skipQueueLabel =
    skipQueue === 'requeue_for_me'
      ? t('project.settings.interface.skipQueueRequeueForMe')
      : skipQueue === 'requeue_for_others'
        ? t('project.settings.interface.skipQueueRequeueForOthers')
        : t('project.settings.interface.skipQueueIgnoreSkipped')

  return (
    <SettingsGroupStack>
      {/* Who gets which items */}
      <SettingsGroup
        title={t('project.settings.groups.assignment')}
        data-testid="settings-group-assignment"
      >
        <SettingField
          label={t('project.settings.annotationBehavior.assignmentMode')}
          htmlFor="assignment_mode"
          help={t('project.settings.annotationBehavior.assignmentModeHelp')}
        >
          <Select
            value={advancedSettings.assignment_mode}
            onValueChange={(value: string) =>
              set(
                'assignment_mode',
                value as AdvancedSettings['assignment_mode'],
              )
            }
            disabled={!editing}
          >
            <SelectTrigger id="assignment_mode">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="open">
                {t('project.settings.annotationBehavior.modes.open')}
              </SelectItem>
              <SelectItem value="manual">
                {t('project.settings.annotationBehavior.modes.manual')}
              </SelectItem>
              <SelectItem value="auto">
                {t('project.settings.annotationBehavior.modes.auto')}
              </SelectItem>
            </SelectContent>
          </Select>
        </SettingField>

        <SettingField
          label={t('project.settings.annotationBehavior.maxAnnotations')}
          htmlFor="maximum_annotations"
          help={t('project.settings.annotationBehavior.maxAnnotationsHelp')}
        >
          <Select
            value={advancedSettings.maximum_annotations.toString()}
            onValueChange={(value: string) =>
              set('maximum_annotations', parseInt(value))
            }
            disabled={!editing}
          >
            <SelectTrigger id="maximum_annotations">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="1">
                {t('project.settings.annotationBehavior.annotations.single')}
              </SelectItem>
              <SelectItem value="2">
                {t('project.settings.annotationBehavior.annotations.double')}
              </SelectItem>
              <SelectItem value="3">
                {t('project.settings.annotationBehavior.annotations.triple')}
              </SelectItem>
              <SelectItem value="5">
                {t('project.settings.annotationBehavior.annotations.multiple')}
              </SelectItem>
              <SelectItem value="10">10</SelectItem>
              <SelectItem value="50">50</SelectItem>
              <SelectItem value="100">100</SelectItem>
              <SelectItem value="0">
                {t('project.settings.annotationBehavior.annotations.unlimited')}
              </SelectItem>
            </SelectContent>
          </Select>
        </SettingField>

        <SettingField
          label={t(
            'project.settings.annotationBehavior.minAnnotationsForCompletion',
          )}
          htmlFor="min_annotations_per_task"
          help={t('project.settings.annotationBehavior.minAnnotationsHelp')}
        >
          <Select
            value={advancedSettings.min_annotations_per_task.toString()}
            onValueChange={(value: string) =>
              set('min_annotations_per_task', parseInt(value))
            }
            disabled={!editing}
          >
            <SelectTrigger id="min_annotations_per_task">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {[1, 2, 3, 4, 5].map((n) => (
                <SelectItem key={n} value={String(n)}>
                  {t(
                    `project.settings.annotationBehavior.annotations.count${n}`,
                  )}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </SettingField>

        <SettingRow
          label={t('project.settings.annotationBehavior.randomizeTaskOrder')}
          htmlFor="randomize_task_order"
          help={t('project.settings.annotationBehavior.randomizeTaskOrderHelp')}
          control={toggle(
            'randomize_task_order',
            'randomize_task_order',
            advancedSettings.randomize_task_order,
          )}
        />
      </SettingsGroup>

      {/* What the annotator may do while working */}
      <SettingsGroup
        title={t('project.settings.groups.work')}
        data-testid="settings-group-work"
      >
        <SettingRow
          label={t('projects.creation.wizard.stepSettings.timeLimit')}
          htmlFor="annotation_time_limit_enabled"
          help={t('projects.creation.wizard.stepSettings.timeLimitHint')}
          control={
            <Checkbox
              id="annotation_time_limit_enabled"
              checked={advancedSettings.annotation_time_limit_enabled}
              onChange={(e) => {
                const checked = e.target.checked
                setAdvancedSettings((prev) => ({
                  ...prev,
                  annotation_time_limit_enabled: checked,
                  annotation_time_limit_seconds: checked
                    ? (prev.annotation_time_limit_seconds ?? 1800)
                    : null,
                  strict_timer_enabled: checked
                    ? prev.strict_timer_enabled
                    : false,
                }))
              }}
              disabled={!editing}
            />
          }
        >
          {advancedSettings.annotation_time_limit_enabled ? (
            <>
              <TimeLimitMinutes
                t={t}
                seconds={advancedSettings.annotation_time_limit_seconds}
                editing={editing}
                onCommit={(seconds, revert) =>
                  setAdvancedSettings(
                    (prev) => ({
                      ...prev,
                      annotation_time_limit_seconds: seconds,
                    }),
                    { onCancel: revert },
                  )
                }
              />
              <SettingRow
                label={t('projects.creation.wizard.stepSettings.strictTimer')}
                htmlFor="strict_timer_enabled"
                help={t(
                  'projects.creation.wizard.stepSettings.strictTimerHint',
                )}
                control={toggle(
                  'strict_timer_enabled',
                  'strict_timer_enabled',
                  advancedSettings.strict_timer_enabled,
                )}
              />
            </>
          ) : null}
        </SettingRow>

        <SettingRow
          label={t('project.settings.interface.allowExternalPaste')}
          htmlFor="allow_external_paste"
          help={t('project.settings.interface.allowExternalPasteHelp')}
          control={toggle(
            'allow_external_paste',
            'allow_external_paste',
            advancedSettings.allow_external_paste,
            'allow-external-paste-checkbox',
          )}
        />

        {ProjectSettingsInterfaceExtra && (
          <ProjectSettingsInterfaceExtra {...slotProps} />
        )}
        {ProjectSettingsAnnotationWork && (
          <ProjectSettingsAnnotationWork {...slotProps} />
        )}
      </SettingsGroup>

      {/* Skipping */}
      <SettingsGroup
        title={t('project.settings.groups.skipping')}
        data-testid="settings-group-skipping"
      >
        <SettingRow
          label={t('project.settings.interface.showSkipButton')}
          htmlFor="show_skip_button"
          help={t('project.settings.interface.showSkipButtonHelp')}
          control={toggle(
            'show_skip_button',
            'show_skip_button',
            advancedSettings.show_skip_button,
          )}
        >
          <SettingRow
            label={t('project.settings.interface.requireCommentOnSkip')}
            htmlFor="require_comment_on_skip"
            help={t('project.settings.interface.requireCommentOnSkipHelp')}
            control={toggle(
              'require_comment_on_skip',
              'require_comment_on_skip',
              advancedSettings.require_comment_on_skip,
            )}
          />
          <SettingField
            label={t('project.settings.interface.skipQueue')}
            htmlFor="skip_queue"
            help={t('project.settings.interface.skipQueueHelp')}
          >
            <Select
              value={skipQueue}
              onValueChange={(v) =>
                set('skip_queue', v as AdvancedSettings['skip_queue'])
              }
              disabled={!editing}
              displayValue={skipQueueLabel}
            >
              <SelectTrigger id="skip_queue">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="requeue_for_me">
                  {t('project.settings.interface.skipQueueRequeueForMe')}
                </SelectItem>
                <SelectItem value="requeue_for_others">
                  {t('project.settings.interface.skipQueueRequeueForOthers')}
                </SelectItem>
                <SelectItem value="ignore_skipped">
                  {t('project.settings.interface.skipQueueIgnoreSkipped')}
                </SelectItem>
              </SelectContent>
            </Select>
          </SettingField>
        </SettingRow>
      </SettingsGroup>

      {/* Submitting */}
      <SettingsGroup
        title={t('project.settings.groups.submission')}
        data-testid="settings-group-submission"
      >
        <SettingRow
          label={t('project.settings.interface.showSubmitButton')}
          htmlFor="show_submit_button"
          help={t('project.settings.interface.showSubmitButtonHelp')}
          control={toggle(
            'show_submit_button',
            'show_submit_button',
            advancedSettings.show_submit_button,
          )}
        />
        <SettingRow
          label={t('project.settings.interface.requireConfirmBeforeSubmit')}
          htmlFor="require_confirm_before_submit"
          help={t('project.settings.interface.requireConfirmBeforeSubmitHelp')}
          control={toggle(
            'require_confirm_before_submit',
            'require_confirm_before_submit',
            advancedSettings.require_confirm_before_submit,
          )}
        />
      </SettingsGroup>

      {/* After submitting */}
      <SettingsGroup
        title={t('project.settings.groups.afterSubmit')}
        data-testid="settings-group-after-submit"
      >
        <SettingRow
          label={t(
            'project.settings.annotationBehavior.annotatorFullVisibility',
          )}
          htmlFor="annotator_full_visibility_after_submit"
          help={t(
            'project.settings.annotationBehavior.annotatorFullVisibilityHelp',
          )}
          control={toggle(
            'annotator_full_visibility_after_submit',
            'annotator_full_visibility_after_submit',
            advancedSettings.annotator_full_visibility_after_submit,
          )}
        />
        {/* Its own row, never hidden by the switch above: the two are
            independent once stored (null follows the switch above). */}
        <SettingRow
          label={t('project.settings.annotationBehavior.annotatorStepDetail')}
          htmlFor="annotator_step_detail_after_submit"
          help={t(
            'project.settings.annotationBehavior.annotatorStepDetailHelp',
          )}
          control={
            <Checkbox
              id="annotator_step_detail_after_submit"
              data-testid="annotator-step-detail-toggle"
              checked={
                advancedSettings.annotator_step_detail_after_submit ??
                advancedSettings.annotator_full_visibility_after_submit
              }
              onChange={(e) =>
                set('annotator_step_detail_after_submit', e.target.checked)
              }
              disabled={!editing}
            />
          }
        />
      </SettingsGroup>

      {/* Review stage (extension). Its own titled group comes from the
          slot; the wrapper adds the divider and disappears when the slot
          renders nothing. */}
      {ProjectSettingsExtended && (
        <div className="border-t border-zinc-200 pt-6 empty:hidden dark:border-zinc-700">
          <ProjectSettingsExtended {...slotProps} />
        </div>
      )}
    </SettingsGroupStack>
  )
}

/**
 * Minutes of the time limit. Typed digits stay local until the field loses
 * focus or Enter is pressed, so a half-typed number is never applied (the
 * limit applies to people working right now). A cancelled confirmation puts
 * the stored minutes back.
 */
function TimeLimitMinutes({
  t,
  seconds,
  editing,
  onCommit,
}: {
  t: Translate
  seconds: number | null
  editing: boolean
  onCommit: (seconds: number, revert: () => void) => void
}) {
  const stored = seconds ? Math.round(seconds / 60) : 30
  const [draft, setDraft] = useState(String(stored))
  // A new stored value (save, undo, reload) replaces the draft.
  const [shown, setShown] = useState(stored)
  if (shown !== stored) {
    setShown(stored)
    setDraft(String(stored))
  }
  const commit = () => {
    const minutes = parseInt(draft) || 30
    setDraft(String(minutes))
    if (minutes * 60 !== seconds)
      onCommit(minutes * 60, () => setDraft(String(stored)))
  }
  return (
    <div className="flex items-center gap-2">
      <Input
        type="number"
        min={1}
        max={360}
        aria-label={t('projects.creation.wizard.stepSettings.minutes')}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === 'Enter') commit()
        }}
        disabled={!editing}
        className="w-24"
      />
      <span className="text-sm text-zinc-500 dark:text-zinc-400">
        {t('projects.creation.wizard.stepSettings.minutes')}
      </span>
    </div>
  )
}

/**
 * "Anzeige" group of the instructions sub-collapsible: whether annotators
 * see the instructions, and whether always.
 */
export function InstructionDisplaySettings({
  t,
  advancedSettings,
  setAdvancedSettings,
  editing,
}: {
  t: Translate
  advancedSettings: AdvancedSettings
  setAdvancedSettings: AdvancedSettingsSetter
  editing: boolean
}) {
  return (
    <SettingsGroup
      title={t('project.settings.groups.display')}
      data-testid="settings-group-instruction-display"
    >
      <SettingRow
        label={t('project.settings.interface.showInstructions')}
        htmlFor="show_instruction"
        help={t('project.settings.interface.showInstructionsHelp')}
        control={
          <Checkbox
            id="show_instruction"
            checked={advancedSettings.show_instruction}
            onChange={(e) => {
              const checked = e.target.checked
              setAdvancedSettings((prev) => ({
                ...prev,
                show_instruction: checked,
              }))
            }}
            disabled={!editing}
          />
        }
      >
        <SettingRow
          label={t('project.settings.interface.instructionsAlwaysVisible')}
          htmlFor="instructions_always_visible"
          help={t('project.settings.interface.instructionsAlwaysVisibleHelp')}
          control={
            <Checkbox
              id="instructions_always_visible"
              checked={advancedSettings.instructions_always_visible}
              onChange={(e) => {
                const checked = e.target.checked
                setAdvancedSettings((prev) => ({
                  ...prev,
                  instructions_always_visible: checked,
                }))
              }}
              disabled={!editing}
            />
          }
        />
      </SettingRow>
    </SettingsGroup>
  )
}

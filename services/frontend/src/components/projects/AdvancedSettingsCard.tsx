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
 *   Nach der Abgabe  what annotators see afterwards, the questionnaire
 *   Überprüfung      extension slot (review stage)
 *
 * The instruction display switches live with the instructions themselves
 * (`InstructionDisplaySettings`, rendered in "Annotationsanweisungen").
 *
 * Presentational: all state lives in the page and arrives through
 * `advancedSettings` / `setAdvancedSettings`; the page auto-saves the
 * buffer. Free text (the questionnaire XML) passes `{ deferSave: true }`
 * and saves on blur through `onTextCommit`.
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
  questionnaire_enabled: boolean
  questionnaire_config: string
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
 * saves on blur (`onTextCommit`) instead of after the usual delay.
 * `onCancel` runs when a risky change is cancelled in its confirmation, for
 * controls that already show the new value.
 */
export type AdvancedSettingsSetter = (
  value: SetStateAction<AdvancedSettings>,
  options?: { deferSave?: boolean; onCancel?: () => void },
) => void

type Translate = (key: string, params?: any) => string

const QUESTIONNAIRE_TEMPLATES: Record<string, string> = {
  confidence_difficulty: `<View>
  <Header value="Post-Annotation Feedback"/>
  <Header value="How confident are you in your annotation?" size="4"/>
  <Rating name="confidence" toName="confidence" maxRating="5" required="true"/>
  <Header value="How difficult was this task?" size="4"/>
  <Rating name="difficulty" toName="difficulty" maxRating="5" required="true"/>
</View>`,
  extended: `<View>
  <Header value="Post-Annotation Feedback"/>
  <Header value="How confident are you in your annotation?" size="4"/>
  <Rating name="confidence" toName="confidence" maxRating="5" required="true"/>
  <Header value="How difficult was this task?" size="4"/>
  <Rating name="difficulty" toName="difficulty" maxRating="5" required="true"/>
  <Header value="How clear were the annotation guidelines?" size="4"/>
  <Choices name="guideline_clarity" toName="guideline_clarity" choice="single" layout="horizontal" required="true">
    <Choice value="Very Clear"/>
    <Choice value="Clear"/>
    <Choice value="Neutral"/>
    <Choice value="Unclear"/>
    <Choice value="Very Unclear"/>
  </Choices>
  <Header value="Additional comments (optional)" size="4"/>
  <TextArea name="comments" toName="comments" rows="3" placeholder="Note any edge cases, ambiguities, or concerns..."/>
</View>`,
  utaut_study: `<View>
  <Header value="Post-Annotations-Fragebogen" level="3"/>

  <Header value="Allgemeine Fragen" level="4"/>
  <Likert name="difficulty" toName="difficulty" min="1" max="7" required="true" label="Es fiel mir leicht die Aufgabe zu lösen."/>
  <Likert name="responsibility" toName="responsibility" min="1" max="7" required="true" label="Ich fühle mich verantwortlich für das von mir eingereichte Ergebnis."/>

  <Header value="Fragen zur KI-Unterstützung (nur beantworten, wenn du in der KI-Gruppe warst)" level="4"/>
  <Likert name="ai_adequate" toName="ai_adequate" min="1" max="7" label="Der Output der KI war auf Anhieb adäquat."/>
  <Likert name="ai_reviewed" toName="ai_reviewed" min="1" max="7" label="Ich habe den Output der KI überprüft."/>
  <Likert name="utaut_pe" toName="utaut_pe" min="1" max="7" label="Ich würde die KI in meiner Arbeit/meinem Studium als nützlich empfinden."/>
  <Likert name="utaut_ee" toName="utaut_ee" min="1" max="7" label="Ich empfinde die KI als einfach zu nutzen."/>
  <Likert name="utaut_att1" toName="utaut_att1" min="1" max="7" label="Die Nutzung der KI ist eine gute Idee."/>
  <Likert name="utaut_att2" toName="utaut_att2" min="1" max="7" label="Die Arbeit mit der KI macht Spaß."/>
  <Likert name="utaut_att3" toName="utaut_att3" min="1" max="7" label="Ich arbeite gerne mit der KI."/>

  <Header value="Anteil an der Fallbearbeitung (nur beantworten, wenn du in der KI-Gruppe warst)" level="4"/>
  <Number name="human_share" toName="human_share" min="0" max="100" label="x Prozent der Fallbearbeitung gehen auf mich zurück." hint="Wert zwischen 0 und 100"/>
  <Number name="ai_share" toName="ai_share" min="0" max="100" label="y Prozent der Fallbearbeitung gehen auf die KI zurück." hint="Wert zwischen 0 und 100"/>

  <Header value="Frage ohne KI (nur beantworten, wenn du NICHT in der KI-Gruppe warst)" level="4"/>
  <Likert name="desired_ai" toName="desired_ai" min="1" max="7" label="Ich hätte mir die KI für die Bearbeitung dieser Aufgabe gewünscht."/>
</View>`,
}

interface AdvancedSettingsCardProps {
  t: Translate
  canEditProject: () => boolean
  getReadOnlyMessage: (sectionTitle: string) => string
  advancedSettings: AdvancedSettings
  setAdvancedSettings: AdvancedSettingsSetter
  /** Save a deferred free-text edit now (blur). */
  onTextCommit?: () => void
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
  onTextCommit,
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
        <SettingRow
          label={t('project.settings.questionnaireEnabled')}
          htmlFor="questionnaire_enabled"
          help={t('project.settings.questionnaireEnabledDescription')}
          control={toggle(
            'questionnaire_enabled',
            'questionnaire_enabled',
            advancedSettings.questionnaire_enabled,
          )}
        >
          {advancedSettings.questionnaire_enabled ? (
            <>
              <SettingField
                label={t('project.settings.questionnaireTemplate')}
                htmlFor="questionnaire_template"
              >
                <Select
                  value=""
                  onValueChange={(v) => {
                    if (v in QUESTIONNAIRE_TEMPLATES) {
                      set('questionnaire_config', QUESTIONNAIRE_TEMPLATES[v])
                    }
                  }}
                  disabled={!editing}
                >
                  <SelectTrigger id="questionnaire_template">
                    <SelectValue
                      placeholder={t(
                        'project.settings.questionnaireSelectTemplate',
                      )}
                    />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="confidence_difficulty">
                      {t('project.settings.questionnaireTemplateConfidence')}
                    </SelectItem>
                    <SelectItem value="extended">
                      {t('project.settings.questionnaireTemplateExtended')}
                    </SelectItem>
                    <SelectItem value="utaut_study">
                      {t('project.settings.questionnaireTemplateUtaut')}
                    </SelectItem>
                  </SelectContent>
                </Select>
              </SettingField>
              <SettingField
                label={t('project.settings.questionnaireConfig')}
                htmlFor="questionnaire_config"
              >
                <Textarea
                  id="questionnaire_config"
                  value={advancedSettings.questionnaire_config}
                  onChange={(e) => {
                    const value = e.target.value
                    setAdvancedSettings(
                      (prev) => ({ ...prev, questionnaire_config: value }),
                      { deferSave: true },
                    )
                  }}
                  onBlur={() => onTextCommit?.()}
                  disabled={!editing}
                  rows={10}
                  className="font-mono"
                  placeholder={`<View>\n  <Header value="Post-Annotation Feedback"/>\n  <Rating name="confidence" toName="confidence" maxRating="5" required="true"/>\n</View>`}
                />
              </SettingField>
            </>
          ) : null}
        </SettingRow>
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

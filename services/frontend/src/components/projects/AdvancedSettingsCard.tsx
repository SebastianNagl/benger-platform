/**
 * Advanced annotation-settings block for the project detail page.
 *
 * Renders the contents of the "Annotation Settings" SubSection inside the
 * Annotation ConfigCard: annotation-behavior controls (max/min annotations,
 * assignment mode, randomize, full-visibility, timer), interface settings
 * (instruction/skip/submit toggles, skip-queue, confirm), the post-annotation
 * questionnaire, and the extended project-settings slot.
 *
 * Extracted verbatim from ProjectDetailPage as a behavior-preserving
 * presentational sub-component — the rendered DOM/text/classNames are
 * identical to the inline version. All state lives in the parent and is
 * prop-drilled here.
 */

'use client'

import { type ComponentType, type Dispatch, type SetStateAction } from 'react'
import { Input } from '@/components/shared/Input'
import { Label } from '@/components/shared/Label'
import { isoToLocalInput, localInputToIso } from '@/utils/projectWindow'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/shared/Select'

export interface AdvancedSettings {
  show_instruction: boolean
  instructions_always_visible: boolean
  show_skip_button: boolean
  show_submit_button: boolean
  require_comment_on_skip: boolean
  require_confirm_before_submit: boolean
  skip_queue: 'requeue_for_me' | 'requeue_for_others' | 'ignore_skipped'
  questionnaire_enabled: boolean
  questionnaire_config: string
  maximum_annotations: number
  min_annotations_per_task: number
  assignment_mode: 'open' | 'manual' | 'auto'
  randomize_task_order: boolean
  annotator_full_visibility_after_submit: boolean
  review_enabled: boolean
  review_mode: 'in_place' | 'independent' | 'both'
  allow_self_review: boolean
  korrektur_enabled: boolean
  korrektur_config: Array<{ value: string; background: string }>
  annotation_time_limit_enabled: boolean
  annotation_time_limit_seconds: number | null
  strict_timer_enabled: boolean
  restorable_checkpoints_enabled: boolean
  // Timed access window (ISO 8601 UTC strings, or null when unset). The access
  // group can only annotate/generate/evaluate between these; data is hidden
  // before the start; it's read-only after the end. Editors are exempt.
  window_start_at: string | null
  window_end_at: string | null
}

interface AdvancedSettingsCardProps {
  t: (key: string, params?: any) => string
  canEditProject: () => boolean
  getReadOnlyMessage: (sectionTitle: string) => string
  advancedSettings: AdvancedSettings
  setAdvancedSettings: Dispatch<SetStateAction<AdvancedSettings>>
  editing: boolean
  ProjectSettingsExtended: ComponentType<any> | null
}

export function AdvancedSettingsCard({
  t,
  canEditProject,
  getReadOnlyMessage,
  advancedSettings,
  setAdvancedSettings,
  editing,
  ProjectSettingsExtended,
}: AdvancedSettingsCardProps) {
  return (
    <div className="bg-white dark:bg-zinc-900">
      {canEditProject() ? (
      <>
        <div className="space-y-6">
          {/* Annotation Behavior */}
          <div>
            <h3 className="text-md mb-4 font-medium text-zinc-900 dark:text-white">
              {t('project.settings.annotationBehavior.title')}
            </h3>
            <div className="space-y-4">
              <div>
                <Label htmlFor="maximum_annotations">
                  {t(
                    'project.settings.annotationBehavior.maxAnnotations'
                  )}
                </Label>
                <Select
                  value={advancedSettings.maximum_annotations.toString()}
                  onValueChange={(value: string) =>
                    setAdvancedSettings((prev) => ({
                      ...prev,
                      maximum_annotations: parseInt(value),
                    }))
                  }
                  disabled={!editing}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="1">
                      {t(
                        'project.settings.annotationBehavior.annotations.single'
                      )}
                    </SelectItem>
                    <SelectItem value="2">
                      {t(
                        'project.settings.annotationBehavior.annotations.double'
                      )}
                    </SelectItem>
                    <SelectItem value="3">
                      {t(
                        'project.settings.annotationBehavior.annotations.triple'
                      )}
                    </SelectItem>
                    <SelectItem value="5">
                      {t(
                        'project.settings.annotationBehavior.annotations.multiple'
                      )}
                    </SelectItem>
                    <SelectItem value="10">10</SelectItem>
                    <SelectItem value="50">50</SelectItem>
                    <SelectItem value="100">100</SelectItem>
                    <SelectItem value="0">
                      {t(
                        'project.settings.annotationBehavior.annotations.unlimited',
                        'Unbegrenzt'
                      )}
                    </SelectItem>
                  </SelectContent>
                </Select>
                <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                  {t(
                    'project.settings.annotationBehavior.maxAnnotationsHelp'
                  )}
                </p>
              </div>

              <div>
                <Label htmlFor="min_annotations_per_task">
                  {t(
                    'project.settings.annotationBehavior.minAnnotationsForCompletion'
                  )}
                </Label>
                <Select
                  value={advancedSettings.min_annotations_per_task.toString()}
                  onValueChange={(value: string) =>
                    setAdvancedSettings((prev) => ({
                      ...prev,
                      min_annotations_per_task: parseInt(value),
                    }))
                  }
                  disabled={!editing}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="1">
                      {t(
                        'project.settings.annotationBehavior.annotations.count1'
                      )}
                    </SelectItem>
                    <SelectItem value="2">
                      {t(
                        'project.settings.annotationBehavior.annotations.count2'
                      )}
                    </SelectItem>
                    <SelectItem value="3">
                      {t(
                        'project.settings.annotationBehavior.annotations.count3'
                      )}
                    </SelectItem>
                    <SelectItem value="4">
                      {t(
                        'project.settings.annotationBehavior.annotations.count4'
                      )}
                    </SelectItem>
                    <SelectItem value="5">
                      {t(
                        'project.settings.annotationBehavior.annotations.count5'
                      )}
                    </SelectItem>
                  </SelectContent>
                </Select>
                <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                  {t(
                    'project.settings.annotationBehavior.minAnnotationsHelp'
                  )}
                </p>
              </div>

              <div>
                <Label htmlFor="assignment_mode">
                  {t(
                    'project.settings.annotationBehavior.assignmentMode'
                  )}
                </Label>
                <Select
                  value={advancedSettings.assignment_mode}
                  onValueChange={(value: string) =>
                    setAdvancedSettings((prev: any) => ({
                      ...prev,
                      assignment_mode: value as
                        | 'open'
                        | 'manual'
                        | 'auto',
                    }))
                  }
                  disabled={!editing}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="open">
                      {t(
                        'project.settings.annotationBehavior.modes.open'
                      )}
                    </SelectItem>
                    <SelectItem value="manual">
                      {t(
                        'project.settings.annotationBehavior.modes.manual'
                      )}
                    </SelectItem>
                    <SelectItem value="auto">
                      {t(
                        'project.settings.annotationBehavior.modes.auto'
                      )}
                    </SelectItem>
                  </SelectContent>
                </Select>
                <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                  {t(
                    'project.settings.annotationBehavior.assignmentModeHelp'
                  )}
                </p>
              </div>

              <div className="flex items-center justify-between">
                <div>
                  <Label>
                    {t('project.settings.annotationBehavior.randomizeTaskOrder', 'Randomize task order')}
                  </Label>
                  <p className="text-sm text-zinc-500 dark:text-zinc-400">
                    {t('project.settings.annotationBehavior.randomizeTaskOrderHelp', 'Each annotator sees tasks in a different random order for even annotation distribution')}
                  </p>
                </div>
                <input
                  type="checkbox"
                  checked={advancedSettings.randomize_task_order}
                  onChange={(e) =>
                    setAdvancedSettings((prev: any) => ({
                      ...prev,
                      randomize_task_order: e.target.checked,
                    }))
                  }
                  disabled={!editing}
                  className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
                />
              </div>

              <div className="flex items-center justify-between">
                <div>
                  <Label>
                    {t('project.settings.annotationBehavior.annotatorFullVisibility', 'Reveal all fields after submission')}
                  </Label>
                  <p className="text-sm text-zinc-500 dark:text-zinc-400">
                    {t('project.settings.annotationBehavior.annotatorFullVisibilityHelp', 'When on, annotators reviewing their own submitted work see all task fields including the reference solution. When off, that view is filtered to only the fields they saw while labeling, keeping the reference hidden.')}
                  </p>
                </div>
                <input
                  type="checkbox"
                  checked={advancedSettings.annotator_full_visibility_after_submit}
                  onChange={(e) =>
                    setAdvancedSettings((prev: any) => ({
                      ...prev,
                      annotator_full_visibility_after_submit: e.target.checked,
                    }))
                  }
                  disabled={!editing}
                  className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
                />
              </div>

              {/* Annotation timer */}
              <div className="space-y-3 border-t border-zinc-200 pt-4 dark:border-zinc-700">
                <div className="flex items-center justify-between">
                  <div>
                    <Label>
                      {t('projects.creation.wizard.stepSettings.timeLimit', 'Annotation time limit')}
                    </Label>
                    <p className="text-sm text-zinc-500 dark:text-zinc-400">
                      {t('projects.creation.wizard.stepSettings.timeLimitHint', 'Limit how long annotators may spend on a single task')}
                    </p>
                  </div>
                  <input
                    type="checkbox"
                    checked={advancedSettings.annotation_time_limit_enabled}
                    onChange={(e) =>
                      setAdvancedSettings((prev: any) => ({
                        ...prev,
                        annotation_time_limit_enabled: e.target.checked,
                        annotation_time_limit_seconds: e.target.checked
                          ? (prev.annotation_time_limit_seconds ?? 1800)
                          : null,
                        strict_timer_enabled: e.target.checked
                          ? prev.strict_timer_enabled
                          : false,
                      }))
                    }
                    disabled={!editing}
                    className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
                  />
                </div>

                {advancedSettings.annotation_time_limit_enabled && (
                  <>
                    <div className="ml-4 flex items-center gap-2">
                      <Input
                        type="number"
                        min={1}
                        max={360}
                        value={
                          advancedSettings.annotation_time_limit_seconds
                            ? Math.round(
                                advancedSettings.annotation_time_limit_seconds / 60,
                              )
                            : 30
                        }
                        onChange={(e) =>
                          setAdvancedSettings((prev: any) => ({
                            ...prev,
                            annotation_time_limit_seconds:
                              (parseInt(e.target.value) || 30) * 60,
                          }))
                        }
                        disabled={!editing}
                        className="w-20 text-sm"
                      />
                      <span className="text-sm text-zinc-500">
                        {t('projects.creation.wizard.stepSettings.minutes', 'minutes')}
                      </span>
                    </div>

                    <div className="ml-4 flex items-center justify-between">
                      <div>
                        <Label>
                          {t('projects.creation.wizard.stepSettings.strictTimer', 'Strict timer')}
                        </Label>
                        <p className="text-sm text-zinc-500 dark:text-zinc-400">
                          {t('projects.creation.wizard.stepSettings.strictTimerHint', 'Auto-submit the annotation when the time limit is reached')}
                        </p>
                      </div>
                      <input
                        type="checkbox"
                        checked={advancedSettings.strict_timer_enabled}
                        onChange={(e) =>
                          setAdvancedSettings((prev: any) => ({
                            ...prev,
                            strict_timer_enabled: e.target.checked,
                          }))
                        }
                        disabled={!editing}
                        className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
                      />
                    </div>
                  </>
                )}
              </div>

              {/* Timed access window (annotate / generate / evaluate) */}
              <div className="space-y-3 border-t border-zinc-200 pt-4 dark:border-zinc-700">
                <div className="flex items-center justify-between">
                  <div>
                    <Label>
                      {t('project.settings.accessWindow.title', 'Timed access window')}
                    </Label>
                    <p className="text-sm text-zinc-500 dark:text-zinc-400">
                      {t(
                        'project.settings.accessWindow.hint',
                        'Open the project to its access group only during a set time. Before it opens, the project is listed but its data stays hidden; after it closes, the data is read-only. Owners and admins are never restricted.',
                      )}
                    </p>
                  </div>
                  <input
                    type="checkbox"
                    checked={
                      !!(
                        advancedSettings.window_start_at ||
                        advancedSettings.window_end_at
                      )
                    }
                    onChange={(e) => {
                      if (e.target.checked) {
                        setAdvancedSettings((prev: any) => {
                          if (prev.window_start_at || prev.window_end_at) return prev
                          const start = new Date()
                          start.setSeconds(0, 0)
                          const end = new Date(start.getTime() + 2 * 3600 * 1000)
                          return {
                            ...prev,
                            window_start_at: start.toISOString(),
                            window_end_at: end.toISOString(),
                          }
                        })
                      } else {
                        setAdvancedSettings((prev: any) => ({
                          ...prev,
                          window_start_at: null,
                          window_end_at: null,
                        }))
                      }
                    }}
                    disabled={!editing}
                    className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
                  />
                </div>

                {(advancedSettings.window_start_at ||
                  advancedSettings.window_end_at) && (
                  <div className="ml-4 space-y-2">
                    <div className="flex items-center gap-2">
                      <Label className="w-16 text-sm">
                        {t('project.settings.accessWindow.opens', 'Opens')}
                      </Label>
                      <Input
                        type="datetime-local"
                        value={isoToLocalInput(advancedSettings.window_start_at)}
                        onChange={(e) =>
                          setAdvancedSettings((prev: any) => ({
                            ...prev,
                            window_start_at: localInputToIso(e.target.value),
                          }))
                        }
                        disabled={!editing}
                        className="text-sm"
                      />
                    </div>
                    <div className="flex items-center gap-2">
                      <Label className="w-16 text-sm">
                        {t('project.settings.accessWindow.closes', 'Closes')}
                      </Label>
                      <Input
                        type="datetime-local"
                        value={isoToLocalInput(advancedSettings.window_end_at)}
                        onChange={(e) =>
                          setAdvancedSettings((prev: any) => ({
                            ...prev,
                            window_end_at: localInputToIso(e.target.value),
                          }))
                        }
                        disabled={!editing}
                        className="text-sm"
                      />
                    </div>
                    {advancedSettings.window_start_at &&
                      advancedSettings.window_end_at &&
                      new Date(advancedSettings.window_end_at) <=
                        new Date(advancedSettings.window_start_at) && (
                        <p className="text-xs text-red-500">
                          {t(
                            'project.settings.accessWindow.invalid',
                            'The close time must be after the open time.',
                          )}
                        </p>
                      )}
                  </div>
                )}
              </div>

              {/* Restorable draft checkpoints (opt-in) is an extended feature —
                  its toggle is rendered by the project-settings-extended slot
                  below, not here, so the community edition doesn't expose it. */}
            </div>
          </div>

          {/* Interface Settings */}
          <div>
            <h3 className="text-md mb-4 font-medium text-zinc-900 dark:text-white">
              {t('project.settings.interface.title')}
            </h3>
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <Label>
                    {t('project.settings.interface.showInstructions')}
                  </Label>
                  <p className="text-sm text-zinc-500 dark:text-zinc-400">
                    {t('project.settings.interface.showInstructionsHelp')}
                  </p>
                </div>
                <input
                  type="checkbox"
                  checked={advancedSettings.show_instruction}
                  onChange={(e) =>
                    setAdvancedSettings((prev: any) => ({
                      ...prev,
                      show_instruction: e.target.checked,
                    }))
                  }
                  disabled={!editing}
                  className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
                />
              </div>

              <div className="flex items-center justify-between">
                <div>
                  <Label>
                    {t('project.settings.interface.instructionsAlwaysVisible', { defaultValue: 'Always show instructions' })}
                  </Label>
                  <p className="text-sm text-zinc-500 dark:text-zinc-400">
                    {t('project.settings.interface.instructionsAlwaysVisibleHelp', { defaultValue: "Show instructions on every task, even if annotator clicked 'don't show again'" })}
                  </p>
                </div>
                <input
                  type="checkbox"
                  checked={advancedSettings.instructions_always_visible}
                  onChange={(e) =>
                    setAdvancedSettings((prev: any) => ({
                      ...prev,
                      instructions_always_visible: e.target.checked,
                    }))
                  }
                  disabled={!editing}
                  className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
                />
              </div>

              <div className="flex items-center justify-between">
                <div>
                  <Label>
                    {t('project.settings.interface.showSkipButton')}
                  </Label>
                  <p className="text-sm text-zinc-500 dark:text-zinc-400">
                    {t('project.settings.interface.showSkipButtonHelp')}
                  </p>
                </div>
                <input
                  type="checkbox"
                  checked={advancedSettings.show_skip_button}
                  onChange={(e) =>
                    setAdvancedSettings((prev: any) => ({
                      ...prev,
                      show_skip_button: e.target.checked,
                    }))
                  }
                  disabled={!editing}
                  className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
                />
              </div>

              <div className="flex items-center justify-between">
                <div>
                  <Label>
                    {t('project.settings.interface.requireCommentOnSkip')}
                  </Label>
                  <p className="text-sm text-zinc-500 dark:text-zinc-400">
                    {t(
                      'project.settings.interface.requireCommentOnSkipHelp'
                    )}
                  </p>
                </div>
                <input
                  type="checkbox"
                  checked={advancedSettings.require_comment_on_skip}
                  onChange={(e) =>
                    setAdvancedSettings((prev: any) => ({
                      ...prev,
                      require_comment_on_skip: e.target.checked,
                    }))
                  }
                  disabled={!editing}
                  className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
                />
              </div>

              <div className="flex items-center justify-between">
                <div>
                  <Label>
                    {t('project.settings.interface.skipQueue', { defaultValue: 'Skip behavior' })}
                  </Label>
                  <p className="text-sm text-zinc-500 dark:text-zinc-400">
                    {t('project.settings.interface.skipQueueHelp', { defaultValue: 'Controls what happens when an annotator skips a task' })}
                  </p>
                </div>
                <Select
                  value={advancedSettings.skip_queue || 'requeue_for_others'}
                  onValueChange={(v) =>
                    setAdvancedSettings((prev: any) => ({
                      ...prev,
                      skip_queue: v,
                    }))
                  }
                  disabled={!editing}
                  displayValue={
                    (advancedSettings.skip_queue || 'requeue_for_others') === 'requeue_for_me'
                      ? t('project.settings.interface.skipQueueRequeueForMe', { defaultValue: 'Re-queue for me' })
                      : (advancedSettings.skip_queue || 'requeue_for_others') === 'requeue_for_others'
                      ? t('project.settings.interface.skipQueueRequeueForOthers', { defaultValue: 'Re-queue for others' })
                      : t('project.settings.interface.skipQueueIgnoreSkipped', { defaultValue: 'Skip permanently' })
                  }
                >
                  <SelectTrigger className="w-auto min-w-[10rem]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="requeue_for_me">
                      {t('project.settings.interface.skipQueueRequeueForMe', { defaultValue: 'Re-queue for me' })}
                    </SelectItem>
                    <SelectItem value="requeue_for_others">
                      {t('project.settings.interface.skipQueueRequeueForOthers', { defaultValue: 'Re-queue for others' })}
                    </SelectItem>
                    <SelectItem value="ignore_skipped">
                      {t('project.settings.interface.skipQueueIgnoreSkipped', { defaultValue: 'Skip permanently' })}
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="flex items-center justify-between">
                <div>
                  <Label>
                    {t('project.settings.interface.showSubmitButton')}
                  </Label>
                  <p className="text-sm text-zinc-500 dark:text-zinc-400">
                    {t('project.settings.interface.showSubmitButtonHelp')}
                  </p>
                </div>
                <input
                  type="checkbox"
                  checked={advancedSettings.show_submit_button}
                  onChange={(e) =>
                    setAdvancedSettings((prev: any) => ({
                      ...prev,
                      show_submit_button: e.target.checked,
                    }))
                  }
                  disabled={!editing}
                  className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
                />
              </div>

              <div className="flex items-center justify-between">
                <div>
                  <Label>
                    {t('project.settings.interface.requireConfirmBeforeSubmit', { defaultValue: 'Require confirmation before submit' })}
                  </Label>
                  <p className="text-sm text-zinc-500 dark:text-zinc-400">
                    {t('project.settings.interface.requireConfirmBeforeSubmitHelp', { defaultValue: 'Annotators must check a confirmation checkbox before submitting.' })}
                  </p>
                </div>
                <input
                  type="checkbox"
                  checked={advancedSettings.require_confirm_before_submit}
                  onChange={(e) =>
                    setAdvancedSettings((prev: any) => ({
                      ...prev,
                      require_confirm_before_submit: e.target.checked,
                    }))
                  }
                  disabled={!editing}
                  className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
                />
              </div>

            </div>
          </div>

          {/* Post-Annotation Questionnaire (Issue #1208) */}
          <div>
            <h3 className="text-md mb-4 font-medium text-zinc-900 dark:text-white">
              {t('project.settings.questionnaireTitle', { defaultValue: 'Post-Annotation Questionnaire' })}
            </h3>
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <Label>
                    {t('project.settings.questionnaireEnabled', { defaultValue: 'Enable Questionnaire' })}
                  </Label>
                  <p className="text-sm text-zinc-500 dark:text-zinc-400">
                    {t('project.settings.questionnaireEnabledDescription', { defaultValue: 'Show a feedback form after each annotation submission' })}
                  </p>
                </div>
                <input
                  type="checkbox"
                  checked={advancedSettings.questionnaire_enabled}
                  onChange={(e) =>
                    setAdvancedSettings((prev: any) => ({
                      ...prev,
                      questionnaire_enabled: e.target.checked,
                    }))
                  }
                  disabled={!editing}
                  className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
                />
              </div>

              {advancedSettings.questionnaire_enabled && (
                <div className="space-y-3 border-t border-zinc-200 pt-3 dark:border-zinc-700">
                  <div>
                    <Label>
                      {t('project.settings.questionnaireTemplate', { defaultValue: 'Template' })}
                    </Label>
                    <Select
                      value=""
                      onValueChange={(v) => {
                        const templates: Record<string, string> = {
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

  <Header value="Fragen zur KI-Unterstützung (nur beantworten, wenn Sie in der KI-Gruppe waren)" level="4"/>
  <Likert name="ai_adequate" toName="ai_adequate" min="1" max="7" label="Der Output der KI war auf Anhieb adäquat."/>
  <Likert name="ai_reviewed" toName="ai_reviewed" min="1" max="7" label="Ich habe den Output der KI überprüft."/>
  <Likert name="utaut_pe" toName="utaut_pe" min="1" max="7" label="Ich würde die KI in meiner Arbeit/meinem Studium als nützlich empfinden."/>
  <Likert name="utaut_ee" toName="utaut_ee" min="1" max="7" label="Ich empfinde die KI als einfach zu nutzen."/>
  <Likert name="utaut_att1" toName="utaut_att1" min="1" max="7" label="Die Nutzung der KI ist eine gute Idee."/>
  <Likert name="utaut_att2" toName="utaut_att2" min="1" max="7" label="Die Arbeit mit der KI macht Spaß."/>
  <Likert name="utaut_att3" toName="utaut_att3" min="1" max="7" label="Ich arbeite gerne mit der KI."/>

  <Header value="Anteil an der Fallbearbeitung (nur beantworten, wenn Sie in der KI-Gruppe waren)" level="4"/>
  <Number name="human_share" toName="human_share" min="0" max="100" label="x Prozent der Fallbearbeitung gehen auf mich zurück." hint="Wert zwischen 0 und 100"/>
  <Number name="ai_share" toName="ai_share" min="0" max="100" label="y Prozent der Fallbearbeitung gehen auf die KI zurück." hint="Wert zwischen 0 und 100"/>

  <Header value="Frage ohne KI (nur beantworten, wenn Sie NICHT in der KI-Gruppe waren)" level="4"/>
  <Likert name="desired_ai" toName="desired_ai" min="1" max="7" label="Ich hätte mir die KI für die Bearbeitung dieser Aufgabe gewünscht."/>
</View>`,
                        }
                        if (v in templates) {
                          setAdvancedSettings((prev: any) => ({
                            ...prev,
                            questionnaire_config: templates[v],
                          }))
                        }
                      }}
                      disabled={!editing}
                    >
                      <SelectTrigger className="mt-1">
                        <SelectValue placeholder={t('project.settings.questionnaireSelectTemplate', { defaultValue: 'Select a template...' })} />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="confidence_difficulty">
                          {t('project.settings.questionnaireTemplateConfidence', { defaultValue: 'Confidence & Difficulty (2 items)' })}
                        </SelectItem>
                        <SelectItem value="extended">
                          {t('project.settings.questionnaireTemplateExtended', { defaultValue: 'Extended Feedback (4 items)' })}
                        </SelectItem>
                        <SelectItem value="utaut_study">
                          {t('project.settings.questionnaireTemplateUtaut', { defaultValue: 'UTAUT Study (12 items, Likert 1-7)' })}
                        </SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  <div>
                    <Label>
                      {t('project.settings.questionnaireConfig', { defaultValue: 'Questionnaire Config (Label Studio XML)' })}
                    </Label>
                    <textarea
                      value={advancedSettings.questionnaire_config}
                      onChange={(e) =>
                        setAdvancedSettings((prev: any) => ({
                          ...prev,
                          questionnaire_config: e.target.value,
                        }))
                      }
                      disabled={!editing}
                      rows={10}
                      className="mt-1 block w-full rounded-md border border-zinc-300 bg-white px-3 py-2 font-mono text-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500 dark:border-zinc-600 dark:bg-zinc-800 dark:text-white"
                      placeholder={`<View>\n  <Header value="Post-Annotation Feedback"/>\n  <Rating name="confidence" toName="confidence" maxRating="5" required="true"/>\n</View>`}
                    />
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Extended project settings (review, feedback) — rendered by extension slot */}
          {ProjectSettingsExtended && (
            <ProjectSettingsExtended
              settings={advancedSettings}
              onSettingsChange={setAdvancedSettings}
              editing={editing}
            />
          )}

          {/* Per-section Save/Cancel removed — card-level Speichern handles it. */}
        </div>
      </>
      ) : (
        <div className="py-6 text-center">
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            {getReadOnlyMessage(t('project.settings.title'))}
          </p>
        </div>
      )}
    </div>
  )
}

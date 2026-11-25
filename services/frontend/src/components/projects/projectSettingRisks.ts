/**
 * The platform's high-impact project settings, registered in the shared
 * risk registry (`@/components/shared/settingRisk`). Extensions register
 * their own settings the same way. Keys are the stored field names; the
 * composite settings use `visibility` and `access_window`.
 *
 * Imported for its side effect by the project page.
 */

import { registerSettingRisk } from '@/components/shared/settingRisk'
import { computeWindowState } from '@/utils/projectWindow'
import { PROJECT_KIND_OPTIONS } from './wizard/ProjectTypeAndIcon'

const kindNameKey = (kind: unknown) =>
  (
    PROJECT_KIND_OPTIONS.find((o) => o.id === (kind ?? 'generic')) ??
    PROJECT_KIND_OPTIONS[0]
  ).nameKey

let registered = false

export function registerProjectSettingRisks() {
  if (registered) return
  registered = true

  registerSettingRisk('visibility', {
    label: (t) => t('project.settings.visibilityDangerZone.title'),
    consequence: (t, _ctx, { to }) => {
      const next = (to as { visibility?: string } | null)?.visibility
      return next === 'public'
        ? t('project.settingRisk.visibility.public')
        : next === 'private'
          ? t('project.settingRisk.visibility.private')
          : t('project.settingRisk.visibility.organization')
    },
  })

  registerSettingRisk('access_window', {
    label: (t) => t('project.settings.accessWindow.title'),
    consequence: (t, _ctx, { to }) => {
      const next = (to ?? {}) as {
        window_start_at?: string | null
        window_end_at?: string | null
      }
      const state = computeWindowState(next.window_start_at, next.window_end_at)
      return t(`project.settingRisk.accessWindow.${state}`)
    },
  })

  registerSettingRisk('kind', {
    label: (t) => t('projects.creation.wizard.step1.kind.title'),
    consequence: (t, _ctx, { to }) =>
      t('project.settingRisk.kind', {
        kind: t(kindNameKey(to)),
      }),
  })

  registerSettingRisk('enable_annotation', {
    isRisky: (_from, to) => to === false,
    label: (t) => t('project.annotationConfiguration.title'),
    consequence: (t) => t('project.settingRisk.enableAnnotationOff'),
  })

  registerSettingRisk('annotator_full_visibility_after_submit', {
    isRisky: (_from, to) => to === true,
    label: (t) =>
      t('project.settings.annotationBehavior.annotatorFullVisibility'),
    consequence: (t, ctx) =>
      t('project.settingRisk.fullVisibility', { count: ctx.submittedCount }),
  })

  registerSettingRisk('annotator_step_detail_after_submit', {
    isRisky: (_from, to) => to === true,
    label: (t) => t('project.settings.annotationBehavior.annotatorStepDetail'),
    consequence: (t, ctx) =>
      t('project.settingRisk.stepDetail', { count: ctx.submittedCount }),
  })

  registerSettingRisk('annotation_time_limit_enabled', {
    label: (t) => t('projects.creation.wizard.stepSettings.timeLimit'),
    consequence: (t, _ctx, { to }) =>
      to
        ? t('project.settingRisk.timeLimitOn')
        : t('project.settingRisk.timeLimitOff'),
  })

  registerSettingRisk('annotation_time_limit_seconds', {
    // Switching the limit on seeds a value; that change is confirmed with
    // the switch. Editing the minutes later is confirmed on its own.
    isRisky: (from, to) => from != null && to != null,
    label: (t) => t('projects.creation.wizard.stepSettings.timeLimit'),
    consequence: (t, _ctx, { to }) =>
      t('project.settingRisk.timeLimitMinutes', {
        minutes: Math.round(Number(to) / 60),
      }),
  })

  registerSettingRisk('strict_timer_enabled', {
    isRisky: (_from, to) => to === true,
    label: (t) => t('projects.creation.wizard.stepSettings.strictTimer'),
    consequence: (t) => t('project.settingRisk.strictTimer'),
  })

  registerSettingRisk('assignment_mode', {
    label: (t) => t('project.settings.annotationBehavior.assignmentMode'),
    consequence: (t, _ctx, { to }) =>
      t(`project.settingRisk.assignmentMode.${String(to)}`),
  })

  registerSettingRisk('maximum_annotations', {
    // Lowering the cap (0 = unlimited) can close tasks to new annotators.
    isRisky: (from, to) => {
      const f = Number(from)
      const n = Number(to)
      return n !== 0 && (f === 0 || n < f)
    },
    label: (t) => t('project.settings.annotationBehavior.maxAnnotations'),
    consequence: (t, _ctx, { to }) =>
      t('project.settingRisk.maxAnnotations', { count: Number(to) }),
  })

  registerSettingRisk('allow_external_paste', {
    label: (t) => t('project.settings.interface.allowExternalPaste'),
    consequence: (t, _ctx, { to }) =>
      to ? t('project.settingRisk.pasteOn') : t('project.settingRisk.pasteOff'),
  })

  registerSettingRisk('immediate_evaluation_enabled', {
    isRisky: (_from, to) => to === true,
    label: (t) => t('projects.creation.wizard.step7.immediateEvaluation'),
    consequence: (t) => t('project.settingRisk.immediateEvaluation'),
  })
}

'use client'

import { Alert } from '@/components/shared/Alert'
import { Input } from '@/components/shared/Input'
import { Label } from '@/components/shared/Label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/shared/Select'
import { useI18n } from '@/contexts/I18nContext'
import { ProjectSettings } from './types'

interface StepSettingsProps {
  settings: ProjectSettings
  onSettingsChange: (settings: ProjectSettings) => void
}

export function StepSettings({
  settings,
  onSettingsChange,
}: StepSettingsProps) {
  const { t } = useI18n()

  const update = (partial: Partial<ProjectSettings>) => {
    onSettingsChange({ ...settings, ...partial })
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="mb-2 text-2xl font-semibold text-zinc-900 dark:text-white">
          {t('projects.creation.wizard.stepSettings.title')}
        </h2>
        <p className="text-zinc-600 dark:text-zinc-400">
          {t('projects.creation.wizard.stepSettings.subtitle')}
        </p>
      </div>

      <div className="space-y-4">
        {/* Assignment Mode */}
        <div>
          <Label>
            {t('projects.creation.wizard.stepSettings.assignmentMode')}
          </Label>
          <p className="mb-1 text-xs text-zinc-500 dark:text-zinc-400">
            {t('projects.creation.wizard.stepSettings.assignmentModeHint')}
          </p>
          <Select
            value={settings.assignment_mode}
            onValueChange={(value) =>
              update({
                assignment_mode: value as 'open' | 'manual' | 'auto',
              })
            }
          >
            <SelectTrigger data-testid="wizard-setting-mode">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="open">
                {t('projects.creation.wizard.stepSettings.modes.open')}
              </SelectItem>
              <SelectItem value="manual">
                {t('projects.creation.wizard.stepSettings.modes.manual')}
              </SelectItem>
              <SelectItem value="auto">
                {t('projects.creation.wizard.stepSettings.modes.auto')}
              </SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Max / Min Annotations */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <Label>
              {t('projects.creation.wizard.stepSettings.maxAnnotations')}
            </Label>
            <Select
              value={settings.maximum_annotations.toString()}
              onValueChange={(value) =>
                update({ maximum_annotations: parseInt(value) })
              }
              displayValue={
                settings.maximum_annotations === 0
                  ? t('projects.creation.wizard.stepSettings.unlimited')
                  : undefined
              }
            >
              <SelectTrigger data-testid="wizard-setting-max-annotations">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="0">
                  {t('projects.creation.wizard.stepSettings.unlimited')}
                </SelectItem>
                <SelectItem value="1">1</SelectItem>
                <SelectItem value="2">2</SelectItem>
                <SelectItem value="3">3</SelectItem>
                <SelectItem value="5">5</SelectItem>
                <SelectItem value="10">10</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div>
            <Label>
              {t('projects.creation.wizard.stepSettings.minAnnotations')}
            </Label>
            <Select
              value={settings.min_annotations_per_task.toString()}
              onValueChange={(value) =>
                update({
                  min_annotations_per_task: parseInt(value),
                })
              }
            >
              <SelectTrigger data-testid="wizard-setting-min-annotations">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="1">1</SelectItem>
                <SelectItem value="2">2</SelectItem>
                <SelectItem value="3">3</SelectItem>
                <SelectItem value="4">4</SelectItem>
                <SelectItem value="5">5</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        {/* Toggle settings */}
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <Label>
                {t('projects.creation.wizard.stepSettings.requireConfirm')}
              </Label>
              <p className="text-sm text-zinc-500 dark:text-zinc-400">
                {t('projects.creation.wizard.stepSettings.requireConfirmHint')}
              </p>
            </div>
            <input
              type="checkbox"
              checked={settings.require_confirm_before_submit}
              onChange={(e) =>
                update({ require_confirm_before_submit: e.target.checked })
              }
              className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
              data-testid="wizard-setting-require-confirm"
            />
          </div>

          <div className="flex items-center justify-between">
            <div>
              <Label>
                {t('projects.creation.wizard.stepSettings.randomizeOrder')}
              </Label>
              <p className="text-sm text-zinc-500 dark:text-zinc-400">
                {t('projects.creation.wizard.stepSettings.randomizeOrderHint')}
              </p>
            </div>
            <input
              type="checkbox"
              checked={settings.randomize_task_order}
              onChange={(e) =>
                update({ randomize_task_order: e.target.checked })
              }
              className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
              data-testid="wizard-setting-randomize"
            />
          </div>
        </div>

        {/* Timer settings */}
        <div className="space-y-3 border-t border-zinc-200 pt-4 dark:border-zinc-700">
          <div className="flex items-center justify-between">
            <div>
              <Label>
                {t('projects.creation.wizard.stepSettings.timeLimit')}
              </Label>
              <p className="text-sm text-zinc-500 dark:text-zinc-400">
                {t('projects.creation.wizard.stepSettings.timeLimitHint')}
              </p>
            </div>
            <input
              type="checkbox"
              checked={settings.annotation_time_limit_enabled}
              onChange={(e) =>
                update({
                  annotation_time_limit_enabled: e.target.checked,
                  annotation_time_limit_seconds: e.target.checked ? 1800 : null,
                  strict_timer_enabled: false,
                })
              }
              className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
            />
          </div>

          {settings.annotation_time_limit_enabled && (
            <>
              <div className="ml-4 flex items-center gap-2">
                <Input
                  type="number"
                  min={1}
                  max={360}
                  value={
                    settings.annotation_time_limit_seconds
                      ? Math.round(settings.annotation_time_limit_seconds / 60)
                      : 30
                  }
                  onChange={(e) =>
                    update({
                      annotation_time_limit_seconds:
                        (parseInt(e.target.value) || 30) * 60,
                    })
                  }
                  className="w-20 text-sm"
                />
                <span className="text-sm text-zinc-500">
                  {t('projects.creation.wizard.stepSettings.minutes')}
                </span>
              </div>

              <div className="ml-4 flex items-center justify-between">
                <div>
                  <Label>
                    {t('projects.creation.wizard.stepSettings.strictTimer')}
                  </Label>
                  <p className="text-sm text-zinc-500 dark:text-zinc-400">
                    {t('projects.creation.wizard.stepSettings.strictTimerHint')}
                  </p>
                </div>
                <input
                  type="checkbox"
                  checked={settings.strict_timer_enabled}
                  onChange={(e) =>
                    update({ strict_timer_enabled: e.target.checked })
                  }
                  className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
                />
              </div>
            </>
          )}
        </div>

        <Alert variant="info">
          <p className="text-sm">
            {t('projects.creation.wizard.stepSettings.advancedNote')}
          </p>
        </Alert>
      </div>
    </div>
  )
}

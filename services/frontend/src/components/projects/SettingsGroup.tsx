/**
 * Shared layout for settings inside the project page's sub-collapsibles.
 *
 * - `SettingsGroup`: a titled group of related settings. Consecutive groups
 *   are separated by a hairline; a group whose content renders nothing (for
 *   example an extension slot that is switched off) is hidden, so it leaves
 *   no empty title or double divider behind.
 * - `SettingRow`: one setting with its label and help text on the left and
 *   its control (a checkbox or a compact select) on the right. Settings that
 *   only matter while this one is on go into `children` and render indented
 *   under it.
 * - `SettingField`: one setting whose control needs the full width (number
 *   inputs, text areas, wide selects), with the label above it.
 *
 * Exported for extension slots as well, so settings contributed by an
 * extension look and group the same way as the platform's own.
 */

'use client'

import { Label } from '@/components/shared/Label'
import { cn } from '@/lib/utils'
import type { ReactNode } from 'react'

const HELP_CLASS = 'mt-1 text-xs text-zinc-500 dark:text-zinc-400'
const ROW_HELP_CLASS = 'mt-0.5 text-xs text-zinc-500 dark:text-zinc-400'

interface SettingsGroupProps {
  title: string
  description?: ReactNode
  children: ReactNode
  className?: string
  'data-testid'?: string
}

export function SettingsGroup({
  title,
  description,
  children,
  className,
  'data-testid': testId,
}: SettingsGroupProps) {
  return (
    <section
      data-testid={testId}
      data-settings-group=""
      // Groups follow each other inside one stack: every group after the
      // first gets the divider. A group without rendered settings (only its
      // header left, because a slot returned null) collapses entirely.
      className={cn(
        '[[data-settings-group]~&]:border-t [[data-settings-group]~&]:border-zinc-200 [[data-settings-group]~&]:pt-6 dark:[[data-settings-group]~&]:border-zinc-700',
        'has-[[data-settings-group-body]:empty]:hidden',
        className,
      )}
    >
      <h3 className="text-sm font-semibold text-zinc-900 dark:text-white">
        {title}
      </h3>
      {description ? <p className={HELP_CLASS}>{description}</p> : null}
      <div data-settings-group-body="" className="mt-4 space-y-4">
        {children}
      </div>
    </section>
  )
}

/** Vertical stack of `SettingsGroup`s with the standard spacing. */
export function SettingsGroupStack({
  children,
  className,
}: {
  children: ReactNode
  className?: string
}) {
  return <div className={cn('space-y-6', className)}>{children}</div>
}

interface SettingRowProps {
  label: ReactNode
  help?: ReactNode
  /** id of the control, so clicking the label focuses or toggles it. */
  htmlFor?: string
  control: ReactNode
  /** Dependent settings, rendered indented under this one. */
  children?: ReactNode
  className?: string
  'data-testid'?: string
}

export function SettingRow({
  label,
  help,
  htmlFor,
  control,
  children,
  className,
  'data-testid': testId,
}: SettingRowProps) {
  return (
    <div className={className} data-testid={testId} data-setting-row="">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          {/* The shared Label's look without its bottom margin: the help
              text sits right under the label in a row. */}
          <label
            htmlFor={htmlFor}
            className="block text-sm font-medium text-zinc-700 dark:text-zinc-300"
          >
            {label}
          </label>
          {help ? <p className={ROW_HELP_CLASS}>{help}</p> : null}
        </div>
        <div className="flex shrink-0 items-center pt-0.5">{control}</div>
      </div>
      {children ? <SettingChildren>{children}</SettingChildren> : null}
    </div>
  )
}

interface SettingFieldProps {
  label: ReactNode
  help?: ReactNode
  htmlFor?: string
  children: ReactNode
  className?: string
  'data-testid'?: string
}

export function SettingField({
  label,
  help,
  htmlFor,
  children,
  className,
  'data-testid': testId,
}: SettingFieldProps) {
  return (
    <div className={className} data-testid={testId}>
      <Label htmlFor={htmlFor}>{label}</Label>
      {children}
      {help ? <p className={HELP_CLASS}>{help}</p> : null}
    </div>
  )
}

/** Indented block for settings that depend on the setting above them. */
export function SettingChildren({ children }: { children: ReactNode }) {
  return (
    <div className="mt-3 ml-1 space-y-4 border-l border-zinc-200 pl-4 empty:hidden dark:border-zinc-700">
      {children}
    </div>
  )
}

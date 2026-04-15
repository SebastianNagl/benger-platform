'use client'

import { Switch } from '@headlessui/react'
import clsx from 'clsx'

interface ToggleSwitchProps {
  enabled: boolean
  onChange: (enabled: boolean) => void
  label?: string
  disabled?: boolean
}

export function ToggleSwitch({
  enabled,
  onChange,
  label,
  disabled = false,
}: ToggleSwitchProps) {
  return (
    <Switch.Group as="div" className="flex items-center">
      <Switch
        checked={enabled}
        onChange={onChange}
        disabled={disabled}
        className={clsx(
          'relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-offset-2',
          enabled ? 'bg-emerald-600' : 'bg-zinc-200 dark:bg-zinc-700',
          disabled && 'cursor-not-allowed opacity-50'
        )}
      >
        <span
          className={clsx(
            'inline-block h-4 w-4 transform rounded-full bg-white transition-transform',
            enabled ? 'translate-x-6' : 'translate-x-1'
          )}
        />
      </Switch>
      {label && (
        <Switch.Label className="ml-3 text-sm">
          <span className="font-medium text-zinc-900 dark:text-zinc-100">
            {label}
          </span>
        </Switch.Label>
      )}
    </Switch.Group>
  )
}

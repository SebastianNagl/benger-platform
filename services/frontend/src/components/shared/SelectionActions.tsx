'use client'

/**
 * The actions menu over the selected rows of a table: an "Actions" button
 * with the number of selected rows, opening a menu of what can be done with
 * them. Every table with row selection renders it (project data, projects
 * list, global data, and the overlays' tables), so the actions look and
 * behave the same everywhere.
 *
 * Generic on purpose: the caller passes the actions as data; the component
 * knows nothing about what they do. The button is disabled while no row is
 * selected, and the menu closes itself after an action is chosen.
 */

import { Menu, MenuButton, MenuItem, MenuItems } from '@headlessui/react'
import {
  ChevronDownIcon,
  EllipsisHorizontalIcon,
} from '@heroicons/react/24/outline'
import clsx from 'clsx'
import { Fragment, type ComponentType, type SVGProps } from 'react'

import { Button } from '@/components/shared/Button'
import { useI18n } from '@/contexts/I18nContext'

export interface SelectionAction {
  /** Stable key of the action. */
  id: string
  label: string
  /** A 24/outline heroicon, drawn at 16px left of the label. */
  icon?: ComponentType<SVGProps<SVGSVGElement>>
  /** Runs when the action is chosen; the menu closes on its own. */
  onSelect: () => void
  /** Destructive actions (delete, withdraw) are drawn in red. */
  danger?: boolean
  disabled?: boolean
  /** Draws a divider above this action, to group the actions. */
  separatorBefore?: boolean
  testId?: string
}

export interface SelectionActionsProps {
  /** Number of selected rows: the button's badge; 0 disables the button. */
  selectedCount: number
  /** The actions, in the order they are listed. */
  actions: SelectionAction[]
  /** Small header inside the menu, e.g. "3 tasks selected". */
  selectedLabel?: string
  /** The button's text; "Actions" in the UI language when left out. */
  label?: string
  /** Disables the button regardless of the selection (e.g. while busy). */
  disabled?: boolean
  /** Prefix of the test ids: `<testId>-button` and `<testId>-menu`. */
  testId?: string
}

export function SelectionActions({
  selectedCount,
  actions,
  selectedLabel,
  label,
  disabled = false,
  testId = 'selection-actions',
}: SelectionActionsProps) {
  const { t } = useI18n()
  const isDisabled = disabled || selectedCount === 0 || actions.length === 0

  return (
    <Menu as="div" className="relative inline-block text-left">
      <MenuButton
        as={Button}
        variant="outline"
        className="gap-2"
        disabled={isDisabled}
        data-testid={`${testId}-button`}
      >
        <EllipsisHorizontalIcon className="h-4 w-4" aria-hidden="true" />
        {label ?? t('shared.selectionActions.actions')}
        {selectedCount > 0 && (
          <span
            className="ml-1 inline-flex items-center rounded-full bg-emerald-100 px-2 py-0.5 text-xs leading-none font-medium text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200"
            data-testid={`${testId}-count`}
          >
            {selectedCount}
          </span>
        )}
        <ChevronDownIcon className="h-4 w-4" aria-hidden="true" />
      </MenuButton>

      <MenuItems
        anchor="bottom start"
        className="z-20 mt-2 w-64 rounded-lg bg-white p-1 shadow-lg ring-1 ring-black/5 transition duration-100 ease-out [--anchor-gap:0.5rem] focus:outline-none data-closed:scale-95 data-closed:opacity-0 dark:bg-zinc-900 dark:ring-white/10"
        data-testid={`${testId}-menu`}
      >
        {selectedLabel && (
          <div className="px-3 py-2 text-xs font-medium text-zinc-500 dark:text-zinc-400">
            {selectedLabel}
          </div>
        )}
        {actions.map((action) => {
          const Icon = action.icon
          return (
            <Fragment key={action.id}>
              {action.separatorBefore && (
                <div
                  role="separator"
                  className="my-1 border-t border-zinc-200 dark:border-zinc-700"
                />
              )}
              <MenuItem disabled={action.disabled}>
                <button
                  type="button"
                  onClick={action.onSelect}
                  data-testid={action.testId}
                  className={clsx(
                    'group flex w-full items-center rounded-md px-3 py-2 text-left text-sm data-disabled:cursor-not-allowed data-disabled:opacity-50',
                    action.danger
                      ? 'text-red-600 data-focus:bg-red-50 dark:text-red-400 dark:data-focus:bg-red-950/40'
                      : 'text-zinc-900 data-focus:bg-zinc-100 dark:text-white dark:data-focus:bg-zinc-800',
                  )}
                >
                  {Icon && (
                    <Icon
                      className="mr-3 h-4 w-4 shrink-0"
                      aria-hidden="true"
                    />
                  )}
                  {action.label}
                </button>
              </MenuItem>
            </Fragment>
          )
        })}
      </MenuItems>
    </Menu>
  )
}

export default SelectionActions

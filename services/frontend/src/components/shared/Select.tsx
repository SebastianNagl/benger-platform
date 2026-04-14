'use client'

import { Listbox } from '@headlessui/react'
import { CheckIcon, ChevronDownIcon } from '@heroicons/react/24/outline'
import clsx from 'clsx'
import React, { ReactNode, createContext, useContext } from 'react'

interface SelectContextType {
  value: string
  onValueChange: (value: string) => void
  disabled?: boolean
  displayValue?: string
}

const SelectContext = createContext<SelectContextType | null>(null)

interface SelectProps {
  value: string
  onValueChange: (value: string) => void
  disabled?: boolean
  displayValue?: string
  children: ReactNode
}

interface SelectTriggerProps extends Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, 'value'> {
  children: ReactNode
  className?: string
}

interface SelectContentProps {
  children: ReactNode
  className?: string
}

interface SelectItemProps {
  value: string
  children: ReactNode
  className?: string
}

interface SelectValueProps {
  placeholder?: string
  className?: string
}

export function Select({
  value,
  onValueChange,
  disabled,
  displayValue,
  children,
}: SelectProps) {
  return (
    <SelectContext.Provider value={{ value, onValueChange, disabled, displayValue }}>
      <Listbox value={value} onChange={onValueChange} disabled={disabled}>
        <div className="relative">{children}</div>
      </Listbox>
    </SelectContext.Provider>
  )
}

export function SelectTrigger({ children, className, ...props }: SelectTriggerProps) {
  const context = useContext(SelectContext)
  if (!context) throw new Error('SelectTrigger must be used within Select')

  return (
    <Listbox.Button
      {...props}
      className={clsx(
        'relative h-8 w-full cursor-default rounded-full bg-white pl-3 pr-8 text-left text-sm text-zinc-900 ring-1 ring-zinc-900/10 transition',
        'hover:ring-zinc-900/20 focus:outline-none focus:ring-2 focus:ring-emerald-500',
        'dark:bg-white/5 dark:text-zinc-100 dark:ring-inset dark:ring-white/10 dark:hover:ring-white/20 dark:focus:ring-emerald-400',
        'disabled:cursor-not-allowed disabled:opacity-50',
        className
      )}
    >
      {children}
      <span className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-2.5">
        <ChevronDownIcon
          className="h-4 w-4 text-zinc-400"
          aria-hidden="true"
        />
      </span>
    </Listbox.Button>
  )
}

export function SelectContent({ children, className }: SelectContentProps) {
  return (
    <Listbox.Options
      className={clsx(
        'absolute z-50 mt-1 max-h-60 w-full overflow-auto rounded-lg bg-white py-1 text-sm shadow-lg ring-1 ring-black ring-opacity-5 transition duration-100 ease-in focus:outline-none data-[closed]:opacity-0 dark:bg-zinc-800',
        className
      )}
    >
      {children}
    </Listbox.Options>
  )
}

export function SelectItem({ value, children, className }: SelectItemProps) {
  return (
    <Listbox.Option
      value={value}
      data-value={value}
      className={({ active }) =>
        clsx(
          'relative cursor-default select-none py-2 pl-10 pr-4',
          active
            ? 'bg-emerald-100 text-emerald-900 dark:bg-emerald-900 dark:text-emerald-100'
            : 'text-zinc-900 dark:text-zinc-100',
          className
        )
      }
    >
      {({ selected }) => (
        <>
          <span
            className={clsx(
              'block truncate',
              selected ? 'font-medium' : 'font-normal'
            )}
          >
            {children}
          </span>
          {selected && (
            <span className="absolute inset-y-0 left-0 flex items-center pl-3 text-emerald-600 dark:text-emerald-400">
              <CheckIcon className="h-5 w-5" aria-hidden="true" />
            </span>
          )}
        </>
      )}
    </Listbox.Option>
  )
}

export function SelectValue({ placeholder, className }: SelectValueProps) {
  const context = useContext(SelectContext)
  if (!context) throw new Error('SelectValue must be used within Select')

  return (
    <span
      className={clsx(
        'block truncate text-zinc-900 dark:text-white',
        !context.value && 'text-zinc-500 dark:text-zinc-400',
        className
      )}
    >
      {context.displayValue || context.value || placeholder}
    </span>
  )
}

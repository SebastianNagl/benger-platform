'use client'

import { useI18n } from '@/contexts/I18nContext'
import {
  Combobox,
  ComboboxInput,
  ComboboxOption,
  ComboboxOptions,
  Listbox,
  Popover,
  PopoverButton,
  PopoverPanel,
} from '@headlessui/react'
import {
  CheckIcon,
  ChevronDownIcon,
  MagnifyingGlassIcon,
} from '@heroicons/react/24/outline'
import clsx from 'clsx'
import React, {
  Children,
  ElementType,
  ReactNode,
  createContext,
  isValidElement,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react'
import { arrangeOptions, hasOptions } from './selectOptions'

interface SelectContextType {
  value: string | string[]
  onValueChange: (value: any) => void
  disabled?: boolean
  displayValue?: string
  childrenForLookup: ReactNode
  searchable: boolean
  multiple: boolean
  searchPlaceholder?: string
  emptyMessage?: string
  /** A key typed on the closed trigger, handed to the search field on open. */
  pendingQuery: string
  setPendingQuery: (query: string) => void
  /** The searchable trigger, which gets focus back after a pick. */
  trigger: HTMLElement | null
  setTrigger: (element: HTMLElement | null) => void
}

const SelectContext = createContext<SelectContextType | null>(null)

interface SelectBaseProps {
  disabled?: boolean
  displayValue?: string
  children: ReactNode
  /**
   * For options that come from loaded data (projects, users, models, ...):
   * sorts them alphabetically by visible label with German collation and
   * adds a search field that filters by label. Options marked `pinned`
   * ("All", "None") stay at the top of their group. Leave it off for fixed
   * lists whose order means something (severity, status sequences, sizes).
   */
  searchable?: boolean
  /** Search field placeholder; defaults to the shared "Search..." text. */
  searchPlaceholder?: string
  /** Shown when the search matches nothing; defaults to "No matches". */
  emptyMessage?: string
}

interface SingleSelectProps extends SelectBaseProps {
  multiple?: false
  value: string
  onValueChange: (value: string) => void
}

/** Pick several values; implies `searchable`, and the list stays open. */
interface MultiSelectProps extends SelectBaseProps {
  multiple: true
  value: string[]
  onValueChange: (value: string[]) => void
}

type SelectProps = SingleSelectProps | MultiSelectProps

type SelectTriggerProps = Omit<
  React.ButtonHTMLAttributes<HTMLButtonElement>,
  'value'
> & {
  children: ReactNode
  className?: string
  /**
   * Render the trigger as another element (e.g. the shared Button) instead of
   * the rounded field; extra props pass through to it.
   */
  as?: ElementType
  /** Drop the field look and chevron, for triggers that bring their own. */
  unstyled?: boolean
  [key: string]: unknown
}

interface SelectContentProps {
  children: ReactNode
  className?: string
}

interface SelectItemProps {
  value: string
  children: ReactNode
  className?: string
  disabled?: boolean
  /** In a searchable Select: keep at the top of its group ("All", "None"). */
  pinned?: boolean
  /** Sort and search text when the visible label is not plain text. */
  textValue?: string
}

interface SelectValueProps {
  placeholder?: string
  className?: string
}

export function Select(props: SelectProps) {
  const {
    value,
    onValueChange,
    disabled,
    displayValue,
    children,
    searchPlaceholder,
    emptyMessage,
  } = props
  const multiple = props.multiple === true
  const searchable = multiple || props.searchable === true
  const [pendingQuery, setPendingQuery] = useState('')
  const [trigger, setTrigger] = useState<HTMLElement | null>(null)

  const context: SelectContextType = {
    value,
    onValueChange,
    disabled,
    displayValue,
    childrenForLookup: children,
    searchable,
    multiple,
    searchPlaceholder,
    emptyMessage,
    pendingQuery,
    setPendingQuery,
    trigger,
    setTrigger,
  }

  if (searchable) {
    return (
      <SelectContext.Provider value={context}>
        <Popover className="relative">{children}</Popover>
      </SelectContext.Provider>
    )
  }

  return (
    <SelectContext.Provider value={context}>
      {/* Like a native <select>, re-picking the current option is no change:
          HeadlessUI calls onChange on every option click. */}
      <Listbox
        value={value as string}
        onChange={(next: string) => {
          if (next !== value) (onValueChange as (v: string) => void)(next)
        }}
        disabled={disabled}
      >
        <div className="relative">{children}</div>
      </Listbox>
    </SelectContext.Provider>
  )
}

function findItemLabel(node: ReactNode, value: string): ReactNode | null {
  let result: ReactNode | null = null
  Children.forEach(node, (child) => {
    if (result !== null) return
    if (!isValidElement(child)) return
    const props = child.props as { value?: string; children?: ReactNode }
    if (props.value === value) {
      result = props.children ?? null
      return
    }
    if (props.children) {
      const nested = findItemLabel(props.children, value)
      if (nested !== null) result = nested
    }
  })
  return result
}

function Chevron() {
  return (
    <span className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-2.5">
      <ChevronDownIcon className="h-4 w-4 text-zinc-400" aria-hidden="true" />
    </span>
  )
}

export function SelectTrigger({
  children,
  className,
  as,
  unstyled = false,
  ...props
}: SelectTriggerProps) {
  const context = useContext(SelectContext)
  if (!context) throw new Error('SelectTrigger must be used within Select')

  const shared = {
    ...props,
    ...(as ? { as } : {}),
    'data-value': context.multiple ? undefined : context.value,
    className: clsx(!unstyled && 'ui-select-trigger', className),
  }

  if (!context.searchable) {
    return (
      <Listbox.Button {...(shared as any)}>
        {children}
        {!unstyled && <Chevron />}
      </Listbox.Button>
    )
  }

  const { setPendingQuery, setTrigger, disabled } = context
  return (
    <PopoverButton
      {...(shared as any)}
      ref={setTrigger}
      disabled={disabled}
      onKeyDown={(event: React.KeyboardEvent<HTMLButtonElement>) => {
        // A closed native select opens on the arrow keys and jumps on a typed
        // letter; here a typed letter starts the search with that letter.
        const open =
          event.currentTarget.getAttribute('aria-expanded') === 'true'
        const typed =
          event.key.length === 1 &&
          event.key !== ' ' &&
          !event.ctrlKey &&
          !event.metaKey &&
          !event.altKey
        if (
          !open &&
          (typed || event.key === 'ArrowDown' || event.key === 'ArrowUp')
        ) {
          event.preventDefault()
          setPendingQuery(typed ? event.key : '')
          event.currentTarget.click()
        }
        ;(props.onKeyDown as React.KeyboardEventHandler | undefined)?.(event)
      }}
    >
      {children}
      {!unstyled && <Chevron />}
    </PopoverButton>
  )
}

const panelClass =
  'z-60 rounded-lg bg-white text-sm shadow-lg ring-1 ring-black/5 transition duration-100 ease-in [--anchor-gap:4px] focus:outline-none data-closed:opacity-0 dark:bg-zinc-800 dark:ring-white/10'

export function SelectContent({ children, className }: SelectContentProps) {
  const context = useContext(SelectContext)

  if (context?.searchable) {
    return (
      // Anchored like the plain list; at least wide enough for the search
      // field even when the trigger is a narrow filter.
      <PopoverPanel
        anchor="bottom start"
        transition
        className={clsx(
          panelClass,
          'flex w-[max(var(--button-width),16rem)] max-w-[calc(100vw-2rem)] flex-col overflow-hidden',
          className,
        )}
      >
        {({ close }) => (
          <SearchableOptions context={context} close={close}>
            {children}
          </SearchableOptions>
        )}
      </PopoverPanel>
    )
  }

  return (
    // Anchored: rendered in a portal and flipped upward when there is no room
    // below, so dialogs and scroll containers never clip the list.
    <Listbox.Options
      anchor="bottom start"
      className={clsx(
        panelClass,
        'max-h-60 w-(--button-width) overflow-auto py-1',
        className,
      )}
    >
      {children}
    </Listbox.Options>
  )
}

function SearchableOptions({
  context,
  close,
  children,
}: {
  context: SelectContextType
  close: (focusAfter?: HTMLElement) => void
  children: ReactNode
}) {
  const { t } = useI18n()
  // Lives inside the panel, so the search starts empty on every open.
  const { pendingQuery, setPendingQuery } = context
  const [query, setQuery] = useState(pendingQuery)
  // The typed key seeded this open only.
  useEffect(() => {
    if (pendingQuery) setPendingQuery('')
  }, [pendingQuery, setPendingQuery])

  const arranged = useMemo(
    () =>
      arrangeOptions(children, {
        isGroupLabel: (element) => element.type === SelectGroupLabel,
        query,
      }),
    [children, query],
  )

  const handleChange = (next: string | string[] | null) => {
    if (next === null) return
    if (context.multiple) {
      context.onValueChange(next)
      return
    }
    if (next !== context.value) context.onValueChange(next)
    // Back to the trigger, as after picking from a native select. Closing
    // waits for the combobox to finish the click: it moves focus back into
    // the search field, and closing first would unmount that focused field
    // and drop focus to the page.
    const trigger = context.trigger ?? undefined
    setTimeout(() => close(trigger), 0)
  }

  return (
    <Combobox
      value={context.value}
      onChange={handleChange}
      multiple={context.multiple as any}
      disabled={context.disabled}
    >
      <div className="relative border-b border-zinc-200 p-2 dark:border-zinc-700">
        <MagnifyingGlassIcon
          className="pointer-events-none absolute top-1/2 left-4 h-4 w-4 -translate-y-1/2 text-zinc-400 dark:text-zinc-500"
          aria-hidden="true"
        />
        <ComboboxInput
          autoFocus
          autoComplete="off"
          className="h-8 w-full rounded-full bg-white pr-3 pl-8 text-sm text-zinc-900 ring-1 ring-zinc-900/10 outline-hidden transition placeholder:text-zinc-500 hover:ring-zinc-900/20 focus:ring-2 focus:ring-emerald-500 dark:bg-white/5 dark:text-white dark:ring-white/10 dark:ring-inset dark:placeholder:text-zinc-400 dark:hover:ring-white/20 dark:focus:ring-emerald-400"
          placeholder={context.searchPlaceholder ?? t('common.search')}
          aria-label={context.searchPlaceholder ?? t('common.search')}
          displayValue={() => query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event: React.KeyboardEvent<HTMLInputElement>) => {
            // One Escape closes the list even after typing; the combobox
            // alone would only reset its own state and leave the panel open.
            if (event.key === 'Escape') {
              event.preventDefault()
              close()
            }
          }}
        />
      </div>
      <ComboboxOptions
        static
        className="max-h-60 overflow-y-auto overscroll-contain py-1 focus:outline-none"
      >
        {arranged}
        {!hasOptions(arranged) && (
          <div className="px-4 py-2 text-sm text-zinc-500 dark:text-zinc-400">
            {context.emptyMessage ?? t('common.noMatches')}
          </div>
        )}
      </ComboboxOptions>
    </Combobox>
  )
}

const itemClass = (active: boolean, disabled?: boolean, className?: string) =>
  clsx(
    'relative cursor-default py-2 pr-4 pl-10 select-none',
    active
      ? 'bg-emerald-100 text-emerald-900 dark:bg-emerald-900 dark:text-emerald-100'
      : 'text-zinc-900 dark:text-zinc-100',
    disabled && 'cursor-not-allowed opacity-50',
    className,
  )

function ItemBody({
  selected,
  children,
}: {
  selected: boolean
  children: ReactNode
}) {
  return (
    <>
      <span
        className={clsx(
          'block truncate',
          selected ? 'font-medium' : 'font-normal',
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
  )
}

export function SelectItem({
  value,
  children,
  className,
  disabled,
}: SelectItemProps) {
  const context = useContext(SelectContext)

  if (context?.searchable) {
    return (
      <ComboboxOption
        value={value}
        data-value={value}
        disabled={disabled}
        className={({ focus }) => itemClass(focus, disabled, className)}
      >
        {({ selected }) => <ItemBody selected={selected}>{children}</ItemBody>}
      </ComboboxOption>
    )
  }

  return (
    <Listbox.Option
      value={value}
      data-value={value}
      disabled={disabled}
      className={({ active }) => itemClass(active, disabled, className)}
    >
      {({ selected }) => <ItemBody selected={selected}>{children}</ItemBody>}
    </Listbox.Option>
  )
}

interface SelectGroupLabelProps {
  children: ReactNode
  className?: string
}

/**
 * A heading inside SelectContent that names the options below it. It is not
 * an option: keyboard navigation skips it, because only SelectItem registers
 * with the listbox, and the trigger's label lookup ignores it, because it
 * carries no value. In a searchable Select the options under each heading
 * sort on their own, and a heading whose options all miss the search hides.
 */
export function SelectGroupLabel({
  children,
  className,
}: SelectGroupLabelProps) {
  return (
    <div
      role="presentation"
      className={clsx(
        'px-3 pt-2 pb-1 text-xs font-medium text-zinc-500 select-none dark:text-zinc-400',
        className,
      )}
    >
      {children}
    </div>
  )
}

export function SelectValue({ placeholder, className }: SelectValueProps) {
  const context = useContext(SelectContext)
  if (!context) throw new Error('SelectValue must be used within Select')

  // Like a native select, an empty value shows the option whose value is ''
  // ("None", "Default") when there is one, and the placeholder otherwise.
  const values = Array.isArray(context.value)
    ? context.value
    : context.value || findItemLabel(context.childrenForLookup, '') !== null
      ? [context.value]
      : []
  const labels = values
    .map((v) => findItemLabel(context.childrenForLookup, v) ?? v)
    .filter((label) => label !== null && label !== '')
  const derivedLabel =
    labels.length === 0
      ? null
      : labels.length === 1
        ? labels[0]
        : labels.map((label, i) => (
            <React.Fragment key={i}>
              {i > 0 && ', '}
              {label}
            </React.Fragment>
          ))

  return (
    <span
      className={clsx(
        'block truncate text-zinc-900 dark:text-white',
        values.length === 0 && 'text-zinc-500 dark:text-zinc-400',
        className,
      )}
    >
      {context.displayValue || derivedLabel || placeholder}
    </span>
  )
}

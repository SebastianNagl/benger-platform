/**
 * Jest mock for the shared Select component.
 *
 * Headless UI's Listbox doesn't render properly in JSDOM, so we provide
 * a native <select> implementation that preserves the same API and allows
 * existing test queries (getByRole('combobox'), fireEvent.change,
 * userEvent.selectOptions, ...) to keep working.
 *
 * The <option> elements are derived from the Select's element tree at render
 * time: SelectTrigger walks the children the Select received (exposed via
 * context) and renders every SelectItem it finds inside the native <select>.
 * Earlier versions handed the options over through an effect + state pair,
 * which React 19 re-runs on every render (children identity changes), so the
 * <select> was empty at the moment tests queried it.
 *
 * A trigger rendered as another element (`as={Button}`, a filter button with
 * its own icon and text) has no native counterpart, so it renders as that
 * button, and clicking it opens a plain list of options (role "option") that
 * select on click, as the real popover does.
 */
import React, { createContext, ReactNode, useContext, useState } from 'react'
import { arrangeOptions, nodeText } from '../selectOptions'

interface SelectContextType {
  value: string | string[]
  onValueChange: (value: any) => void
  searchable: boolean
  multiple: boolean
  disabled?: boolean
  displayValue?: string
  childrenForLookup: ReactNode
  open: boolean
  setOpen: (open: boolean) => void
}

const SelectContext = createContext<SelectContextType | null>(null)

/**
 * Like the real Select, `searchable` (and `multiple`, which implies it) sorts
 * the options alphabetically with pinned ones first, so tests see the order
 * users see. The search field itself has no native counterpart.
 */
export function Select({
  value,
  onValueChange,
  disabled,
  displayValue,
  children,
  searchable = false,
  multiple = false,
}: {
  value: string | string[]
  onValueChange: (value: any) => void
  disabled?: boolean
  displayValue?: string
  children: ReactNode
  searchable?: boolean
  multiple?: boolean
  searchPlaceholder?: string
  emptyMessage?: string
}) {
  const [open, setOpen] = useState(false)
  return (
    <SelectContext.Provider
      value={{
        value,
        onValueChange,
        searchable: searchable || multiple,
        multiple,
        disabled,
        displayValue,
        childrenForLookup: children,
        open,
        setOpen,
      }}
    >
      {children}
    </SelectContext.Provider>
  )
}

/** Flatten arrays/fragments into the list of element children. */
function flattenElements(node: ReactNode, out: React.ReactElement[]): void {
  React.Children.forEach(node, (child) => {
    if (!React.isValidElement(child)) return
    if (child.type === React.Fragment) {
      flattenElements((child.props as { children?: ReactNode }).children, out)
      return
    }
    out.push(child)
  })
}

/**
 * Collect the option elements: everything rendered inside a SelectContent.
 * Matching on the SelectContent wrapper (not on SelectItem's identity) keeps
 * this working for suites that override SelectItem with their own element.
 */
function collectItems(node: ReactNode, out: React.ReactElement[]): void {
  React.Children.forEach(node, (child) => {
    if (!React.isValidElement(child)) return
    const props = child.props as { children?: ReactNode }
    if (child.type === SelectContent) {
      flattenElements(props.children, out)
      return
    }
    if (props.children) collectItems(props.children, out)
  })
}

/** The options in the order the real Select shows them, headings dropped. */
function orderedItems(context: SelectContextType): React.ReactElement[] {
  const collected: React.ReactElement[] = []
  collectItems(context.childrenForLookup, collected)
  const isGroupLabel = (element: React.ReactElement) =>
    element.type === SelectGroupLabel
  const ordered = context.searchable
    ? arrangeOptions(collected, { isGroupLabel })
    : collected
  // A heading is not an option and has no place inside a native <select>.
  return ordered.filter((element) => !isGroupLabel(element))
}

export function SelectTrigger({
  children,
  className,
  as,
  unstyled = false,
  ...rest
}: {
  children: ReactNode
  className?: string
  [key: string]: any
}) {
  const context = useContext(SelectContext)
  if (!context) throw new Error('SelectTrigger must be used within Select')
  const items = orderedItems(context)

  if (as) {
    const { variant: _variant, ...props } = rest
    const selected = (value: string) =>
      Array.isArray(context.value)
        ? context.value.includes(value)
        : context.value === value
    const pick = (value: string) => {
      if (Array.isArray(context.value)) {
        context.onValueChange(
          selected(value)
            ? context.value.filter((v) => v !== value)
            : [...context.value, value],
        )
        return
      }
      if (value !== context.value) context.onValueChange(value)
      context.setOpen(false)
    }
    return (
      <>
        <button
          type="button"
          className={className}
          disabled={context.disabled}
          aria-expanded={context.open}
          onClick={() => context.setOpen(!context.open)}
          {...props}
        >
          {children}
        </button>
        {context.open && (
          <ul
            role="listbox"
            aria-multiselectable={context.multiple || undefined}
          >
            {items.map((item, i) => {
              const {
                value,
                disabled,
                children: label,
              } = item.props as {
                value?: string
                disabled?: boolean
                children?: ReactNode
              }
              if (value === undefined) return null
              return (
                <li
                  key={item.key ?? i}
                  role="option"
                  aria-selected={selected(value)}
                  aria-disabled={disabled || undefined}
                  data-value={value}
                  onClick={() => !disabled && pick(value)}
                >
                  {label}
                </li>
              )
            })}
          </ul>
        )}
      </>
    )
  }

  const props = rest
  return (
    <select
      value={context.value}
      multiple={context.multiple || undefined}
      onChange={(e) =>
        context.onValueChange(
          context.multiple
            ? Array.from(e.target.selectedOptions, (o) => o.value)
            : e.target.value,
        )
      }
      disabled={context.disabled}
      className={className}
      {...props}
    >
      {!unstyled && children}
      {items.map((item, i) => React.cloneElement(item, { key: item.key ?? i }))}
    </select>
  )
}

export function SelectContent(_props: {
  children: ReactNode
  className?: string
}) {
  // The options are rendered by SelectTrigger inside the native <select>.
  return null
}

export function SelectItem({
  value,
  children,
  disabled,
}: {
  value: string
  children: ReactNode
  className?: string
  disabled?: boolean
  pinned?: boolean
  textValue?: string
}) {
  // A native option holds text only, so rich labels (a name over a
  // description) read as one string, the way a browser would show them.
  return (
    <option value={value} disabled={disabled}>
      {typeof children === 'string' ? children : nodeText(children)}
    </option>
  )
}

export function SelectValue({
  placeholder,
}: {
  placeholder?: string
  className?: string
}) {
  const context = useContext(SelectContext)
  if (!context) return null

  // Render a placeholder option if no value selected
  if (!context.value && placeholder) {
    return (
      <option value="" disabled>
        {placeholder}
      </option>
    )
  }
  return null
}

/**
 * Headings have no native <select> counterpart that keeps option queries
 * stable, so the mock renders none; flattenElements skips them.
 */
export function SelectGroupLabel(_props: {
  children: ReactNode
  className?: string
}) {
  return null
}

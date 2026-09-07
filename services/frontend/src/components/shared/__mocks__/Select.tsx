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
 */
import React, { createContext, ReactNode, useContext } from 'react'

interface SelectContextType {
  value: string
  onValueChange: (value: string) => void
  disabled?: boolean
  displayValue?: string
  childrenForLookup: ReactNode
}

const SelectContext = createContext<SelectContextType | null>(null)

export function Select({
  value,
  onValueChange,
  disabled,
  displayValue,
  children,
}: {
  value: string
  onValueChange: (value: string) => void
  disabled?: boolean
  displayValue?: string
  children: ReactNode
}) {
  return (
    <SelectContext.Provider
      value={{
        value,
        onValueChange,
        disabled,
        displayValue,
        childrenForLookup: children,
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

export function SelectTrigger({
  children,
  className,
  ...props
}: {
  children: ReactNode
  className?: string
  [key: string]: any
}) {
  const context = useContext(SelectContext)
  if (!context) throw new Error('SelectTrigger must be used within Select')
  const items: React.ReactElement[] = []
  collectItems(context.childrenForLookup, items)

  return (
    <select
      value={context.value}
      onChange={(e) => context.onValueChange(e.target.value)}
      disabled={context.disabled}
      className={className}
      {...props}
    >
      {children}
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
}) {
  return (
    <option value={value} disabled={disabled}>
      {children}
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

/**
 * Jest mock for the shared Select component.
 *
 * Headless UI's Listbox doesn't render properly in JSDOM, so we provide
 * a native <select> implementation that preserves the same API and allows
 * existing test queries (getByRole('combobox'), fireEvent.change, etc.)
 * to keep working.
 *
 * The mock collects <option> elements from SelectContent/SelectItem children
 * and renders them inside the native <select> produced by SelectTrigger, so
 * that userEvent.selectOptions() works correctly.
 */
import React, { createContext, ReactNode, useContext, useRef, useEffect, useState } from 'react'

interface SelectContextType {
  value: string
  onValueChange: (value: string) => void
  disabled?: boolean
  displayValue?: string
}

const SelectContext = createContext<SelectContextType | null>(null)

/**
 * Shared ref so SelectContent can push its rendered children into the
 * <select> rendered by SelectTrigger.  Because React renders children
 * depth-first, SelectTrigger renders first; SelectContent collects the
 * <option> nodes and triggers a re-render via the items state.
 */
const ItemsContext = createContext<{
  items: React.ReactElement[]
  setItems: (items: React.ReactElement[]) => void
}>({ items: [], setItems: () => {} })

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
  const [items, setItems] = useState<React.ReactElement[]>([])

  return (
    <SelectContext.Provider value={{ value, onValueChange, disabled, displayValue }}>
      <ItemsContext.Provider value={{ items, setItems }}>
        {children}
      </ItemsContext.Provider>
    </SelectContext.Provider>
  )
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
  const { items } = useContext(ItemsContext)

  return (
    <select
      value={context.value}
      onChange={(e) => context.onValueChange(e.target.value)}
      disabled={context.disabled}
      className={className}
      {...props}
    >
      {children}
      {items}
    </select>
  )
}

export function SelectContent({
  children,
}: {
  children: ReactNode
  className?: string
}) {
  const { setItems } = useContext(ItemsContext)

  // Collect option elements from children and push them into the shared
  // items list so SelectTrigger can render them inside the <select>.
  useEffect(() => {
    const options: React.ReactElement[] = []
    React.Children.forEach(children, (child) => {
      if (React.isValidElement(child)) {
        options.push(child)
      }
    })
    setItems(options)
    return () => setItems([])
  }, [children, setItems])

  // Don't render anything here – the options are rendered by SelectTrigger
  return null
}

export function SelectItem({
  value,
  children,
}: {
  value: string
  children: ReactNode
  className?: string
}) {
  return <option value={value}>{children}</option>
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

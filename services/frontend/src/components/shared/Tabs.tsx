'use client'

import { useHydration } from '@/contexts/HydrationContext'
import clsx from 'clsx'
import {
  ButtonHTMLAttributes,
  HTMLAttributes,
  KeyboardEvent,
  ReactNode,
  createContext,
  useContext,
  useId,
  useState,
} from 'react'

/**
 * Tabs following the WAI-ARIA tabs pattern: the list is a `tablist`, each
 * trigger a `tab` with `aria-selected`, each content a `tabpanel` labelled
 * by its tab. The arrow keys, Home and End move between the tabs of a list
 * and select the one they land on.
 */

interface TabsContextType {
  activeTab: string
  setActiveTab: (tab: string) => void
  baseId: string
}

/** A DOM id fragment for a tab value (values may hold any character). */
function idPart(value: string): string {
  return value.replace(/[^A-Za-z0-9_-]/g, '_')
}

function tabId(baseId: string, value: string): string {
  return `${baseId}-tab-${idPart(value)}`
}

function panelId(baseId: string, value: string): string {
  return `${baseId}-panel-${idPart(value)}`
}

const TabsContext = createContext<TabsContextType | null>(null)

interface TabsProps extends Omit<
  HTMLAttributes<HTMLDivElement>,
  'defaultValue' | 'children' | 'className'
> {
  defaultValue: string
  /** Controlled mode: when set, the active tab is owned by the parent. */
  value?: string
  /** Fires on every trigger click (controlled and uncontrolled mode). */
  onValueChange?: (value: string) => void
  children: ReactNode
  className?: string
}

interface TabsListProps extends Omit<
  HTMLAttributes<HTMLDivElement>,
  'children' | 'className' | 'role'
> {
  children: ReactNode
  className?: string
}

interface TabsTriggerProps extends Omit<
  ButtonHTMLAttributes<HTMLButtonElement>,
  'onClick' | 'value' | 'children' | 'className' | 'type'
> {
  value: string
  children: ReactNode
  className?: string
}

interface TabsContentProps extends Omit<
  HTMLAttributes<HTMLDivElement>,
  'children' | 'className'
> {
  value: string
  children: ReactNode
  className?: string
  forceMount?: boolean
}

export function Tabs({
  defaultValue,
  value,
  onValueChange,
  children,
  className,
  ...rest
}: TabsProps) {
  const [internalTab, setInternalTab] = useState<string>(value ?? defaultValue)
  // Once the user picks a tab themselves, a changed defaultValue must not
  // yank them away from it (uncontrolled mode only).
  const [userSelected, setUserSelected] = useState(false)
  const mounted = useHydration()
  const baseId = useId()
  const isControlled = value !== undefined

  // Uncontrolled mode: re-sync with a changed defaultValue only while the
  // user has not yet clicked a tab (render-phase state adjustment, see
  // react.dev "adjusting state when a prop changes").
  const [prevDefault, setPrevDefault] = useState(defaultValue)
  if (prevDefault !== defaultValue) {
    setPrevDefault(defaultValue)
    if (!isControlled && !userSelected) {
      setInternalTab(defaultValue)
    }
  }

  const activeTab = isControlled ? value : internalTab
  const setActiveTab = (tab: string) => {
    setUserSelected(true)
    if (!isControlled) setInternalTab(tab)
    onValueChange?.(tab)
  }

  return (
    <TabsContext.Provider
      value={{
        activeTab: mounted || isControlled ? activeTab : defaultValue,
        setActiveTab,
        baseId,
      }}
    >
      <div className={className} {...rest}>
        {children}
      </div>
    </TabsContext.Provider>
  )
}

export function TabsList({
  children,
  className,
  onKeyDown,
  ...rest
}: TabsListProps) {
  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    onKeyDown?.(event)
    if (event.defaultPrevented) return
    const tabs = Array.from(
      event.currentTarget.querySelectorAll<HTMLButtonElement>(
        '[role="tab"]:not([disabled])',
      ),
    )
    const current = tabs.indexOf(event.target as HTMLButtonElement)
    if (current < 0) return
    let next: number
    switch (event.key) {
      case 'ArrowRight':
        next = (current + 1) % tabs.length
        break
      case 'ArrowLeft':
        next = (current - 1 + tabs.length) % tabs.length
        break
      case 'Home':
        next = 0
        break
      case 'End':
        next = tabs.length - 1
        break
      default:
        return
    }
    event.preventDefault()
    tabs[next].focus()
    tabs[next].click()
  }

  return (
    <div
      role="tablist"
      onKeyDown={handleKeyDown}
      {...rest}
      className={clsx(
        'inline-flex items-center justify-center gap-0.5 rounded-full bg-zinc-100 p-0.5 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400',
        className,
      )}
    >
      {children}
    </div>
  )
}

export function TabsTrigger({
  value,
  children,
  className,
  ...rest
}: TabsTriggerProps) {
  const context = useContext(TabsContext)

  // During SSR or initial render, context might not be available yet
  // Return a non-interactive version that won't throw an error
  if (!context) {
    return (
      <button
        type="button"
        role="tab"
        aria-selected={false}
        disabled
        className={clsx(
          'inline-flex h-7 items-center justify-center rounded-full px-3 text-sm font-medium whitespace-nowrap transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 disabled:pointer-events-none disabled:opacity-50',
          'text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white',
          className,
        )}
        {...rest}
      >
        {children}
      </button>
    )
  }

  const { activeTab, setActiveTab, baseId } = context
  const isActive = activeTab === value

  return (
    <button
      type="button"
      role="tab"
      id={tabId(baseId, value)}
      aria-selected={isActive}
      onClick={() => setActiveTab(value)}
      className={clsx(
        'inline-flex h-7 items-center justify-center rounded-full px-3 text-sm font-medium whitespace-nowrap transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 disabled:pointer-events-none disabled:opacity-50',
        isActive
          ? 'bg-white text-zinc-900 shadow-sm dark:bg-zinc-700 dark:text-white'
          : 'text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white',
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  )
}

export function TabsContent({
  value,
  children,
  className,
  forceMount,
  ...rest
}: TabsContentProps) {
  const context = useContext(TabsContext)

  // During SSR or initial render, context might not be available yet
  // Return null to avoid errors
  if (!context) {
    return null
  }

  const { activeTab, baseId } = context
  const isActive = activeTab === value
  const panelProps = {
    role: 'tabpanel' as const,
    id: panelId(baseId, value),
    'aria-labelledby': tabId(baseId, value),
  }

  // If not force mounting and not active, don't render
  if (!forceMount && !isActive) return null

  // If force mounting, always render but control visibility
  if (forceMount) {
    return (
      <div
        className={clsx(
          'mt-2 ring-offset-white focus-visible:ring-2 focus-visible:ring-emerald-400 focus-visible:ring-offset-2 focus-visible:outline-none',
          className,
        )}
        style={{ display: isActive ? 'block' : 'none' }}
        {...panelProps}
        {...rest}
      >
        {children}
      </div>
    )
  }

  // Normal behavior - only render when active
  return (
    <div
      className={clsx(
        'mt-2 ring-offset-white focus-visible:ring-2 focus-visible:ring-emerald-400 focus-visible:ring-offset-2 focus-visible:outline-none',
        className,
      )}
      {...panelProps}
      {...rest}
    >
      {children}
    </div>
  )
}

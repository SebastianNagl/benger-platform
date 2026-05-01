'use client'

import clsx from 'clsx'
import { useHydration } from '@/contexts/HydrationContext'
import {
  ButtonHTMLAttributes,
  HTMLAttributes,
  ReactNode,
  createContext,
  useContext,
  useEffect,
  useState,
} from 'react'

interface TabsContextType {
  activeTab: string
  setActiveTab: (tab: string) => void
}

const TabsContext = createContext<TabsContextType | null>(null)

interface TabsProps {
  defaultValue: string
  children: ReactNode
  className?: string
}

interface TabsListProps {
  children: ReactNode
  className?: string
}

interface TabsTriggerProps
  extends Omit<
    ButtonHTMLAttributes<HTMLButtonElement>,
    'onClick' | 'value' | 'children' | 'className' | 'type'
  > {
  value: string
  children: ReactNode
  className?: string
}

interface TabsContentProps
  extends Omit<HTMLAttributes<HTMLDivElement>, 'children' | 'className'> {
  value: string
  children: ReactNode
  className?: string
  forceMount?: boolean
}

export function Tabs({ defaultValue, children, className }: TabsProps) {
  const [activeTab, setActiveTab] = useState<string>(defaultValue)
  const mounted = useHydration()

  // Sync activeTab with defaultValue when it changes externally
  useEffect(() => {
     
    setActiveTab(defaultValue)
  }, [defaultValue])

  return (
    <TabsContext.Provider
      value={{ activeTab: mounted ? activeTab : defaultValue, setActiveTab }}
    >
      <div className={className}>{children}</div>
    </TabsContext.Provider>
  )
}

export function TabsList({ children, className }: TabsListProps) {
  return (
    <div
      className={clsx(
        'inline-flex h-10 items-center justify-center rounded-md bg-zinc-100 p-1 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400',
        className
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
        disabled
        className={clsx(
          'inline-flex items-center justify-center whitespace-nowrap rounded-sm px-3 py-1.5 text-sm font-medium ring-offset-white transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400 focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50',
          'hover:bg-zinc-200 hover:text-zinc-900 dark:hover:bg-zinc-700 dark:hover:text-white',
          className
        )}
        {...rest}
      >
        {children}
      </button>
    )
  }

  const { activeTab, setActiveTab } = context
  const isActive = activeTab === value

  return (
    <button
      type="button"
      onClick={() => setActiveTab(value)}
      className={clsx(
        'inline-flex items-center justify-center whitespace-nowrap rounded-sm px-3 py-1.5 text-sm font-medium ring-offset-white transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400 focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50',
        isActive
          ? 'bg-white text-zinc-900 shadow-sm dark:bg-zinc-700 dark:text-white'
          : 'hover:bg-zinc-200 hover:text-zinc-900 dark:hover:bg-zinc-700 dark:hover:text-white',
        className
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

  const { activeTab } = context
  const isActive = activeTab === value

  // If not force mounting and not active, don't render
  if (!forceMount && !isActive) return null

  // If force mounting, always render but control visibility
  if (forceMount) {
    return (
      <div
        className={clsx(
          'mt-2 ring-offset-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400 focus-visible:ring-offset-2',
          className
        )}
        style={{ display: isActive ? 'block' : 'none' }}
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
        'mt-2 ring-offset-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400 focus-visible:ring-offset-2',
        className
      )}
      {...rest}
    >
      {children}
    </div>
  )
}

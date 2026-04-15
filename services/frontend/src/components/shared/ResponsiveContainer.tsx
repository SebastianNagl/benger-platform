import { useUIStore } from '@/stores'
import clsx from 'clsx'

interface ResponsiveContainerProps {
  children: React.ReactNode
  className?: string
  size?: 'sm' | 'md' | 'lg' | 'xl' | 'full'
  adaptToSidebar?: boolean
}

export function ResponsiveContainer({
  children,
  className,
  size = 'lg',
  adaptToSidebar = true,
}: ResponsiveContainerProps) {
  const { isSidebarHidden } = useUIStore()

  const getSizeClasses = () => {
    // For full size, always return no max-width constraint
    if (size === 'full') {
      return ''
    }

    if (adaptToSidebar) {
      if (isSidebarHidden) {
        // More generous widths when sidebar is collapsed
        switch (size) {
          case 'sm':
            return 'max-w-3xl 3xl:max-w-5xl 4xl:max-w-6xl 5xl:max-w-7xl'
          case 'md':
            return 'max-w-5xl 3xl:max-w-6xl 4xl:max-w-7xl 5xl:max-w-8xl'
          case 'lg':
            return 'max-w-6xl 3xl:max-w-7xl 4xl:max-w-8xl 5xl:max-w-9xl'
          case 'xl':
            return 'max-w-7xl 3xl:max-w-8xl 4xl:max-w-9xl 5xl:max-w-none'
        }
      } else {
        // Standard widths when sidebar is expanded
        switch (size) {
          case 'sm':
            return 'max-w-2xl 3xl:max-w-3xl 4xl:max-w-4xl 5xl:max-w-5xl'
          case 'md':
            return 'max-w-3xl 3xl:max-w-4xl 4xl:max-w-5xl 5xl:max-w-6xl'
          case 'lg':
            return 'max-w-4xl 3xl:max-w-5xl 4xl:max-w-6xl 5xl:max-w-7xl'
          case 'xl':
            return 'max-w-5xl 3xl:max-w-6xl 4xl:max-w-7xl 5xl:max-w-8xl'
        }
      }
    } else {
      // Non-adaptive sizes
      switch (size) {
        case 'sm':
          return 'max-w-2xl 3xl:max-w-3xl 4xl:max-w-4xl 5xl:max-w-5xl'
        case 'md':
          return 'max-w-3xl 3xl:max-w-4xl 4xl:max-w-5xl 5xl:max-w-6xl'
        case 'lg':
          return 'max-w-4xl 3xl:max-w-5xl 4xl:max-w-6xl 5xl:max-w-7xl'
        case 'xl':
          return 'max-w-5xl 3xl:max-w-6xl 4xl:max-w-7xl 5xl:max-w-8xl'
      }
    }
  }

  const getPaddingClasses = () => {
    if (size === 'full') {
      return ''
    }
    return 'px-4 sm:px-6 3xl:px-8 4xl:px-10 5xl:px-12'
  }

  return (
    <div
      className={clsx(
        size !== 'full' && 'mx-auto',
        'transition-all duration-300',
        getSizeClasses(),
        getPaddingClasses(),
        className
      )}
    >
      {children}
    </div>
  )
}

// Legacy compatibility - maintains the old responsive pattern
export function LegacyContainer({
  children,
  className,
}: {
  children: React.ReactNode
  className?: string
}) {
  return (
    <div
      className={clsx(
        'mx-auto max-w-2xl pb-10 pt-16 lg:mx-[calc(50%-min(50%,theme(container.lg)))] lg:max-w-3xl 3xl:max-w-4xl 4xl:max-w-5xl 5xl:max-w-6xl',
        className
      )}
    >
      {children}
    </div>
  )
}

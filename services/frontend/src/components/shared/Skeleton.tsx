/**
 * Skeleton Component
 *
 * Loading placeholder with shimmer animation
 */

import { cn } from '@/lib/utils'

interface SkeletonProps {
  className?: string
  variant?: 'text' | 'circular' | 'rectangular'
}

export function Skeleton({
  className,
  variant = 'rectangular',
}: SkeletonProps) {
  return (
    <div
      className={cn(
        'animate-pulse bg-zinc-200 dark:bg-zinc-700',
        {
          'rounded-md': variant === 'rectangular',
          'rounded-full': variant === 'circular',
          'h-4 w-full rounded': variant === 'text',
        },
        className
      )}
    />
  )
}

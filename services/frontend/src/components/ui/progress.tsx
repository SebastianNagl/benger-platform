import { cn } from '@/lib/utils'
import React from 'react'

interface ProgressProps extends React.HTMLAttributes<HTMLDivElement> {
  value?: number
  max?: number
}

export function Progress({
  className,
  value = 0,
  max = 100,
  ...props
}: ProgressProps) {
  const percentage = Math.min(Math.max((value / max) * 100, 0), 100)

  return (
    <div
      className={cn(
        'relative h-4 w-full overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800',
        className
      )}
      {...props}
    >
      <div
        className="h-full w-full flex-1 bg-emerald-600 transition-all dark:bg-emerald-500"
        style={{ transform: `translateX(-${100 - percentage}%)` }}
      />
    </div>
  )
}

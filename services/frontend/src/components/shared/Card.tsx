import clsx from 'clsx'
import { HTMLAttributes, ReactNode } from 'react'

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode
  className?: string
  onClick?: () => void
}

export function Card({ children, className, onClick, ...props }: CardProps) {
  return (
    <div
      className={clsx(
        'rounded-lg border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-900',
        className
      )}
      onClick={onClick}
      {...props}
    >
      {children}
    </div>
  )
}

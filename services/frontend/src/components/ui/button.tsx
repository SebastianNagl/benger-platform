import { cn } from '@/lib/utils'
import React from 'react'

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'default' | 'outline' | 'ghost' | 'destructive'
  size?: 'default' | 'sm' | 'lg'
  as?: 'button' | 'span'
  loading?: boolean
}

export function Button({
  className,
  variant = 'default',
  size = 'default',
  as = 'button',
  loading = false,
  children,
  disabled,
  ...props
}: ButtonProps) {
  const baseStyles =
    'inline-flex items-center justify-center font-medium rounded-md transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 disabled:opacity-50 disabled:pointer-events-none'

  const variants = {
    default:
      'bg-emerald-600 text-white hover:bg-emerald-700 focus:ring-emerald-500',
    outline:
      'border border-zinc-300 bg-transparent hover:bg-zinc-100 dark:border-zinc-600 dark:hover:bg-zinc-800',
    ghost: 'hover:bg-zinc-100 dark:hover:bg-zinc-800',
    destructive: 'bg-red-600 text-white hover:bg-red-700 focus:ring-red-500',
  }

  const sizes = {
    default: 'px-4 py-2 text-sm',
    sm: 'px-3 py-1.5 text-xs',
    lg: 'px-6 py-3 text-base',
  }

  const Component = as as any

  return (
    <Component
      className={cn(
        baseStyles,
        variants[variant],
        sizes[size],
        loading && 'cursor-wait',
        className
      )}
      disabled={disabled || loading}
      {...props}
    >
      {loading ? (
        <span className="flex items-center gap-2">
          <svg
            className="h-4 w-4 animate-spin"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            ></circle>
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
            ></path>
          </svg>
          {children}
        </span>
      ) : (
        children
      )}
    </Component>
  )
}

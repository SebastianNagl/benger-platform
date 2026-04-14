'use client'

import { useI18n } from '@/contexts/I18nContext'
import { MagnifyingGlassIcon } from '@heroicons/react/24/outline'
import clsx from 'clsx'
import { forwardRef } from 'react'

interface SearchInputProps
  extends Omit<
    React.InputHTMLAttributes<HTMLInputElement>,
    'onChange' | 'type'
  > {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  className?: string
  loading?: boolean
  showIcon?: boolean
  iconPosition?: 'left' | 'right'
}

export const SearchInput = forwardRef<HTMLInputElement, SearchInputProps>(
  (
    {
      value,
      onChange,
      placeholder,
      className,
      loading = false,
      showIcon = true,
      iconPosition = 'left',
      ...props
    },
    ref
  ) => {
    const { t } = useI18n()
    const displayPlaceholder = placeholder ?? t('common.search')

    const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
      onChange(e.target.value)
    }

    return (
      <div className={clsx('relative', className)}>
        {showIcon && iconPosition === 'left' && (
          <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3">
            <MagnifyingGlassIcon
              className={clsx(
                'h-5 w-5',
                loading
                  ? 'text-zinc-300 dark:text-zinc-600'
                  : 'text-zinc-400 dark:text-zinc-500'
              )}
            />
          </div>
        )}

        <input
          ref={ref}
          type="search"
          value={value}
          onChange={handleChange}
          placeholder={displayPlaceholder}
          className={clsx(
            // Base styles matching navigation search
            'block w-full rounded-full',
            'bg-white dark:bg-white/5',
            'text-sm text-zinc-900 dark:text-zinc-100',
            'placeholder-zinc-500 dark:placeholder-zinc-400',
            'ring-1 ring-zinc-900/10 dark:ring-inset dark:ring-white/10',
            // Padding based on icon position
            showIcon && iconPosition === 'left' ? 'pl-10 pr-3' : 'px-3',
            showIcon && iconPosition === 'right' ? 'pl-3 pr-10' : '',
            // Height matching navigation
            'h-8 py-2',
            // Focus and hover states matching navigation
            'transition',
            'hover:ring-zinc-900/20 dark:hover:ring-white/20',
            'focus:outline-none focus:ring-2 focus:ring-emerald-500 dark:focus:ring-emerald-400',
            // Disabled state
            'disabled:cursor-not-allowed disabled:opacity-50',
            // Remove default search input styling
            '[&::-webkit-search-cancel-button]:hidden',
            '[&::-webkit-search-decoration]:hidden',
            '[&::-webkit-search-results-button]:hidden',
            '[&::-webkit-search-results-decoration]:hidden'
          )}
          {...props}
        />

        {showIcon && iconPosition === 'right' && (
          <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-3">
            <MagnifyingGlassIcon
              className={clsx(
                'h-5 w-5',
                loading
                  ? 'text-zinc-300 dark:text-zinc-600'
                  : 'text-zinc-400 dark:text-zinc-500'
              )}
            />
          </div>
        )}

        {loading && (
          <div className="absolute inset-y-0 right-3 flex items-center">
            <svg
              className="h-4 w-4 animate-spin text-zinc-400 dark:text-zinc-500"
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
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
              />
            </svg>
          </div>
        )}
      </div>
    )
  }
)

SearchInput.displayName = 'SearchInput'

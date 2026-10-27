import clsx from 'clsx'
import { TextareaHTMLAttributes, forwardRef } from 'react'

interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  className?: string
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, ...props }, ref) => {
    return (
      <textarea
        ref={ref}
        className={clsx(
          // Same field style as Input; rounded corners instead of a pill.
          'rounded-2xl px-4 py-2',
          'block w-full bg-white text-base text-zinc-900 ring-1 ring-zinc-900/10 transition placeholder:text-zinc-500 hover:ring-zinc-900/20 focus:ring-2 focus:ring-emerald-500 focus:outline-none sm:text-sm dark:bg-white/5 dark:text-white dark:ring-white/10 dark:ring-inset dark:placeholder:text-zinc-400 dark:hover:ring-white/20 dark:focus:ring-emerald-400',
          'disabled:cursor-not-allowed disabled:bg-zinc-50 disabled:text-zinc-500 disabled:hover:ring-zinc-900/10 dark:disabled:bg-white/2.5',
          'resize-vertical',
          className,
        )}
        {...props}
      />
    )
  },
)

Textarea.displayName = 'Textarea'

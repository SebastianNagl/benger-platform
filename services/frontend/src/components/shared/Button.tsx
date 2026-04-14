import clsx from 'clsx'
import Link from 'next/link'

function ArrowIcon(props: React.ComponentPropsWithoutRef<'svg'>) {
  return (
    <svg viewBox="0 0 20 20" fill="none" aria-hidden="true" {...props}>
      <path
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        d="m11.5 6.5 3 3.5m0 0-3 3.5m3-3.5h-9"
      />
    </svg>
  )
}

const variantStyles = {
  primary:
    'rounded-full bg-zinc-900 py-1.5 px-3 text-white hover:bg-zinc-700 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-zinc-900 dark:bg-emerald-400/10 dark:text-emerald-400 dark:ring-1 dark:ring-inset dark:ring-emerald-400/20 dark:hover:bg-emerald-400/10 dark:hover:text-emerald-300 dark:hover:ring-emerald-300 dark:disabled:hover:bg-emerald-400/10 dark:disabled:hover:text-emerald-400',
  secondary:
    'rounded-full bg-zinc-100 py-1.5 px-3 text-zinc-900 hover:bg-zinc-200 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-zinc-100 dark:bg-zinc-800/40 dark:text-zinc-400 dark:ring-1 dark:ring-inset dark:ring-zinc-800 dark:hover:bg-zinc-800 dark:hover:text-zinc-300 dark:disabled:hover:bg-zinc-800/40 dark:disabled:hover:text-zinc-400',
  filled:
    'rounded-full bg-zinc-900 py-1.5 px-3 text-white hover:bg-zinc-700 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-zinc-900 dark:bg-emerald-500 dark:text-white dark:hover:bg-emerald-400 dark:disabled:hover:bg-emerald-500',
  outline:
    'rounded-full py-1.5 px-3 text-zinc-700 ring-1 ring-inset ring-zinc-900/10 hover:bg-zinc-900/2.5 hover:text-zinc-900 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-transparent dark:text-zinc-400 dark:ring-white/10 dark:hover:bg-white/5 dark:hover:text-white dark:disabled:hover:bg-transparent dark:disabled:hover:text-zinc-400',
  text: 'text-emerald-500 hover:text-emerald-600 disabled:opacity-50 disabled:cursor-not-allowed dark:text-emerald-400 dark:hover:text-emerald-500',
}

type ButtonProps = {
  variant?: keyof typeof variantStyles
  arrow?: 'left' | 'right'
  size?: string
} & (
  | React.ComponentPropsWithoutRef<typeof Link>
  | (React.ComponentPropsWithoutRef<'button'> & { href?: undefined })
)

export function Button({
  variant = 'primary',
  className,
  children,
  arrow,
  ...props
}: ButtonProps) {
  // Check if className contains a custom gap class
  const hasCustomGap = className && /gap-\d+/.test(className)

  className = clsx(
    'inline-flex items-center justify-center overflow-hidden text-sm font-medium transition leading-tight',
    !hasCustomGap && 'gap-2', // Only add default gap if no custom gap is provided
    variantStyles[variant],
    className
  )

  let arrowIcon = (
    <ArrowIcon
      className={clsx(
        'mt-0.5 h-5 w-5',
        variant === 'text' && 'relative top-px',
        arrow === 'left' && '-ml-1 rotate-180',
        arrow === 'right' && '-mr-1'
      )}
    />
  )

  let inner = (
    <>
      {arrow === 'left' && arrowIcon}
      {children}
      {arrow === 'right' && arrowIcon}
    </>
  )

  if (typeof props.href === 'undefined') {
    // Handle as button
    const { href, ...buttonProps } =
      props as React.ComponentPropsWithoutRef<'button'> & { href?: undefined }
    return (
      <button type="button" className={className} {...buttonProps}>
        {inner}
      </button>
    )
  }

  // Handle as Link
  const linkProps = props as React.ComponentPropsWithoutRef<typeof Link>

  // If disabled, render as a button without href to prevent navigation
  if ('disabled' in linkProps && linkProps.disabled) {
    const { href, disabled, ...buttonProps } = linkProps as any
    return (
      <button className={className} disabled={disabled} {...buttonProps}>
        {inner}
      </button>
    )
  }

  return (
    <Link className={className} {...linkProps}>
      {inner}
    </Link>
  )
}

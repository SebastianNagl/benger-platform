import clsx from 'clsx'

interface SeparatorProps {
  className?: string
  orientation?: 'horizontal' | 'vertical'
}

export function Separator({
  className,
  orientation = 'horizontal',
}: SeparatorProps) {
  return (
    <div
      className={clsx(
        'bg-zinc-200 dark:bg-zinc-700',
        orientation === 'horizontal' ? 'h-px w-full' : 'h-full w-px',
        className,
      )}
    />
  )
}

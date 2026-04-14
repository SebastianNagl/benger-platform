interface LogoProps extends React.ComponentPropsWithoutRef<'div'> {
  subtitle?: string
}

export function Logo({ subtitle, ...props }: LogoProps) {
  return (
    <div
      {...props}
      className={`flex items-center gap-2 text-lg font-bold text-zinc-900 dark:text-white ${props.className || ''}`}
    >
      <span className="text-xl">🤘</span>
      <span className="whitespace-nowrap">
        BenGER{subtitle && <span className="hidden sm:inline"> - {subtitle}</span>}
      </span>
    </div>
  )
}

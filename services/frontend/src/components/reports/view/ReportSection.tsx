import { Card } from '@/components/shared/Card'
import type { ReactNode } from 'react'

interface ReportSectionProps {
  title: string
  children: ReactNode
  /** Optional element rendered right of the title (e.g. a selector). */
  aside?: ReactNode
  id?: string
}

/** A titled card, the building block of every report section. */
export function ReportSection({ title, children, aside, id }: ReportSectionProps) {
  return (
    <Card className="p-6" id={id} data-testid={id ? `section-${id}` : undefined}>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-semibold text-zinc-900 dark:text-white">{title}</h2>
        {aside}
      </div>
      {children}
    </Card>
  )
}

/** Muted paragraph used for section prose. */
export function Prose({ children }: { children: ReactNode }) {
  return (
    <p className="whitespace-pre-line text-sm leading-6 text-zinc-700 dark:text-zinc-300">
      {children}
    </p>
  )
}

/** Sub-heading inside a section. */
export function SubHeading({ children }: { children: ReactNode }) {
  return (
    <h3 className="mb-3 text-base font-semibold text-zinc-900 dark:text-white">{children}</h3>
  )
}

/** Quiet inline note for empty states. */
export function QuietNote({ children }: { children: ReactNode }) {
  return (
    <p className="rounded-md border border-dashed border-zinc-200 px-4 py-3 text-sm text-zinc-500 dark:border-zinc-700 dark:text-zinc-400">
      {children}
    </p>
  )
}

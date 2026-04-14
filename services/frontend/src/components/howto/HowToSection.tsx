'use client'

import { useSectionStore } from '@/components/layout/SectionProvider'
import { useEffect, useRef } from 'react'

interface HowToSectionProps {
  title: string
  children: React.ReactNode
  id?: string
  level?: 'h2' | 'h3'
}

export function HowToSection({
  title,
  children,
  id,
  level = 'h2',
}: HowToSectionProps) {
  const headingRef = useRef<HTMLHeadingElement>(null)
  const registerHeading = useSectionStore((s) => s.registerHeading)

  const headingClasses = {
    h2: 'text-3xl font-bold tracking-tight text-zinc-900 dark:text-white',
    h3: 'text-2xl font-semibold tracking-tight text-zinc-900 dark:text-white',
  }

  useEffect(() => {
    if (id && headingRef.current) {
      registerHeading({
        id,
        ref: headingRef,
        offsetRem: 8,
      })
    }
  }, [id, registerHeading])

  return (
    <section id={id} className="scroll-mt-24">
      {level === 'h2' ? (
        <h2 ref={headingRef} className={headingClasses[level]}>
          {title}
        </h2>
      ) : (
        <h3 ref={headingRef} className={headingClasses[level]}>
          {title}
        </h3>
      )}

      <div className="mt-6 text-base text-zinc-600 dark:text-zinc-400">
        {children}
      </div>
    </section>
  )
}

'use client'

import { Footer } from '@/components/layout/Footer'
import { SiteHeader } from '@/components/layout/SiteHeader'
import {
  SectionProvider,
  type Section,
} from '@/components/layout/SectionProvider'

interface MinimalLayoutProps {
  children: React.ReactNode
  sections?: Array<Section>
  /**
   * Wrap the content in typography (`prose`) styles. On by default for the
   * MDX legal pages; app pages that bring their own components (public
   * reports) pass `false` so headings, tables and charts keep their app
   * spacing and can use the wider column.
   */
  prose?: boolean
}

export function MinimalLayout({ children, sections = [], prose = true }: MinimalLayoutProps) {
  return (
    <SectionProvider sections={sections}>
      <div className="flex min-h-screen w-full flex-col bg-white dark:bg-zinc-900">
        <SiteHeader />
        <main
          className={
            prose
              ? 'mx-auto w-full max-w-4xl flex-1 px-4 py-8 sm:px-6 lg:px-8'
              : 'mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6 lg:px-8'
          }
        >
          {prose ? (
            <div className="prose prose-zinc max-w-none dark:prose-invert">
              {children}
            </div>
          ) : (
            children
          )}
        </main>
        <Footer />
      </div>
    </SectionProvider>
  )
}

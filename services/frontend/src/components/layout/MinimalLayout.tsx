'use client'

import { SiteFooter } from '@/components/layout/SiteFooter'
import { SiteHeader } from '@/components/layout/SiteHeader'
import {
  SectionProvider,
  type Section,
} from '@/components/layout/SectionProvider'

interface MinimalLayoutProps {
  children: React.ReactNode
  sections?: Array<Section>
}

export function MinimalLayout({ children, sections = [] }: MinimalLayoutProps) {
  return (
    <SectionProvider sections={sections}>
      <div className="min-h-screen w-full bg-white dark:bg-zinc-900">
        <SiteHeader />
        <main className="mx-auto max-w-4xl px-4 py-8 sm:px-6 lg:px-8">
          <div className="prose prose-zinc max-w-none dark:prose-invert">
            {children}
          </div>
        </main>
        <SiteFooter />
      </div>
    </SectionProvider>
  )
}

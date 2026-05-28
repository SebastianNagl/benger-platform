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
}

export function MinimalLayout({ children, sections = [] }: MinimalLayoutProps) {
  return (
    <SectionProvider sections={sections}>
      <div className="flex min-h-screen w-full flex-col bg-white dark:bg-zinc-900">
        <SiteHeader />
        <main className="mx-auto w-full max-w-4xl flex-1 px-4 py-8 sm:px-6 lg:px-8">
          <div className="prose prose-zinc max-w-none dark:prose-invert">
            {children}
          </div>
        </main>
        <Footer />
      </div>
    </SectionProvider>
  )
}

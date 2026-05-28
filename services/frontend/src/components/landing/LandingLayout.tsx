'use client'

import { Footer } from '@/components/layout/Footer'
import { SiteHeader } from '@/components/layout/SiteHeader'
import { ReactNode } from 'react'

interface LandingLayoutProps {
  children: ReactNode
}

export function LandingLayout({ children }: LandingLayoutProps) {
  return (
    <div className="flex min-h-screen w-full flex-col bg-white dark:bg-zinc-900">
      <SiteHeader />
      <main className="flex-1">{children}</main>
      <Footer />
    </div>
  )
}

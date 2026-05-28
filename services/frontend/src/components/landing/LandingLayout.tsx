'use client'

import { SiteFooter } from '@/components/layout/SiteFooter'
import { SiteHeader } from '@/components/layout/SiteHeader'
import { ReactNode } from 'react'

interface LandingLayoutProps {
  children: ReactNode
}

export function LandingLayout({ children }: LandingLayoutProps) {
  return (
    <div className="min-h-screen w-full bg-white dark:bg-zinc-900">
      <SiteHeader />
      <main>{children}</main>
      <SiteFooter />
    </div>
  )
}

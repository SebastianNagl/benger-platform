'use client'

import { LanguageSwitcher } from '@/components/layout/LanguageSwitcher'
import { Logo } from '@/components/layout/Logo'
import { ThemeToggle } from '@/components/layout/ThemeToggle'
import { useI18n } from '@/contexts/I18nContext'
import clsx from 'clsx'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useEffect, useState, type MouseEvent } from 'react'

const NAV_SECTIONS = [
  { id: 'information', key: 'landing.nav.information' },
  { id: 'news', key: 'landing.nav.news' },
  { id: 'people', key: 'landing.nav.people' },
  { id: 'license', key: 'landing.nav.license' },
] as const

export function SiteHeader() {
  const { t } = useI18n()
  const pathname = usePathname()
  const isHome = pathname === '/'
  const [activeSection, setActiveSection] = useState<string>('')

  useEffect(() => {
    if (!isHome) {
      setActiveSection('')
      return
    }
    const visibleSections = new Set<string>()
    const sectionIds = NAV_SECTIONS.map((s) => s.id)
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) visibleSections.add(entry.target.id)
          else visibleSections.delete(entry.target.id)
        }
        setActiveSection(
          sectionIds.find((id) => visibleSections.has(id)) || ''
        )
      },
      { threshold: 0.3 }
    )
    sectionIds.forEach((id) => {
      const el = document.getElementById(id)
      if (el) observer.observe(el)
    })
    return () => observer.disconnect()
  }, [isHome])

  const handleSectionClick =
    (id: string) => (e: MouseEvent<HTMLAnchorElement>) => {
      if (!isHome) return
      e.preventDefault()
      document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' })
      window.history.replaceState(null, '', `/#${id}`)
    }

  return (
    <header className="sticky top-0 z-50 flex h-14 items-center justify-between border-b border-zinc-900/10 bg-white pl-1 pr-4 sm:px-6 lg:px-8 dark:border-white/10 dark:bg-zinc-900">
      <div className="flex items-center gap-3">
        <Link href="/" className="flex items-center">
          <span className="sr-only">BenGER</span>
          <Logo className="h-6" />
        </Link>

        <div className="flex gap-1 lg:ml-16">
          {NAV_SECTIONS.map(({ id, key }) => (
            <Link
              key={id}
              href={`/#${id}`}
              onClick={handleSectionClick(id)}
              className={clsx(
                'whitespace-nowrap rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
                isHome && activeSection === id
                  ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-400'
                  : 'text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-white'
              )}
            >
              {t(key)}
            </Link>
          ))}
        </div>
      </div>

      <div className="flex items-center gap-5">
        <div className="flex gap-4">
          <LanguageSwitcher />
          <ThemeToggle />
        </div>
        <Link
          href="/login"
          className="inline-flex items-center justify-center overflow-hidden rounded-full px-4 py-1.5 text-sm font-medium text-zinc-700 ring-1 ring-inset ring-zinc-900/10 transition hover:text-zinc-900 dark:text-zinc-400 dark:ring-white/10 dark:hover:bg-white/5 dark:hover:text-white"
        >
          {t('landing.nav.login')}
        </Link>
      </div>
    </header>
  )
}

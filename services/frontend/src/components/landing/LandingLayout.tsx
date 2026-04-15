'use client'

import { LanguageSwitcher } from '@/components/layout/LanguageSwitcher'
import { Logo } from '@/components/layout/Logo'
import { ThemeToggle } from '@/components/layout/ThemeToggle'
import { useI18n } from '@/contexts/I18nContext'
import clsx from 'clsx'
import Link from 'next/link'
import { ReactNode, useEffect, useRef, useState } from 'react'

interface LandingLayoutProps {
  children: ReactNode
}

const NAV_SECTIONS = [
  { id: 'information', key: 'landing.nav.information' },
  { id: 'news', key: 'landing.nav.news' },
  { id: 'people', key: 'landing.nav.people' },
  { id: 'license', key: 'landing.nav.license' },
] as const

export function LandingLayout({ children }: LandingLayoutProps) {
  const { t } = useI18n()
  const [activeSection, setActiveSection] = useState<string>('')
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const visibleSections = new Set<string>()
    const sectionIds = NAV_SECTIONS.map((s) => s.id)

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            visibleSections.add(entry.target.id)
          } else {
            visibleSections.delete(entry.target.id)
          }
        }
        // Pick the first visible section in DOM order, or clear if none
        const active = sectionIds.find((id) => visibleSections.has(id)) || ''
        setActiveSection(active)
      },
      { threshold: 0.3 }
    )

    sectionIds.forEach((id) => {
      const el = document.getElementById(id)
      if (el) observer.observe(el)
    })

    return () => observer.disconnect()
  }, [])

  const scrollToSection = (id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' })
  }

  return (
    <div ref={scrollRef} className="min-h-screen bg-white dark:bg-zinc-900">
      {/* Sticky Header */}
      <header
        className="sticky top-0 z-50 flex h-14 items-center justify-between border-b border-zinc-900/10 bg-white pl-1 pr-4 sm:px-6 lg:px-8 dark:border-white/10 dark:bg-zinc-900"
      >
        <div className="flex items-center gap-3">
          <Link href="/" className="flex items-center">
            <span className="sr-only">BenGER</span>
            <Logo className="h-6" />
          </Link>

          {/* Section Navigation Tabs */}
          <div className="flex gap-1 lg:ml-16">
            {NAV_SECTIONS.map(({ id, key }) => (
              <button
                key={id}
                onClick={() => scrollToSection(id)}
                className={clsx(
                  'whitespace-nowrap rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
                  activeSection === id
                    ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-400'
                    : 'text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-white'
                )}
              >
                {t(key)}
              </button>
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

      {/* Main Content */}
      <main>
        {children}
      </main>

      {/* Footer */}
      <footer className="border-t border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
        <div className="mx-auto max-w-7xl px-6 py-12 md:flex md:items-center md:justify-between lg:px-8">
          <div className="flex justify-center space-x-6 md:order-2">
            <Link
              href="/about/imprint"
              className="text-zinc-400 hover:text-zinc-500 dark:hover:text-zinc-300"
            >
              <span className="sr-only">{t('footer.imprint')}</span>
              <span className="text-sm">{t('footer.imprint')}</span>
            </Link>
            <Link
              href="/about/data-protection"
              className="text-zinc-400 hover:text-zinc-500 dark:hover:text-zinc-300"
            >
              <span className="sr-only">{t('footer.dataProtection')}</span>
              <span className="text-sm">{t('footer.dataProtection')}</span>
            </Link>
            <a
              href="https://legaltechcolab.com/"
              className="text-zinc-400 hover:text-zinc-500 dark:hover:text-zinc-300"
            >
              <span className="sr-only">{t('footer.followOnNotion')}</span>
              <svg
                className="h-6 w-6"
                fill="currentColor"
                viewBox="0 0 20 20"
                aria-hidden="true"
              >
                <path d="M2 2h16v16H2V2zm4 3v10h1.5V7l5 8h1.5V5H12v8l-5-8H4z" />
              </svg>
            </a>
            <a
              href="https://github.com/SebastianNagl/BenGER"
              className="text-zinc-400 hover:text-zinc-500 dark:hover:text-zinc-300"
            >
              <span className="sr-only">{t('footer.github')}</span>
              <svg
                className="h-6 w-6"
                fill="currentColor"
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <path
                  fillRule="evenodd"
                  d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"
                  clipRule="evenodd"
                />
              </svg>
            </a>
          </div>
          <div className="mt-8 md:order-1 md:mt-0">
            <p className="text-center text-xs leading-5 text-zinc-500 dark:text-zinc-400">
              &copy; {t('footer.copyright')}{' '}
              <a
                href="https://legalplusplus.net"
                className="font-bold hover:text-zinc-900 dark:hover:text-zinc-300"
              >
                pschOrr95
              </a>{' '}
              {new Date().getFullYear()}. {t('footer.allRightsReserved')}
            </p>
          </div>
        </div>
      </footer>
    </div>
  )
}

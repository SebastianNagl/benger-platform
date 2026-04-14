'use client'

import { ThemeToggle } from '@/components/layout'
import { LanguageSwitcher } from '@/components/layout/LanguageSwitcher'
import { useI18n } from '@/contexts/I18nContext'
import {
  SectionProvider,
  type Section,
} from '@/components/layout/SectionProvider'
import Link from 'next/link'

interface MinimalLayoutProps {
  children: React.ReactNode
  sections?: Array<Section>
}

export function MinimalLayout({ children, sections = [] }: MinimalLayoutProps) {
  const { t } = useI18n()

  return (
    <SectionProvider sections={sections}>
      <div className="min-h-screen bg-white dark:bg-zinc-900">
        {/* Header */}
        <header className="relative z-10">
          <nav
            className="mx-auto flex max-w-7xl items-center justify-between p-4 sm:p-6 lg:px-8"
            aria-label={t('layout.minimal.globalNav')}
          >
            <div className="flex lg:flex-1">
              <Link href="/" className="-m-1.5 p-1.5">
                <span className="sr-only">BenGER</span>
                <div className="flex items-center gap-2 text-lg font-bold text-zinc-900 dark:text-white sm:text-xl">
                  <span className="text-xl sm:text-2xl">🤘</span>
                  <span>BenGER</span>
                </div>
              </Link>
            </div>

            {/* Language Switcher and Theme Toggle */}
            <div className="flex items-center gap-2 sm:gap-4">
              <LanguageSwitcher />
              <ThemeToggle />
            </div>
          </nav>
        </header>

        {/* Main Content with proper MDX styling */}
        <main className="mx-auto max-w-4xl px-4 py-8 sm:px-6 lg:px-8">
          <div className="prose prose-zinc max-w-none dark:prose-invert">
            {children}
          </div>
        </main>

        {/* Footer */}
        <footer className="border-t border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
          <div className="mx-auto max-w-7xl px-6 py-12 md:flex md:items-center md:justify-between lg:px-8">
            <div className="flex justify-center space-x-6 md:order-2">
              <Link
                href="/about/imprint"
                className="text-zinc-400 hover:text-zinc-500 dark:hover:text-zinc-300"
              >
                <span className="sr-only">{t('layout.minimal.imprint')}</span>
                <span className="text-sm">{t('layout.minimal.imprint')}</span>
              </Link>
              <Link
                href="/about/data-protection"
                className="text-zinc-400 hover:text-zinc-500 dark:hover:text-zinc-300"
              >
                <span className="sr-only">{t('layout.minimal.dataProtection')}</span>
                <span className="text-sm">{t('layout.minimal.dataProtection')}</span>
              </Link>
              <a
                href="https://legaltechcolab.com/"
                className="text-zinc-400 hover:text-zinc-500 dark:hover:text-zinc-300"
              >
                <span className="sr-only">{t('layout.minimal.followOnNotion')}</span>
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
                <span className="sr-only">GitHub</span>
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
                &copy; Copyright{' '}
                <a
                  href="https://legalplusplus.net"
                  className="font-bold hover:text-zinc-900 dark:hover:text-zinc-300"
                >
                  pschOrr95
                </a>{' '}
                {new Date().getFullYear()}. {t('layout.minimal.allRightsReserved')}
              </p>
            </div>
          </div>
        </footer>
      </div>
    </SectionProvider>
  )
}

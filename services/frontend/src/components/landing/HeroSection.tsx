'use client'

import { HeroPattern } from '@/components/shared'
import { Button } from '@/components/shared/Button'
import { RotatingText } from '@/components/shared/RotatingText'
import { useI18n } from '@/contexts/I18nContext'
import { getSisterHostUrl } from '@/lib/utils/subdomain'
import { useEffect, useState } from 'react'

export function HeroSection() {
  const { t } = useI18n()
  // Students who landed on the benchmarking shell get pointed at Vertretbar.
  // Resolved after mount (host-dependent); null hides the line.
  const [studentSiteUrl, setStudentSiteUrl] = useState<string | null>(null)
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { setStudentSiteUrl(getSisterHostUrl()) }, [])

  return (
    <div className="relative isolate px-4 pt-8 sm:px-6 sm:pt-14 lg:px-8">
      <HeroPattern />

      <div className="mx-auto max-w-5xl py-12 sm:py-16 md:py-24 lg:py-32">
        <div className="text-center">
          {/* German Rotating Headline */}
          <h1 className="text-4xl font-bold tracking-tight text-zinc-900 dark:text-white sm:text-5xl md:text-6xl lg:text-7xl">
            <span className="block">
              {t('landing.heroTitle.prefix')}
            </span>
            <span className="mt-6 block whitespace-nowrap sm:mt-10">
              <RotatingText
                words={t('landing.heroTitle.rotatingWords')}
                className="text-[clamp(3.75rem,8vw,8rem)] text-emerald-600 dark:text-emerald-400"
              />
              <span className="text-[clamp(3.75rem,8vw,8rem)]">
                {t('landing.heroTitle.suffix')}
              </span>
            </span>
          </h1>

          {/* Streamlined Subheading with increased white space */}
          <p className="mx-auto mt-8 max-w-4xl text-lg leading-8 text-zinc-600 dark:text-zinc-400 sm:mt-12 sm:text-xl sm:leading-9 lg:text-2xl lg:leading-10">
            {t('landing.heroSubtitle')}
          </p>

          {/* Single Primary CTA - Significantly increased white space */}
          <div className="mt-12 flex items-center justify-center sm:mt-16">
            <Button
              href="/login"
              className="bg-emerald-600 px-12 py-4 text-xl font-semibold text-white shadow-lg transition-all duration-200 hover:bg-emerald-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-600 sm:px-16 sm:py-5 sm:text-2xl"
            >
              {t('landing.cta.primary')}
            </Button>
          </div>

          {/* Minimal register link with increased spacing */}
          <div className="mt-8 text-center sm:mt-12">
            <p className="text-base text-zinc-600 dark:text-zinc-400 sm:text-lg">
              {t('landing.cta.registerPrompt')}{' '}
              <a
                href="/register"
                className="font-medium text-emerald-600 transition-colors duration-200 hover:text-emerald-500 dark:text-emerald-400 dark:hover:text-emerald-300"
              >
                {t('landing.cta.registerLink')}
              </a>
            </p>
          </div>

          {/* Highlight box: the sister interface for students (Vertretbar).
              Below the CTA block so the primary flow stays untouched. */}
          {studentSiteUrl && (
            <a
              href={studentSiteUrl}
              data-testid="hero-student-site"
              className="group mt-10 flex w-full flex-col items-center gap-2 rounded-2xl border border-emerald-200 bg-emerald-50 px-6 py-5 text-center transition-colors hover:border-emerald-400 hover:bg-emerald-100/70 dark:border-emerald-900 dark:bg-emerald-950/40 dark:hover:border-emerald-700 dark:hover:bg-emerald-950/70 sm:mt-14 sm:flex-row sm:justify-between sm:gap-6 sm:text-left"
            >
              <span className="text-base text-emerald-900 dark:text-emerald-200">
                {t('landing.cta.studentPrompt')}
              </span>
              <span className="shrink-0 text-base font-semibold text-emerald-700 group-hover:text-emerald-600 dark:text-emerald-400 dark:group-hover:text-emerald-300">
                {t('landing.cta.studentLink')} &rarr;
              </span>
            </a>
          )}
        </div>
      </div>
    </div>
  )
}

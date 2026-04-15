'use client'

import { HeroPattern } from '@/components/shared'
import { Button } from '@/components/shared/Button'
import { RotatingText } from '@/components/shared/RotatingText'
import { useI18n } from '@/contexts/I18nContext'

export function HeroSection() {
  const { t } = useI18n()

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
        </div>
      </div>
    </div>
  )
}

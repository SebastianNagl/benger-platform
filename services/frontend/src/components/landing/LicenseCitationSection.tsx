'use client'

import { Card } from '@/components/shared/Card'
import { useI18n } from '@/contexts/I18nContext'

export function LicenseCitationSection() {
  const { t } = useI18n()

  const citations = t('landing.license.citations') as unknown as {
    label: string
    bibtex: string
  }[]
  const citationItems = Array.isArray(citations) ? citations : []

  return (
    <section
      id="license"
      className="flex min-h-screen items-center bg-zinc-50 py-16 dark:bg-zinc-800/50 sm:py-24"
    >
      <div className="mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="text-center">
          <h2 className="text-3xl font-bold tracking-tight text-zinc-900 dark:text-white sm:text-4xl">
            {t('landing.license.title')}
          </h2>
          <p className="mx-auto mt-4 max-w-2xl text-lg text-zinc-600 dark:text-zinc-400">
            {t('landing.license.subtitle')}
          </p>
        </div>

        {/* License */}
        <div className="mt-12">
          <Card className="p-6">
            <div className="flex items-center gap-4">
              <div className="flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-lg bg-emerald-600">
                <svg
                  className="h-6 w-6 text-white"
                  fill="none"
                  viewBox="0 0 24 24"
                  strokeWidth="1.5"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M12 21a9.004 9.004 0 008.716-6.747M12 21a9.004 9.004 0 01-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 017.843 4.582M12 3a8.997 8.997 0 00-7.843 4.582m15.686 0A11.953 11.953 0 0112 10.5c-2.998 0-5.74-1.1-7.843-2.918m15.686 0A8.959 8.959 0 0121 12c0 .778-.099 1.533-.284 2.253m0 0A17.919 17.919 0 0112 16.5c-3.162 0-6.133-.815-8.716-2.247m0 0A9.015 9.015 0 013 12c0-1.605.42-3.113 1.157-4.418"
                  />
                </svg>
              </div>
              <div>
                <h3 className="text-lg font-semibold text-zinc-900 dark:text-white">
                  {t('landing.license.licenseTitle')}
                </h3>
                <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
                  {t('landing.license.licenseDescription')}
                </p>
              </div>
            </div>
          </Card>
        </div>

        {/* Citations */}
        <div className="mt-12">
          <h3 className="text-center text-xl font-semibold text-zinc-900 dark:text-white">
            {t('landing.license.citationTitle')}
          </h3>
          <p className="mx-auto mt-2 max-w-2xl text-center text-sm text-zinc-600 dark:text-zinc-400">
            {t('landing.license.citationDescription')}
          </p>
          <div className="mt-8 grid gap-6 md:grid-cols-2">
            {citationItems.map((item, i) => (
              <Card key={i} className="p-6">
                <h4 className="mb-3 font-semibold text-zinc-900 dark:text-white">
                  {item.label}
                </h4>
                {/* bibtex citations hidden until peer review is complete
                <pre className="overflow-x-auto rounded-md bg-zinc-100 p-4 text-xs leading-relaxed text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">
                  {item.bibtex}
                </pre>
                */}
                <p className="text-sm text-zinc-500 dark:text-zinc-400 italic">
                  t.b.a.
                </p>
              </Card>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}

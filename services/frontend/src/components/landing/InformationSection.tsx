'use client'

import { Card } from '@/components/shared/Card'
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/shared/Tabs'
import { useI18n } from '@/contexts/I18nContext'

export function InformationSection() {
  const { t } = useI18n()

  return (
    <section
      id="information"
      className="min-h-screen py-16 sm:py-24"
    >
      <div className="mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8">
        <h2 className="text-center text-3xl font-bold tracking-tight text-zinc-900 dark:text-white sm:text-4xl">
          {t('landing.information.title')}
        </h2>

        <Tabs defaultValue="whatIsIt" className="mt-12">
          <TabsList className="mx-auto flex !h-auto w-full max-w-2xl justify-center overflow-hidden rounded-lg !p-0">
            <TabsTrigger
              value="whatIsIt"
              className="flex-1 !rounded-none px-4 py-2.5 text-sm sm:px-6 sm:text-base"
            >
              {t('landing.information.tabs.whatIsIt')}
            </TabsTrigger>
            <TabsTrigger
              value="howItWorks"
              className="flex-1 !rounded-none px-4 py-2.5 text-sm sm:px-6 sm:text-base"
            >
              {t('landing.information.tabs.howItWorks')}
            </TabsTrigger>
            <TabsTrigger
              value="whyNeeded"
              className="flex-1 !rounded-none px-4 py-2.5 text-sm sm:px-6 sm:text-base"
            >
              {t('landing.information.tabs.whyNeeded')}
            </TabsTrigger>
          </TabsList>

          {/* What is it? */}
          <TabsContent value="whatIsIt" className="mt-8">
            <p className="mx-auto max-w-4xl text-center text-lg text-zinc-600 dark:text-zinc-400">
              {t('landing.information.whatIsIt.description')}
            </p>
            <div className="mt-10 grid gap-8 md:grid-cols-2 lg:grid-cols-3">
              {(
                [
                  {
                    key: 'annotation',
                    icon: 'M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0115.75 21H5.25A2.25 2.25 0 013 18.75V8.25A2.25 2.25 0 015.25 6H10',
                  },
                  {
                    key: 'generation',
                    icon: 'M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 00-2.455 2.456z',
                  },
                  {
                    key: 'evaluation',
                    icon: 'M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z',
                  },
                  {
                    key: 'collaboration',
                    icon: 'M18 18.72a9.094 9.094 0 003.741-.479 3 3 0 00-4.682-2.72m.94 3.198l.001.031c0 .225-.012.447-.037.666A11.944 11.944 0 0112 21c-2.17 0-4.207-.576-5.963-1.584A6.062 6.062 0 016 18.719m12 0a5.971 5.971 0 00-.941-3.197m0 0A5.995 5.995 0 0012 12.75a5.995 5.995 0 00-5.058 2.772m0 0a3 3 0 00-4.681 2.72 8.986 8.986 0 003.74.477m.94-3.197a5.971 5.971 0 00-.94 3.197M15 6.75a3 3 0 11-6 0 3 3 0 016 0zm6 3a2.25 2.25 0 11-4.5 0 2.25 2.25 0 014.5 0zm-13.5 0a2.25 2.25 0 11-4.5 0 2.25 2.25 0 014.5 0z',
                  },
                  {
                    key: 'feedback',
                    icon: 'M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227 1.129.166 2.27.293 3.423.379.35.026.67.21.865.501L12 21l2.755-4.133a1.14 1.14 0 01.865-.501 48.172 48.172 0 003.423-.379c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0012 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018z',
                  },
                  {
                    key: 'openSource',
                    icon: 'M17.25 6.75L22.5 12l-5.25 5.25m-10.5 0L1.5 12l5.25-5.25m7.5-3l-4.5 16.5',
                  },
                ] as const
              ).map(({ key, icon }) => (
                <Card key={key} className="p-6">
                  <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-lg bg-emerald-600">
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
                        d={icon}
                      />
                    </svg>
                  </div>
                  <h3 className="text-lg font-semibold text-zinc-900 dark:text-white">
                    {t(`landing.information.whatIsIt.${key}.title`)}
                  </h3>
                  <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
                    {t(`landing.information.whatIsIt.${key}.description`)}
                  </p>
                </Card>
              ))}
            </div>
          </TabsContent>

          {/* How it works */}
          <TabsContent value="howItWorks" className="mt-8">
            <p className="mx-auto max-w-4xl text-center text-lg text-zinc-600 dark:text-zinc-400">
              {t('landing.information.howItWorks.description')}
            </p>
            <div className="mt-10 grid gap-6 md:grid-cols-2 lg:grid-cols-3">
              {(['create', 'import', 'annotate', 'generate', 'evaluate', 'report'] as const).map(
                (step) => (
                  <div
                    key={step}
                    className="flex items-start gap-4 rounded-lg border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900"
                  >
                    <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full bg-emerald-600 text-sm font-bold text-white">
                      {t(`landing.information.howItWorks.steps.${step}.number`)}
                    </div>
                    <div>
                      <h3 className="font-semibold text-zinc-900 dark:text-white">
                        {t(`landing.information.howItWorks.steps.${step}.title`)}
                      </h3>
                      <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
                        {t(`landing.information.howItWorks.steps.${step}.description`)}
                      </p>
                    </div>
                  </div>
                )
              )}
            </div>
          </TabsContent>

          {/* Why this is needed */}
          <TabsContent value="whyNeeded" className="mt-8">
            <p className="mx-auto max-w-4xl text-center text-lg text-zinc-600 dark:text-zinc-400">
              {t('landing.information.whyNeeded.description')}
            </p>
            <div className="mt-10 grid gap-8 md:grid-cols-2 lg:grid-cols-3">
              {(
                [
                  'gaps',
                  'rigor',
                  'reproducibility',
                  'accessibility',
                  'community',
                ] as const
              ).map((item) => (
                <Card key={item} className="p-6">
                  <h3 className="text-lg font-semibold text-zinc-900 dark:text-white">
                    {t(`landing.information.whyNeeded.${item}.title`)}
                  </h3>
                  <p className="mt-3 text-sm text-zinc-600 dark:text-zinc-400">
                    {t(`landing.information.whyNeeded.${item}.description`)}
                  </p>
                </Card>
              ))}
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </section>
  )
}

'use client'

import { InlineText } from '@/components/howto'
import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { ResponsiveContainer } from '@/components/shared/ResponsiveContainer'
import { useI18n } from '@/contexts/I18nContext'
import { ARCHITECTURE_SECTIONS } from '@/data/architecture'
import { pick, pickList } from '@/lib/howto'

/**
 * /architecture — the platform's technical architecture, rendered from
 * data/architecture.ts (bilingual inline content, one section per topic).
 */
export default function ArchitecturePage() {
  const { t, locale } = useI18n()

  return (
    <ResponsiveContainer size="xl" className="pb-16 pt-8">
      <div className="mb-4">
        <Breadcrumb
          items={[
            { label: t('navigation.dashboard', 'Dashboard'), href: '/dashboard' },
            { label: t('navigation.architecture', 'Architektur') },
          ]}
        />
      </div>

      <h1 className="text-3xl font-bold tracking-tight text-zinc-900 dark:text-white">
        {t('navigation.architecture', 'Architektur')}
      </h1>

      <div className="mt-8 lg:grid lg:grid-cols-[15rem_minmax(0,1fr)] lg:gap-10">
        <nav aria-label={t('howTo.toc', 'Themen')} className="hidden lg:block" data-testid="architecture-toc">
          <ul className="sticky top-24 space-y-1.5 border-l border-zinc-200 pl-3 text-sm dark:border-zinc-800">
            {ARCHITECTURE_SECTIONS.map((s) => (
              <li key={s.id}>
                <a
                  href={`#${s.id}`}
                  className="block text-zinc-600 hover:text-emerald-600 dark:text-zinc-400 dark:hover:text-emerald-400"
                >
                  {pick(s.title, locale)}
                </a>
              </li>
            ))}
          </ul>
        </nav>

        <div className="min-w-0 space-y-14">
          {ARCHITECTURE_SECTIONS.map((s) => (
            <section key={s.id} id={s.id} className="scroll-mt-24" data-testid={`architecture-${s.id}`}>
              <h2 className="text-2xl font-bold tracking-tight text-zinc-900 dark:text-white">
                {pick(s.title, locale)}
              </h2>
              <p className="mt-3 text-base text-zinc-700 dark:text-zinc-300">
                <InlineText text={pick(s.intro, locale)} />
              </p>
              {s.diagram && (
                <div className="mt-5 overflow-x-auto rounded-lg border border-zinc-200 bg-zinc-50 p-5 dark:border-zinc-800 dark:bg-zinc-900">
                  <pre className="font-mono text-xs leading-relaxed text-zinc-800 dark:text-zinc-200">{s.diagram}</pre>
                </div>
              )}
              <ul className="mt-4 list-disc space-y-2 pl-5 text-sm text-zinc-700 dark:text-zinc-300">
                {pickList(s.bullets, locale).map((b, i) => (
                  <li key={i}>
                    <InlineText text={b} />
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      </div>
    </ResponsiveContainer>
  )
}

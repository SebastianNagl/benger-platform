'use client'

import Link from 'next/link'
import {
  ArrowTopRightOnSquareIcon,
  ExclamationTriangleIcon,
  LightBulbIcon,
  LinkIcon,
} from '@heroicons/react/24/outline'

import { useI18n } from '@/contexts/I18nContext'
import { pick, pickList, type HowToGuide } from '@/lib/howto'

import { InlineText } from './InlineText'

interface Props {
  guide: HowToGuide
}

/**
 * One how-to guide: question-style title (anchored, deep-linkable), the
 * short answer, numbered steps, "good to know" tips, pitfalls and related
 * links. Pure over the guide object so the page and tests stay simple.
 */
export function GuideCard({ guide }: Props) {
  const { t, locale } = useI18n()
  const steps = pickList(guide.steps, locale)
  const tips = pickList(guide.tips, locale)
  const pitfalls = pickList(guide.pitfalls, locale)
  const links = guide.links ?? []

  return (
    <article
      id={guide.id}
      data-testid={`howto-guide-${guide.id}`}
      className="scroll-mt-28 rounded-lg border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-900"
    >
      <h3 className="group flex items-start gap-2 text-lg font-semibold text-zinc-900 dark:text-white">
        <a href={`#${guide.id}`} className="hover:text-emerald-600 dark:hover:text-emerald-400">
          {pick(guide.title, locale)}
        </a>
        <a
          href={`#${guide.id}`}
          aria-label={t('howTo.labels.permalink', 'Link zu dieser Anleitung')}
          className="mt-1 text-zinc-300 opacity-0 transition group-hover:opacity-100 hover:text-emerald-500 dark:text-zinc-600"
        >
          <LinkIcon className="h-4 w-4" />
        </a>
      </h3>
      <p className="mt-2 text-base text-zinc-700 dark:text-zinc-300">
        <InlineText text={pick(guide.summary, locale)} />
      </p>

      {steps.length > 0 && (
        <ol className="mt-4 space-y-2 border-l-2 border-emerald-200 pl-4 dark:border-emerald-900">
          {steps.map((step, i) => (
            <li key={i} className="flex gap-3 text-sm text-zinc-700 dark:text-zinc-300">
              <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-emerald-100 text-xs font-semibold text-emerald-800 dark:bg-emerald-900/50 dark:text-emerald-300">
                {i + 1}
              </span>
              <span>
                <InlineText text={step} />
              </span>
            </li>
          ))}
        </ol>
      )}

      {tips.length > 0 && (
        <div className="mt-4 rounded-md bg-zinc-50 p-3 dark:bg-zinc-800/60">
          <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
            <LightBulbIcon className="h-4 w-4 text-emerald-500" />
            {t('howTo.labels.tips', 'Gut zu wissen')}
          </p>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-zinc-700 dark:text-zinc-300">
            {tips.map((tip, i) => (
              <li key={i}>
                <InlineText text={tip} />
              </li>
            ))}
          </ul>
        </div>
      )}

      {pitfalls.length > 0 && (
        <div className="mt-3 rounded-md bg-amber-50 p-3 dark:bg-amber-950/30">
          <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-amber-800 dark:text-amber-300">
            <ExclamationTriangleIcon className="h-4 w-4" />
            {t('howTo.labels.pitfalls', 'Typische Stolpersteine')}
          </p>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-amber-900 dark:text-amber-200">
            {pitfalls.map((p, i) => (
              <li key={i}>
                <InlineText text={p} />
              </li>
            ))}
          </ul>
        </div>
      )}

      {links.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-2">
          {links.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="inline-flex items-center gap-1 rounded-full border border-zinc-200 px-3 py-1 text-xs font-medium text-zinc-700 transition hover:border-emerald-400 hover:text-emerald-700 dark:border-zinc-700 dark:text-zinc-300 dark:hover:border-emerald-600 dark:hover:text-emerald-400"
            >
              {pick(link.label, locale)}
              <ArrowTopRightOnSquareIcon className="h-3 w-3" />
            </Link>
          ))}
        </div>
      )}
    </article>
  )
}

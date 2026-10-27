'use client'

import { useEffect, useMemo, useRef, useState } from 'react'

import { GuideCard } from '@/components/howto'
import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { Button } from '@/components/shared/Button'
import { ResponsiveContainer } from '@/components/shared/ResponsiveContainer'
import { useI18n } from '@/contexts/I18nContext'
import { usePublicApiEnabled } from '@/hooks/usePublicApiEnabled'
import {
  HOWTO_CATEGORIES,
  categoryText,
  filterAvailableGuides,
  guideText,
  useHowToGuides,
  type HowToCategoryId,
} from '@/lib/howto'

type CategoryFilter = HowToCategoryId | 'all'

/**
 * /how-to — guide catalog. Guides come from the how-to registry (platform
 * guides + whatever the extended package registers), grouped by category,
 * narrowed by the category chips, and deep-linkable via #guide-id. Searching
 * is the job of the nav-bar search, which indexes every guide.
 */
export default function HowToPage() {
  const { t, locale } = useI18n()
  // Guides about features that are off for this user stay hidden.
  const publicApi = usePublicApiEnabled() === true
  const guides = filterAvailableGuides(useHowToGuides(), { publicApi })
  const [category, setCategory] = useState<CategoryFilter>('all')
  const scrolledTo = useRef<string | null>(null)

  const visible = useMemo(
    () =>
      category === 'all'
        ? guides
        : guides.filter((g) => g.category === category),
    [guides, category],
  )
  const grouped = useMemo(
    () =>
      HOWTO_CATEGORIES.map((cat) => ({
        cat,
        guides: visible.filter((g) => g.category === cat.id),
      })).filter((group) => group.guides.length > 0),
    [visible],
  )
  const countByCategory = useMemo(() => {
    const counts: Partial<Record<HowToCategoryId, number>> = {}
    for (const g of guides) counts[g.category] = (counts[g.category] ?? 0) + 1
    return counts
  }, [guides])

  // Deep link (#guide-id): scroll once the guide exists. Extended guides
  // register after the first paint, so this waits for them too.
  useEffect(() => {
    if (typeof window === 'undefined') return
    const hash = window.location.hash.replace(/^#/, '')
    if (!hash || scrolledTo.current === hash) return
    const el = document.getElementById(hash)
    if (el) {
      scrolledTo.current = hash
      el.scrollIntoView({ block: 'start' })
    }
  }, [guides])

  return (
    <ResponsiveContainer size="xl" className="pt-8 pb-16">
      <div className="mb-4">
        <Breadcrumb
          items={[
            {
              label: t('navigation.dashboard'),
              href: '/dashboard',
            },
            { label: t('howTo.title') },
          ]}
        />
      </div>

      <h1 className="text-3xl font-bold tracking-tight text-zinc-900 dark:text-white">
        {t('howTo.title')}
      </h1>

      {/* Category chips */}
      <div className="mt-5 flex flex-wrap gap-2" data-testid="howto-chips">
        <Chip
          active={category === 'all'}
          onClick={() => setCategory('all')}
          label={t('howTo.allTopics')}
          count={guides.length}
        />
        {HOWTO_CATEGORIES.map((cat) => {
          const n = countByCategory[cat.id] ?? 0
          if (n === 0) return null
          return (
            <Chip
              key={cat.id}
              active={category === cat.id}
              onClick={() => setCategory(category === cat.id ? 'all' : cat.id)}
              label={categoryText(cat.id, locale).title}
              count={n}
            />
          )
        })}
      </div>

      <div className="mt-10 lg:grid lg:grid-cols-[15rem_minmax(0,1fr)] lg:gap-10">
        {/* Sticky table of contents */}
        <nav
          aria-label={t('howTo.toc')}
          className="hidden lg:block"
          data-testid="howto-toc"
        >
          {/* Bounded height + own scroll: the catalog is taller than the
              viewport, and a sticky element never scrolls its own overflow —
              without this the last categories are unreachable. The
              scrollbar itself stays hidden. */}
          <div className="sticky top-24 max-h-[calc(100vh-7rem)] scrollbar-none space-y-5 overflow-y-auto overscroll-contain text-sm">
            {grouped.map(({ cat, guides: catGuides }) => (
              <div key={cat.id}>
                <a
                  href={`#howto-${cat.id}`}
                  className="font-semibold text-zinc-900 hover:text-emerald-600 dark:text-white dark:hover:text-emerald-400"
                >
                  {categoryText(cat.id, locale).title}
                </a>
                <ul className="mt-1.5 space-y-1 border-l border-zinc-200 pl-3 dark:border-zinc-800">
                  {catGuides.map((g) => (
                    <li key={g.id}>
                      <a
                        href={`#${g.id}`}
                        className="block truncate text-zinc-600 hover:text-emerald-600 dark:text-zinc-400 dark:hover:text-emerald-400"
                        title={guideText(g, locale).title}
                      >
                        {guideText(g, locale).title}
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </nav>

        {/* Guides */}
        <div className="min-w-0 space-y-14">
          {grouped.map(({ cat, guides: catGuides }) => (
            <section
              key={cat.id}
              id={`howto-${cat.id}`}
              className="scroll-mt-24"
            >
              <h2 className="text-2xl font-bold tracking-tight text-zinc-900 dark:text-white">
                {categoryText(cat.id, locale).title}
              </h2>
              <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
                {categoryText(cat.id, locale).blurb}
              </p>
              <div className="mt-5 space-y-5">
                {catGuides.map((g) => (
                  <GuideCard key={g.id} guide={g} />
                ))}
              </div>
            </section>
          ))}

          <p className="border-t border-zinc-200 pt-6 text-sm text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
            {t('howTo.contact.text')}{' '}
            <a
              href={t('howTo.contact.href')}
              className="font-medium text-emerald-600 hover:text-emerald-500 dark:text-emerald-400"
            >
              {t('howTo.contact.link')}
            </a>
          </p>
        </div>
      </div>
    </ResponsiveContainer>
  )
}

function Chip({
  active,
  label,
  count,
  onClick,
}: {
  active: boolean
  label: string
  count: number
  onClick: () => void
}) {
  return (
    <Button
      variant={active ? 'filled' : 'outline'}
      onClick={onClick}
      aria-pressed={active}
      className="gap-1.5 text-xs"
    >
      {label}
      <span
        className={
          active
            ? 'text-zinc-300 dark:text-emerald-100'
            : 'text-zinc-400 dark:text-zinc-500'
        }
      >
        {count}
      </span>
    </Button>
  )
}

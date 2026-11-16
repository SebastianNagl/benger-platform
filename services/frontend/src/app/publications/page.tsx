'use client'

import { NewsCard, useNewsItems } from '@/components/landing/NewsCard'
import { Badge } from '@/components/shared/Badge'
import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { Card } from '@/components/shared/Card'
import { ResponsiveContainer } from '@/components/shared/ResponsiveContainer'
import { useI18n } from '@/contexts/I18nContext'
import {
  OUR_GROUP,
  OUR_PAPER_LINKS,
  RELATED_GROUPS,
  RELATED_PUBLICATIONS,
  SIMILAR_PROJECTS,
  type NetworkLink,
  type RelatedPublication,
} from '@/data/publicationsNetwork'

const SECTION_IDS = ['ours', 'related', 'projects', 'groups'] as const

const externalLink = {
  target: '_blank',
  rel: 'noopener noreferrer',
} as const

/**
 * /publications: our publications (the publication entries of the landing
 * page's news list), related legal benchmarks for other jurisdictions and
 * languages, similar projects, and our and related research groups. The
 * external entries come from data/publicationsNetwork.ts, the copy from the
 * catalog keys publicationsNetwork.*.
 */
export default function PublicationsPage() {
  const { t } = useI18n()
  const ourPublications = useNewsItems().filter(
    (item) => item.type === 'publication',
  )

  const relatedCard = (pub: RelatedPublication) => (
    <li key={pub.id} data-testid={`publication-${pub.id}`}>
      <Card className="p-5">
        <h3 className="font-semibold text-zinc-900 dark:text-white">
          <a
            href={pub.url}
            {...externalLink}
            className="hover:text-emerald-600 dark:hover:text-emerald-400"
          >
            {pub.title}
          </a>
        </h3>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          {pub.authors} · {pub.venue}
        </p>
        <p className="mt-2 text-sm text-zinc-700 dark:text-zinc-300">
          {t(`publicationsNetwork.entries.${pub.id}`)}
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Badge variant="secondary">
            {t(`publicationsNetwork.jurisdictions.${pub.jurisdiction}`)}
          </Badge>
          {pub.languages && pub.languages.length > 0 && (
            <span
              className="text-xs text-zinc-500 dark:text-zinc-400"
              aria-label={`${t('publicationsNetwork.languages')}: ${pub.languages.join(', ')}`}
            >
              {pub.languages.map((l) => l.toUpperCase()).join(' · ')}
            </span>
          )}
        </div>
      </Card>
    </li>
  )

  const linkCard = (entry: NetworkLink) => (
    <li key={entry.id} data-testid={`network-${entry.id}`}>
      <Card className="h-full p-5">
        <h3 className="font-semibold text-zinc-900 dark:text-white">
          <a
            href={entry.url}
            {...externalLink}
            className="hover:text-emerald-600 dark:hover:text-emerald-400"
          >
            {entry.name}
          </a>
        </h3>
        {entry.institution && (
          <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
            {entry.institution}
          </p>
        )}
        <p className="mt-2 text-sm text-zinc-700 dark:text-zinc-300">
          {t(`publicationsNetwork.entries.${entry.id}`)}
        </p>
      </Card>
    </li>
  )

  const sectionHeading = (id: (typeof SECTION_IDS)[number]) => (
    <>
      <h2 className="text-2xl font-bold tracking-tight text-zinc-900 dark:text-white">
        {t(`publicationsNetwork.sections.${id}.title`)}
      </h2>
      <p className="mt-3 text-base text-zinc-700 dark:text-zinc-300">
        {t(`publicationsNetwork.sections.${id}.intro`)}
      </p>
    </>
  )

  return (
    <ResponsiveContainer size="xl" className="pt-8 pb-16">
      <div className="mb-4">
        <Breadcrumb
          items={[
            { label: t('navigation.dashboard'), href: '/dashboard' },
            { label: t('navigation.publications') },
          ]}
        />
      </div>

      <h1 className="text-3xl font-bold tracking-tight text-zinc-900 dark:text-white">
        {t('navigation.publications')}
      </h1>
      <p className="mt-3 max-w-3xl text-base text-zinc-600 dark:text-zinc-400">
        {t('publicationsNetwork.intro')}
      </p>

      <div className="mt-8 lg:grid lg:grid-cols-[15rem_minmax(0,1fr)] lg:gap-10">
        <nav
          aria-label={t('howTo.toc')}
          className="hidden lg:block"
          data-testid="publications-toc"
        >
          <ul className="sticky top-24 space-y-1.5 border-l border-zinc-200 pl-3 text-sm dark:border-zinc-800">
            {SECTION_IDS.map((id) => (
              <li key={id}>
                <a
                  href={`#${id}`}
                  className="block text-zinc-600 hover:text-emerald-600 dark:text-zinc-400 dark:hover:text-emerald-400"
                >
                  {t(`publicationsNetwork.sections.${id}.title`)}
                </a>
              </li>
            ))}
          </ul>
        </nav>

        <div className="min-w-0 space-y-14">
          <section
            id="ours"
            className="scroll-mt-24"
            data-testid="publications-ours"
          >
            {sectionHeading('ours')}
            <ul className="mt-6 grid gap-6 md:grid-cols-2">
              {ourPublications.map((item, i) => {
                const paper = item.url ? OUR_PAPER_LINKS[item.url] : undefined
                return (
                  <li key={i} className="flex flex-col gap-2">
                    <NewsCard item={item} />
                    {paper && (
                      <a
                        href={paper}
                        {...externalLink}
                        className="self-start text-sm font-medium text-emerald-600 hover:text-emerald-700 dark:text-emerald-400 dark:hover:text-emerald-300"
                      >
                        {t('publicationsNetwork.paperLink')} &rarr;
                      </a>
                    )}
                  </li>
                )
              })}
            </ul>
          </section>

          <section
            id="related"
            className="scroll-mt-24"
            data-testid="publications-related"
          >
            {sectionHeading('related')}
            <ul className="mt-6 space-y-4">
              {RELATED_PUBLICATIONS.map(relatedCard)}
            </ul>
          </section>

          <section
            id="projects"
            className="scroll-mt-24"
            data-testid="publications-projects"
          >
            {sectionHeading('projects')}
            <ul className="mt-6 grid gap-4 md:grid-cols-2">
              {SIMILAR_PROJECTS.map(linkCard)}
            </ul>
          </section>

          <section
            id="groups"
            className="scroll-mt-24"
            data-testid="publications-groups"
          >
            {sectionHeading('groups')}
            <h3 className="mt-6 text-sm font-semibold tracking-wide text-zinc-500 uppercase dark:text-zinc-400">
              {t('publicationsNetwork.sections.groups.ourGroup')}
            </h3>
            <ul className="mt-3 grid gap-4 md:grid-cols-2">
              {linkCard(OUR_GROUP)}
            </ul>
            <h3 className="mt-8 text-sm font-semibold tracking-wide text-zinc-500 uppercase dark:text-zinc-400">
              {t('publicationsNetwork.sections.groups.relatedGroups')}
            </h3>
            <ul className="mt-3 grid gap-4 md:grid-cols-2">
              {RELATED_GROUPS.map(linkCard)}
            </ul>
          </section>
        </div>
      </div>
    </ResponsiveContainer>
  )
}

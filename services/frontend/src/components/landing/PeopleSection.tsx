'use client'

import { Card } from '@/components/shared/Card'
import { useI18n } from '@/contexts/I18nContext'
import { UserIcon } from '@heroicons/react/24/outline'
import Image from 'next/image'
import { useState } from 'react'

interface TeamMember {
  name: string
  role: string
  institution: string
  url: string
  image?: string
}

interface NetworkPartner {
  name: string
  description: string
  url: string
  logo?: string
}

// The first two rows (six cards) show by default, so the order of
// `landing.people.members` in the locale files decides who is visible
// before "show all".
const COLLAPSED_COUNT = 6

export function PeopleSection() {
  const { t } = useI18n()
  const [showAll, setShowAll] = useState(false)

  const list = t('landing.people.members') as unknown as TeamMember[]
  const members = Array.isArray(list) ? list.filter((m) => m?.name) : []
  const visibleMembers = showAll ? members : members.slice(0, COLLAPSED_COUNT)
  const network = t('landing.people.network') as unknown as NetworkPartner[]
  const networkPartners = Array.isArray(network) ? network : []

  const renderMemberCard = (member: TeamMember, key: number) => (
    <Card key={key} className="p-6">
      <div className="flex items-center gap-4">
        {member.image ? (
          <Image
            src={member.image}
            alt={member.name}
            width={56}
            height={56}
            className="h-14 w-14 shrink-0 rounded-full object-cover"
          />
        ) : (
          <div
            className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-zinc-200 dark:bg-zinc-700"
            aria-hidden="true"
          >
            <UserIcon className="h-8 w-8 text-zinc-500 dark:text-zinc-400" />
          </div>
        )}
        <div className="min-w-0">
          <h3 className="truncate font-semibold text-zinc-900 dark:text-white">
            {member.url ? (
              <a
                href={member.url}
                target="_blank"
                rel="noopener noreferrer"
                className="hover:text-emerald-600 dark:hover:text-emerald-400"
              >
                {member.name}
              </a>
            ) : (
              member.name
            )}
          </h3>
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            {member.role}
          </p>
          <p className="text-xs text-zinc-500 dark:text-zinc-400">
            {member.institution}
          </p>
        </div>
      </div>
    </Card>
  )

  return (
    <section
      id="people"
      className="flex min-h-screen items-center py-16 sm:py-24"
    >
      <div className="mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="text-center">
          <h2 className="text-3xl font-bold tracking-tight text-zinc-900 sm:text-4xl dark:text-white">
            {t('landing.people.title')}
          </h2>
          <p className="mx-auto mt-4 max-w-2xl text-lg text-zinc-600 dark:text-zinc-400">
            {t('landing.people.subtitle')}
          </p>
        </div>

        {/* People */}
        <div
          id="people-list"
          className="mt-12 grid gap-6 md:grid-cols-2 lg:grid-cols-3"
        >
          {visibleMembers.map((member, i) => renderMemberCard(member, i))}
        </div>
        {members.length > COLLAPSED_COUNT && (
          <div className="mt-6 text-center">
            <button
              type="button"
              onClick={() => setShowAll((v) => !v)}
              aria-expanded={showAll}
              aria-controls="people-list"
              className="text-sm font-medium text-emerald-600 hover:text-emerald-700 dark:text-emerald-400 dark:hover:text-emerald-300"
            >
              {showAll
                ? t('landing.people.showLess')
                : `${t('landing.people.showAll')} (${members.length})`}
            </button>
          </div>
        )}

        {/* Network partners — same block, logo cards below the people. */}
        <div className="mt-12">
          <h3 className="text-sm font-medium tracking-wide text-zinc-500 uppercase dark:text-zinc-400">
            {t('landing.people.networkTitle')}
          </h3>
          <div className="mt-4 grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
            {networkPartners.map((partner, i) => (
              <Card key={i} className="flex flex-col items-center p-6">
                <div className="mb-4 flex h-16 w-full items-center justify-center">
                  {partner.logo ? (
                    <Image
                      src={partner.logo}
                      alt={`${partner.name} Logo`}
                      width={200}
                      height={64}
                      className="max-h-16 max-w-full object-contain"
                    />
                  ) : (
                    <div className="h-12 w-12 rounded bg-zinc-200 dark:bg-zinc-700" />
                  )}
                </div>
                <h4 className="text-center font-semibold text-zinc-900 dark:text-white">
                  {partner.url ? (
                    <a
                      href={partner.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="hover:text-emerald-600 dark:hover:text-emerald-400"
                    >
                      {partner.name}
                    </a>
                  ) : (
                    partner.name
                  )}
                </h4>
                <p className="mt-2 text-center text-sm text-zinc-600 dark:text-zinc-400">
                  {partner.description}
                </p>
              </Card>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}

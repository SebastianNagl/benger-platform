'use client'

import { Card } from '@/components/shared/Card'
import { useI18n } from '@/contexts/I18nContext'
import Image from 'next/image'

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

export function PeopleSection() {
  const { t } = useI18n()

  const team = t('landing.people.team') as unknown as TeamMember[]
  const network = t('landing.people.network') as unknown as NetworkPartner[]
  const teamMembers = Array.isArray(team) ? team : []
  const networkPartners = Array.isArray(network) ? network : []

  return (
    <section
      id="people"
      className="flex min-h-screen items-center py-16 sm:py-24"
    >
      <div className="mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="text-center">
          <h2 className="text-3xl font-bold tracking-tight text-zinc-900 dark:text-white sm:text-4xl">
            {t('landing.people.title')}
          </h2>
          <p className="mx-auto mt-4 max-w-2xl text-lg text-zinc-600 dark:text-zinc-400">
            {t('landing.people.subtitle')}
          </p>
        </div>

        {/* Team */}
        <div className="mt-12">
          <h3 className="text-xl font-semibold text-zinc-900 dark:text-white">
            {t('landing.people.teamTitle')}
          </h3>
          <div className="mt-6 grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            {teamMembers.map((member, i) => (
              <Card key={i} className="p-6">
                <div className="flex items-center gap-4">
                  {member.image ? (
                    <Image
                      src={member.image}
                      alt={member.name}
                      width={56}
                      height={56}
                      className="h-14 w-14 flex-shrink-0 rounded-full object-cover"
                    />
                  ) : (
                    <div className="h-14 w-14 flex-shrink-0 rounded-full bg-zinc-200 dark:bg-zinc-700" />
                  )}
                  <div className="min-w-0">
                    <h4 className="truncate font-semibold text-zinc-900 dark:text-white">
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
                    </h4>
                    <p className="text-sm text-zinc-600 dark:text-zinc-400">
                      {member.role}
                    </p>
                    <p className="text-xs text-zinc-500 dark:text-zinc-500">
                      {member.institution}
                    </p>
                  </div>
                </div>
              </Card>
            ))}
          </div>
        </div>

        {/* Network */}
        <div className="mt-16">
          <h3 className="text-xl font-semibold text-zinc-900 dark:text-white">
            {t('landing.people.networkTitle')}
          </h3>
          <div className="mt-6 grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
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

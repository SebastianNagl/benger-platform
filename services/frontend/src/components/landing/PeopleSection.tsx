'use client'

import { Card } from '@/components/shared/Card'
import { useI18n } from '@/contexts/I18nContext'
import { UserIcon } from '@heroicons/react/24/outline'
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

  const teamPlatform = t('landing.people.teamPlatform') as unknown as TeamMember[]
  const teamDatasetCore = t('landing.people.teamDatasetCore') as unknown as TeamMember[]
  const teamDatasetContribution = t('landing.people.teamDatasetContribution') as unknown as TeamMember[]
  const teamDatasetSenior = t('landing.people.teamDatasetSenior') as unknown as TeamMember[]
  const acknowledgements = t('landing.people.acknowledgements') as unknown as TeamMember[]
  const network = t('landing.people.network') as unknown as NetworkPartner[]
  const platformMembers = Array.isArray(teamPlatform) ? teamPlatform : []
  const datasetCoreMembers = Array.isArray(teamDatasetCore) ? teamDatasetCore : []
  const datasetContributionMembers = Array.isArray(teamDatasetContribution)
    ? teamDatasetContribution
    : []
  const datasetSeniorMembers = Array.isArray(teamDatasetSenior) ? teamDatasetSenior : []
  const acknowledgementsMembers = Array.isArray(acknowledgements) ? acknowledgements : []
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
            className="h-14 w-14 flex-shrink-0 rounded-full object-cover"
          />
        ) : (
          <div
            className="flex h-14 w-14 flex-shrink-0 items-center justify-center rounded-full bg-zinc-200 dark:bg-zinc-700"
            aria-hidden="true"
          >
            <UserIcon className="h-8 w-8 text-zinc-500 dark:text-zinc-400" />
          </div>
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
  )

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

        {/* Platform Team */}
        <div className="mt-12">
          <h3 className="text-xl font-semibold text-zinc-900 dark:text-white">
            {t('landing.people.teamPlatformTitle')}
          </h3>
          <div className="mt-6 grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            {platformMembers.map((member, i) => renderMemberCard(member, i))}
          </div>
        </div>

        {/* Dataset Team */}
        <div className="mt-12">
          <h3 className="text-xl font-semibold text-zinc-900 dark:text-white">
            {t('landing.people.teamDatasetTitle')}
          </h3>

          <div className="mt-6">
            <h4 className="text-sm font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
              {t('landing.people.teamDatasetCoreTitle')}
            </h4>
            <div className="mt-3 grid gap-6 md:grid-cols-2 lg:grid-cols-3">
              {datasetCoreMembers.map((member, i) => renderMemberCard(member, i))}
            </div>
          </div>

          <div className="mt-8">
            <h4 className="text-sm font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
              {t('landing.people.teamDatasetContributionTitle')}
            </h4>
            <div className="mt-3 grid gap-6 md:grid-cols-2 lg:grid-cols-3">
              {datasetContributionMembers.map((member, i) =>
                renderMemberCard(member, i)
              )}
            </div>
          </div>

          <div className="mt-8">
            <h4 className="text-sm font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
              {t('landing.people.teamDatasetSeniorTitle')}
            </h4>
            <div className="mt-3 grid gap-6 md:grid-cols-2 lg:grid-cols-3">
              {datasetSeniorMembers.map((member, i) => renderMemberCard(member, i))}
            </div>
          </div>
        </div>

        {/* Acknowledgements */}
        <div className="mt-12">
          <h3 className="text-xl font-semibold text-zinc-900 dark:text-white">
            {t('landing.people.acknowledgementsTitle')}
          </h3>
          <div className="mt-6 grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            {acknowledgementsMembers.map((member, i) =>
              renderMemberCard(member, i)
            )}
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

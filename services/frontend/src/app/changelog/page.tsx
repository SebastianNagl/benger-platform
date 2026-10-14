'use client'

import { useSyncExternalStore } from 'react'

import { LegalPageWrapper } from '@/components/layout/LegalPageWrapper'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { PLATFORM_CHANGELOG } from '@/data/changelog'
import { usePublicApiEnabled } from '@/hooks/usePublicApiEnabled'
import { useResolvedUiMode } from '@/hooks/useResolvedUiMode'
import {
  type ChangelogAudience,
  filterAvailableChangelogEntries,
  useChangelogEntries,
} from '@/lib/extensions/changelog'
import { intlTag } from '@/lib/i18n/locales'
import { filterAndGroup } from '@/lib/utils/changelog'
import { isStudentLockedHost } from '@/lib/utils/subdomain'

// isStudentLockedHost reads window.location, which does not exist during SSR.
// Routing it through useSyncExternalStore (server snapshot: false) keeps the
// server HTML and the hydration render identical, then React re-renders with
// the real host synchronously after hydration — no mismatch warning, no
// visible flash, even once a benger-only platform entry exists.
const noopSubscribe = () => () => {}
const useStudentLockedHost = () =>
  useSyncExternalStore(noopSubscribe, isStudentLockedHost, () => false)

export default function ChangelogPage() {
  const { t, locale } = useI18n()
  const { user } = useAuth()
  const mode = useResolvedUiMode()
  const extendedEntries = useChangelogEntries()
  const studentLockedHost = useStudentLockedHost()
  const publicApi = usePublicApiEnabled() === true

  // Which product the visitor is experiencing. useResolvedUiMode is the
  // single source of truth (host default + superadmin view switch); the
  // studentLockedHost term covers the window on vertretbar hosts before
  // the extended package registers StudentShell (the hook returns 'expert'
  // then), so anonymous vertretbar visitors never flash benger entries.
  const brand: ChangelogAudience =
    mode === 'student' || (studentLockedHost && !user?.is_superadmin)
      ? 'vertretbar'
      : 'benger'

  const groups = filterAndGroup(
    filterAvailableChangelogEntries(
      [...PLATFORM_CHANGELOG, ...extendedEntries],
      { publicApi },
    ),
    brand,
  )

  const dateFormat = new Intl.DateTimeFormat(intlTag(locale), {
    dateStyle: 'long',
  })
  const formatDate = (isoDate: string) => {
    const parsed = new Date(`${isoDate}T00:00:00`)
    return Number.isNaN(parsed.getTime()) ? isoDate : dateFormat.format(parsed)
  }

  return (
    <LegalPageWrapper
      titleKey="changelog.title"
      breadcrumbLabel={t('changelog.title')}
      href="/changelog"
    >
      <h1>{t('changelog.title')}</h1>

      <p className="lead text-zinc-700 dark:text-zinc-200">
        {t('changelog.intro')}
      </p>

      {groups.length === 0 ? (
        <p className="text-zinc-700 dark:text-zinc-200">
          {t('changelog.empty')}
        </p>
      ) : (
        groups.map((group) => (
          <section key={group.date}>
            <h2>{formatDate(group.date)}</h2>
            <ul>
              {group.entries.map((entry) => (
                <li key={entry.id} className="text-zinc-700 dark:text-zinc-200">
                  {t(`changelogEntries.${entry.id}`)}
                </li>
              ))}
            </ul>
          </section>
        ))
      )}
    </LegalPageWrapper>
  )
}

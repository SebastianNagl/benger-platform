'use client'

import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { ResponsiveContainer } from '@/components/shared/ResponsiveContainer'
import { useI18n } from '@/contexts/I18nContext'
import { useSlot } from '@/lib/extensions/slots'

/**
 * "Meine Lernstatistik" — the expert shell's personal learning analytics
 * (score history, retention, due cards) as a dedicated page, reachable
 * from the sidebar below Berichte. The widgets come from the extended
 * edition via the PersonalAnalyticsPage slot (the student dashboard shows
 * the same grid); community edition: nothing registered → a short notice
 * instead of a 404.
 */
export default function LearningStatsPage() {
  const { t } = useI18n()
  const PersonalAnalyticsPage = useSlot('PersonalAnalyticsPage')

  return (
    <ResponsiveContainer>
      <div className="mb-6">
        <Breadcrumb
          items={[
            { label: t('navigation.dashboard', 'Dashboard'), href: '/dashboard' },
            { label: t('navigation.learningStats', 'Lernstatistik') },
          ]}
        />
      </div>
      <h1 className="mb-6 text-3xl font-bold text-zinc-900 dark:text-white">
        {t('dashboard.personal.title', 'Meine Lernstatistik')}
      </h1>
      {PersonalAnalyticsPage ? (
        // eslint-disable-next-line react-hooks/static-components
        <PersonalAnalyticsPage />
      ) : (
        <p
          className="text-sm text-zinc-500 dark:text-zinc-400"
          data-testid="learning-stats-unavailable"
        >
          {t(
            'dashboard.personal.unavailable',
            'Die Lernstatistik ist in dieser Edition nicht verfügbar.',
          )}
        </p>
      )}
    </ResponsiveContainer>
  )
}

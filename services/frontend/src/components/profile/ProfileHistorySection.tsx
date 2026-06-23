'use client'

import { ChevronDownIcon } from '@heroicons/react/24/outline'

import { useI18n } from '@/contexts/I18nContext'
import type { ProfileHistoryEntry } from '@/lib/api/types'

interface ProfileHistorySectionProps {
  profileHistory: ProfileHistoryEntry[]
  expanded: boolean
  onToggle: (next: boolean) => void
}

export function ProfileHistorySection({
  profileHistory,
  expanded,
  onToggle,
}: ProfileHistorySectionProps) {
  const { t } = useI18n()

  return (
    <div className="border-t border-zinc-200 pt-8 dark:border-zinc-700">
      <button
        type="button"
        onClick={() => onToggle(!expanded)}
        className="group flex w-full items-center justify-between text-left"
      >
        <h2 className="text-xl font-semibold text-zinc-900 dark:text-white">
          {t('profile.profileHistory')}
        </h2>
        <div className="inline-flex items-center gap-1.5">
          <span className="text-sm text-zinc-500 dark:text-zinc-400">
            {expanded
              ? t('profile.hideProfileHistory')
              : t('profile.showProfileHistory')}
          </span>
          <ChevronDownIcon
            className={`h-4 w-4 opacity-70 transition-transform ${
              expanded ? 'rotate-180' : ''
            }`}
          />
        </div>
      </button>

      {expanded && (
        <div className="mt-6 space-y-3">
          {profileHistory.map((entry) => (
            <div
              key={entry.id}
              className="rounded-lg border border-zinc-200 bg-zinc-50 p-4 dark:border-zinc-700 dark:bg-zinc-800/50"
            >
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                  {entry.change_type}
                </span>
                <span className="text-xs text-zinc-500 dark:text-zinc-400">
                  {new Date(entry.changed_at).toLocaleString()}
                </span>
              </div>
              <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
                {t('profile.changedFields')}:{' '}
                {entry.changed_fields.join(', ')}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default ProfileHistorySection

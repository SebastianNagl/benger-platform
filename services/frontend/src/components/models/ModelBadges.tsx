'use client'

/**
 * Small pill badges for the BYOM (bring-your-own-model) feature.
 *
 * - OfficialBadge:   catalog models curated by the platform
 * - CustomBadge:     user-registered custom models (optionally with owner)
 * - VisibilityBadge: private / org-shared / public state of a custom model
 *
 * Pill styling follows the "configured" pill in UserApiKeys; the color
 * palette follows the provider chips in ModelSelectionSection.
 */

import { useI18n } from '@/contexts/I18nContext'

export type ModelVisibility = 'private' | 'organization' | 'public'

const pillBase =
  'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium'

export function OfficialBadge({ className = '' }: { className?: string }) {
  const { t } = useI18n()
  return (
    <span
      className={`${pillBase} bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400 ${className}`}
      data-testid="official-badge"
    >
      {t('customModels.badges.official')}
    </span>
  )
}

export function CustomBadge({
  ownerName,
  className = '',
}: {
  /** Optional owner username shown after the label ("Custom – alice"). */
  ownerName?: string | null
  className?: string
}) {
  const { t } = useI18n()
  return (
    <span
      className={`${pillBase} bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300 ${className}`}
      data-testid="custom-badge"
    >
      {ownerName
        ? t('customModels.badges.customBy', { owner: ownerName })
        : t('customModels.badges.custom')}
    </span>
  )
}

const visibilityStyles: Record<ModelVisibility, string> = {
  private: 'bg-zinc-100 text-zinc-600 dark:bg-zinc-700 dark:text-zinc-300',
  organization:
    'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
  public:
    'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300',
}

export function VisibilityBadge({
  visibility,
  className = '',
}: {
  visibility: ModelVisibility
  className?: string
}) {
  const { t } = useI18n()
  const labels: Record<ModelVisibility, string> = {
    private: t('customModels.badges.private'),
    organization: t('customModels.badges.organization'),
    public: t('customModels.badges.public'),
  }
  return (
    <span
      className={`${pillBase} ${visibilityStyles[visibility]} ${className}`}
      data-testid={`visibility-badge-${visibility}`}
    >
      {labels[visibility]}
    </span>
  )
}

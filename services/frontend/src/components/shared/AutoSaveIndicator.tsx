/**
 * AutoSaveIndicator Component
 *
 * Displays the current auto-save status to the user.
 * Shows saving state, last saved time, and any errors.
 *
 * Issue #1041: Auto-save for annotation fields
 */

'use client'

import { useI18n } from '@/contexts/I18nContext'
import { CheckCircleIcon, CloudArrowUpIcon, ExclamationCircleIcon } from '@heroicons/react/24/outline'
import { useCallback, useEffect, useState } from 'react'

interface AutoSaveIndicatorProps {
  isSaving: boolean
  lastSaved: Date | null
  error: string | null
  className?: string
}

export function AutoSaveIndicator({
  isSaving,
  lastSaved,
  error,
  className = '',
}: AutoSaveIndicatorProps) {
  const { t, locale } = useI18n()
  const [displayTime, setDisplayTime] = useState<string>('')

  /**
   * Format relative time (e.g., "2m ago", "just now")
   */
  const formatRelativeTime = useCallback((date: Date): string => {
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffSeconds = Math.floor(diffMs / 1000)
    const diffMinutes = Math.floor(diffSeconds / 60)
    const diffHours = Math.floor(diffMinutes / 60)

    if (diffSeconds < 10) {
      return t('common.autoSave.justNow')
    }
    if (diffSeconds < 60) {
      return t('common.autoSave.secondsAgo', { seconds: diffSeconds })
    }
    if (diffMinutes < 60) {
      return t('common.autoSave.minutesAgo', { minutes: diffMinutes })
    }
    if (diffHours < 24) {
      return t('common.autoSave.hoursAgo', { hours: diffHours })
    }
    return date.toLocaleTimeString(locale === 'de' ? 'de-DE' : 'en-US', { hour: '2-digit', minute: '2-digit' })
  }, [t, locale])

  // Update relative time every 10 seconds
  useEffect(() => {
    if (!lastSaved) return

    const updateTime = () => {
      setDisplayTime(formatRelativeTime(lastSaved))
    }

    updateTime()
    const interval = setInterval(updateTime, 10000)

    return () => clearInterval(interval)
  }, [lastSaved, formatRelativeTime])

  // Error state
  if (error) {
    return (
      <div
        className={`flex items-center gap-1.5 text-xs text-red-600 dark:text-red-400 ${className}`}
        title={error}
      >
        <ExclamationCircleIcon className="h-4 w-4" />
        <span>{t('common.autoSave.saveFailed')}</span>
      </div>
    )
  }

  // Saving state
  if (isSaving) {
    return (
      <div
        className={`flex items-center gap-1.5 text-xs text-zinc-500 dark:text-zinc-400 ${className}`}
      >
        <CloudArrowUpIcon className="h-4 w-4 animate-pulse" />
        <span>{t('common.autoSave.saving')}</span>
      </div>
    )
  }

  // Saved state
  if (lastSaved) {
    return (
      <div
        className={`flex items-center gap-1.5 text-xs text-zinc-500 dark:text-zinc-400 ${className}`}
        title={`${t('common.autoSave.lastSaved')} ${lastSaved.toLocaleString(locale === 'de' ? 'de-DE' : 'en-US')}`}
      >
        <CheckCircleIcon className="h-4 w-4 text-emerald-500" />
        <span>{t('common.autoSave.saved', { displayTime })}</span>
      </div>
    )
  }

  // No state to display
  return null
}

export default AutoSaveIndicator

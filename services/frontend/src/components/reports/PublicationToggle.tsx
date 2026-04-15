/**
 * Publication Toggle Component
 *
 * Allows superadmins to publish/unpublish project reports
 * Only visible to superadmins
 * Shows publish status and requirements
 *
 * Issue #770: Project Reports Publishing System
 */

'use client'

import { Button } from '@/components/shared/Button'
import { useI18n } from '@/contexts/I18nContext'
import { useState } from 'react'

interface PublicationToggleProps {
  projectId: string
  isPublished: boolean
  canPublish: boolean
  canPublishReason: string
  onToggle?: (published: boolean) => void
}

// Map backend reason messages to translation keys
const getReasonTranslationKey = (reason: string): string => {
  const reasonMap: Record<string, string> = {
    'Report not found': 'project.report.reasons.reportNotFound',
    'Project must have tasks': 'project.report.reasons.mustHaveTasks',
    'Project must have LLM generations':
      'project.report.reasons.mustHaveGenerations',
    'Project must have completed evaluations':
      'project.report.reasons.mustHaveEvaluations',
    'Report not created yet': 'project.report.reasons.notCreatedYet',
  }
  return reasonMap[reason] || ''
}

export function PublicationToggle({
  projectId,
  isPublished,
  canPublish,
  canPublishReason,
  onToggle,
}: PublicationToggleProps) {
  const { t } = useI18n()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showConfirm, setShowConfirm] = useState(false)

  // Translate the reason if a translation key exists
  const translatedReason = getReasonTranslationKey(canPublishReason)
    ? t(getReasonTranslationKey(canPublishReason))
    : canPublishReason

  const handleToggle = async () => {
    setShowConfirm(false)
    setLoading(true)
    setError(null)

    try {
      const endpoint = isPublished ? 'unpublish' : 'publish'
      const response = await fetch(
        `/api/projects/${projectId}/report/${endpoint}`,
        {
          method: 'PUT',
          credentials: 'include',
        }
      )

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || `Failed to ${endpoint} report`)
      }

      const data = await response.json()
      onToggle?.(data.is_published)
    } catch (err: any) {
      console.error('Failed to toggle publication:', err)
      setError(err.message || t('project.report.publication.errorToggle'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-700 dark:bg-zinc-800">
      <div className="space-y-3">
        <div className="flex items-center justify-between gap-2">
          <h3 className="min-w-0 truncate text-sm font-medium text-zinc-900 dark:text-white">
            {t('project.report.publication.title')}
          </h3>
          <span
            className={`inline-flex shrink-0 rounded-full px-2 py-1 text-xs font-semibold ${
              isPublished
                ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400'
                : 'bg-zinc-100 text-zinc-800 dark:bg-zinc-700 dark:text-zinc-300'
            }`}
          >
            {isPublished
              ? t('project.report.publication.statusPublished')
              : t('project.report.publication.statusDraft')}
          </span>
        </div>

        <p className="text-sm text-zinc-500 dark:text-zinc-400">
          {isPublished
            ? t('project.report.publication.published')
            : t('project.report.publication.draft')}
        </p>

        {!canPublish && !isPublished && (
          <p className="text-xs text-amber-600 dark:text-amber-500">
            {translatedReason}
          </p>
        )}

        <Button
          onClick={() => setShowConfirm(true)}
          disabled={loading || (!canPublish && !isPublished)}
          variant={isPublished ? 'outline' : 'filled'}
          className="w-full"
        >
          {loading
            ? t('project.report.publication.processing')
            : isPublished
              ? t('project.report.publication.unpublish')
              : t('project.report.publication.publish')}
        </Button>
      </div>

      {error && (
        <div className="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-800 dark:bg-red-900/20 dark:text-red-400">
          {error}
        </div>
      )}

      {/* Confirmation Modal */}
      {showConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
          <div className="mx-4 max-w-md rounded-lg bg-white p-6 shadow-xl dark:bg-zinc-900">
            <h3 className="text-lg font-semibold text-zinc-900 dark:text-white">
              {isPublished
                ? t('project.report.publication.confirmUnpublishTitle')
                : t('project.report.publication.confirmPublishTitle')}
            </h3>
            <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
              {isPublished
                ? t('project.report.publication.confirmUnpublishMessage')
                : t('project.report.publication.confirmPublishMessage')}
            </p>
            <div className="mt-6 flex justify-end gap-3">
              <Button onClick={() => setShowConfirm(false)} variant="outline">
                {t('project.report.publication.cancel')}
              </Button>
              <Button
                onClick={handleToggle}
                variant={isPublished ? 'outline' : 'filled'}
              >
                {isPublished
                  ? t('project.report.publication.unpublish')
                  : t('project.report.publication.publish')}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

/**
 * Publication Toggle Component
 *
 * Shows the publication state of a project report and lets superadmins
 * move it between three states:
 *
 *   Entwurf ─"Veröffentlichen"─▶ Veröffentlicht (Projektorganisationen)
 *                                   │  "Öffentlich machen" / "Nur Organisationen"
 *                                   ▼
 *                                Öffentlich (lesbar ohne Anmeldung, Link kopierbar)
 *
 * "Veröffentlichung zurückziehen" returns either published state to draft.
 * Non-superadmins only see the status.
 *
 * Issue #770: Project Reports Publishing System
 */

'use client'

import { Button } from '@/components/shared/Button'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import {
  publishReport,
  setReportVisibility,
  unpublishReport,
  type ReportResponse,
} from '@/lib/api/reports'
import { useEffect, useRef, useState } from 'react'

export interface PublicationState {
  is_published: boolean
  is_public: boolean
}

interface PublicationToggleProps {
  projectId: string
  /** Report id, used for the public link (/reports/{id}). */
  reportId?: string | null
  isPublished: boolean
  /** Readable without a session (only meaningful while published). */
  isPublic?: boolean
  canPublish: boolean
  canPublishReason: string
  /** Legacy callback: published flag only. */
  onToggle?: (published: boolean) => void
  /** Full publication state after any successful change. */
  onChange?: (state: PublicationState) => void
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

type DialogKind = 'publish' | 'unpublish' | null

export function PublicationToggle({
  projectId,
  reportId,
  isPublished,
  isPublic = false,
  canPublish,
  canPublishReason,
  onToggle,
  onChange,
}: PublicationToggleProps) {
  const { t } = useI18n()
  const { user } = useAuth()
  const isSuperadmin = Boolean(user?.is_superadmin)

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [dialog, setDialog] = useState<DialogKind>(null)
  const [publishPublic, setPublishPublic] = useState(false)
  const [copied, setCopied] = useState(false)
  const copiedTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    return () => {
      if (copiedTimer.current) clearTimeout(copiedTimer.current)
    }
  }, [])

  // Translate the reason if a translation key exists
  const translatedReason = getReasonTranslationKey(canPublishReason)
    ? t(getReasonTranslationKey(canPublishReason))
    : canPublishReason

  const effectivePublic = isPublished && isPublic
  const publicPath = reportId ? `/reports/${reportId}` : null
  const publicUrl =
    publicPath && typeof window !== 'undefined'
      ? `${window.location.origin}${publicPath}`
      : publicPath

  const applyResult = (data: ReportResponse) => {
    // Legacy callers toast on publish/unpublish; a visibility-only change
    // must not re-trigger that.
    if (data.is_published !== isPublished) {
      onToggle?.(data.is_published)
    }
    onChange?.({
      is_published: data.is_published,
      is_public: Boolean(data.is_public),
    })
  }

  const run = async (
    action: () => Promise<ReportResponse>,
    fallbackMessageKey: string,
    fallbackMessage: string
  ) => {
    setDialog(null)
    setLoading(true)
    setError(null)
    try {
      const data = await action()
      applyResult(data)
    } catch (err: any) {
      console.error('Failed to change publication state:', err)
      setError(err?.message || t(fallbackMessageKey, fallbackMessage))
    } finally {
      setLoading(false)
    }
  }

  const handlePublish = () =>
    run(
      () => publishReport(projectId, { is_public: publishPublic }),
      'project.report.publication.errorToggle',
      'Fehler beim Ändern des Veröffentlichungsstatus'
    )

  const handleUnpublish = () =>
    run(
      () => unpublishReport(projectId),
      'project.report.publication.errorToggle',
      'Fehler beim Ändern des Veröffentlichungsstatus'
    )

  const handleVisibility = (nextPublic: boolean) =>
    run(
      () => setReportVisibility(projectId, { is_public: nextPublic }),
      'reports.publication.errorVisibility',
      'Sichtbarkeit konnte nicht geändert werden'
    )

  const handleCopy = async () => {
    if (!publicUrl) return
    try {
      await navigator.clipboard.writeText(publicUrl)
      setCopied(true)
      if (copiedTimer.current) clearTimeout(copiedTimer.current)
      copiedTimer.current = setTimeout(() => setCopied(false), 2000)
    } catch (err) {
      console.error('Failed to copy public link:', err)
    }
  }

  const statusBadge = effectivePublic
    ? {
        label: t('reports.publication.statusPublic', 'Öffentlich'),
        className:
          'bg-sky-100 text-sky-800 dark:bg-sky-900/30 dark:text-sky-300',
      }
    : isPublished
      ? {
          label: t('project.report.publication.statusPublished'),
          className:
            'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400',
        }
      : {
          label: t('project.report.publication.statusDraft'),
          className:
            'bg-zinc-100 text-zinc-800 dark:bg-zinc-700 dark:text-zinc-300',
        }

  const statusText = effectivePublic
    ? t('reports.publication.visibleToPublic', 'Öffentlich sichtbar')
    : isPublished
      ? t(
          'reports.publication.visibleToOrgs',
          'Sichtbar für Projektorganisationen'
        )
      : t('project.report.publication.draft')

  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-700 dark:bg-zinc-800">
      <div className="space-y-3">
        <div className="flex items-center justify-between gap-2">
          <h3 className="min-w-0 text-sm font-medium text-zinc-900 dark:text-white">
            {t('project.report.publication.title')}
          </h3>
          <span
            data-testid="publication-status"
            className={`inline-flex shrink-0 rounded-full px-2 py-1 text-xs font-semibold ${statusBadge.className}`}
          >
            {statusBadge.label}
          </span>
        </div>

        <p className="text-sm text-zinc-500 dark:text-zinc-400">{statusText}</p>

        {effectivePublic && publicUrl && (
          <div>
            <label
              htmlFor={`public-link-${projectId}`}
              className="mb-1 block text-xs font-medium text-zinc-600 dark:text-zinc-300"
            >
              {t('reports.publication.publicLink', 'Öffentlicher Link')}
            </label>
            <div className="flex gap-2">
              <input
                id={`public-link-${projectId}`}
                type="text"
                readOnly
                value={publicUrl}
                onFocus={(e) => e.currentTarget.select()}
                className="min-w-0 flex-1 rounded-md border border-zinc-300 bg-zinc-50 px-2 py-1 text-xs text-zinc-700 dark:border-zinc-600 dark:bg-zinc-900 dark:text-zinc-200"
              />
              <Button
                onClick={handleCopy}
                variant="outline"
                className="shrink-0"
              >
                {copied
                  ? t('reports.publication.copied', 'Kopiert')
                  : t('reports.publication.copyLink', 'Kopieren')}
              </Button>
            </div>
          </div>
        )}

        {!canPublish && !isPublished && (
          <p className="text-xs text-amber-600 dark:text-amber-500">
            {translatedReason}
          </p>
        )}

        {isSuperadmin && !isPublished && (
          <Button
            onClick={() => {
              setPublishPublic(false)
              setDialog('publish')
            }}
            disabled={loading || !canPublish}
            variant="filled"
            className="w-full"
          >
            {loading
              ? t('project.report.publication.processing')
              : t('project.report.publication.publish')}
          </Button>
        )}

        {isSuperadmin && isPublished && (
          <div className="flex flex-col gap-2">
            {effectivePublic ? (
              <Button
                onClick={() => handleVisibility(false)}
                disabled={loading}
                variant="outline"
                className="w-full"
              >
                {loading
                  ? t('project.report.publication.processing')
                  : t('reports.publication.orgsOnly', 'Nur Organisationen')}
              </Button>
            ) : (
              <Button
                onClick={() => handleVisibility(true)}
                disabled={loading}
                variant="filled"
                className="w-full"
              >
                {loading
                  ? t('project.report.publication.processing')
                  : t('reports.publication.makePublic', 'Öffentlich machen')}
              </Button>
            )}
            <Button
              onClick={() => setDialog('unpublish')}
              disabled={loading}
              variant="outline"
              className="w-full"
            >
              {effectivePublic
                ? t('reports.publication.withdraw', 'Zurückziehen')
                : t('project.report.publication.unpublish')}
            </Button>
          </div>
        )}
      </div>

      {error && (
        <div className="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-800 dark:bg-red-900/20 dark:text-red-400">
          {error}
        </div>
      )}

      {/* Publish dialog: pick the audience */}
      {dialog === 'publish' && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
          <div
            role="dialog"
            aria-labelledby="publish-dialog-title"
            className="mx-4 w-full max-w-md rounded-lg bg-white p-6 shadow-xl dark:bg-zinc-900"
          >
            <h3
              id="publish-dialog-title"
              className="text-lg font-semibold text-zinc-900 dark:text-white"
            >
              {t('project.report.publication.confirmPublishTitle')}
            </h3>
            <fieldset className="mt-4 space-y-3">
              <legend className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                {t('reports.publication.visibilityLabel', 'Sichtbarkeit')}
              </legend>
              <label className="flex cursor-pointer items-start gap-3 rounded-md border border-zinc-200 p-3 dark:border-zinc-700">
                <input
                  type="radio"
                  name="report-visibility"
                  value="organizations"
                  checked={!publishPublic}
                  onChange={() => setPublishPublic(false)}
                  className="mt-0.5 h-4 w-4 border-zinc-300 text-emerald-600 focus:ring-emerald-500"
                />
                <span className="text-sm">
                  <span className="block font-medium text-zinc-900 dark:text-white">
                    {t(
                      'reports.publication.visibilityOrgs',
                      'Nur Projektorganisationen'
                    )}
                  </span>
                  <span className="block text-xs text-zinc-500 dark:text-zinc-400">
                    {t(
                      'reports.publication.visibilityOrgsHint',
                      'Nur angemeldete Mitglieder der Projektorganisationen können den Bericht lesen.'
                    )}
                  </span>
                </span>
              </label>
              <label className="flex cursor-pointer items-start gap-3 rounded-md border border-zinc-200 p-3 dark:border-zinc-700">
                <input
                  type="radio"
                  name="report-visibility"
                  value="public"
                  checked={publishPublic}
                  onChange={() => setPublishPublic(true)}
                  className="mt-0.5 h-4 w-4 border-zinc-300 text-emerald-600 focus:ring-emerald-500"
                />
                <span className="text-sm">
                  <span className="block font-medium text-zinc-900 dark:text-white">
                    {t(
                      'reports.publication.visibilityPublic',
                      'Öffentlich (auch ohne Anmeldung)'
                    )}
                  </span>
                  <span className="block text-xs text-zinc-500 dark:text-zinc-400">
                    {t(
                      'reports.publication.visibilityPublicHint',
                      'Jeder mit dem Link kann den Bericht lesen.'
                    )}
                  </span>
                </span>
              </label>
            </fieldset>
            <div className="mt-6 flex justify-end gap-3">
              <Button onClick={() => setDialog(null)} variant="outline">
                {t('project.report.publication.cancel')}
              </Button>
              <Button onClick={handlePublish} variant="filled">
                {t('project.report.publication.publish')}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Unpublish confirmation */}
      {dialog === 'unpublish' && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
          <div
            role="dialog"
            aria-labelledby="unpublish-dialog-title"
            className="mx-4 max-w-md rounded-lg bg-white p-6 shadow-xl dark:bg-zinc-900"
          >
            <h3
              id="unpublish-dialog-title"
              className="text-lg font-semibold text-zinc-900 dark:text-white"
            >
              {t('project.report.publication.confirmUnpublishTitle')}
            </h3>
            <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
              {t('project.report.publication.confirmUnpublishMessage')}
            </p>
            <div className="mt-6 flex justify-end gap-3">
              <Button onClick={() => setDialog(null)} variant="outline">
                {t('project.report.publication.cancel')}
              </Button>
              <Button onClick={handleUnpublish} variant="outline">
                {t('project.report.publication.unpublish')}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

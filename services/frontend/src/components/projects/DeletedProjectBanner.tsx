/**
 * Banner on every page of a soft-deleted project (migration 093).
 *
 * Only superadmins can open a deleted project at all (the API answers 404
 * to everyone else), and they open it to look inside, not to work in it:
 * the banner says so, links back to the deleted-projects list and offers the
 * restore. It reads the project from the shared store, which every project
 * page fills through fetchProject, so it needs no request of its own.
 */

'use client'

import { Button } from '@/components/shared/Button'
import { useToast } from '@/components/shared/Toast'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { projectsAPI } from '@/lib/api/projects'
import { intlTag } from '@/lib/i18n/locales'
import { useProjectStore } from '@/stores/projectStore'
import { ArrowUturnLeftIcon, TrashIcon } from '@heroicons/react/24/outline'
import Link from 'next/link'
import { useState } from 'react'

export function DeletedProjectBanner({
  projectId,
}: {
  projectId: string | null
}) {
  const { t, locale } = useI18n()
  const { user } = useAuth()
  const { addToast } = useToast()
  const currentProject = useProjectStore((s) => s.currentProject)
  const fetchProject = useProjectStore((s) => s.fetchProject)
  const [busy, setBusy] = useState(false)

  if (
    !projectId ||
    !user?.is_superadmin ||
    !currentProject ||
    currentProject.id !== projectId ||
    !currentProject.deleted_at
  ) {
    return null
  }

  const handleRestore = async () => {
    setBusy(true)
    try {
      await projectsAPI.restoreProject(projectId)
      addToast(t('projects.deleted.restored'), 'success')
      // The fresh project has no deleted_at: the banner goes away and the
      // project page becomes editable again.
      await fetchProject(projectId)
    } catch (err: any) {
      addToast(err?.message || t('common.error'), 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mx-auto max-w-7xl px-4 pt-6 sm:px-6">
      <div
        role="status"
        className="flex flex-col gap-3 rounded-lg border border-rose-200 bg-rose-50 p-4 sm:flex-row sm:items-center sm:justify-between dark:border-rose-400/30 dark:bg-rose-400/10"
        data-testid="deleted-project-banner"
      >
        <div className="flex items-start gap-3">
          <TrashIcon
            className="mt-0.5 h-5 w-5 shrink-0 text-rose-600 dark:text-rose-400"
            aria-hidden
          />
          <div>
            <p className="text-sm font-semibold text-rose-800 dark:text-rose-300">
              {t('projects.deleted.bannerTitle', {
                date: new Date(currentProject.deleted_at).toLocaleString(
                  intlTag(locale),
                ),
              })}
            </p>
            <p className="mt-1 text-sm text-rose-700 dark:text-rose-300/80">
              {t('projects.deleted.bannerBody')}
            </p>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-3">
          <Link
            href="/projects/deleted"
            className="text-sm font-medium text-rose-700 hover:text-rose-600 dark:text-rose-300 dark:hover:text-rose-200"
            data-testid="deleted-project-banner-list"
          >
            {t('projects.deleted.bannerBackToList')}
          </Link>
          <Button
            variant="outline"
            className="gap-1.5 bg-white dark:bg-transparent"
            disabled={busy}
            onClick={handleRestore}
            data-testid="deleted-project-banner-restore"
          >
            <ArrowUturnLeftIcon className="h-4 w-4" />
            {t('projects.deleted.restore')}
          </Button>
        </div>
      </div>
    </div>
  )
}

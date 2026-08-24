'use client'

import { useCallback, useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { ArrowUturnLeftIcon, TrashIcon } from '@heroicons/react/24/outline'

import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { Button } from '@/components/shared/Button'
import { ResponsiveContainer } from '@/components/shared/ResponsiveContainer'
import { useToast } from '@/components/shared/Toast'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { useConfirm } from '@/hooks/useDialogs'
import { projectsAPI } from '@/lib/api/projects'
import { projectIcon } from '@/lib/projectKind'
import type { Project } from '@/types/labelStudio'

/**
 * Superadmin-only view of soft-deleted projects (migration 093). A normal
 * "delete" anywhere on the platform only hides the project; everything can
 * be restored from here, and ONLY here can data really be destroyed.
 */
export default function DeletedProjectsPage() {
  const { t } = useI18n()
  const { user, isLoading } = useAuth()
  const router = useRouter()
  const { addToast } = useToast()
  const confirm = useConfirm()
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await projectsAPI.list(1, 200, undefined, undefined, undefined, true)
      setProjects(res.items ?? [])
    } catch {
      setProjects([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!isLoading && user && !user.is_superadmin) router.replace('/projects')
  }, [isLoading, user, router])

  useEffect(() => {
    if (user?.is_superadmin) load()
  }, [user?.is_superadmin, load])

  if (isLoading || !user?.is_superadmin) return null

  const handleRestore = async (project: Project) => {
    setBusyId(project.id)
    try {
      await projectsAPI.restoreProject(project.id)
      addToast(t('projects.deleted.restored', 'Projekt wiederhergestellt.'), 'success')
      await load()
    } catch (err: any) {
      addToast(err?.message || t('common.error', 'Fehler'), 'error')
    } finally {
      setBusyId(null)
    }
  }

  const handlePurge = async (project: Project) => {
    const ok = await confirm({
      title: t('projects.deleted.purge', 'Endgültig löschen'),
      message: t(
        'projects.deleted.purgeConfirm',
        '„{title}“ und ALLE zugehörigen Daten (Aufgaben, Abgaben, Bewertungen, Lernverläufe) endgültig löschen? Das kann nicht rückgängig gemacht werden.',
        { title: project.title }
      ),
      variant: 'danger',
      confirmText: t('projects.deleted.purge', 'Endgültig löschen'),
      confirmButtonVariant: 'filled',
    })
    if (!ok) return
    setBusyId(project.id)
    try {
      await projectsAPI.purgeProject(project.id)
      addToast(t('projects.deleted.purged', 'Projekt endgültig gelöscht.'), 'success')
      await load()
    } catch (err: any) {
      addToast(err?.message || t('common.error', 'Fehler'), 'error')
    } finally {
      setBusyId(null)
    }
  }

  return (
    <ResponsiveContainer>
      <div className="mb-6">
        <Breadcrumb
          items={[
            { label: t('navigation.projects', 'Projekte'), href: '/projects' },
            { label: t('projects.deleted.title', 'Gelöschte Projekte') },
          ]}
        />
      </div>
      <h1 className="mb-2 text-3xl font-bold text-zinc-900 dark:text-white">
        {t('projects.deleted.title', 'Gelöschte Projekte')}
      </h1>
      <p className="mb-6 text-sm text-zinc-500 dark:text-zinc-400">
        {t(
          'projects.deleted.subtitle',
          'Gelöschte Projekte sind für alle ausgeblendet, ihre Daten bleiben erhalten. Nur hier können sie wiederhergestellt oder endgültig gelöscht werden.'
        )}
      </p>

      {loading ? (
        <div className="flex min-h-[30vh] items-center justify-center">
          <div className="h-8 w-8 animate-spin rounded-full border-b-2 border-emerald-500" />
        </div>
      ) : projects.length === 0 ? (
        <p className="text-sm text-zinc-500 dark:text-zinc-400" data-testid="deleted-empty">
          {t('projects.deleted.empty', 'Keine gelöschten Projekte.')}
        </p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-700">
          <table className="min-w-full divide-y divide-zinc-200 dark:divide-zinc-700">
            <thead className="bg-zinc-50 dark:bg-zinc-800/50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
                  {t('projects.deleted.project', 'Projekt')}
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
                  {t('projects.deleted.deletedAt', 'Gelöscht am')}
                </th>
                <th className="px-6 py-3 text-right text-xs font-medium uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
                  {t('projects.deleted.actions', 'Aktionen')}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-200 bg-white dark:divide-zinc-700 dark:bg-zinc-900">
              {projects.map((p) => (
                <tr key={p.id} data-testid={`deleted-row-${p.id}`}>
                  <td className="px-6 py-4 text-sm font-medium text-zinc-900 dark:text-zinc-100">
                    <span className="mr-2" aria-hidden>
                      {projectIcon(p)}
                    </span>
                    {p.title}
                    <span className="ml-2 inline-flex items-center rounded-md bg-rose-50 px-1.5 py-0.5 text-xs font-medium text-rose-700 dark:bg-rose-400/10 dark:text-rose-400">
                      {t('projects.deleted.badge', 'Gelöscht')}
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-6 py-4 text-sm text-zinc-500 dark:text-zinc-400">
                    {p.deleted_at ? new Date(p.deleted_at).toLocaleString('de-DE') : '—'}
                  </td>
                  <td className="whitespace-nowrap px-6 py-4 text-right text-sm">
                    <Button
                      variant="outline"
                      className="mr-2 gap-1.5"
                      disabled={busyId === p.id}
                      onClick={() => handleRestore(p)}
                      data-testid={`deleted-restore-${p.id}`}
                    >
                      <ArrowUturnLeftIcon className="h-4 w-4" />
                      {t('projects.deleted.restore', 'Wiederherstellen')}
                    </Button>
                    <Button
                      variant="outline"
                      className="gap-1.5 text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-900/20"
                      disabled={busyId === p.id}
                      onClick={() => handlePurge(p)}
                      data-testid={`deleted-purge-${p.id}`}
                    >
                      <TrashIcon className="h-4 w-4" />
                      {t('projects.deleted.purge', 'Endgültig löschen')}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </ResponsiveContainer>
  )
}

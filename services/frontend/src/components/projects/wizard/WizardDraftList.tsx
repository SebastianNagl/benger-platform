/**
 * "Unfinished projects" on /projects/create: the caller's wizard drafts
 * (CORE 2.55) with Continue and Discard. Rendered by the wizard only where a
 * draft policy is registered and no draft is open; renders nothing while
 * loading, on an error, or when there is no draft.
 */

'use client'

import { Button } from '@/components/shared/Button'
import { useI18n } from '@/contexts/I18nContext'
import {
  wizardDraftsAPI,
  type WizardDraftSummary,
} from '@/lib/api/wizardDrafts'
import { intlTag } from '@/lib/i18n/locales'
import { useCallback, useEffect, useState } from 'react'
import type { DraftConfirmRequest } from './useWizardDraft'

interface WizardDraftListProps {
  onContinue: (projectId: string) => void
  confirm: (request: DraftConfirmRequest) => Promise<boolean>
  discardMessage: (projectId: string, title: string) => Promise<string>
  onError: (message: string) => void
}

export function WizardDraftList({
  onContinue,
  confirm,
  discardMessage,
  onError,
}: WizardDraftListProps) {
  const { t, locale } = useI18n()
  const [drafts, setDrafts] = useState<WizardDraftSummary[]>([])
  const [busyId, setBusyId] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setDrafts(await wizardDraftsAPI.list())
    } catch {
      setDrafts([])
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  if (drafts.length === 0) return null

  const formatDate = (iso: string | null) =>
    iso
      ? new Date(iso).toLocaleDateString(intlTag(locale), {
          day: 'numeric',
          month: 'long',
          year: 'numeric',
        })
      : ''

  const handleDiscard = async (draft: WizardDraftSummary) => {
    const ok = await confirm({
      title: t('projects.creation.wizard.draft.discardTitle'),
      message: await discardMessage(draft.project_id, draft.title),
      confirmText: t('projects.creation.wizard.draft.discardConfirm'),
      variant: 'danger',
    })
    if (!ok) return
    setBusyId(draft.project_id)
    try {
      await wizardDraftsAPI.discard(draft.project_id)
      await load()
    } catch (error) {
      onError(
        t('projects.creation.wizard.draft.discardFailed', {
          error:
            error instanceof Error && error.message
              ? error.message
              : t('projects.wizard.unknownError'),
        }),
      )
    } finally {
      setBusyId(null)
    }
  }

  return (
    <section
      className="mb-6 rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-700 dark:bg-zinc-900"
      data-testid="wizard-draft-list"
    >
      <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
        {t('projects.creation.wizard.draft.listTitle')}
      </h2>
      <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
        {t('projects.creation.wizard.draft.listHint')}
      </p>
      <ul className="mt-3 divide-y divide-zinc-100 dark:divide-zinc-800">
        {drafts.map((draft) => (
          <li
            key={draft.project_id}
            className="flex flex-wrap items-center justify-between gap-3 py-2"
            data-testid="wizard-draft-item"
          >
            <div className="min-w-0">
              <p className="truncate text-sm text-zinc-900 dark:text-zinc-100">
                {draft.icon ? `${draft.icon} ` : ''}
                {draft.title}
              </p>
              <p className="text-xs text-zinc-500 dark:text-zinc-400">
                {t('projects.creation.wizard.draft.lastChanged', {
                  date: formatDate(draft.touched_at),
                })}
                {' · '}
                {t('projects.creation.wizard.draft.expiresOn', {
                  date: formatDate(draft.expires_at),
                })}
              </p>
            </div>
            <div className="flex gap-2">
              <Button
                variant="outline"
                onClick={() => void handleDiscard(draft)}
                disabled={busyId !== null}
                data-testid="wizard-draft-discard"
              >
                {t('projects.creation.wizard.draft.discard')}
              </Button>
              <Button
                onClick={() => onContinue(draft.project_id)}
                disabled={busyId !== null}
                data-testid="wizard-draft-continue"
              >
                {t('projects.creation.wizard.draft.continue')}
              </Button>
            </div>
          </li>
        ))}
      </ul>
    </section>
  )
}

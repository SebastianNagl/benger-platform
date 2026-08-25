'use client'

import { useEffect, useState } from 'react'
import { UserGroupIcon } from '@heroicons/react/24/outline'

import { Button } from '@/components/shared/Button'
import { useToast } from '@/components/shared/Toast'
import { useI18n } from '@/contexts/I18nContext'
import { useConfirm } from '@/hooks/useDialogs'
import { sharesAPI, type Participation } from '@/lib/api/shares'
import { useSlot } from '@/lib/extensions/slots'

interface Props {
  projectId: string
  via: 'share' | 'entitlement' | 'org_exam' | null
  /** Called after the user left the project (e.g. navigate to the list). */
  onLeft: () => void
}

/**
 * Sidebar card for projects reached through the participant tier (share
 * link, discovery enrollment, org exam): says how the user got in, lets them
 * leave (GDPR Art. 7(3) — withdrawal as easy as consent) and hosts the
 * extended cohort leaderboard slot.
 */
export function ParticipantCard({ projectId, via, onLeft }: Props) {
  const { t } = useI18n()
  const confirm = useConfirm()
  const { addToast } = useToast()
  const CohortLeaderboard = useSlot('ProjectCohortLeaderboard')
  const [participation, setParticipation] = useState<Participation | null>(null)
  const [leaving, setLeaving] = useState(false)

  useEffect(() => {
    let cancelled = false
    sharesAPI
      .getParticipation(projectId)
      .then((p) => {
        if (!cancelled) setParticipation(p)
      })
      .catch(() => {
        if (!cancelled) setParticipation(null)
      })
    return () => {
      cancelled = true
    }
  }, [projectId])

  const effectiveVia = participation?.via ?? via ?? 'share'
  const canLeave = participation?.can_leave ?? false
  const blockedReason = participation?.cannot_leave_reason ?? null

  const handleLeave = async () => {
    const ok = await confirm({
      title: t('project.participant.leave', 'Projekt verlassen'),
      message: t(
        'project.participant.leaveConfirm',
        'Sie verlieren den Zugang zu diesem Projekt. Ihre bisherigen Abgaben bleiben erhalten.'
      ),
      variant: 'warning',
      confirmText: t('project.participant.leave', 'Projekt verlassen'),
    })
    if (!ok) return
    setLeaving(true)
    try {
      await sharesAPI.leaveProject(projectId)
      addToast(t('project.participant.left', 'Sie haben das Projekt verlassen.'), 'success')
      onLeft()
    } catch (err: any) {
      addToast(err?.message || t('common.error', 'Fehler'), 'error')
    } finally {
      setLeaving(false)
    }
  }

  return (
    <div
      className="rounded-lg border border-zinc-200 bg-white p-6 shadow-sm ring-1 ring-zinc-900/5 dark:border-zinc-700 dark:bg-zinc-900 dark:ring-white/10"
      data-testid="participant-card"
    >
      <h2 className="mb-2 flex items-center gap-2 text-lg font-semibold text-zinc-900 dark:text-white">
        <UserGroupIcon className="h-5 w-5 text-sky-500 dark:text-sky-400" />
        {t('project.participant.title', 'Teilnahme')}
      </h2>
      <p className="mb-4 text-sm text-zinc-600 dark:text-zinc-400" data-testid="participant-via">
        {t(`projects.list.participantVia.${effectiveVia}`, 'Beigetreten')}
      </p>
      {canLeave ? (
        <Button
          variant="outline"
          onClick={handleLeave}
          disabled={leaving}
          data-testid="participant-leave"
          className="w-full"
        >
          {t('project.participant.leave', 'Projekt verlassen')}
        </Button>
      ) : participation ? (
        <p className="text-xs text-zinc-500 dark:text-zinc-400" data-testid="participant-cannot-leave">
          {blockedReason === 'entitlement_not_leavable'
            ? t(
                'project.participant.cannotLeavePurchase',
                'Gekaufter Zugang kann nicht verlassen werden.'
              )
            : t(
                'project.participant.cannotLeaveOrg',
                'Der Zugang kommt über Ihre Organisation und wird dort verwaltet.'
              )}
        </p>
      ) : null}
      {CohortLeaderboard && (
        <div className="mt-6" data-testid="participant-cohort">
          <CohortLeaderboard projectId={projectId} />
        </div>
      )}
    </div>
  )
}

export default ParticipantCard

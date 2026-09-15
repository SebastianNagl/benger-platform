'use client'

import { UserGroupIcon } from '@heroicons/react/24/outline'
import { useCallback, useEffect, useState } from 'react'

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
 * Props the `ProjectCohortLeaderboard` slot component receives.
 *
 * The slot reports whether it has anything to show through `onEmpty`: call
 * it with `true` once the cohort turned out to have no rows, with `false`
 * once rows are there. The callback identity is stable, so it is safe in an
 * effect dependency list. Until the slot reports, the card treats the
 * cohort as possibly non-empty and keeps the box mounted so the slot can
 * fetch. A slot that never calls `onEmpty` keeps the pre-contract behaviour
 * (always shown).
 */
export interface ProjectCohortLeaderboardSlotProps {
  projectId: string
  onEmpty?: (empty: boolean) => void
}

/**
 * Sidebar card for projects reached through the participant tier (share
 * link, discovery enrollment, org exam): says how the user got in, lets them
 * leave (GDPR Art. 7(3) — withdrawal as easy as consent) and hosts the
 * extended cohort leaderboard slot.
 *
 * The card renders nothing when it has nothing actionable: the participation
 * is known and cannot be left (org exam, purchase) AND the cohort is empty,
 * i.e. no slot is registered (community edition) or the slot reported
 * `onEmpty(true)`. A leavable participation always shows the card (the leave
 * button is the GDPR withdrawal); its cohort box collapses while the slot
 * reports empty instead of framing an empty table. While the participation
 * is loading, or when that fetch fails, the card shows the `via` text as
 * before, so a page whose participation endpoint is unavailable still says
 * how the user got in.
 */
export function ParticipantCard({ projectId, via, onLeft }: Props) {
  const { t } = useI18n()
  const confirm = useConfirm()
  const { addToast } = useToast()
  const CohortLeaderboard = useSlot('ProjectCohortLeaderboard')
  const [participation, setParticipation] = useState<Participation | null>(null)
  const [leaving, setLeaving] = useState(false)
  // null until the slot reports; see ProjectCohortLeaderboardSlotProps.
  const [cohortEmpty, setCohortEmpty] = useState<boolean | null>(null)
  const onCohortEmpty = useCallback((empty: boolean) => {
    setCohortEmpty(empty)
  }, [])

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
  const cohortIsEmpty = !CohortLeaderboard || cohortEmpty === true

  const handleLeave = async () => {
    const ok = await confirm({
      title: t('project.participant.leave', 'Projekt verlassen'),
      message: t(
        'project.participant.leaveConfirm',
        'Sie verlieren den Zugang zu diesem Projekt. Ihre bisherigen Abgaben bleiben erhalten.',
      ),
      variant: 'warning',
      confirmText: t('project.participant.leave', 'Projekt verlassen'),
    })
    if (!ok) return
    setLeaving(true)
    try {
      await sharesAPI.leaveProject(projectId)
      addToast(
        t('project.participant.left', 'Sie haben das Projekt verlassen.'),
        'success',
      )
      onLeft()
    } catch (err: any) {
      addToast(err?.message || t('common.error', 'Fehler'), 'error')
    } finally {
      setLeaving(false)
    }
  }

  // Nothing actionable: the user cannot leave and there is no cohort to show.
  if (participation && !canLeave && cohortIsEmpty) return null

  return (
    <div
      className="rounded-lg border border-zinc-200 bg-white p-6 shadow-sm ring-1 ring-zinc-900/5 dark:border-zinc-700 dark:bg-zinc-900 dark:ring-white/10"
      data-testid="participant-card"
    >
      <h2 className="mb-2 flex items-center gap-2 text-lg font-semibold text-zinc-900 dark:text-white">
        <UserGroupIcon className="h-5 w-5 text-sky-500 dark:text-sky-400" />
        {t('project.participant.title', 'Teilnahme')}
      </h2>
      <p
        className="mb-4 text-sm text-zinc-600 dark:text-zinc-400"
        data-testid="participant-via"
      >
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
        <p
          className="text-xs text-zinc-500 dark:text-zinc-400"
          data-testid="participant-cannot-leave"
        >
          {blockedReason === 'entitlement_not_leavable'
            ? t(
                'project.participant.cannotLeavePurchase',
                'Gekaufter Zugang kann nicht verlassen werden.',
              )
            : t(
                'project.participant.cannotLeaveOrg',
                'Der Zugang kommt über Ihre Organisation und wird dort verwaltet.',
              )}
        </p>
      ) : null}
      {CohortLeaderboard && (
        // Stays mounted while empty (hidden, not unmounted) so the slot can
        // report rows that arrive later.
        <div
          className={cohortEmpty ? 'hidden' : 'mt-6'}
          data-testid="participant-cohort"
          data-empty={cohortEmpty === null ? undefined : String(cohortEmpty)}
        >
          <CohortLeaderboard projectId={projectId} onEmpty={onCohortEmpty} />
        </div>
      )}
    </div>
  )
}

export default ParticipantCard

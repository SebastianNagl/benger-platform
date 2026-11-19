/**
 * Agreement block of the evaluations page: loads the project's annotator
 * agreement and renders it in a card. Renders nothing while loading, on an
 * error, or when no task has two annotators, so projects without overlap
 * see no change.
 */

'use client'

import { AnnotatorAgreement } from '@/components/evaluation/AnnotatorAgreement'
import { Card } from '@/components/shared/Card'
import { useI18n } from '@/contexts/I18nContext'
import {
  getAnnotatorAgreement,
  hasAgreement,
  type AnnotatorAgreementSummary,
} from '@/lib/api/agreement'
import { useEffect, useState } from 'react'

export function AnnotatorAgreementCard({ projectId }: { projectId: string }) {
  const { t } = useI18n()
  // Keyed by project, so a project switch never shows the previous numbers.
  const [loaded, setLoaded] = useState<{
    projectId: string
    agreement: AnnotatorAgreementSummary
  } | null>(null)

  useEffect(() => {
    let cancelled = false
    getAnnotatorAgreement(projectId)
      .then((res) => {
        if (!cancelled && res?.available && hasAgreement(res)) {
          setLoaded({ projectId, agreement: res })
        }
      })
      .catch((err) => {
        // The block is optional: a failed read hides it, the rest of the
        // page is unaffected.
        console.warn('Annotator agreement unavailable', err)
      })
    return () => {
      cancelled = true
    }
  }, [projectId])

  const agreement = loaded?.projectId === projectId ? loaded.agreement : null
  if (!agreement) return null
  return (
    <Card className="p-6" data-testid="annotator-agreement-card">
      <h3 className="mb-1 text-lg font-semibold dark:text-white">
        {t('evaluation.annotatorAgreement.title')}
      </h3>
      <p className="mb-4 text-sm text-zinc-500 dark:text-zinc-400">
        {t('evaluation.annotatorAgreement.description')}
      </p>
      <AnnotatorAgreement agreement={agreement} />
    </Card>
  )
}

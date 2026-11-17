'use client'

import { useI18n } from '@/contexts/I18nContext'

import { useSlot } from '@/lib/extensions/slots'
import { useParams } from 'next/navigation'

/**
 * Host route for the check step of a project's grading sheets.
 *
 * The review workflow (checklist, edit log, confirmation, reordering) ships
 * in the extended package via the 'ProjectRubricReviewPage' slot; the
 * platform only provides the route and the fallback.
 */
export default function ProjectRubricReviewPage() {
  const { t } = useI18n()
  const params = useParams<{ id: string }>()
  const projectId = params!.id
  const RubricReview = useSlot('ProjectRubricReviewPage')

  if (!RubricReview) {
    return (
      <div className="flex min-h-[400px] items-center justify-center">
        <p className="text-zinc-500 dark:text-zinc-400">
          {t('project.rubricReview.extendedRequired')}
        </p>
      </div>
    )
  }

  // eslint-disable-next-line react-hooks/static-components
  return <RubricReview projectId={projectId} />
}

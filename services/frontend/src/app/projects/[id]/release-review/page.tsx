'use client'

import { useI18n } from '@/contexts/I18nContext'

import { useSlot } from '@/lib/extensions/slots'
import { useParams } from 'next/navigation'

/**
 * Host route for reviewing a project's gradings before their release.
 *
 * Results that wait for a teacher's release (feedback-only judge rows,
 * core 2.41) are listed, edited and released in bulk by the extended
 * package via the 'ProjectReleaseReviewPage' slot; the platform only
 * provides the route and the fallback.
 */
export default function ProjectReleaseReviewPage() {
  const { t } = useI18n()
  const params = useParams<{ id: string }>()
  const projectId = params!.id
  const ReleaseReview = useSlot('ProjectReleaseReviewPage')

  if (!ReleaseReview) {
    return (
      <div className="flex min-h-[400px] items-center justify-center">
        <p className="text-zinc-500 dark:text-zinc-400">
          {t('project.releaseReview.extendedRequired')}
        </p>
      </div>
    )
  }

  // eslint-disable-next-line react-hooks/static-components
  return <ReleaseReview projectId={projectId} />
}

/**
 * Full-page notice for a participant whose task read was refused with 403
 * `{code: "exam_not_ready"}` (see `isExamNotReadyError`): the exam is held
 * closed until its grading sheet is checked. Shown instead of an
 * initialization error or "task not found", which would wrongly suggest the
 * exam is broken or its tasks were deleted.
 */

'use client'

import { Button } from '@/components/shared/Button'
import { Card } from '@/components/shared/Card'
import { useI18n } from '@/contexts/I18nContext'
import { ArrowLeftIcon, ClockIcon } from '@heroicons/react/24/outline'
import { useRouter } from 'next/navigation'

interface ExamNotReadyNoticeProps {
  projectId: string | undefined
}

export function ExamNotReadyNotice({ projectId }: ExamNotReadyNoticeProps) {
  const router = useRouter()
  const { t } = useI18n()
  return (
    <div className="flex min-h-screen flex-col" data-testid="exam-not-ready">
      {projectId && (
        <div className="border-b px-6 py-4">
          <Button
            variant="text"
            onClick={() => router.push(`/projects/${projectId}`)}
          >
            <ArrowLeftIcon className="mr-2 h-4 w-4" />
            {t('annotation.backToProject')}
          </Button>
        </div>
      )}
      <div className="flex flex-1 items-center justify-center px-4">
        <Card className="mx-auto max-w-lg text-center">
          <div className="space-y-6 p-8">
            <ClockIcon
              className="mx-auto h-16 w-16 text-emerald-600"
              aria-hidden="true"
            />
            {/* One sentence, no separate heading: the platform and the
                extended project page use the same wording. */}
            <p className="text-lg font-medium text-zinc-900 dark:text-white">
              {t('annotation.examNotReady.description')}
            </p>
          </div>
        </Card>
      </div>
    </div>
  )
}

'use client'

import { useI18n } from '@/contexts/I18nContext'

import { useSlot } from '@/lib/extensions/slots'
import { useParams } from 'next/navigation'

export default function ProjectLivePage() {
  const { t } = useI18n()
  const params = useParams<{ id: string }>()
  const projectId = params!.id
  const LiveComponent = useSlot('ProjectLivePage')

  if (!LiveComponent) {
    return (
      <div className="flex min-h-[400px] items-center justify-center">
        <p className="text-zinc-500 dark:text-zinc-400">
          {t('student.community.unavailable')}
        </p>
      </div>
    )
  }

  // eslint-disable-next-line react-hooks/static-components
  return <LiveComponent projectId={projectId} />
}

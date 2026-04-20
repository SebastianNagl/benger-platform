'use client'

import { getSlot } from '@/lib/extensions/slots'
import { useParams } from 'next/navigation'

export default function FeedbackPage() {
  const params = useParams()
  const projectId = params.id as string
  const FeedbackComponent = getSlot('FeedbackPage')

  if (!FeedbackComponent) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <p className="text-zinc-500 dark:text-zinc-400">
          Feedback feature is not available in the community edition.
        </p>
      </div>
    )
  }

  return <FeedbackComponent projectId={projectId} />
}

'use client'

import { useSlot } from '@/lib/extensions/slots'
import { useParams } from 'next/navigation'

export default function ReviewPage() {
  const params = useParams()
  const projectId = params.id as string
  const ReviewComponent = useSlot('ReviewPage')

  if (!ReviewComponent) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <p className="text-zinc-500 dark:text-zinc-400">
          Review feature is not available in the community edition.
        </p>
      </div>
    )
  }

  return <ReviewComponent projectId={projectId} />
}

'use client'

import { useSlot } from '@/lib/extensions/slots'
import { useParams } from 'next/navigation'

export default function ReviewPage() {
  const params = useParams<{ id: string }>()
  const projectId = params!.id
  const ReviewComponent = useSlot('ReviewPage')

  if (!ReviewComponent) {
    return (
      <div className="flex min-h-[400px] items-center justify-center">
        <p className="text-zinc-500 dark:text-zinc-400">
          Review feature is not available in the community edition.
        </p>
      </div>
    )
  }

  // eslint-disable-next-line react-hooks/static-components
  return <ReviewComponent projectId={projectId} />
}

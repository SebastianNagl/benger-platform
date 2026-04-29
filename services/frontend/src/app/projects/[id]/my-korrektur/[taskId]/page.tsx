'use client'

import { useSlot } from '@/lib/extensions/slots'
import { useParams } from 'next/navigation'

export default function MyKorrekturPage() {
  const params = useParams<{ id: string; taskId: string }>()
  const projectId = params!.id
  const taskId = params!.taskId
  const MyKorrekturComponent = useSlot('MyKorrekturPage')

  if (!MyKorrekturComponent) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <p className="text-zinc-500 dark:text-zinc-400">
          Korrektur feature is not available in the community edition.
        </p>
      </div>
    )
  }

  return <MyKorrekturComponent projectId={projectId} taskId={taskId} />
}

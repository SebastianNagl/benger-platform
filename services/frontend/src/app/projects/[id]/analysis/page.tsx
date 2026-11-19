import { evaluationsPath } from '@/lib/results/paths'
import { permanentRedirect } from 'next/navigation'

/**
 * The analysis runs of a project moved to the evaluations page, where every
 * result is viewed (`/evaluations?projectId=…&type=analysis`). This route
 * survives as a permanent redirect so bookmarks and stored links keep
 * working; `?from=<runId>` becomes `newRunFrom`, which opens the start
 * dialog prefilled with that run's spec.
 */
export default async function ProjectAnalysisRedirect({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>
  searchParams: Promise<Record<string, string | string[] | undefined>>
}) {
  const { id } = await params
  const { from } = await searchParams
  permanentRedirect(
    evaluationsPath({
      projectId: id,
      type: 'analysis',
      newRunFrom: typeof from === 'string' && from ? from : null,
    }),
  )
}

import { analysisRunPath } from '@/lib/results/paths'
import { permanentRedirect } from 'next/navigation'

/**
 * The analysis run page moved to /evaluations/analysis/[runId], next to the
 * evaluation run page. This route survives as a permanent redirect so
 * bookmarks and stored links (overlays included) keep working.
 */
export default async function AnalysisRunRedirect({
  params,
}: {
  params: Promise<{ id: string; runId: string }>
}) {
  const { runId } = await params
  permanentRedirect(analysisRunPath(runId))
}

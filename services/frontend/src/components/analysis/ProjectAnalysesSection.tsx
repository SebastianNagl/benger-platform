'use client'

/**
 * The Analyses part of the project page's Evaluation card: where analyses
 * are configured and started, next to the metric evaluations. It holds the
 * project's variant designs (status, content hash, check, freeze, import),
 * its saved analysis plans and the Start analysis dialog the evaluations
 * page shares. A started run opens in the evaluations page's Analyses view,
 * which follows it until it completes.
 *
 * The host shows it to the CONTRIBUTOR and ORG_ADMIN roles only (the roles
 * the API lets start runs, save plans and freeze designs).
 */

import { AnalysisPlansPanel } from '@/components/analysis/AnalysisPlansPanel'
import { StartAnalysisDialog } from '@/components/analysis/StartAnalysisDialog'
import { VariantDesignsTable } from '@/components/analysis/VariantDesignsTable'
import { Button } from '@/components/shared/Button'
import { useI18n } from '@/contexts/I18nContext'
import type { AnalysisPlan, AnalysisRun } from '@/lib/api/analysis'
import type { VariantDesign } from '@/lib/api/variantDesigns'
import { evaluationsPath } from '@/lib/results/paths'
import { PlayIcon } from '@heroicons/react/24/outline'
import { useRouter } from 'next/navigation'
import { useCallback, useEffect, useRef, useState } from 'react'

export interface ProjectAnalysesSectionProps {
  projectId: string
  /** Called when the designs or plans load or change (counts for a badge). */
  onSummaryChange?: (summary: { designs: number; plans: number }) => void
}

export function ProjectAnalysesSection({
  projectId,
  onSummaryChange,
}: ProjectAnalysesSectionProps) {
  const { t } = useI18n()
  const router = useRouter()
  const [designKeys, setDesignKeys] = useState<string[]>([])
  // null until loaded; the host hears of the counts once both are known.
  const [counts, setCounts] = useState<{
    designs: number | null
    plans: number | null
  }>({ designs: null, plans: null })
  const [start, setStart] = useState<{ planId: string | null } | null>(null)

  const countsRef = useRef(counts)
  const summaryChanged = useRef(onSummaryChange)
  useEffect(() => {
    summaryChanged.current = onSummaryChange
  }, [onSummaryChange])

  const report = useCallback(
    (next: Partial<{ designs: number; plans: number }>) => {
      const merged = { ...countsRef.current, ...next }
      countsRef.current = merged
      setCounts(merged)
      if (merged.designs !== null && merged.plans !== null)
        summaryChanged.current?.({
          designs: merged.designs,
          plans: merged.plans,
        })
    },
    [],
  )

  const onDesignsChange = useCallback(
    (designs: VariantDesign[]) => {
      setDesignKeys(designs.map((d) => d.key))
      report({ designs: designs.length })
    },
    [report],
  )
  const onPlansChange = useCallback(
    (plans: AnalysisPlan[]) => report({ plans: plans.length }),
    [report],
  )

  const onStarted = (run: AnalysisRun) => {
    setStart(null)
    router.push(evaluationsPath({ projectId, type: 'analysis', run: run.id }))
  }

  return (
    <div className="space-y-6" data-testid="project-analyses">
      <p className="text-sm text-zinc-500 dark:text-zinc-400">
        {t('analysis.section.description')}
      </p>
      <VariantDesignsTable
        projectId={projectId}
        onDesignsChange={onDesignsChange}
      />
      <AnalysisPlansPanel
        projectId={projectId}
        designKeys={designKeys}
        onStartPlan={(planId) => setStart({ planId })}
        onPlansChange={onPlansChange}
      />
      <div className="flex flex-wrap items-center justify-between gap-2 border-t pt-4 dark:border-zinc-700">
        <p className="text-xs text-zinc-500 dark:text-zinc-400">
          {counts.designs === 0
            ? t('analysis.section.needsDesign')
            : t('analysis.section.startHint')}
        </p>
        <Button
          onClick={() => setStart({ planId: null })}
          className="flex items-center gap-2 text-sm"
          data-testid="project-analyses-start"
        >
          <PlayIcon className="h-4 w-4" />
          {t('analysis.section.start')}
        </Button>
      </div>
      <StartAnalysisDialog
        isOpen={start !== null}
        onClose={() => setStart(null)}
        projectId={projectId}
        planId={start?.planId ?? null}
        onStarted={onStarted}
      />
    </div>
  )
}

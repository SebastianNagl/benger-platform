'use client'

/**
 * Analysis run page (/evaluations/analysis/[runId], next to the evaluation
 * run page /evaluations/[id]): one run of a variant-experiment analysis with its
 * status, the forest plot of a contrast (optional equivalence band;
 * Bradley-Terry estimands as strength forests), the profile of estimates
 * over an ordered scope, every estimate with its family and adjusted
 * p-value, the examples of a contrast (units of the run's variant design),
 * the compliance findings slot, the provenance (spec and frame hashes,
 * versions), the variant designs the run read, the spec and the fits, and
 * the frame download. A pending or running run is polled until it
 * finishes. The project is the run's own; the old path
 * /projects/[id]/analysis/[runId] redirects here.
 */

import {
  EstimateProfiles,
  profileGroups,
} from '@/components/analysis/EstimateProfiles'
import { EstimatesForest } from '@/components/analysis/EstimatesForest'
import { EstimatesTable } from '@/components/analysis/EstimatesTable'
import { ExamplesPanel } from '@/components/analysis/ExamplesPanel'
import { RunProvenance } from '@/components/analysis/RunProvenance'
import { RunFits, RunSpec } from '@/components/analysis/RunSpecAndFits'
import { VariantDesignsLoader } from '@/components/analysis/VariantDesignPanel'
import { ComplianceInlineSlot } from '@/components/compliance/ComplianceSlot'
import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { Button } from '@/components/shared/Button'
import { FeatureFlagGate } from '@/components/shared/FeatureFlagGate'
import { RunStatusBadge } from '@/components/shared/RunStatusBadge'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { specDesigns } from '@/lib/analysis/profile'
import {
  analysisAPI,
  isRunActive,
  statusOf,
  type AnalysisEstimate,
  type AnalysisRun,
} from '@/lib/api/analysis'
import { projectsAPI } from '@/lib/api/projects'
import { VARIANT_EXPERIMENTS } from '@/lib/featureFlags/platformFlags'
import { intlTag } from '@/lib/i18n/locales'
import { evaluationsPath } from '@/lib/results/paths'
import {
  ArrowDownTrayIcon,
  DocumentDuplicateIcon,
} from '@heroicons/react/24/outline'
import { useParams } from 'next/navigation'
import { useCallback, useEffect, useState, type ReactNode } from 'react'

/** Poll interval while the run is pending or running. */
const RUN_POLL_MS = 3000

function Section({
  title,
  description,
  children,
  testId,
}: {
  title: string
  description?: string
  children: ReactNode
  testId?: string
}) {
  return (
    <section
      className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-900"
      data-testid={testId}
    >
      <h2 className="text-base font-semibold text-zinc-900 dark:text-white">
        {title}
      </h2>
      {description && (
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
          {description}
        </p>
      )}
      <div className="mt-4">{children}</div>
    </section>
  )
}

function formatDate(value: string | null | undefined, locale: string) {
  if (!value) return '—'
  try {
    return new Date(value).toLocaleString(intlTag(locale), {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  } catch {
    return value
  }
}

type LoadState =
  | { kind: 'loading' }
  | { kind: 'notFound' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; run: AnalysisRun }

function AnalysisRunPageContent() {
  const { t, locale } = useI18n()
  const { user } = useAuth()
  const params = useParams<{ runId: string }>()
  const runId = typeof params?.runId === 'string' ? params.runId : ''

  const [state, setState] = useState<LoadState>({ kind: 'loading' })
  const [estimates, setEstimates] = useState<AnalysisEstimate[] | null>(null)
  const [estimatesError, setEstimatesError] = useState<string | null>(null)
  const [projectTitle, setProjectTitle] = useState<string | null>(null)
  const [projectRole, setProjectRole] = useState<string | null>(null)
  const [projectCanEdit, setProjectCanEdit] = useState(false)
  const [failedPolls, setFailedPolls] = useState(0)
  const [downloading, setDownloading] = useState(false)
  const [downloadError, setDownloadError] = useState<string | null>(null)

  const loadRun = useCallback(
    async (isPoll = false) => {
      try {
        const run = await analysisAPI.getRun(runId)
        setState({ kind: 'ready', run })
        return run
      } catch (error) {
        if (isPoll && statusOf(error) !== 404) {
          setFailedPolls((n) => n + 1)
          return null
        }
        if (statusOf(error) === 404) setState({ kind: 'notFound' })
        else
          setState({
            kind: 'error',
            message: (error as Error)?.message || t('analysis.run.loadFailed'),
          })
        return null
      }
    },
    // t is stable per locale; a locale switch need not reload the run.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [runId],
  )

  useEffect(() => {
    if (runId) void loadRun()
  }, [runId, loadRun])

  const projectId = state.kind === 'ready' ? String(state.run.project_id) : ''

  useEffect(() => {
    if (!projectId) return
    let cancelled = false
    projectsAPI
      .get(projectId)
      .then((project) => {
        if (cancelled) return
        setProjectTitle(project?.title ?? null)
        setProjectRole(project?.effective_role ?? null)
        setProjectCanEdit(project?.can_edit === true)
      })
      .catch(() => {
        // The breadcrumb falls back to a generic label.
      })
    return () => {
      cancelled = true
    }
  }, [projectId])

  const run = state.kind === 'ready' ? state.run : null
  const status = run?.status

  // Poll while the run can still change.
  useEffect(() => {
    if (!status || !isRunActive(status)) return
    const timer = window.setTimeout(() => void loadRun(true), RUN_POLL_MS)
    return () => window.clearTimeout(timer)
  }, [status, run, failedPolls, loadRun])

  // Estimates once the run has completed (failed runs have none).
  useEffect(() => {
    if (status !== 'completed') return
    let cancelled = false
    setEstimatesError(null)
    analysisAPI
      .listEstimates(runId)
      .then((items) => {
        if (!cancelled) setEstimates(items)
      })
      .catch((error) => {
        if (!cancelled)
          setEstimatesError(
            (error as Error)?.message || t('analysis.estimates.loadFailed'),
          )
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, runId])

  const mayStartRun = !!user?.is_superadmin || projectCanEdit
  const mayDownloadFrame =
    !!user?.is_superadmin ||
    projectRole === 'ORG_ADMIN' ||
    projectRole === 'CONTRIBUTOR'

  const downloadFrame = async () => {
    setDownloading(true)
    setDownloadError(null)
    try {
      const { url } = await analysisAPI.getFrameDownload(runId)
      window.location.assign(url)
    } catch (error) {
      setDownloadError(
        statusOf(error) === 403
          ? t('analysis.run.frameForbidden')
          : (error as Error)?.message || t('analysis.run.frameFailed'),
      )
    } finally {
      setDownloading(false)
    }
  }

  const breadcrumb = (
    <div className="mb-4">
      <Breadcrumb
        items={[
          { label: t('navigation.dashboard'), href: '/dashboard' },
          { label: t('navigation.evaluation'), href: '/evaluations' },
          ...(projectId
            ? [
                {
                  label: projectTitle || t('analysis.project'),
                  href: evaluationsPath({ projectId, type: 'analysis' }),
                },
              ]
            : []),
          { label: run?.name || t('analysis.run.title') },
        ]}
      />
    </div>
  )

  if (state.kind === 'loading') {
    return (
      <div className="container mx-auto px-4 py-8">
        {breadcrumb}
        <p className="text-sm text-zinc-500" role="status">
          {t('analysis.run.loading')}
        </p>
      </div>
    )
  }

  if (state.kind === 'notFound' || state.kind === 'error') {
    return (
      <div className="container mx-auto px-4 py-8">
        {breadcrumb}
        <div
          className="rounded border border-red-300 bg-red-50 p-4 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300"
          data-testid="analysis-run-error"
        >
          {state.kind === 'notFound'
            ? t('analysis.run.notFound')
            : state.message}
        </div>
      </div>
    )
  }

  const r = state.run
  const warnings = r.warnings ?? []

  return (
    <div className="container mx-auto space-y-6 px-4 py-8">
      {breadcrumb}

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-2xl font-bold tracking-tight break-words text-zinc-900 sm:text-3xl dark:text-white">
              {r.name}
            </h1>
            <RunStatusBadge status={r.status} />
          </div>
          <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
            {t('analysis.run.timeline', {
              created: formatDate(r.created_at, locale),
              completed: formatDate(r.completed_at, locale),
            })}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {mayStartRun && (
            <Button
              variant="outline"
              href={evaluationsPath({
                projectId,
                type: 'analysis',
                newRunFrom: r.id,
              })}
            >
              <DocumentDuplicateIcon className="mr-2 h-4 w-4" />
              {t('analysis.run.reuseSpec')}
            </Button>
          )}
          {r.frame_available && mayDownloadFrame && (
            <Button
              variant="primary"
              onClick={downloadFrame}
              disabled={downloading}
              data-testid="analysis-frame-download"
            >
              <ArrowDownTrayIcon className="mr-2 h-4 w-4" />
              {downloading
                ? t('analysis.run.frameDownloading')
                : t('analysis.run.frameDownload')}
            </Button>
          )}
        </div>
      </div>

      {downloadError && (
        <div
          className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300"
          role="alert"
        >
          {downloadError}
        </div>
      )}

      {isRunActive(r.status) && (
        <div
          className="rounded border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-900/20 dark:text-amber-300"
          role="status"
          data-testid="analysis-run-active"
        >
          {t(`analysis.run.${r.status}`)}
        </div>
      )}

      {r.status === 'failed' && (
        <div
          className="rounded border border-red-300 bg-red-50 p-4 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300"
          role="alert"
          data-testid="analysis-run-failed"
        >
          <p className="font-medium">{t('analysis.run.failed')}</p>
          {r.error_message && <p className="mt-1">{r.error_message}</p>}
        </div>
      )}

      {warnings.length > 0 && (
        <div
          className="rounded border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-900/20 dark:text-amber-300"
          data-testid="analysis-run-warnings"
        >
          <p className="font-medium">
            {t('analysis.run.warnings', { count: warnings.length })}
          </p>
          <ul className="mt-1 list-disc space-y-0.5 pl-5">
            {warnings.map((w, i) => (
              <li key={i} className="break-words">
                {w}
              </li>
            ))}
          </ul>
        </div>
      )}

      {r.status === 'completed' && (
        <>
          {estimatesError && (
            <div
              className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300"
              role="alert"
            >
              {estimatesError}
            </div>
          )}
          {!estimates && !estimatesError && (
            <p className="text-sm text-zinc-500" role="status">
              {t('analysis.estimates.loading')}
            </p>
          )}
          {estimates && (
            <>
              <Section
                title={t('analysis.forest.title')}
                description={t('analysis.forest.description')}
                testId="analysis-forest-section"
              >
                <EstimatesForest run={r} estimates={estimates} />
              </Section>
              {profileGroups(estimates).length > 0 && (
                <Section
                  title={t('analysis.views.profile.title')}
                  description={t('analysis.views.profile.description')}
                  testId="analysis-profile-section"
                >
                  <EstimateProfiles run={r} estimates={estimates} />
                </Section>
              )}
              <Section
                title={t('analysis.estimates.title')}
                description={t('analysis.estimates.description')}
                testId="analysis-estimates-section"
              >
                <EstimatesTable estimates={estimates} />
              </Section>
              {specDesigns(r).length > 0 && (
                <Section
                  title={t('analysis.views.examples.title')}
                  description={t('analysis.views.examples.description')}
                  testId="analysis-examples-section"
                >
                  <ExamplesPanel
                    projectId={projectId}
                    run={r}
                    estimates={estimates}
                  />
                </Section>
              )}
              <div
                className="empty:hidden"
                data-testid="analysis-run-findings-slot"
              >
                <ComplianceInlineSlot
                  slot="AnalysisRunFindings"
                  props={{ projectId, run: r, estimates }}
                />
              </div>
            </>
          )}
        </>
      )}

      <Section
        title={t('analysis.provenance.title')}
        description={t('analysis.provenance.description')}
        testId="analysis-provenance-section"
      >
        <RunProvenance run={r} />
      </Section>

      {specDesigns(r).length > 0 && (
        <VariantDesignsLoader
          projectId={projectId}
          keys={specDesigns(r)}
          frame={(content) => (
            <Section
              title={t('analysis.views.design.title')}
              description={t('analysis.views.design.description')}
              testId="analysis-designs-section"
            >
              {content}
            </Section>
          )}
        />
      )}

      <Section title={t('analysis.spec.title')} testId="analysis-spec-section">
        <RunSpec run={r} />
      </Section>

      {r.fits && r.fits.length > 0 && (
        <Section
          title={t('analysis.fits.title')}
          description={t('analysis.fits.description')}
          testId="analysis-fits-section"
        >
          <RunFits fits={r.fits} />
        </Section>
      )}
    </div>
  )
}

/** Behind the variant_experiments flag: not found while it is off. */
export default function AnalysisRunPage() {
  return (
    <FeatureFlagGate flag={VARIANT_EXPERIMENTS}>
      <AnalysisRunPageContent />
    </FeatureFlagGate>
  )
}

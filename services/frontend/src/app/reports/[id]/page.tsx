/**
 * Report Viewer Page - publication-quality view of a project report.
 *
 * Renders `content` (editor prose + presentation settings) together with the
 * server-computed `snapshot` (ReportSnapshot). Works for anonymous visitors:
 * nothing here is gated on auth; a report author merely gets an edit link,
 * and a 401/403 turns into a friendly "not public" card inside the normal
 * layout.
 *
 * The report reads as the project's paper: Data (with variant designs and
 * import provenance), Annotation, Generation (with per-model outcome rates),
 * Evaluation, Human evaluation, Analyses (the analysis runs and exhibits the
 * author chose; the conclusions follow them), the Reproducibility appendix
 * and a citation block. Sections without data hide themselves, so an annotation-only
 * project gets a short, complete report. The page prints as a document
 * (see the print rules in styles/tailwind.css).
 */

'use client'

import { AnnotatorAgreement } from '@/components/evaluation/AnnotatorAgreement'
import {
  AnalysesSection,
  CitationBlock,
  CodeValidations,
  codeValidationsOf,
  DataProvenance,
  EvaluationSection,
  GenerationDetails,
  hasAnalyses,
  hasHumanEvaluations,
  HumanEvaluationSection,
  ModelChips,
  ParticipantsList,
  Prose,
  ReportHeader,
  ReportSection,
  ReproducibilitySection,
  StatTiles,
  StatusCard,
  SubHeading,
  type StatTile,
} from '@/components/reports/view'
import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { ResponsiveContainer } from '@/components/shared/ResponsiveContainer'
import { useI18n } from '@/contexts/I18nContext'
import { hasAgreement } from '@/lib/api/agreement'
import { getMetricDefinitions } from '@/lib/api/evaluation-types'
import { getReportData, type ReportResponse } from '@/lib/api/reports'
import { formatCount, type MetricRegistry } from '@/lib/reports/format'
import { analysisRunPath } from '@/lib/results/paths'
import type { ReportChartsConfig, ReportSnapshot } from '@/types/report'
import Link from 'next/link'
import {
  use,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'

type StoredSections = ReportResponse['content']['sections']
type ViewSections = {
  [K in keyof StoredSections]-?: Partial<NonNullable<StoredSections[K]>>
}

/**
 * Older stored reports and minimal content can lack any section, so every
 * absent section reads as empty settings (its defaults apply) instead of
 * crashing the page.
 */
function readSections(report: ReportResponse | null): ViewSections | null {
  const stored = report?.content?.sections as
    Partial<StoredSections> | undefined
  if (!stored) return null
  return {
    project_info: stored.project_info ?? {},
    data: stored.data ?? {},
    annotations: stored.annotations ?? {},
    generation: stored.generation ?? {},
    evaluation: stored.evaluation ?? {},
    analyses: stored.analyses ?? {},
    reproducibility: stored.reproducibility ?? {},
  }
}

/** Shape of `GET /api/reports/{id}/data` (snapshot-based contract). */
export interface ReportViewData {
  report: ReportResponse & { is_public?: boolean }
  snapshot: ReportSnapshot | null
}

interface LoadError {
  /** True for 401/403: the report is not public and the visitor is not entitled. */
  forbidden: boolean
  message: string | null
}

/** Classify a thrown API error: the client attaches `response.status`; older paths only carry text. */
export function classifyLoadError(err: unknown): LoadError {
  const anyErr = err as {
    response?: { status?: number }
    status?: number
    message?: string
  } | null
  const status = anyErr?.response?.status ?? anyErr?.status
  const message = err instanceof Error && err.message ? err.message : null
  const forbidden =
    status === 401 ||
    status === 403 ||
    (status === undefined &&
      !!message &&
      /status: 40[13]\b|unauthenticated|not authenticated|forbidden/i.test(
        message,
      ))
  return { forbidden, message: forbidden ? null : message }
}

export default function ReportViewerPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { t, locale } = useI18n()
  const { id } = use(params)
  const [data, setData] = useState<ReportViewData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<LoadError | null>(null)

  const load = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const response = (await getReportData(id)) as unknown as ReportViewData
      setData(response)
    } catch (err: unknown) {
      setError(classifyLoadError(err))
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => {
    load()
  }, [load])

  const registry = useMemo<MetricRegistry>(() => {
    const defs = getMetricDefinitions()
    const out: MetricRegistry = {}
    for (const [key, def] of Object.entries(defs)) {
      out[key] = {
        display_name: def.display_name,
        display_scale: def.display_scale,
      }
    }
    return out
  }, [])

  const report = data?.report ?? null
  const snapshot = data?.snapshot ?? null
  const sections = readSections(report)
  const title =
    sections?.project_info.custom_title ||
    report?.project_title ||
    t('reports.view.reportFallbackTitle')

  const frame = (children: ReactNode) => (
    <ResponsiveContainer
      size="xl"
      className="report-print pt-8 pb-16 print:max-w-none print:px-0 print:pt-0"
    >
      <div className="mb-6 print:hidden">
        <Breadcrumb
          items={[
            {
              label: t('navigation.dashboard'),
              href: '/dashboard',
            },
            { label: t('navigation.reports'), href: '/reports' },
            { label: title, href: `/reports/${id}` },
          ]}
        />
      </div>
      {children}
      <footer className="mt-12 border-t border-zinc-200 pt-6 text-center text-sm text-zinc-500 dark:border-zinc-800 dark:text-zinc-400 print:mt-6">
        {t('reports.view.madeWith')}{' '}
        <Link
          href="/"
          className="font-medium text-emerald-700 hover:underline dark:text-emerald-400"
        >
          BenGER
        </Link>
      </footer>
    </ResponsiveContainer>
  )

  if (loading) {
    return frame(
      <>
        <h1 className="mb-6 text-3xl font-bold tracking-tight text-zinc-900 dark:text-white">
          {title}
        </h1>
        <StatusCard kind="loading" t={t} />
      </>,
    )
  }

  if (error || !report || !sections) {
    const loginHref = `/login?next=${encodeURIComponent(`/reports/${id}`)}`
    return frame(
      <>
        <h1 className="mb-6 text-3xl font-bold tracking-tight text-zinc-900 dark:text-white">
          {title}
        </h1>
        {error?.forbidden ? (
          <StatusCard kind="forbidden" loginHref={loginHref} t={t} />
        ) : (
          <StatusCard
            kind="error"
            message={error ? error.message : t('reports.view.notFound')}
            onRetry={load}
            t={t}
          />
        )}
      </>,
    )
  }

  const stats = snapshot?.statistics
  // The report as project paper (report_paper): its parts are in the
  // snapshot only when it was built with the flag and the flag is on for
  // anybody (the API strips them otherwise). Without them the page reads as
  // a classic report: every tile and section, no citation block.
  const paper = Boolean(snapshot?.reproducibility)
  const chartsConfig = (sections.evaluation.charts_config ??
    null) as ReportChartsConfig | null
  const showParticipants = sections.annotations.show_participants !== false
  const description =
    sections.project_info.custom_description ||
    sections.project_info.description
  const editHref = report.can_edit
    ? `/projects/${report.project_id}/report/edit`
    : null

  const tiles: StatTile[] = []
  if (stats) {
    tiles.push({
      id: 'tasks',
      label: t('reports.view.tasks'),
      value: formatCount(stats.task_count, locale),
    })
    if (stats.annotation_count > 0) {
      tiles.push({
        id: 'annotations',
        label: t('reports.view.submissionsTile'),
        value: formatCount(stats.annotation_count, locale),
      })
    }
    if (stats.participant_count > 0 && showParticipants) {
      tiles.push({
        id: 'participants',
        label: t('reports.view.participants'),
        value: formatCount(stats.participant_count, locale),
      })
    }
    // The paper hides empty tiles; a classic report shows every tile.
    if (!paper || stats.model_count > 0) {
      tiles.push({
        id: 'models',
        label: t('reports.view.modelsEvaluated'),
        value: formatCount(stats.model_count, locale),
      })
    }
    if (!paper || stats.evaluation_count > 0) {
      tiles.push({
        id: 'evaluations',
        label: t('reports.view.evaluations'),
        value: formatCount(stats.evaluation_count, locale),
      })
    }
    // Snapshots taken before analyses were counted have no analysis_count.
    if ((stats.analysis_count ?? 0) > 0) {
      tiles.push({
        id: 'analyses',
        label: t('reports.view.analyses.title'),
        value: formatCount(stats.analysis_count ?? 0, locale),
      })
    }
  }

  const annotationCount = stats?.annotation_count ?? 0
  // The validations behind the shown analyses' codes; a project whose
  // codes were validated on coding projects has them without annotations
  // of its own. Both show only what the served snapshot carries (none
  // without variant_experiments).
  const analysesContent = sections.analyses
  const showAnalyses =
    analysesContent?.visible !== false && hasAnalyses(snapshot?.analyses)
  const codeValidations =
    showAnalyses && sections.annotations.show_code_validations !== false
      ? codeValidationsOf(snapshot?.analyses)
      : []
  const showAnnotations =
    sections.annotations.visible !== false &&
    (annotationCount > 0 ||
      Boolean(sections.annotations.custom_text) ||
      codeValidations.length > 0)
  const models = snapshot?.models ?? []
  // Sections without data hide themselves; a draft without a snapshot keeps
  // the evaluation card with its "no evaluation yet" note.
  const generationModels = snapshot?.generation?.models.length ?? models.length
  const showGeneration =
    sections.generation.visible !== false &&
    (!paper || generationModels > 0 || Boolean(sections.generation.custom_text))
  // With an Analyses section the conclusions follow it, as in a paper.
  const conclusions = sections.evaluation.conclusions
  const conclusionsAfterAnalyses =
    showAnalyses &&
    sections.evaluation.visible !== false &&
    Boolean(conclusions)
  const hasEvaluation =
    !snapshot ||
    snapshot.series.length > 0 ||
    snapshot.methods.length > 0 ||
    Boolean(sections.evaluation.custom_interpretation) ||
    (Boolean(conclusions) && !conclusionsAfterAnalyses)
  const showEvaluation =
    sections.evaluation.visible !== false && (!paper || hasEvaluation)
  const showHuman =
    sections.evaluation.visible !== false &&
    sections.evaluation.show_human_evaluation !== false &&
    hasHumanEvaluations(snapshot?.human_evaluations)
  const reproSection = sections.reproducibility
  const repro = snapshot?.reproducibility
  const showRepro = Boolean(repro) && reproSection.visible !== false
  const reportUrl =
    typeof window !== 'undefined'
      ? `${window.location.origin}/reports/${id}`
      : `/reports/${id}`
  const snapshotAgreement = snapshot?.annotator_agreement
  const agreement = hasAgreement(snapshotAgreement) ? snapshotAgreement : null
  const showAgreement = sections.annotations.show_agreement !== false

  return frame(
    <>
      <ReportHeader
        title={title}
        description={description}
        publishedAt={report.published_at}
        generatedAt={snapshot?.generated_at}
        isDraft={!report.is_published}
        editHref={editHref}
        locale={locale}
        t={t}
      />

      <StatTiles tiles={tiles} />

      <div className="space-y-6">
        {sections.data.visible !== false && (
          <ReportSection title={t('reports.view.data')} id="data">
            <Prose>
              {sections.data.custom_text ||
                t('reports.view.defaultDataText', {
                  count: formatCount(stats?.task_count ?? 0, locale),
                })}
            </Prose>
            {sections.data.show_provenance !== false && (
              <DataProvenance data={snapshot?.data} locale={locale} t={t} />
            )}
          </ReportSection>
        )}

        {showAnnotations && (
          <ReportSection title={t('reports.view.annotations')} id="annotations">
            {(annotationCount > 0 || sections.annotations.custom_text) && (
              <Prose>
                {sections.annotations.custom_text ||
                  t('reports.view.defaultAnnotationsText', {
                    annotations: formatCount(annotationCount, locale),
                    participants: formatCount(
                      stats?.participant_count ?? 0,
                      locale,
                    ),
                  })}
              </Prose>
            )}
            {sections.annotations.acknowledgment_text && (
              <p className="mt-4 rounded-md bg-zinc-50 p-3 text-sm text-zinc-600 italic dark:bg-zinc-800/60 dark:text-zinc-300">
                {sections.annotations.acknowledgment_text}
              </p>
            )}
            {showAgreement && agreement && (
              <div className="mt-6" data-testid="report-annotator-agreement">
                <SubHeading>
                  {t('evaluation.annotatorAgreement.title')}
                </SubHeading>
                <AnnotatorAgreement
                  agreement={agreement}
                  showPairs={showParticipants}
                />
              </div>
            )}
            {codeValidations.length > 0 && (
              <CodeValidations
                analyses={snapshot?.analyses}
                locale={locale}
                t={t}
              />
            )}
          </ReportSection>
        )}

        {showGeneration && (
          <ReportSection title={t('reports.view.generation')} id="generation">
            <Prose>
              {sections.generation.custom_text ||
                t('reports.view.defaultGenerationText', {
                  count: formatCount(
                    stats?.model_count ?? models.length,
                    locale,
                  ),
                })}
            </Prose>
            {sections.generation.show_models !== false && models.length > 0 && (
              <div className="mt-4">
                <ModelChips models={models} t={t} />
              </div>
            )}
            {sections.generation.show_details !== false && (
              <GenerationDetails
                generation={snapshot?.generation}
                locale={locale}
                t={t}
              />
            )}
          </ReportSection>
        )}

        {showEvaluation && (
          <EvaluationSection
            snapshot={snapshot}
            chartsConfig={chartsConfig}
            interpretation={sections.evaluation.custom_interpretation}
            conclusions={conclusionsAfterAnalyses ? null : conclusions}
            registry={registry}
            locale={locale}
            t={t}
          />
        )}

        {showHuman && (
          <HumanEvaluationSection
            human={snapshot?.human_evaluations}
            locale={locale}
            t={t}
          />
        )}

        {showAnalyses && (
          <AnalysesSection
            analyses={snapshot?.analyses}
            content={analysesContent}
            locale={locale}
            t={t}
            runHref={report.can_edit ? analysisRunPath : null}
          />
        )}

        {conclusionsAfterAnalyses && (
          <ReportSection title={t('reports.view.conclusions')} id="conclusions">
            <Prose>{conclusions}</Prose>
          </ReportSection>
        )}

        {showParticipants && snapshot && (
          <ParticipantsList
            participants={snapshot.participants}
            locale={locale}
            t={t}
          />
        )}

        {showRepro && repro && (
          <ReproducibilitySection
            repro={repro}
            generatedAt={snapshot?.generated_at}
            note={reproSection.custom_text}
            locale={locale}
            t={t}
          />
        )}

        {paper && report.is_published && (
          <CitationBlock
            reportId={report.id}
            title={title}
            url={reportUrl}
            publishedAt={report.published_at}
            snapshotSha256={repro?.snapshot_sha256}
            locale={locale}
            t={t}
          />
        )}
      </div>
    </>,
  )
}

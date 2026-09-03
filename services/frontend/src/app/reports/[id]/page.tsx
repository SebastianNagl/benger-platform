/**
 * Report Viewer Page - publication-quality view of a project report.
 *
 * Renders `content` (editor prose + presentation settings) together with the
 * server-computed `snapshot` (ReportSnapshot). Works for anonymous visitors:
 * nothing here is gated on auth; a superadmin merely gets an edit link, and a
 * 401/403 turns into a friendly "not public" card inside the normal layout.
 */

'use client'

import Link from 'next/link'
import { use, useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { ResponsiveContainer } from '@/components/shared/ResponsiveContainer'
import {
  EvaluationSection,
  ModelChips,
  ParticipantsList,
  Prose,
  ReportHeader,
  ReportSection,
  StatTiles,
  StatusCard,
  type StatTile,
} from '@/components/reports/view'
import { useOptionalAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { getMetricDefinitions } from '@/lib/api/evaluation-types'
import { getReportData, type ReportResponse } from '@/lib/api/reports'
import { formatCount, type MetricRegistry } from '@/lib/reports/format'
import type { ReportChartsConfig, ReportSnapshot } from '@/types/report'

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
  const anyErr = err as { response?: { status?: number }; status?: number; message?: string } | null
  const status = anyErr?.response?.status ?? anyErr?.status
  const message = err instanceof Error && err.message ? err.message : null
  const forbidden =
    status === 401 ||
    status === 403 ||
    (status === undefined && !!message && /status: 40[13]\b|unauthenticated|not authenticated|forbidden/i.test(message))
  return { forbidden, message: forbidden ? null : message }
}

export default function ReportViewerPage({ params }: { params: Promise<{ id: string }> }) {
  const { t, locale } = useI18n()
  const auth = useOptionalAuth()
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
      out[key] = { display_name: def.display_name, display_scale: def.display_scale }
    }
    return out
  }, [])

  const report = data?.report ?? null
  const snapshot = data?.snapshot ?? null
  const sections = report?.content.sections
  const title = sections?.project_info.custom_title || report?.project_title || t('reports.view.reportFallbackTitle', 'Bericht')

  const frame = (children: ReactNode) => (
    <ResponsiveContainer size="xl" className="pb-16 pt-8">
      <div className="mb-6">
        <Breadcrumb
          items={[
            { label: t('navigation.dashboard', 'Dashboard'), href: '/dashboard' },
            { label: t('navigation.reports', 'Berichte'), href: '/reports' },
            { label: title, href: `/reports/${id}` },
          ]}
        />
      </div>
      {children}
      <footer className="mt-12 border-t border-zinc-200 pt-6 text-center text-sm text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
        {t('reports.view.madeWith', 'Erstellt mit')}{' '}
        <Link href="/" className="font-medium text-emerald-700 hover:underline dark:text-emerald-400">
          BenGER
        </Link>
      </footer>
    </ResponsiveContainer>
  )

  if (loading) {
    return frame(
      <>
        <h1 className="mb-6 text-3xl font-bold tracking-tight text-zinc-900 dark:text-white">{title}</h1>
        <StatusCard kind="loading" t={t} />
      </>,
    )
  }

  if (error || !report || !sections) {
    const loginHref = `/login?next=${encodeURIComponent(`/reports/${id}`)}`
    return frame(
      <>
        <h1 className="mb-6 text-3xl font-bold tracking-tight text-zinc-900 dark:text-white">{title}</h1>
        {error?.forbidden ? (
          <StatusCard kind="forbidden" loginHref={loginHref} t={t} />
        ) : (
          <StatusCard
            kind="error"
            message={error ? error.message : t('reports.view.notFound', 'Bericht nicht gefunden.')}
            onRetry={load}
            t={t}
          />
        )}
      </>,
    )
  }

  const stats = snapshot?.statistics
  const chartsConfig = (sections.evaluation.charts_config ?? null) as ReportChartsConfig | null
  const showParticipants = sections.annotations.show_participants !== false
  const description = sections.project_info.custom_description || sections.project_info.description
  const editHref = auth?.user?.is_superadmin ? `/projects/${report.project_id}/report/edit` : null

  const tiles: StatTile[] = []
  if (stats) {
    tiles.push({ id: 'tasks', label: t('reports.view.tasks', 'Aufgaben'), value: formatCount(stats.task_count, locale) })
    if (stats.annotation_count > 0) {
      tiles.push({ id: 'annotations', label: t('reports.view.submissionsTile', 'Abgaben'), value: formatCount(stats.annotation_count, locale) })
    }
    if (stats.participant_count > 0 && showParticipants) {
      tiles.push({ id: 'participants', label: t('reports.view.participants', 'Teilnehmende'), value: formatCount(stats.participant_count, locale) })
    }
    tiles.push({ id: 'models', label: t('reports.view.modelsEvaluated', 'Evaluierte Modelle'), value: formatCount(stats.model_count, locale) })
    tiles.push({ id: 'evaluations', label: t('reports.view.evaluations', 'Bewertungen'), value: formatCount(stats.evaluation_count, locale) })
  }

  const annotationCount = stats?.annotation_count ?? 0
  const showAnnotations =
    sections.annotations.visible !== false && (annotationCount > 0 || Boolean(sections.annotations.custom_text))
  const models = snapshot?.models ?? []

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
          <ReportSection title={t('reports.view.data', 'Daten')} id="data">
            <Prose>
              {sections.data.custom_text ||
                t('reports.view.defaultDataText', 'Der Datensatz umfasst {count} Aufgaben.', {
                  count: formatCount(stats?.task_count ?? 0, locale),
                })}
            </Prose>
          </ReportSection>
        )}

        {showAnnotations && (
          <ReportSection title={t('reports.view.annotations', 'Abgaben')} id="annotations">
            <Prose>
              {sections.annotations.custom_text ||
                t(
                  'reports.view.defaultAnnotationsText',
                  '{annotations} Abgaben von {participants} Teilnehmenden wurden erfasst.',
                  {
                    annotations: formatCount(annotationCount, locale),
                    participants: formatCount(stats?.participant_count ?? 0, locale),
                  },
                )}
            </Prose>
            {sections.annotations.acknowledgment_text && (
              <p className="mt-4 rounded-md bg-zinc-50 p-3 text-sm italic text-zinc-600 dark:bg-zinc-800/60 dark:text-zinc-300">
                {sections.annotations.acknowledgment_text}
              </p>
            )}
          </ReportSection>
        )}

        {sections.generation.visible !== false && (
          <ReportSection title={t('reports.view.generation', 'Modelle')} id="generation">
            <Prose>
              {sections.generation.custom_text ||
                t('reports.view.defaultGenerationText', 'Die Antworten wurden von {count} Sprachmodellen erzeugt.', {
                  count: formatCount(stats?.model_count ?? models.length, locale),
                })}
            </Prose>
            {sections.generation.show_models !== false && models.length > 0 && (
              <div className="mt-4">
                <ModelChips models={models} t={t} />
              </div>
            )}
          </ReportSection>
        )}

        {sections.evaluation.visible !== false && (
          <EvaluationSection
            snapshot={snapshot}
            chartsConfig={chartsConfig}
            interpretation={sections.evaluation.custom_interpretation}
            conclusions={sections.evaluation.conclusions}
            registry={registry}
            locale={locale}
            t={t}
          />
        )}

        {showParticipants && snapshot && (
          <ParticipantsList participants={snapshot.participants} locale={locale} t={t} />
        )}
      </div>
    </>,
  )
}

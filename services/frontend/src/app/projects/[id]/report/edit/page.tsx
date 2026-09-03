/**
 * Report Editor Page
 *
 * Lets superadmins edit a project report: free-text fields per section,
 * section visibility switches, and the presentation of the evaluation
 * (primary metric / judge configuration, visible metrics + configurations,
 * hidden models/participants, distribution + human rows). The editable
 * options come from the server-computed `content.snapshot`; "Daten
 * aktualisieren" recomputes it.
 *
 * Saving round-trips the whole `content` (spread the loaded content, overlay
 * only the edited fields) so `snapshot` and auto-populated data survive.
 *
 * Issue #770: Project Reports Publishing System
 */

'use client'

import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { Button } from '@/components/shared/Button'
import { Label } from '@/components/shared/Label'
import { Textarea } from '@/components/shared/Textarea'
import { ToggleSwitch } from '@/components/shared/ToggleSwitch'
import { useToast } from '@/components/shared/Toast'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { getMetricDefinitions } from '@/lib/api/evaluation-types'
import {
  getProjectReport,
  refreshReport,
  updateProjectReport,
  type ReportContent,
  type ReportResponse,
} from '@/lib/api/reports'
import type {
  ReportChartsConfig,
  ReportConfigRef,
  ReportMethod,
  ReportSnapshot,
  ReportSubject,
} from '@/types/report'
import {
  ArrowLeftIcon,
  ArrowPathIcon,
  ArrowTopRightOnSquareIcon,
} from '@heroicons/react/24/outline'
import { useRouter } from 'next/navigation'
import { useEffect, useMemo, useState } from 'react'

interface ReportEditorPageProps {
  params: Promise<{
    id: string
  }>
}

type SectionKey =
  | 'project_info'
  | 'data'
  | 'annotations'
  | 'generation'
  | 'evaluation'

const SECTION_KEYS: SectionKey[] = [
  'project_info',
  'data',
  'annotations',
  'generation',
  'evaluation',
]

/** Metric keys that carry raw payloads, never shown as report metrics. */
const isInternalMetricKey = (id: string) => /_(raw|details)$/.test(id)

interface EditorState {
  customTitle: string
  customDescription: string
  dataText: string
  annotationsText: string
  acknowledgment: string
  generationText: string
  interpretation: string
  conclusions: string
  sectionVisible: Record<SectionKey, boolean>
  showDataCount: boolean
  showParticipants: boolean
  showModels: boolean
  primaryMetric: string | null
  primaryConfigId: string | null
  visibleConfigs: Set<string>
  visibleMetrics: Set<string>
  hiddenSubjects: Set<string>
  showDistribution: boolean
  showHumans: boolean
}

// Loose views over the content: the API guarantees the shape, but reports
// created before a section existed may miss keys, so read defensively.
type LooseSections = Partial<Record<SectionKey, Record<string, any>>>

function getSections(report: ReportResponse | null): LooseSections {
  return (report?.content?.sections ?? {}) as LooseSections
}

function getSnapshot(report: ReportResponse | null): ReportSnapshot | null {
  return report?.content?.snapshot ?? null
}

function getChartsConfig(report: ReportResponse | null): ReportChartsConfig {
  return (getSections(report).evaluation?.charts_config ??
    {}) as ReportChartsConfig
}

/** Report metrics (non-internal), in snapshot order. */
function listReportMetrics(
  snapshot: ReportSnapshot | null
): ReportMethod[] {
  return (snapshot?.methods ?? []).filter(
    (m) => !isInternalMetricKey(m.id)
  )
}

/** Display name: metric registry first, then the snapshot's name, then the id. */
function metricDisplayName(method: ReportMethod): string {
  const def = getMetricDefinitions()[method.id]
  return def?.display_name || method.name || method.id
}

function configLabel(config: ReportConfigRef): string {
  const base = config.name || config.metric
  const judge = config.judge_label ? ` · ${config.judge_label}` : ''
  return `${base}${judge} (n=${config.n})`
}

/** Subjects across all series + snapshot models, de-duplicated, models first. */
function listReportSubjects(
  snapshot: ReportSnapshot | null
): ReportSubject[] {
  if (!snapshot) return []
  const byId = new Map<string, ReportSubject>()
  for (const model of snapshot.models ?? []) {
    if (!byId.has(model.id)) byId.set(model.id, model)
  }
  for (const row of snapshot.series ?? []) {
    const subject = row.subject
    if (!byId.has(subject.id)) byId.set(subject.id, subject)
  }
  const all = Array.from(byId.values())
  return [
    ...all.filter((s) => s.kind === 'model'),
    ...all.filter((s) => s.kind !== 'model'),
  ]
}

/** The config with the most samples for a metric (the snapshot's default rule). */
function defaultConfigFor(
  configs: ReportConfigRef[],
  metric: string | null
): string | null {
  if (!metric) return null
  const candidates = configs.filter((c) => c.metric === metric)
  if (candidates.length === 0) return null
  return candidates.reduce((best, c) => (c.n > best.n ? c : best)).id
}

function deriveEditorState(report: ReportResponse): EditorState {
  const sections = getSections(report)
  const snapshot = getSnapshot(report)
  const cfg = getChartsConfig(report)
  const metricIds = listReportMetrics(snapshot).map((m) => m.id)
  const configs = snapshot?.configs ?? []
  const configIds = configs.map((c) => c.id)

  const primaryMetric = cfg.primary_metric ?? snapshot?.primary_metric ?? null
  const primaryConfigId =
    cfg.primary_config_id ??
    snapshot?.primary_config_id ??
    defaultConfigFor(configs, primaryMetric)

  const sectionVisible = {} as Record<SectionKey, boolean>
  for (const key of SECTION_KEYS) {
    sectionVisible[key] = sections[key]?.visible !== false
  }

  return {
    customTitle: sections.project_info?.custom_title || '',
    customDescription: sections.project_info?.custom_description || '',
    dataText: sections.data?.custom_text || '',
    annotationsText: sections.annotations?.custom_text || '',
    acknowledgment: sections.annotations?.acknowledgment_text || '',
    generationText: sections.generation?.custom_text || '',
    interpretation: sections.evaluation?.custom_interpretation || '',
    conclusions: sections.evaluation?.conclusions || '',
    sectionVisible,
    showDataCount: sections.data?.show_count !== false,
    showParticipants: sections.annotations?.show_participants !== false,
    showModels: sections.generation?.show_models !== false,
    primaryMetric,
    primaryConfigId,
    visibleConfigs: new Set(
      Array.isArray(cfg.visible_configs) ? cfg.visible_configs : configIds
    ),
    visibleMetrics: new Set(
      Array.isArray(cfg.visible_metrics)
        ? cfg.visible_metrics.filter((m) => !isInternalMetricKey(m))
        : metricIds
    ),
    hiddenSubjects: new Set(cfg.hidden_subjects ?? []),
    showDistribution: cfg.show_distribution !== false,
    showHumans: cfg.show_humans !== false,
  }
}

/**
 * After a snapshot refresh: keep the editor's choices, but make newly
 * appeared metrics/configs visible and fall back when a chosen primary
 * metric/config disappeared.
 */
function reconcileWithSnapshot(
  state: EditorState,
  previous: ReportSnapshot | null,
  next: ReportSnapshot | null
): EditorState {
  const prevMetricIds = new Set(listReportMetrics(previous).map((m) => m.id))
  const prevConfigIds = new Set((previous?.configs ?? []).map((c) => c.id))
  const nextMetrics = listReportMetrics(next).map((m) => m.id)
  const nextConfigs = next?.configs ?? []
  const nextConfigIds = nextConfigs.map((c) => c.id)

  const visibleMetrics = new Set(state.visibleMetrics)
  nextMetrics
    .filter((id) => !prevMetricIds.has(id))
    .forEach((id) => visibleMetrics.add(id))
  const visibleConfigs = new Set(state.visibleConfigs)
  nextConfigIds
    .filter((id) => !prevConfigIds.has(id))
    .forEach((id) => visibleConfigs.add(id))

  const primaryMetric =
    state.primaryMetric && nextMetrics.includes(state.primaryMetric)
      ? state.primaryMetric
      : (next?.primary_metric ?? null)
  const primaryConfigId =
    state.primaryConfigId &&
    nextConfigs.some(
      (c) => c.id === state.primaryConfigId && c.metric === primaryMetric
    )
      ? state.primaryConfigId
      : (next?.primary_config_id ?? defaultConfigFor(nextConfigs, primaryMetric))

  return {
    ...state,
    visibleMetrics,
    visibleConfigs,
    primaryMetric,
    primaryConfigId,
  }
}

function toggleInSet(set: Set<string>, value: string): Set<string> {
  const next = new Set(set)
  if (next.has(value)) {
    next.delete(value)
  } else {
    next.add(value)
  }
  return next
}

const cardClass =
  'rounded-lg border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-700 dark:bg-zinc-900'
const checkboxLabelClass =
  'flex items-center gap-2 rounded border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-700 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200'
const checkboxClass =
  'h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500'
const selectClass =
  'mt-1 w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500 dark:border-zinc-600 dark:bg-zinc-800 dark:text-white sm:w-96'

export default function ReportEditorPage({ params }: ReportEditorPageProps) {
  const router = useRouter()
  const { user, isLoading: authLoading } = useAuth()
  const { addToast } = useToast()
  const { t } = useI18n()

  const [projectId, setProjectId] = useState<string | null>(null)
  const [report, setReport] = useState<ReportResponse | null>(null)
  const [loadFailed, setLoadFailed] = useState(false)
  const [saving, setSaving] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [state, setState] = useState<EditorState | null>(null)

  const isSuperadmin = Boolean(user?.is_superadmin)

  // Resolve params
  useEffect(() => {
    const resolveParams = async () => {
      const resolvedParams = await params
      setProjectId(resolvedParams.id)
    }
    resolveParams()
  }, [params])

  // Fetch report (superadmins only; everyone else gets the notice below)
  useEffect(() => {
    if (!projectId || !user?.is_superadmin) {
      return
    }

    const load = async () => {
      try {
        const data = await getProjectReport(projectId)
        setReport(data)
        setState(deriveEditorState(data))
      } catch (error) {
        console.error('Failed to fetch report:', error)
        setLoadFailed(true)
        addToast(t('project.report.editor.failedToLoad'), 'error')
        router.push(`/projects/${projectId}`)
      }
    }

    load()
  }, [projectId, user, router, addToast, t])

  const snapshot = useMemo(() => getSnapshot(report), [report])
  const metrics = useMemo(() => listReportMetrics(snapshot), [snapshot])
  const primaryMetricOptions = useMemo(
    () => metrics.filter((m) => !m.derived),
    [metrics]
  )
  const configs = useMemo(() => snapshot?.configs ?? [], [snapshot])
  const configsForPrimary = useMemo(
    () => configs.filter((c) => c.metric === state?.primaryMetric),
    [configs, state?.primaryMetric]
  )
  const subjects = useMemo(() => listReportSubjects(snapshot), [snapshot])
  const modelSubjects = subjects.filter((s) => s.kind === 'model')
  const humanSubjects = subjects.filter((s) => s.kind !== 'model')

  const update = (patch: Partial<EditorState>) =>
    setState((prev) => (prev ? { ...prev, ...patch } : prev))

  const handlePrimaryMetricChange = (metricId: string) => {
    const nextMetric = metricId || null
    setState((prev) => {
      if (!prev) return prev
      const keepConfig =
        prev.primaryConfigId &&
        configs.some(
          (c) => c.id === prev.primaryConfigId && c.metric === nextMetric
        )
      return {
        ...prev,
        primaryMetric: nextMetric,
        primaryConfigId: keepConfig
          ? prev.primaryConfigId
          : defaultConfigFor(configs, nextMetric),
      }
    })
  }

  const buildContent = (): ReportContent | null => {
    if (!report || !state) return null
    const base = (report.content ?? {}) as Partial<ReportContent>
    const sections = getSections(report)
    const cfg = getChartsConfig(report)
    const metricIds = metrics.map((m) => m.id)
    const configIds = configs.map((c) => c.id)

    const chartsConfig: ReportChartsConfig = {
      ...cfg,
      primary_metric: state.primaryMetric,
      primary_config_id: state.primaryConfigId,
      hidden_subjects: Array.from(state.hiddenSubjects),
      show_distribution: state.showDistribution,
      show_humans: state.showHumans,
      // Without a snapshot there is nothing to choose from: keep what is stored.
      visible_metrics:
        metricIds.length > 0
          ? metricIds.filter((m) => state.visibleMetrics.has(m))
          : cfg.visible_metrics,
      visible_configs:
        configIds.length > 0
          ? configIds.filter((c) => state.visibleConfigs.has(c))
          : cfg.visible_configs,
    }

    return {
      ...base,
      sections: {
        ...sections,
        project_info: {
          ...sections.project_info,
          visible: state.sectionVisible.project_info,
          custom_title: state.customTitle || null,
          custom_description: state.customDescription || null,
        },
        data: {
          ...sections.data,
          visible: state.sectionVisible.data,
          show_count: state.showDataCount,
          custom_text: state.dataText || null,
        },
        annotations: {
          ...sections.annotations,
          visible: state.sectionVisible.annotations,
          show_participants: state.showParticipants,
          custom_text: state.annotationsText || null,
          acknowledgment_text: state.acknowledgment || null,
        },
        generation: {
          ...sections.generation,
          visible: state.sectionVisible.generation,
          show_models: state.showModels,
          custom_text: state.generationText || null,
        },
        evaluation: {
          ...sections.evaluation,
          visible: state.sectionVisible.evaluation,
          custom_interpretation: state.interpretation || null,
          conclusions: state.conclusions || null,
          charts_config: chartsConfig,
        },
      },
    } as ReportContent
  }

  const handleSave = async () => {
    if (!report || !projectId || !state) return

    if (
      metrics.length > 0 &&
      !metrics.some((m) => state.visibleMetrics.has(m.id))
    ) {
      addToast(
        t(
          'reports.editor.noMetricsVisible',
          'Mindestens eine Metrik muss sichtbar bleiben.'
        ),
        'warning'
      )
      return
    }

    const content = buildContent()
    if (!content) return

    setSaving(true)
    try {
      const updated = await updateProjectReport(projectId, content)
      setReport(updated)
      addToast(t('project.report.editor.savedSuccessfully'), 'success')
    } catch (error) {
      console.error('Failed to save report:', error)
      addToast(t('project.report.editor.failedToSave'), 'error')
    } finally {
      setSaving(false)
    }
  }

  const handleRefresh = async () => {
    if (!projectId) return
    setRefreshing(true)
    try {
      const previous = snapshot
      const refreshed = await refreshReport(projectId)
      setReport(refreshed)
      setState((prev) =>
        prev
          ? reconcileWithSnapshot(prev, previous, getSnapshot(refreshed))
          : deriveEditorState(refreshed)
      )
      addToast(t('reports.editor.refreshed', 'Daten aktualisiert'), 'success')
    } catch (error) {
      console.error('Failed to refresh report data:', error)
      addToast(
        t(
          'reports.editor.refreshFailed',
          'Daten konnten nicht aktualisiert werden'
        ),
        'error'
      )
    } finally {
      setRefreshing(false)
    }
  }

  // Session still resolving or route params not ready
  if (authLoading || (!user && authLoading !== false) || !projectId) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-center">
          <div className="mx-auto h-12 w-12 animate-spin rounded-full border-b-2 border-emerald-500"></div>
          <p className="mt-4 text-zinc-600 dark:text-zinc-400">
            {t('project.report.editor.loading')}
          </p>
        </div>
      </div>
    )
  }

  // Clear dead-end instead of a blank page
  if (!isSuperadmin) {
    return (
      <div className="mx-auto max-w-2xl px-4 pb-10 pt-16 sm:px-6 lg:px-8">
        <div
          className="rounded-lg border border-amber-200 bg-amber-50 p-6 dark:border-amber-800 dark:bg-amber-900/20"
          role="alert"
        >
          <h1 className="text-lg font-semibold text-amber-900 dark:text-amber-200">
            {t(
              'reports.editor.notSuperadmin',
              'Nur Superadmins können Berichte bearbeiten'
            )}
          </h1>
          <p className="mt-2 text-sm text-amber-800 dark:text-amber-300">
            {t(
              'reports.editor.notSuperadminHint',
              'Veröffentlichte Berichte finden Sie unter „Berichte“.'
            )}
          </p>
          <div className="mt-4 flex gap-3">
            <Button
              onClick={() => router.push(`/projects/${projectId}`)}
              variant="outline"
            >
              <ArrowLeftIcon className="mr-2 h-4 w-4" />
              {t('project.report.editor.backToProject')}
            </Button>
          </div>
        </div>
      </div>
    )
  }

  if (!report || !state) {
    if (loadFailed) return null
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-center">
          <div className="mx-auto h-12 w-12 animate-spin rounded-full border-b-2 border-emerald-500"></div>
          <p className="mt-4 text-zinc-600 dark:text-zinc-400">
            {t('project.report.editor.loading')}
          </p>
        </div>
      </div>
    )
  }

  const sectionSwitch = (key: SectionKey) => (
    <ToggleSwitch
      enabled={state.sectionVisible[key]}
      onChange={(enabled) =>
        update({
          sectionVisible: { ...state.sectionVisible, [key]: enabled },
        })
      }
      label={t('reports.editor.showSection', 'Abschnitt anzeigen')}
    />
  )

  const sectionHeader = (key: SectionKey, title: string) => (
    <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
      <h2 className="text-lg font-semibold text-zinc-900 dark:text-white">
        {title}
      </h2>
      {sectionSwitch(key)}
    </div>
  )

  const snapshotDate = snapshot?.generated_at
    ? new Date(snapshot.generated_at).toLocaleString()
    : null

  return (
    <div className="mx-auto max-w-5xl px-4 pb-10 pt-16 sm:px-6 lg:px-8">
      {/* Header */}
      <div className="mb-8">
        <Breadcrumb
          items={[
            {
              label: t('navigation.dashboard') || 'Dashboard',
              href: '/dashboard',
            },
            {
              label: t('navigation.projects') || 'Projects',
              href: '/projects',
            },
            { label: report.project_title, href: `/projects/${projectId}` },
            {
              label: t('project.report.editor.title'),
              href: `/projects/${projectId}/report/edit`,
            },
          ]}
        />

        <div className="mt-4 flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold text-zinc-900 dark:text-white">
              {t('project.report.editor.title')}
            </h1>
            <p className="mt-2 text-zinc-600 dark:text-zinc-400">
              {t('project.report.editor.subtitle')}
            </p>
            <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-500">
              {snapshotDate
                ? t('reports.editor.snapshotGeneratedAt', 'Datenstand: {date}', {
                    date: snapshotDate,
                  })
                : t(
                    'reports.editor.noSnapshot',
                    'Noch keine Daten berechnet. Klicken Sie auf „Daten aktualisieren“.'
                  )}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              onClick={handleRefresh}
              disabled={refreshing || saving}
              variant="outline"
            >
              <ArrowPathIcon
                className={`mr-2 h-4 w-4 ${refreshing ? 'animate-spin' : ''}`}
              />
              {refreshing
                ? t('reports.editor.refreshing', 'Wird aktualisiert...')
                : t('reports.editor.refresh', 'Daten aktualisieren')}
            </Button>
            <a
              href={`/reports/${report.id}`}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center rounded-md border border-zinc-300 px-3 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-50 dark:border-zinc-600 dark:text-zinc-200 dark:hover:bg-zinc-800"
            >
              <ArrowTopRightOnSquareIcon className="mr-2 h-4 w-4" />
              {t('reports.editor.preview', 'Vorschau')}
            </a>
            <Button
              onClick={() => router.push(`/projects/${projectId}`)}
              variant="outline"
            >
              <ArrowLeftIcon className="mr-2 h-4 w-4" />
              {t('project.report.editor.backToProject')}
            </Button>
          </div>
        </div>
      </div>

      {/* Editor Form */}
      <div className="space-y-8">
        {/* Project Info Section */}
        <div className={cardClass} data-testid="section-project_info">
          {sectionHeader(
            'project_info',
            t('project.report.editor.projectInfo.title')
          )}
          <div className="space-y-4">
            <div>
              <Label htmlFor="customTitle">
                {t('project.report.editor.projectInfo.customTitle')}
              </Label>
              <input
                id="customTitle"
                type="text"
                value={state.customTitle}
                onChange={(e) => update({ customTitle: e.target.value })}
                placeholder={report.project_title}
                className="mt-1 w-full rounded-md border border-zinc-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500 dark:border-zinc-600 dark:bg-zinc-800 dark:text-white"
              />
              <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                {t('project.report.editor.projectInfo.useDefaultTitle', {
                  title: report.project_title,
                })}
              </p>
            </div>
            <div>
              <Label htmlFor="customDescription">
                {t('project.report.editor.projectInfo.customDescription')}
              </Label>
              <Textarea
                id="customDescription"
                value={state.customDescription}
                onChange={(e) => update({ customDescription: e.target.value })}
                placeholder={t(
                  'project.report.editor.projectInfo.customDescriptionPlaceholder'
                )}
                rows={3}
              />
            </div>
          </div>
        </div>

        {/* Data Section */}
        <div className={cardClass} data-testid="section-data">
          {sectionHeader('data', t('project.report.editor.dataSection.title'))}
          <div className="space-y-4">
            <div>
              <Label htmlFor="dataText">
                {t('project.report.editor.dataSection.customText')}
              </Label>
              <Textarea
                id="dataText"
                value={state.dataText}
                onChange={(e) => update({ dataText: e.target.value })}
                placeholder={t(
                  'project.report.editor.dataSection.customTextPlaceholder'
                )}
                rows={4}
              />
            </div>
            <ToggleSwitch
              enabled={state.showDataCount}
              onChange={(enabled) => update({ showDataCount: enabled })}
              label={t(
                'reports.editor.showDataCount',
                'Anzahl der Aufgaben anzeigen'
              )}
            />
          </div>
        </div>

        {/* Annotations Section */}
        <div className={cardClass} data-testid="section-annotations">
          {sectionHeader(
            'annotations',
            t('project.report.editor.annotationsSection.title')
          )}
          <div className="space-y-4">
            <div>
              <Label htmlFor="annotationsText">
                {t('project.report.editor.annotationsSection.customText')}
              </Label>
              <Textarea
                id="annotationsText"
                value={state.annotationsText}
                onChange={(e) => update({ annotationsText: e.target.value })}
                placeholder={t(
                  'project.report.editor.annotationsSection.customTextPlaceholder'
                )}
                rows={4}
              />
            </div>
            <div>
              <Label htmlFor="acknowledgment">
                {t('project.report.editor.annotationsSection.acknowledgment')}
              </Label>
              <Textarea
                id="acknowledgment"
                value={state.acknowledgment}
                onChange={(e) => update({ acknowledgment: e.target.value })}
                placeholder={t(
                  'project.report.editor.annotationsSection.acknowledgmentPlaceholder'
                )}
                rows={3}
              />
            </div>
            <ToggleSwitch
              enabled={state.showParticipants}
              onChange={(enabled) => update({ showParticipants: enabled })}
              label={t(
                'reports.editor.showParticipants',
                'Teilnehmende anzeigen'
              )}
            />
          </div>
        </div>

        {/* Generation Section */}
        <div className={cardClass} data-testid="section-generation">
          {sectionHeader(
            'generation',
            t('project.report.editor.generationSection.title')
          )}
          <div className="space-y-4">
            <div>
              <Label htmlFor="generationText">
                {t('project.report.editor.generationSection.customText')}
              </Label>
              <Textarea
                id="generationText"
                value={state.generationText}
                onChange={(e) => update({ generationText: e.target.value })}
                placeholder={t(
                  'project.report.editor.generationSection.customTextPlaceholder'
                )}
                rows={4}
              />
            </div>
            <ToggleSwitch
              enabled={state.showModels}
              onChange={(enabled) => update({ showModels: enabled })}
              label={t('reports.editor.showModels', 'Modelle anzeigen')}
            />
          </div>
        </div>

        {/* Evaluation Section */}
        <div className={cardClass} data-testid="section-evaluation">
          {sectionHeader(
            'evaluation',
            t('project.report.editor.evaluationSection.title')
          )}
          <div className="space-y-6">
            <div>
              <Label htmlFor="interpretation">
                {t('project.report.editor.evaluationSection.interpretation')}
              </Label>
              <Textarea
                id="interpretation"
                value={state.interpretation}
                onChange={(e) => update({ interpretation: e.target.value })}
                placeholder={t(
                  'project.report.editor.evaluationSection.interpretationPlaceholder'
                )}
                rows={5}
              />
            </div>
            <div>
              <Label htmlFor="conclusions">
                {t('project.report.editor.evaluationSection.conclusions')}
              </Label>
              <Textarea
                id="conclusions"
                value={state.conclusions}
                onChange={(e) => update({ conclusions: e.target.value })}
                placeholder={t(
                  'project.report.editor.evaluationSection.conclusionsPlaceholder'
                )}
                rows={4}
              />
            </div>

            <div className="border-t border-zinc-200 pt-6 dark:border-zinc-700">
              <h3 className="text-base font-semibold text-zinc-900 dark:text-white">
                {t('reports.editor.presentation', 'Darstellung der Evaluation')}
              </h3>

              {!snapshot || metrics.length === 0 ? (
                <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">
                  {t(
                    'project.report.editor.evaluationSection.noMetricsAvailable'
                  )}
                </p>
              ) : (
                <div className="mt-4 space-y-6">
                  {/* Primary metric */}
                  <div>
                    <Label htmlFor="primaryMetric">
                      {t('reports.editor.primaryMetric', 'Primäre Metrik')}
                    </Label>
                    <p className="text-xs text-zinc-500 dark:text-zinc-400">
                      {t(
                        'reports.editor.primaryMetricHint',
                        'Metrik, nach der die Rangliste sortiert wird und die das Hauptdiagramm zeigt.'
                      )}
                    </p>
                    <select
                      id="primaryMetric"
                      value={state.primaryMetric ?? ''}
                      onChange={(e) =>
                        handlePrimaryMetricChange(e.target.value)
                      }
                      className={selectClass}
                    >
                      <option value="">
                        {t('reports.editor.none', 'Keine')}
                      </option>
                      {primaryMetricOptions.map((m) => (
                        <option key={m.id} value={m.id}>
                          {metricDisplayName(m)}
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Primary config */}
                  <div>
                    <Label htmlFor="primaryConfig">
                      {t('reports.editor.primaryConfig', 'Judge-Konfiguration')}
                    </Label>
                    <p className="text-xs text-zinc-500 dark:text-zinc-400">
                      {t(
                        'reports.editor.primaryConfigHint',
                        'Welche Bewertungskonfiguration die Rangliste und das Hauptdiagramm liefert.'
                      )}
                    </p>
                    {configsForPrimary.length === 0 ? (
                      <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
                        {t(
                          'reports.editor.noConfigsForMetric',
                          'Keine Konfiguration für diese Metrik.'
                        )}
                      </p>
                    ) : (
                      <select
                        id="primaryConfig"
                        value={state.primaryConfigId ?? ''}
                        onChange={(e) =>
                          update({ primaryConfigId: e.target.value || null })
                        }
                        className={selectClass}
                      >
                        {configsForPrimary.map((c) => (
                          <option key={c.id} value={c.id}>
                            {configLabel(c)}
                          </option>
                        ))}
                      </select>
                    )}
                  </div>

                  {/* Visible configs */}
                  {configs.length > 0 && (
                    <div>
                      <Label>
                        {t(
                          'reports.editor.visibleConfigs',
                          'Sichtbare Judge-Konfigurationen'
                        )}
                      </Label>
                      <div
                        className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2"
                        data-testid="visible-configs"
                      >
                        {configs.map((c) => (
                          <label key={c.id} className={checkboxLabelClass}>
                            <input
                              type="checkbox"
                              checked={state.visibleConfigs.has(c.id)}
                              onChange={() =>
                                update({
                                  visibleConfigs: toggleInSet(
                                    state.visibleConfigs,
                                    c.id
                                  ),
                                })
                              }
                              className={checkboxClass}
                            />
                            <span>{configLabel(c)}</span>
                          </label>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Visible metrics */}
                  <div>
                    <div className="mb-1 flex items-center justify-between">
                      <Label>
                        {t('reports.editor.visibleMetrics', 'Sichtbare Metriken')}
                      </Label>
                      <div className="flex gap-3 text-xs">
                        <button
                          type="button"
                          onClick={() =>
                            update({
                              visibleMetrics: new Set(metrics.map((m) => m.id)),
                            })
                          }
                          className="text-emerald-700 hover:underline dark:text-emerald-400"
                        >
                          {t('project.report.editor.evaluationSection.selectAll')}
                        </button>
                        <button
                          type="button"
                          onClick={() => update({ visibleMetrics: new Set() })}
                          className="text-zinc-600 hover:underline dark:text-zinc-300"
                        >
                          {t('project.report.editor.evaluationSection.clearAll')}
                        </button>
                      </div>
                    </div>
                    <p className="mb-2 text-xs text-zinc-500 dark:text-zinc-400">
                      {t(
                        'project.report.editor.evaluationSection.visibleMetricsHint'
                      )}
                    </p>
                    <div
                      className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3"
                      data-testid="visible-metrics"
                    >
                      {metrics.map((m) => (
                        <label key={m.id} className={checkboxLabelClass}>
                          <input
                            type="checkbox"
                            checked={state.visibleMetrics.has(m.id)}
                            onChange={() =>
                              update({
                                visibleMetrics: toggleInSet(
                                  state.visibleMetrics,
                                  m.id
                                ),
                              })
                            }
                            className={checkboxClass}
                          />
                          <span>{metricDisplayName(m)}</span>
                        </label>
                      ))}
                    </div>
                  </div>

                  {/* Hidden subjects */}
                  {subjects.length > 0 && (
                    <div>
                      <Label>
                        {t(
                          'reports.editor.hiddenSubjects',
                          'Ausgeblendete Modelle/Teilnehmende'
                        )}
                      </Label>
                      <p className="mb-2 text-xs text-zinc-500 dark:text-zinc-400">
                        {t(
                          'reports.editor.hiddenSubjectsHint',
                          'Angehakte Einträge erscheinen nicht im Bericht.'
                        )}
                      </p>
                      <div className="space-y-3" data-testid="hidden-subjects">
                        {[
                          {
                            key: 'models',
                            title: t('reports.editor.models', 'Modelle'),
                            items: modelSubjects,
                          },
                          {
                            key: 'humans',
                            title: t('reports.editor.humans', 'Teilnehmende'),
                            items: humanSubjects,
                          },
                        ]
                          .filter((group) => group.items.length > 0)
                          .map((group) => (
                            <div key={group.key}>
                              <p className="mb-1 text-xs font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
                                {group.title}
                              </p>
                              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
                                {group.items.map((s) => (
                                  <label key={s.id} className={checkboxLabelClass}>
                                    <input
                                      type="checkbox"
                                      checked={state.hiddenSubjects.has(s.id)}
                                      onChange={() =>
                                        update({
                                          hiddenSubjects: toggleInSet(
                                            state.hiddenSubjects,
                                            s.id
                                          ),
                                        })
                                      }
                                      className={checkboxClass}
                                    />
                                    <span className="truncate">
                                      {s.label || s.id}
                                      {s.is_custom && (
                                        <span className="ml-1 text-xs text-zinc-500 dark:text-zinc-400">
                                          (
                                          {t(
                                            'reports.editor.customModel',
                                            'custom'
                                          )}
                                          )
                                        </span>
                                      )}
                                    </span>
                                  </label>
                                ))}
                              </div>
                            </div>
                          ))}
                      </div>
                    </div>
                  )}

                  <div className="flex flex-col gap-3 sm:flex-row sm:gap-8">
                    <ToggleSwitch
                      enabled={state.showDistribution}
                      onChange={(enabled) =>
                        update({ showDistribution: enabled })
                      }
                      label={t(
                        'reports.editor.showDistribution',
                        'Verteilung anzeigen'
                      )}
                    />
                    <ToggleSwitch
                      enabled={state.showHumans}
                      onChange={(enabled) => update({ showHumans: enabled })}
                      label={t(
                        'reports.editor.showHumans',
                        'Menschliche Teilnehmende anzeigen'
                      )}
                    />
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center justify-end space-x-3 border-t border-zinc-200 pt-6 dark:border-zinc-700">
          <Button
            onClick={() => router.push(`/projects/${projectId}`)}
            variant="outline"
            disabled={saving}
          >
            {t('project.report.editor.cancel')}
          </Button>
          <Button onClick={handleSave} disabled={saving} variant="filled">
            {saving
              ? t('project.report.editor.saving')
              : t('project.report.editor.saveReport')}
          </Button>
        </div>
      </div>
    </div>
  )
}

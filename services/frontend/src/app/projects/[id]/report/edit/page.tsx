/**
 * Report Editor Page
 *
 * Allows superadmins to view and edit project report content
 * Supports editing all report sections with preview
 *
 * Issue #770: Project Reports Publishing System
 */

'use client'

import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { Button } from '@/components/shared/Button'
import { Label } from '@/components/shared/Label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/shared/Select'
import { Textarea } from '@/components/shared/Textarea'
import { useToast } from '@/components/shared/Toast'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import {
  type ChartType,
  getChartTypes,
} from '@/components/evaluation/ChartTypeSelector'
import { ArrowLeftIcon } from '@heroicons/react/24/outline'
import { useRouter } from 'next/navigation'
import { useEffect, useMemo, useState } from 'react'

const REPORT_VIEW_TYPES: ChartType[] = ['data', 'bar', 'radar', 'table', 'heatmap']
const DEFAULT_REPORT_VIEW: ChartType = 'data'
const DEFAULT_AVAILABLE_VIEWS: ChartType[] = ['data']

interface ReportEditorPageProps {
  params: Promise<{
    id: string
  }>
}

interface ReportContent {
  sections: {
    project_info?: {
      custom_title?: string
      custom_description?: string
    }
    data?: {
      custom_text?: string
      show_count?: boolean
    }
    annotations?: {
      custom_text?: string
      acknowledgment_text?: string
      show_count?: boolean
      show_participants?: boolean
    }
    generation?: {
      custom_text?: string
      show_models?: boolean
    }
    evaluation?: {
      custom_interpretation?: string
      conclusions?: string
      charts_config?: {
        visible_metrics?: string[]
        available_views?: ChartType[]
        default_view?: ChartType
        [key: string]: unknown
      }
    }
  }
  metadata: Record<string, unknown>
}

interface Report {
  id: string
  project_id: string
  project_title: string
  content: ReportContent
  is_published: boolean
}

export default function ReportEditorPage({ params }: ReportEditorPageProps) {
  const router = useRouter()
  const { user } = useAuth()
  const { addToast } = useToast()
  const { t } = useI18n()

  const [projectId, setProjectId] = useState<string | null>(null)
  const [report, setReport] = useState<Report | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  // Editable fields
  const [customTitle, setCustomTitle] = useState('')
  const [customDescription, setCustomDescription] = useState('')
  const [dataText, setDataText] = useState('')
  const [annotationsText, setAnnotationsText] = useState('')
  const [acknowledgment, setAcknowledgment] = useState('')
  const [generationText, setGenerationText] = useState('')
  const [interpretation, setInterpretation] = useState('')
  const [conclusions, setConclusions] = useState('')
  const [availableMetrics, setAvailableMetrics] = useState<string[]>([])
  const [metricLabels, setMetricLabels] = useState<Record<string, string>>({})
  const [visibleMetrics, setVisibleMetrics] = useState<Set<string>>(new Set())
  const [availableViews, setAvailableViews] = useState<Set<ChartType>>(
    new Set(DEFAULT_AVAILABLE_VIEWS)
  )
  const [defaultView, setDefaultView] = useState<ChartType>(DEFAULT_REPORT_VIEW)

  const chartTypeMeta = useMemo(() => getChartTypes(t), [t])
  const chartTypeLabel = useMemo(() => {
    const map: Record<string, string> = {}
    chartTypeMeta.forEach((c) => {
      map[c.type] = c.label
    })
    return map
  }, [chartTypeMeta])

  // Resolve params
  useEffect(() => {
    const resolveParams = async () => {
      const resolvedParams = await params
      setProjectId(resolvedParams.id)
    }
    resolveParams()
  }, [params])

  // Fetch report
  useEffect(() => {
    // Wait for both user and projectId to load before proceeding
    if (!user || !projectId) {
      return
    }

    // Check permissions - superadmin, org admin, or contributor can edit reports
    if (!user.is_superadmin && user.role !== 'ORG_ADMIN' && user.role !== 'CONTRIBUTOR') {
      router.push('/projects')
      return
    }

    const fetchReport = async () => {
      setLoading(true)
      try {
        const response = await fetch(`/api/projects/${projectId}/report`, {
          credentials: 'include',
        })

        if (!response.ok) {
          throw new Error(t('project.report.editor.failedToLoad'))
        }

        const data = await response.json()
        setReport(data)

        // Initialize fields from report content
        const sections = data.content?.sections || {}
        setCustomTitle(sections.project_info?.custom_title || '')
        setCustomDescription(sections.project_info?.custom_description || '')
        setDataText(sections.data?.custom_text || '')
        setAnnotationsText(sections.annotations?.custom_text || '')
        setAcknowledgment(sections.annotations?.acknowledgment_text || '')
        setGenerationText(sections.generation?.custom_text || '')
        setInterpretation(sections.evaluation?.custom_interpretation || '')
        setConclusions(sections.evaluation?.conclusions || '')

        // Load available evaluation metrics (drives the checkbox list).
        try {
          const dataResp = await fetch(`/api/reports/${data.id}/data`, {
            credentials: 'include',
          })
          if (dataResp.ok) {
            const reportData = await dataResp.json()
            const byModel = reportData.evaluation_charts?.by_model || {}
            const metricMetadata =
              reportData.evaluation_charts?.metric_metadata || {}
            const metricsSet = new Set<string>()
            Object.values(byModel).forEach((modelMetrics) => {
              Object.keys(modelMetrics as Record<string, unknown>).forEach((m) =>
                metricsSet.add(m)
              )
            })
            const metrics = Array.from(metricsSet).sort()
            const labels: Record<string, string> = {}
            metrics.forEach((m) => {
              labels[m] =
                (metricMetadata[m] && metricMetadata[m].name) ||
                m.replace(/_/g, ' ')
            })
            setAvailableMetrics(metrics)
            setMetricLabels(labels)

            const persisted =
              sections.evaluation?.charts_config?.visible_metrics
            if (Array.isArray(persisted)) {
              setVisibleMetrics(new Set(persisted))
            } else {
              setVisibleMetrics(new Set(metrics))
            }
          }
        } catch (err) {
          console.error('Failed to load evaluation metrics:', err)
        }

        const persistedViews =
          sections.evaluation?.charts_config?.available_views
        if (Array.isArray(persistedViews) && persistedViews.length > 0) {
          setAvailableViews(
            new Set(
              persistedViews.filter((v): v is ChartType =>
                REPORT_VIEW_TYPES.includes(v as ChartType)
              )
            )
          )
        }
        const persistedDefault =
          sections.evaluation?.charts_config?.default_view
        if (
          persistedDefault &&
          REPORT_VIEW_TYPES.includes(persistedDefault as ChartType)
        ) {
          setDefaultView(persistedDefault as ChartType)
        }
      } catch (error) {
        console.error('Failed to fetch report:', error)
        addToast(t('project.report.editor.failedToLoad'), 'error')
        router.push(`/projects/${projectId}`)
      } finally {
        setLoading(false)
      }
    }

    fetchReport()
  }, [projectId, user, router, addToast, t])

  const handleSave = async () => {
    if (!report || !projectId) return

    setSaving(true)
    try {
      const updatedContent: ReportContent = {
        ...report.content,
        sections: {
          ...report.content.sections,
          project_info: {
            ...report.content.sections.project_info,
            custom_title: customTitle || undefined,
            custom_description: customDescription || undefined,
          },
          data: {
            ...report.content.sections.data,
            custom_text: dataText || undefined,
          },
          annotations: {
            ...report.content.sections.annotations,
            custom_text: annotationsText || undefined,
            acknowledgment_text: acknowledgment || undefined,
          },
          generation: {
            ...report.content.sections.generation,
            custom_text: generationText || undefined,
          },
          evaluation: {
            ...report.content.sections.evaluation,
            custom_interpretation: interpretation || undefined,
            conclusions: conclusions || undefined,
            charts_config: {
              ...(report.content.sections.evaluation?.charts_config || {}),
              visible_metrics:
                availableMetrics.length > 0
                  ? availableMetrics.filter((m) => visibleMetrics.has(m))
                  : undefined,
              available_views: REPORT_VIEW_TYPES.filter((v) =>
                availableViews.has(v)
              ),
              default_view: availableViews.has(defaultView)
                ? defaultView
                : Array.from(availableViews)[0] || DEFAULT_REPORT_VIEW,
            },
          },
        },
      }

      const response = await fetch(`/api/projects/${projectId}/report`, {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ content: updatedContent }),
      })

      if (!response.ok) {
        throw new Error(t('project.report.editor.failedToSave'))
      }

      addToast(t('project.report.editor.savedSuccessfully'), 'success')
      router.push(`/projects/${projectId}`)
    } catch (error) {
      console.error('Failed to save report:', error)
      addToast(t('project.report.editor.failedToSave'), 'error')
    } finally {
      setSaving(false)
    }
  }

  // Show loading while user is being fetched
  if (!user || loading) {
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

  // Only show null if user is loaded but not superadmin
  if (!user.is_superadmin) {
    return null
  }

  if (!report) {
    return null
  }

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

        <div className="mt-4 flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-zinc-900 dark:text-white">
              {t('project.report.editor.title')}
            </h1>
            <p className="mt-2 text-zinc-600 dark:text-zinc-400">
              {t('project.report.editor.subtitle')}
            </p>
          </div>
          <Button
            onClick={() => router.push(`/projects/${projectId}`)}
            variant="outline"
          >
            <ArrowLeftIcon className="mr-2 h-4 w-4" />
            {t('project.report.editor.backToProject')}
          </Button>
        </div>
      </div>

      {/* Editor Form */}
      <div className="space-y-8">
        {/* Project Info Section */}
        <div className="rounded-lg border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-700 dark:bg-zinc-900">
          <h2 className="mb-4 text-lg font-semibold text-zinc-900 dark:text-white">
            {t('project.report.editor.projectInfo.title')}
          </h2>
          <div className="space-y-4">
            <div>
              <Label htmlFor="customTitle">
                {t('project.report.editor.projectInfo.customTitle')}
              </Label>
              <input
                id="customTitle"
                type="text"
                value={customTitle}
                onChange={(e) => setCustomTitle(e.target.value)}
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
                value={customDescription}
                onChange={(e) => setCustomDescription(e.target.value)}
                placeholder={t(
                  'project.report.editor.projectInfo.customDescriptionPlaceholder'
                )}
                rows={3}
              />
            </div>
          </div>
        </div>

        {/* Data Section */}
        <div className="rounded-lg border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-700 dark:bg-zinc-900">
          <h2 className="mb-4 text-lg font-semibold text-zinc-900 dark:text-white">
            {t('project.report.editor.dataSection.title')}
          </h2>
          <div>
            <Label htmlFor="dataText">
              {t('project.report.editor.dataSection.customText')}
            </Label>
            <Textarea
              id="dataText"
              value={dataText}
              onChange={(e) => setDataText(e.target.value)}
              placeholder={t(
                'project.report.editor.dataSection.customTextPlaceholder'
              )}
              rows={4}
            />
          </div>
        </div>

        {/* Annotations Section */}
        <div className="rounded-lg border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-700 dark:bg-zinc-900">
          <h2 className="mb-4 text-lg font-semibold text-zinc-900 dark:text-white">
            {t('project.report.editor.annotationsSection.title')}
          </h2>
          <div className="space-y-4">
            <div>
              <Label htmlFor="annotationsText">
                {t('project.report.editor.annotationsSection.customText')}
              </Label>
              <Textarea
                id="annotationsText"
                value={annotationsText}
                onChange={(e) => setAnnotationsText(e.target.value)}
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
                value={acknowledgment}
                onChange={(e) => setAcknowledgment(e.target.value)}
                placeholder={t(
                  'project.report.editor.annotationsSection.acknowledgmentPlaceholder'
                )}
                rows={3}
              />
            </div>
          </div>
        </div>

        {/* Generation Section */}
        <div className="rounded-lg border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-700 dark:bg-zinc-900">
          <h2 className="mb-4 text-lg font-semibold text-zinc-900 dark:text-white">
            {t('project.report.editor.generationSection.title')}
          </h2>
          <div>
            <Label htmlFor="generationText">
              {t('project.report.editor.generationSection.customText')}
            </Label>
            <Textarea
              id="generationText"
              value={generationText}
              onChange={(e) => setGenerationText(e.target.value)}
              placeholder={t(
                'project.report.editor.generationSection.customTextPlaceholder'
              )}
              rows={4}
            />
          </div>
        </div>

        {/* Evaluation Section */}
        <div className="rounded-lg border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-700 dark:bg-zinc-900">
          <h2 className="mb-4 text-lg font-semibold text-zinc-900 dark:text-white">
            {t('project.report.editor.evaluationSection.title')}
          </h2>
          <div className="space-y-4">
            <div>
              <Label htmlFor="interpretation">
                {t('project.report.editor.evaluationSection.interpretation')}
              </Label>
              <Textarea
                id="interpretation"
                value={interpretation}
                onChange={(e) => setInterpretation(e.target.value)}
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
                value={conclusions}
                onChange={(e) => setConclusions(e.target.value)}
                placeholder={t(
                  'project.report.editor.evaluationSection.conclusionsPlaceholder'
                )}
                rows={4}
              />
            </div>
            <div>
              <div className="mb-1 flex items-center justify-between">
                <Label>
                  {t(
                    'project.report.editor.evaluationSection.visibleMetrics'
                  )}
                </Label>
                {availableMetrics.length > 0 && (
                  <div className="flex gap-3 text-xs">
                    <button
                      type="button"
                      onClick={() =>
                        setVisibleMetrics(new Set(availableMetrics))
                      }
                      className="text-emerald-700 hover:underline dark:text-emerald-400"
                    >
                      {t(
                        'project.report.editor.evaluationSection.selectAll'
                      )}
                    </button>
                    <button
                      type="button"
                      onClick={() => setVisibleMetrics(new Set())}
                      className="text-zinc-600 hover:underline dark:text-zinc-300"
                    >
                      {t(
                        'project.report.editor.evaluationSection.clearAll'
                      )}
                    </button>
                  </div>
                )}
              </div>
              {availableMetrics.length === 0 ? (
                <p className="text-sm text-zinc-500 dark:text-zinc-400">
                  {t(
                    'project.report.editor.evaluationSection.noMetricsAvailable'
                  )}
                </p>
              ) : (
                <>
                  <p className="mb-2 text-xs text-zinc-500 dark:text-zinc-400">
                    {t(
                      'project.report.editor.evaluationSection.visibleMetricsHint'
                    )}
                  </p>
                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
                    {availableMetrics.map((metric) => {
                      const checked = visibleMetrics.has(metric)
                      return (
                        <label
                          key={metric}
                          className="flex items-center gap-2 rounded border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-700 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200"
                        >
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={() =>
                              setVisibleMetrics((prev) => {
                                const next = new Set(prev)
                                if (next.has(metric)) {
                                  next.delete(metric)
                                } else {
                                  next.add(metric)
                                }
                                return next
                              })
                            }
                            className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500"
                          />
                          <span className="capitalize">
                            {metricLabels[metric] || metric}
                          </span>
                        </label>
                      )
                    })}
                  </div>
                </>
              )}
            </div>
            <div>
              <Label>
                {t('project.report.editor.evaluationSection.availableViews')}
              </Label>
              <p className="mb-2 text-xs text-zinc-500 dark:text-zinc-400">
                {t(
                  'project.report.editor.evaluationSection.availableViewsHint'
                )}
              </p>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4">
                {REPORT_VIEW_TYPES.map((view) => {
                  const checked = availableViews.has(view)
                  return (
                    <label
                      key={view}
                      className="flex items-center gap-2 rounded border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-700 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200"
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() =>
                          setAvailableViews((prev) => {
                            const next = new Set(prev)
                            if (next.has(view)) {
                              next.delete(view)
                            } else {
                              next.add(view)
                            }
                            return next
                          })
                        }
                        className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500"
                      />
                      <span>{chartTypeLabel[view] || view}</span>
                    </label>
                  )
                })}
              </div>
            </div>
            <div>
              <Label htmlFor="defaultView">
                {t('project.report.editor.evaluationSection.defaultView')}
              </Label>
              <p className="mb-2 text-xs text-zinc-500 dark:text-zinc-400">
                {t(
                  'project.report.editor.evaluationSection.defaultViewHint'
                )}
              </p>
              <Select
                value={defaultView}
                onValueChange={(value) => setDefaultView(value as ChartType)}
              >
                <SelectTrigger id="defaultView" className="w-full sm:w-64">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {REPORT_VIEW_TYPES.filter((v) =>
                    availableViews.has(v)
                  ).map((view) => (
                    <SelectItem key={view} value={view}>
                      {chartTypeLabel[view] || view}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
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

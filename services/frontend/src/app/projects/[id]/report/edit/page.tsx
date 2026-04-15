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
import { Textarea } from '@/components/shared/Textarea'
import { useToast } from '@/components/shared/Toast'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { ArrowLeftIcon } from '@heroicons/react/24/outline'
import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'

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

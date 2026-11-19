/**
 * Evaluations page: where every result of a project is viewed.
 *
 * The page is a shell: access checks, the searchable project picker, the
 * result type (Metrics or Analyses, `?type=analysis`) and the URL state.
 * The Metrics view (`MetricResultsView`) shows automated, LLM judge and
 * human evaluation results; the Analyses view (`AnalysisResultsView`) shows
 * the analysis runs of variant experiments. Evaluation configuration and
 * starting belongs in project details; editors can also start an analysis
 * run here.
 */

'use client'

import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { Button } from '@/components/shared/Button'
import { Card } from '@/components/shared/Card'
import { LoadingSpinner } from '@/components/shared/LoadingSpinner'
import { ResponsiveContainer } from '@/components/shared/ResponsiveContainer'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { projectsAPI } from '@/lib/api/projects'
import {
  evaluationsPath,
  resultTypeOf,
  type ResultType,
} from '@/lib/results/paths'
import { parseSubdomain } from '@/lib/utils/subdomain'
import { Project } from '@/types/labelStudio'
import { canAccessProjectData } from '@/utils/permissions'
import { ChartBarIcon } from '@heroicons/react/24/outline'
import { useRouter, useSearchParams } from 'next/navigation'
import { useEffect, useMemo, useState } from 'react'
import { AnalysisResultsView } from './_components/AnalysisResultsView'
import {
  MetricResultsView,
  type InitialParams,
} from './_components/MetricResultsView'
import { ProjectPicker, useProjectList } from './_components/ProjectPicker'
import { useAnalysisAvailability } from './_components/useAnalysisAvailability'

/** What a view restores its filters from after a type or project switch. */
const NO_PARAMS: InitialParams = { get: () => null }

/** localStorage key of the last selected project. */
const LAST_PROJECT_KEY = 'evaluations_lastProjectId'

function ResultTypeSwitch({
  value,
  onChange,
}: {
  value: ResultType
  onChange: (type: ResultType) => void
}) {
  const { t } = useI18n()
  const options: { type: ResultType; label: string }[] = [
    { type: 'metrics', label: t('evaluation.viewer.resultType.metrics') },
    { type: 'analysis', label: t('evaluation.viewer.resultType.analysis') },
  ]
  return (
    <div className="flex flex-col">
      <span
        className="mb-1 block text-xs font-medium text-zinc-500"
        id="evaluations-result-type-label"
      >
        {t('evaluation.viewer.resultType.label')}
      </span>
      <div
        role="radiogroup"
        aria-labelledby="evaluations-result-type-label"
        className="inline-flex h-8 items-center gap-0.5 rounded-full bg-zinc-100 p-0.5 dark:bg-zinc-800"
        data-testid="result-type-switch"
      >
        {options.map((option) => {
          const active = option.type === value
          return (
            <button
              key={option.type}
              type="button"
              role="radio"
              aria-checked={active}
              onClick={() => onChange(option.type)}
              className={`rounded-full px-3 py-1 text-xs font-medium whitespace-nowrap transition focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 ${
                active
                  ? 'bg-white text-zinc-900 shadow-sm dark:bg-zinc-600 dark:text-white'
                  : 'text-zinc-600 hover:text-zinc-900 dark:text-zinc-300 dark:hover:text-white'
              }`}
              data-testid={`result-type-${option.type}`}
            >
              {option.label}
            </button>
          )
        })}
      </div>
    </div>
  )
}

export default function EvaluationDashboard() {
  const router = useRouter()
  const { t } = useI18n()
  const searchParams = useSearchParams()
  const { user, isLoading: authLoading, organizations } = useAuth()
  const { isPrivateMode } =
    typeof window !== 'undefined' ? parseSubdomain() : { isPrivateMode: true }

  const projectList = useProjectList(!authLoading)
  const [selectedProject, setSelectedProject] = useState<Project | null>(null)
  // The result type is read from the URL once; the views write it back.
  const [resultType, setResultType] = useState<ResultType>(() =>
    resultTypeOf(searchParams?.get('type')),
  )
  // The URL the views restore their filters from: the page URL on the first
  // view, nothing after the viewer switches the type or the project.
  const [viewParams, setViewParams] = useState<InitialParams | null>(
    () => searchParams ?? null,
  )

  // Load project from URL on mount, or fall back to last selected project
  // from localStorage. A project beyond the picker's first page is fetched
  // by id.
  const wantedProjectId = useMemo(
    () =>
      searchParams?.get('projectId') ||
      (typeof window !== 'undefined'
        ? localStorage.getItem(LAST_PROJECT_KEY)
        : null),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- resolve the wanted project once on mount; picking another one replaces it.
    [],
  )
  useEffect(() => {
    if (!wantedProjectId || selectedProject || !projectList.loaded) return
    const project = projectList.projects.find(
      (p) => p.id.toString() === wantedProjectId,
    )
    if (project) {
      setSelectedProject(project)
      return
    }
    if (projectList.search) return
    let cancelled = false
    ;(async () => {
      try {
        const fetched = await projectsAPI.get(wantedProjectId)
        if (!cancelled && fetched) setSelectedProject(fetched)
      } catch {
        // Not readable: the picker stays empty.
      }
    })()
    return () => {
      cancelled = true
    }
  }, [
    wantedProjectId,
    selectedProject,
    projectList.loaded,
    projectList.projects,
    projectList.search,
  ])

  // Persist last selected project for next visit
  useEffect(() => {
    if (selectedProject) {
      localStorage.setItem(LAST_PROJECT_KEY, selectedProject.id.toString())
    }
  }, [selectedProject])

  const availability = useAnalysisAvailability(
    selectedProject ? selectedProject.id.toString() : null,
  )
  const offerAnalyses =
    resultType === 'analysis' || availability.hasRuns || availability.hasDesigns

  const selectProject = (project: Project) => {
    if (selectedProject?.id === project.id) return
    setSelectedProject(project)
    setViewParams(NO_PARAMS)
  }

  const switchResultType = (type: ResultType) => {
    if (type === resultType) return
    setResultType(type)
    setViewParams(NO_PARAMS)
    router.replace(
      evaluationsPath({ projectId: selectedProject?.id ?? null, type }),
      { scroll: false },
    )
  }

  // Check permissions (resolved across all org memberships)
  useEffect(() => {
    if (
      !authLoading &&
      !canAccessProjectData(user, { isPrivateMode, organizations })
    ) {
      router.replace('/projects?error=no-permission')
    }
  }, [user, authLoading, router, isPrivateMode, organizations])

  if (authLoading) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <LoadingSpinner />
      </div>
    )
  }
  if (!canAccessProjectData(user, { isPrivateMode, organizations })) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <div className="text-center">
          <h3 className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
            {t('evaluation.accessDenied')}
          </h3>
          <Button onClick={() => router.push('/projects')} className="mt-4">
            {t('common.backToProjects')}
          </Button>
        </div>
      </div>
    )
  }

  const lead = (
    <>
      <ProjectPicker
        list={projectList}
        selectedProject={selectedProject}
        onSelect={selectProject}
      />
      {selectedProject && offerAnalyses && (
        <ResultTypeSwitch value={resultType} onChange={switchResultType} />
      )}
    </>
  )

  // Starting a run follows the backend's edit decision (the API's rule):
  // viewers without edit rights see the results but no run controls.
  const canRun =
    Boolean(user?.is_superadmin) || selectedProject?.can_edit === true

  return (
    <ResponsiveContainer size="full" className="pt-8 pb-10">
      {/* Breadcrumb */}
      <div className="mb-4">
        <Breadcrumb
          items={[
            { label: t('navigation.dashboard'), href: '/dashboard' },
            {
              label: t('navigation.evaluation'),
              href: '/evaluations',
            },
          ]}
        />
      </div>

      {/* Header */}
      <div className="mb-6">
        <h1 className="text-3xl font-bold tracking-tight text-zinc-900 dark:text-white">
          {t('evaluation.viewer.title')}
        </h1>
        {!selectedProject && (
          <p className="mt-2 text-zinc-600 dark:text-zinc-400">
            {t('evaluation.viewer.selectProjectDescription')}
          </p>
        )}
      </div>

      {selectedProject && resultType === 'metrics' && (
        <MetricResultsView
          selectedProject={selectedProject}
          filterBarLead={lead}
          initialParams={viewParams}
        />
      )}

      {selectedProject && resultType === 'analysis' && (
        <AnalysisResultsView
          key={selectedProject.id}
          project={selectedProject}
          filterBarLead={lead}
          initialParams={viewParams}
          canStart={canRun}
        />
      )}

      {/* No Project Selected */}
      {!selectedProject && (
        <>
          <Card className="mb-2 p-4">
            <div className="flex flex-wrap items-end gap-3">{lead}</div>
          </Card>
          <Card className="p-12 text-center">
            <ChartBarIcon className="mx-auto h-12 w-12 text-zinc-400" />
            <h3 className="mt-4 text-lg font-semibold text-zinc-900 dark:text-white">
              {t('evaluation.viewer.emptyStates.selectProject.title')}
            </h3>
            <p className="mt-2 text-zinc-500 dark:text-zinc-400">
              {t('evaluation.viewer.emptyStates.selectProject.description')}
            </p>
          </Card>
        </>
      )}
    </ResponsiveContainer>
  )
}

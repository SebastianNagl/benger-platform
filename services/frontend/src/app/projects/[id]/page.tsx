/**
 * Project Detail page - Label Studio aligned with BenGER task page layout
 *
 * Project dashboard with comprehensive management features
 *
 * @version 2.0.0
 * @since Issue #246 - Dynamic model fetching from API instead of hardcoded models
 *
 * Features:
 * - Dynamic LLM model selection based on user's configured API keys
 * - Real-time loading and error states for model fetching
 * - Support for 8+ models from OpenAI, Anthropic, Google, and DeepInfra
 */

'use client'

import { ProjectAnalysesSection } from '@/components/analysis/ProjectAnalysesSection'
import { EvaluationBuilder } from '@/components/evaluation/EvaluationBuilder'
import { EvaluationControlModal } from '@/components/evaluation/EvaluationControlModal'
import { GenerationControlModal } from '@/components/generation/GenerationControlModal'
import {
  AdvancedSettingsCard,
  InstructionDisplaySettings,
  type AdvancedSettings,
  type AdvancedSettingsSetter,
} from '@/components/projects/AdvancedSettingsCard'
import {
  ConditionalInstructionsEditor,
  conditionalInstructionsValid,
  type ConditionalInstruction,
} from '@/components/projects/ConditionalInstructionsEditor'
import { ConfigCard } from '@/components/projects/ConfigCard'
import { EvaluationDefaultsCard } from '@/components/projects/EvaluationDefaultsCard'
import { EvaluationPromptsOverview } from '@/components/projects/EvaluationPromptsOverview'
import { GenerationDefaultsCard } from '@/components/projects/GenerationDefaultsCard'
import {
  LabelConfigEditor,
  labelConfigError,
} from '@/components/projects/LabelConfigEditor'
import {
  ModelSelectionSection,
  providerColors,
  type ReasoningConfig,
} from '@/components/projects/ModelSelectionSection'
import { ParticipantCard } from '@/components/projects/ParticipantCard'
import { ProjectAccessWindowSection } from '@/components/projects/ProjectAccessWindowSection'
import { ProjectBillingCard } from '@/components/projects/ProjectBillingCard'
import { ProjectBreadcrumb } from '@/components/projects/ProjectBreadcrumb'
import { ProjectKindSection } from '@/components/projects/ProjectKindSection'
import { ProjectMetadataCard } from '@/components/projects/ProjectMetadataCard'
import { ProjectPermissionsPanel } from '@/components/projects/ProjectPermissionsPanel'
import { registerProjectSettingRisks } from '@/components/projects/projectSettingRisks'
import { PromptStructuresManager } from '@/components/projects/PromptStructuresManager'
import {
  SettingsGroup,
  SettingsGroupStack,
} from '@/components/projects/SettingsGroup'
import { SubSection } from '@/components/projects/SubSection'
import { IconPickerModal } from '@/components/projects/wizard/ProjectTypeAndIcon'
import { QuestionnairesSettings } from '@/components/questionnaires/QuestionnairesSettings'
import { PublicationToggle } from '@/components/reports/PublicationToggle'
import { AppLoadingScreen } from '@/components/shared/AppLoadingScreen'
import { useAutoSaveBuffer } from '@/components/shared/AutoSave'
import { Button } from '@/components/shared/Button'
import { Card } from '@/components/shared/Card'
import { Checkbox } from '@/components/shared/Checkbox'
import { Input } from '@/components/shared/Input'
import { Label } from '@/components/shared/Label'
import {
  SettingRiskProvider,
  settingChanges,
  useGatedSettingChange,
} from '@/components/shared/settingRisk'
import { Textarea } from '@/components/shared/Textarea'
import { useToast } from '@/components/shared/Toast'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { useModels } from '@/hooks/useModels'
import { useRouteProject } from '@/hooks/useRouteProject'
import { analysisAPI } from '@/lib/api/analysis'
import { apiClient } from '@/lib/api/client'
import { isExamNotReadyError } from '@/lib/api/errors'
import type {
  AvailableEvaluationFields,
  EvaluationConfig,
} from '@/lib/api/evaluation-types'
import { sharesAPI, type Participation } from '@/lib/api/shares'
import { describeEvaluationConfigWarnings } from '@/lib/evaluation/configWarnings'
import { refreshEvaluationConfigs } from '@/lib/evaluation/refreshEvaluationConfigs'
import { useSlot } from '@/lib/extensions/slots'
import { useFeatureFlag, useFeatureFlagsReady } from '@/lib/featureFlags'
import {
  REPORT_PAPER,
  VARIANT_EXPERIMENTS,
} from '@/lib/featureFlags/platformFlags'
import { useMaxGenerationRunsPerTask } from '@/lib/generationLimits'
import { dateFnsLocale } from '@/lib/i18n/locales'
import {
  getDefaultMaxTokens,
  getRecommendedParam,
  getTemperatureConstraints,
  hasRecommendations,
} from '@/lib/modelConstraints'
import { projectIcon } from '@/lib/projectKind'
import { evaluationsPath } from '@/lib/results/paths'
import { logger } from '@/lib/utils/logger'
import { useUIStore } from '@/stores'
import { useProjectStore } from '@/stores/projectStore'
import { computeWindowState } from '@/utils/projectWindow'
import {
  CheckCircleIcon,
  DocumentChartBarIcon,
  DocumentTextIcon,
  PencilIcon,
  PlayIcon,
  UserGroupIcon,
} from '@heroicons/react/24/outline'
import { formatDistanceToNow } from 'date-fns'
import { useRouter } from 'next/navigation'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

// High-impact project settings ask before they are applied.
registerProjectSettingRisks()

// providerColors is shared with ModelSelectionSection — imported above.

// ReasoningConfig is shared with ModelSelectionSection — imported above.
// Thinking-preset shape for the provider preset tables below.
interface ThinkingPreset {
  label: string
  value: number
}

// Anthropic Claude presets (min: 1024, max: 128000)
const CLAUDE_PRESETS: ThinkingPreset[] = [
  { label: 'Low', value: 4096 },
  { label: 'Medium', value: 16000 },
  { label: 'High', value: 64000 },
]

// Google Gemini presets (min: 0, max: 24576)
const GEMINI_PRESETS: ThinkingPreset[] = [
  { label: 'Low', value: 1024 },
  { label: 'Medium', value: 8192 },
  { label: 'High', value: 24576 },
]

// Qwen presets (min: 1024, max: 32000)
const QWEN_PRESETS: ThinkingPreset[] = [
  { label: 'Low', value: 2048 },
  { label: 'Medium', value: 8000 },
  { label: 'High', value: 24000 },
]

// Model defaults are now driven by parameter_constraints from the backend API.
// See getTemperatureConstraints() and getDefaultMaxTokens() from @/lib/modelConstraints.

interface ProjectDetailPageProps {
  params: Promise<{
    id: string
  }>
}

/**
 * The page inside the high-impact settings boundary: the confirmation
 * dialog and the context its texts use (running exam, submitted count)
 * must sit above the page's own hooks, which ask through it.
 */
export default function ProjectDetailPage(props: ProjectDetailPageProps) {
  const currentProject = useProjectStore((s) => s.currentProject)
  return (
    <SettingRiskProvider
      context={{
        project: currentProject as Record<string, any> | null,
        runningExam:
          computeWindowState(
            currentProject?.window_start_at,
            currentProject?.window_end_at,
          ) === 'open',
        submittedCount: currentProject?.annotation_count ?? 0,
      }}
    >
      <ProjectDetailPageContent {...props} />
    </SettingRiskProvider>
  )
}

function ProjectDetailPageContent({ params }: ProjectDetailPageProps) {
  const router = useRouter()
  const [projectId, setProjectId] = useState<string | null>(null)
  const { user } = useAuth()
  const { addToast } = useToast()
  const { isSidebarHidden } = useUIStore()
  const { t, locale } = useI18n()
  // The experiment features (variant_experiments): the Analysis action and
  // count, and a runs cap of 100 instead of 25.
  const variantExperiments = useFeatureFlag(VARIANT_EXPERIMENTS)
  const reportPaper = useFeatureFlag(REPORT_PAPER)
  const maxRunsPerTask = useMaxGenerationRunsPerTask()

  const { fetchProject, updateProject, deleteProject } = useProjectStore()
  // Only the project this URL names: the store may still hold the one
  // opened before, whose title, gates and quick actions must not show here
  // until the answer swaps them. Fetched on every visit (fresh counts).
  const { project: currentProject, notFound } = useRouteProject(projectId, {
    refresh: true,
  })
  // The page's first frame already shows flag-gated parts (the Evaluations
  // target, the report card, the extended quick actions): it waits for the
  // flags rather than adding them a moment later.
  const flagsReady = useFeatureFlagsReady()

  // Every gate below reads the per-project fields the API resolves across
  // ALL of the caller's memberships (effective_role, can_edit, access_tier).
  // The selected organization context plays no part in read or edit access.
  // Narrow tiers: joined via share link / discovery enrollment / org exam
  // (participant), or read access kept through an own submission after the
  // window closed / the project was archived / the membership ended
  // (attempted). The page then behaves like an annotator's view plus a badge;
  // attempted additionally loses every action that would start new work.
  const isAttempted = currentProject?.access_tier === 'attempted'
  const isParticipant =
    currentProject?.access_tier === 'participant' || isAttempted
  // Editor-only fetches wait for the project (so a participant never fires
  // requests that would 403) and run once its id is known.
  const accessTierKnown = currentProject?.id === projectId

  const [tasks, setTasks] = useState([])
  const [userCompletedAllTasks, setUserCompletedAllTasks] = useState(false)
  // The caller's next-task read was refused with 403 `exam_not_ready`: the
  // exam is held until its grading sheet is checked, so starting it would
  // only lead to the "not released yet" card.
  const [examNotReady, setExamNotReady] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [deleting, setDeleting] = useState(false)

  // Editing states
  const [editingTitle, setEditingTitle] = useState(false)
  const [iconPickerOpen, setIconPickerOpen] = useState(false)
  const [titleValue, setTitleValue] = useState('')
  const [editingDescription, setEditingDescription] = useState(false)
  const [descriptionValue, setDescriptionValue] = useState('')
  const [isUpdating, setIsUpdating] = useState(false)

  // Expanded sections
  const [expandedModels, setExpandedModels] = useState(false)
  // Switched-on questionnaires (the Fragebögen card's badge), once loaded.
  const [activeQuestionnaires, setActiveQuestionnaires] = useState<
    number | null
  >(null)
  // Generation/Evaluation Defaults now use the shared SubSection wrapper
  // which owns its own expand state — these locals are no longer needed
  // but TypeScript treats unused setters as errors only when strict, so
  // leaving them removed is the cleaner path.

  // Footer-level "Generierung/Evaluierung starten" buttons live at the
  // ConfigCard level (parallel to the deep button inside EvaluationBuilder
  // that's only visible when Methoden is expanded). Two paths to the same
  // modal is intentional — the deep one stays for power users editing the
  // metric list, the surface one is the always-visible CTA when the card
  // is open.
  const [showGenerationStartModal, setShowGenerationStartModal] =
    useState(false)
  const [showEvaluationStartModal, setShowEvaluationStartModal] =
    useState(false)

  // Saved analysis plans (evaluation_config.analysis_plans), for the badge
  // of the Evaluation card's Analyses part.
  const [analysisPlanCount, setAnalysisPlanCount] = useState(0)
  // Evaluation configs (Phase 8: N:M Field Mapping)
  const [evaluationConfigs, setEvaluationConfigs] = useState<
    EvaluationConfig[]
  >([])
  const [availableEvaluationFields, setAvailableEvaluationFields] =
    useState<AvailableEvaluationFields>({
      model_response_fields: [],
      human_annotation_fields: [],
      reference_fields: [],
      all_fields: [],
    })

  // Model selection
  const [selectedModelIds, setSelectedModelIds] = useState<string[]>([])
  const [modelConfigs, setModelConfigs] = useState<Record<string, any>>({})
  const [isUpdatingModels, setIsUpdatingModels] = useState(false)
  const [skipModelReset, setSkipModelReset] = useState(false)

  // Evaluation defaults
  const [evalDefaultTemperature, setEvalDefaultTemperature] = useState<
    number | undefined
  >(undefined)
  const [evalDefaultMaxTokens, setEvalDefaultMaxTokens] = useState<
    number | undefined
  >(undefined)
  // Multi-run default for evaluation (migration 042). Used when no judge
  // ensemble is configured (i.e. metric_parameters.judges is empty); when an
  // ensemble exists, judge_runs are driven by the per-judge `runs` entries
  // instead. Bounded server-side at 1..25.
  const [evalDefaultRunsPerTask, setEvalDefaultRunsPerTask] = useState<
    number | undefined
  >(undefined)
  const [isUpdatingEvalDefaults, setIsUpdatingEvalDefaults] = useState(false)

  // Defaults mode for evaluation: drives the per-judge pre-fill when a new
  // judge metric is configured. Mirrors the generation-side mode below.
  type DefaultsMode = 'recommended' | 'minimum' | 'custom'
  const [evalDefaultsMode, setEvalDefaultsMode] =
    useState<DefaultsMode>('recommended')

  // Generation defaults
  const [genDefaultTemperature, setGenDefaultTemperature] = useState<
    number | undefined
  >(undefined)
  const [genDefaultMaxTokens, setGenDefaultMaxTokens] = useState<
    number | undefined
  >(undefined)
  // Multi-run default for generation (migration 041). Number of trials per
  // (task, model, structure). Per-trigger override is allowed in the
  // GenerationControlModal. Bounded server-side at 1..25.
  const [genDefaultRunsPerTask, setGenDefaultRunsPerTask] = useState<
    number | undefined
  >(undefined)
  // Defaults mode for generation: drives per-model pre-fill when a model is
  // toggled in. `recommended` reads model.recommended_parameters,
  // `minimum` uses parameter_constraints.temperature.min (lowest stable
  // value the provider allows), `custom` uses the values entered above.
  // Constraint clamping (e.g. GPT-5 forces temp=1.0) always wins.
  const [genDefaultsMode, setGenDefaultsMode] =
    useState<DefaultsMode>('recommended')
  // Ref mirror of the mode + custom values so handleModelToggle reads the
  // LATEST values regardless of React render timing. Without these refs a
  // user pattern of "switch mode, then immediately toggle a model" can read
  // a stale closure-captured mode if React hasn't re-rendered between the
  // radio click and the checkbox click.
  const genDefaultsModeRef = useRef<DefaultsMode>('recommended')
  const genDefaultTempRef = useRef<number | undefined>(undefined)
  const genDefaultMaxTokensRef = useRef<number | undefined>(undefined)
  useEffect(() => {
    genDefaultsModeRef.current = genDefaultsMode
  }, [genDefaultsMode])
  useEffect(() => {
    genDefaultTempRef.current = genDefaultTemperature
  }, [genDefaultTemperature])
  useEffect(() => {
    genDefaultMaxTokensRef.current = genDefaultMaxTokens
  }, [genDefaultMaxTokens])
  const [isUpdatingGenDefaults, setIsUpdatingGenDefaults] = useState(false)

  // Fetch available models dynamically from the API based on user's configured API keys
  // This replaces the previous hardcoded model list and supports all 8+ available models
  // Issue #246: Dynamic model fetching for full LLM selection
  const {
    models: availableModels,
    loading: modelsLoading,
    error: modelsError,
    // Only editors configure models here; for everyone else the endpoint
    // answers 403 (a failed request and a console error per page view).
  } = useModels({
    enabled: !!user?.is_superadmin || !!currentProject?.can_edit,
  })

  // The API lists the models in catalog order, grouped by provider and
  // newest first (lib/modelOrder), the order every model picker shows.
  const sortedModels = availableModels ?? null

  // Recommended-value consensus across the project's selected models, scoped
  // to a usage mode (generation vs evaluation). Mirrors the pattern in
  // GenerationControlModal so the project Defaults SubSection can show the
  // same "Empfehlung: X / Verschiedene / Keine Empfehlung" badge UX. Returns
  // a per-key consensus shape that downstream JSX renders.
  function buildRecommendedConsensus(mode: 'generation' | 'evaluation') {
    function consensusFor(key: 'temperature' | 'max_tokens'): {
      value: number | undefined
      uniform: boolean
      anyRec: boolean
      perModel: Array<{ model: string; value: number | undefined }>
    } {
      if (selectedModelIds.length === 0) {
        return { value: undefined, uniform: false, anyRec: false, perModel: [] }
      }
      const perModel = selectedModelIds.map((modelId) => {
        const model = availableModels?.find((m) => m.id === modelId)
        const rec = getRecommendedParam(model, key, mode)
        return {
          model: modelId,
          value: typeof rec === 'number' ? rec : undefined,
          hasAnyRec: hasRecommendations(model),
        }
      })
      const anyRec = perModel.some((m) => m.hasAnyRec)
      const distinct = Array.from(
        new Set(perModel.map((m) => m.value).filter((v) => v !== undefined)),
      )
      const uniform = distinct.length === 1
      return {
        value: uniform ? (distinct[0] as number) : undefined,
        uniform,
        anyRec,
        perModel: perModel.map(({ model, value }) => ({ model, value })),
      }
    }
    return {
      temperature: consensusFor('temperature'),
      max_tokens: consensusFor('max_tokens'),
    }
  }
  const genRecConsensus = useMemo(
    () => buildRecommendedConsensus('generation'),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- buildRecommendedConsensus closes over selectedModelIds + availableModels
    [selectedModelIds, availableModels],
  )
  const evalRecConsensus = useMemo(
    () => buildRecommendedConsensus('evaluation'),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [selectedModelIds, availableModels],
  )

  // Instructions state
  const [instructions, setInstructions] = useState('')
  const [instructionsValue, setInstructionsValue] = useState('')

  //  settings
  const [expanded, setExpanded] = useState(false)
  const ProjectSettingsExtended = useSlot('project-settings-extended')
  // Overlay checkboxes shown right below the paste switch (e.g. file upload).
  // Further "Bearbeitung" settings of Annotationsablauf & -verhalten
  // (e.g. draft checkpoints), rendered in that group. Community builds
  // register nothing.
  const ProjectSettingsAnnotationWork = useSlot(
    'project-settings-annotation-work',
  )
  const ProjectSettingsInterfaceExtra = useSlot(
    'project-settings-interface-extra',
  )
  const ProjectStatisticsExtended = useSlot('project-statistics-extended')
  // Exam-level Notenschlüssel editor inside the evaluation card. The slot
  // owns its own save (a minimal `{ grade_scale }` PUT against the
  // deep-merging eval-config endpoint), so the card's auto-save lifecycle
  // stays untouched. Community builds register nothing → card unchanged.
  const ProjectGradeScale = useSlot('project-evaluation-grade-scale')
  // Extension rows inside the Evaluation settings sub-section (e.g. grading
  // policy switches stored on an evaluation config). The slot gets the
  // config list being edited and hands a changed list back through
  // `onEvaluationConfigsChange`, which runs the card's own dirty and
  // debounced-save path; it never saves by itself. Community builds register
  // nothing → the sub-section is unchanged.
  const ProjectEvaluationSettingsSection = useSlot(
    'project-evaluation-settings-section',
  )
  // A section of its own inside the evaluation card, after the methods, for
  // how people grade (e.g. the human grading settings). It saves itself like
  // the grade scale slot and is not part of the card's auto-save. Community
  // builds register nothing → the card is unchanged.
  const ProjectEvaluationGradingSection = useSlot(
    'project-evaluation-grading-section',
  )
  // Student access (share links, participants, discoverability) — sub-sections
  // of the Project settings card, filled by the extended edition.
  const ProjectSharing = useSlot('project-sharing')
  // Safe Exam Browser requirement for exams (extended): its own save.
  const ProjectExamSecurity = useSlot('project-exam-security')
  // Exam tools (calculator, calendar, law texts, ...) the writers may use.
  const ProjectExamTools = useSlot('project-exam-tools')
  const ProjectDeckWorkspace = useSlot('project-deck-workspace')
  const ProjectSolverActions = useSlot('project-solver-actions')
  // Extended Quick Actions for the project's editors only.
  const ProjectEditorActions = useSlot('project-editor-actions')
  // Learning-platform (LMS) activities linked to this project, shown under the
  // quick actions. The slot renders nothing for projects outside an LMS.
  const ProjectLmsActivities = useSlot('project-lms-activities')
  const ProjectLmsLinking = useSlot('project-lms-linking')
  const [advancedSettings, setAdvancedSettings] = useState({
    show_instruction: true,
    instructions_always_visible: false,
    show_skip_button: true,
    show_submit_button: true,
    require_comment_on_skip: false,
    require_confirm_before_submit: false,
    allow_external_paste: true,
    allow_solution_upload: true,
    // Handwritten uploads (extended slot): switch + model override
    // (null = the organization's default, else the platform default)
    handwriting_ocr_enabled: true,
    handwriting_ocr_model: null as string | null,
    skip_queue: 'requeue_for_others' as
      'requeue_for_me' | 'requeue_for_others' | 'ignore_skipped',
    maximum_annotations: 1,
    min_annotations_per_task: 1,
    assignment_mode: 'open' as 'open' | 'manual' | 'auto',
    randomize_task_order: false,
    annotator_full_visibility_after_submit: false,
    // null = follow annotator_full_visibility_after_submit
    annotator_step_detail_after_submit: null as boolean | null,
    review_enabled: false,
    review_mode: 'in_place' as 'in_place' | 'independent' | 'both',
    allow_self_review: false,
    korrektur_enabled: false,
    korrektur_config: [] as Array<{ value: string; background: string }>,
    annotation_time_limit_enabled: false,
    annotation_time_limit_seconds: null as number | null,
    strict_timer_enabled: false,
    restorable_checkpoints_enabled: false,
  })

  // Per-card buffer for evaluation-scoped settings. Decouples the Eval card's
  // Speichern from the Annotation card's so flushing one doesn't drag the
  // other's local buffer into the PATCH.
  const [evaluationSettings, setEvaluationSettings] = useState({
    immediate_evaluation_enabled: false,
  })

  // Conditional instructions state
  const [conditionalInstructions, setConditionalInstructions] = useState<
    ConditionalInstruction[]
  >([])
  // The label configuration being edited (saved by the annotation card).
  const [labelConfigValue, setLabelConfigValue] = useState('')

  // Report state (Issue #770)
  const [reportStatus, setReportStatus] = useState<{
    reportId: string | null
    isPublished: boolean
    isPublic: boolean
    canPublish: boolean
    canPublishReason: string
    /** The viewer authors the report (owner, org admin or superadmin). */
    canEdit: boolean
  } | null>(null)
  const [loadingReport, setLoadingReport] = useState(false)

  // Resolve params Promise
  useEffect(() => {
    const resolveParams = async () => {
      const resolvedParams = await params
      setProjectId(resolvedParams.id)
    }
    resolveParams()
  }, [params])

  // Fetch report status (Issue #770). The API decides who authors the
  // report (can_edit) and creates it on an author's first view; readers get
  // a 403 for a draft, or can_edit false, and no card.
  const fetchReportStatus = async () => {
    // Report authors besides superadmins belong to the report as project
    // paper (report_paper); off, only superadmins get the card.
    if (!projectId || !user || !(user.is_superadmin || reportPaper)) return

    setLoadingReport(true)
    try {
      const response = await fetch(`/api/projects/${projectId}/report`, {
        credentials: 'include',
      })

      if (response.ok) {
        const data = await response.json()
        setReportStatus({
          reportId: data.id ?? null,
          isPublished: data.is_published,
          isPublic: Boolean(data.is_public),
          canPublish: data.can_publish,
          canPublishReason: data.can_publish_reason,
          canEdit: data.can_edit === true,
        })
      } else {
        setReportStatus(null)
      }
    } catch (error) {
      console.error('Failed to fetch report status:', error)
    } finally {
      setLoadingReport(false)
    }
  }

  // Check if current user has completed all tasks (per-user, not global).
  // Its answer shapes the first quick action (the "all annotated" notice,
  // "Annotation starten" disabled while an exam is not ready), so the page
  // waits for it (nextCheckedFor) instead of changing the action later. The
  // first check runs while the project still loads, not after it; the
  // project's arrival is no reason to ask again, a change of its counts is.
  const taskCount = currentProject?.task_count
  const annotationCount = currentProject?.annotation_count
  const [nextCheckedFor, setNextCheckedFor] = useState<string | null>(null)
  const nextAskedRef = useRef<{
    projectId: string
    counts: string | null
    request: number
  } | null>(null)
  useEffect(() => {
    if (!projectId) return
    const counts =
      taskCount === undefined ? null : `${taskCount}:${annotationCount}`
    const prev = nextAskedRef.current
    if (
      prev &&
      prev.projectId === projectId &&
      (prev.counts === null || prev.counts === counts)
    ) {
      prev.counts = counts
      return
    }
    const request = (prev?.request ?? 0) + 1
    nextAskedRef.current = { projectId, counts, request }
    const isLatest = () => nextAskedRef.current?.request === request
    if (taskCount === 0) {
      setUserCompletedAllTasks(false)
      setExamNotReady(false)
      setNextCheckedFor(projectId)
      return
    }
    apiClient
      .get(`/projects/${projectId}/next`)
      .then((result: { task?: unknown; remaining?: number }) => {
        if (!isLatest()) return
        setUserCompletedAllTasks(!result.task && result.remaining === 0)
        setExamNotReady(false)
      })
      .catch((error: unknown) => {
        if (!isLatest()) return
        setUserCompletedAllTasks(false)
        setExamNotReady(isExamNotReadyError(error))
      })
      .finally(() => {
        if (isLatest()) setNextCheckedFor(projectId)
      })
  }, [projectId, taskCount, annotationCount])

  // The participant card shows only what the participation allows (leave
  // button, or nothing at all), so the page reads it before its first frame
  // instead of letting the card appear or vanish later (participationFor).
  // A failed read counts as an answer: the card then falls back to `via`.
  const [participation, setParticipation] = useState<Participation | null>(null)
  const [participationFor, setParticipationFor] = useState<string | null>(null)
  useEffect(() => {
    if (!projectId || !isParticipant) return
    let cancelled = false
    sharesAPI
      .getParticipation(projectId)
      .then((p) => {
        if (cancelled) return
        setParticipation(p)
        setParticipationFor(projectId)
      })
      .catch(() => {
        if (cancelled) return
        setParticipation(null)
        setParticipationFor(projectId)
      })
    return () => {
      cancelled = true
    }
  }, [projectId, isParticipant])

  // Fetch report status when user or projectId changes (Issue #770)
  useEffect(() => {
    if (projectId && user && accessTierKnown && !isParticipant) {
      fetchReportStatus()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fetchReportStatus is stable, only re-run when projectId or user changes
  }, [projectId, user, accessTierKnown, isParticipant, reportPaper])

  // The configs as the card last read or saved them: the base of the
  // three-way merge when another writer changed them (see
  // refreshEvaluationConfigs).
  const evaluationConfigsBaselineRef = useRef<EvaluationConfig[]>([])
  // The card's buffer as of the latest change, kept in step with the
  // baseline so a save always sends a buffer and the base it started from.
  const evaluationConfigsRef = useRef<EvaluationConfig[]>([])
  // A refresh read that overlaps a card save may return the list from before
  // that save; it is only applied when no save started or finished meanwhile.
  const evaluationConfigsSaveSeqRef = useRef(0)
  const evaluationConfigsSaveInFlightRef = useRef<Promise<void> | null>(null)

  const readEvaluationConfig = async () => {
    const configResponse = await apiClient.get(
      `/evaluations/projects/${projectId}/evaluation-config`,
    )
    // Support current key (evaluation_configs) and legacy key (multi_field_evaluations)
    const configs: EvaluationConfig[] =
      configResponse?.evaluation_configs ||
      configResponse?.multi_field_evaluations ||
      []
    return { configResponse, configs }
  }

  // Fetch existing multi-field evaluations on page load (for badge display)
  useEffect(() => {
    const fetchEvaluationConfig = async () => {
      if (!projectId) return
      // Participants have no evaluation config to read (403) — skip.
      if (!accessTierKnown || isParticipant) return

      try {
        const { configResponse, configs } = await readEvaluationConfig()
        if (configs.length > 0) {
          evaluationConfigsBaselineRef.current = configs
          evaluationConfigsRef.current = configs
          setEvaluationConfigs(configs)
        }
        setAnalysisPlanCount(
          Array.isArray(configResponse?.analysis_plans)
            ? configResponse.analysis_plans.length
            : 0,
        )
      } catch (error) {
        console.error('Failed to fetch evaluation config:', error)
      }
    }

    fetchEvaluationConfig()
    // eslint-disable-next-line react-hooks/exhaustive-deps -- readEvaluationConfig only reads projectId
  }, [projectId, accessTierKnown, isParticipant])

  // Re-read the configs after a section that saves into them on its own
  // (the grading section slot). The card's auto-save PUTs the whole list,
  // which the server replaces, so a buffer that missed that write would
  // revert it on the next card save. Unsaved card edits are kept.
  const refreshEvaluationConfigsFromServer = async () => {
    if (!projectId || !accessTierKnown || isParticipant) return
    try {
      for (;;) {
        await evaluationConfigsSaveInFlightRef.current
        const saveSeq = evaluationConfigsSaveSeqRef.current
        const { configs } = await readEvaluationConfig()
        if (evaluationConfigsSaveSeqRef.current !== saveSeq) continue
        const merged = refreshEvaluationConfigs(
          evaluationConfigsBaselineRef.current,
          evaluationConfigsRef.current,
          configs,
        )
        evaluationConfigsBaselineRef.current = configs
        evaluationConfigsRef.current = merged
        setEvaluationConfigs(merged)
        return
      }
    } catch (error) {
      console.error('Failed to refresh evaluation config:', error)
    }
  }

  useEffect(() => {
    const fetchAvailableFields = async () => {
      if (!projectId) return
      if (!accessTierKnown || isParticipant) return

      try {
        const fields =
          await apiClient.evaluations.getAvailableEvaluationFields(projectId)
        setAvailableEvaluationFields(fields)
      } catch (error) {
        console.error('Failed to fetch available fields:', error)
      }
    }

    fetchAvailableFields()
  }, [projectId, accessTierKnown, isParticipant])

  // Persist the evaluation configs. Minimal body — the backend deep-merges
  // into the stored document (lists replace wholesale), so sibling keys
  // written by handleSaveEvalDefaults' PATCH survive without a
  // read-modify-write here (issue #289: the old GET→PUT round-trip re-sent
  // a 30s-cached snapshot of the whole doc and clobbered concurrent saves).
  //
  // The save answers with non-blocking warnings: configs that, as saved,
  // will grade nothing (no reference field, or a prediction side this
  // project has no data on). The card auto-saves on a debounce, so a warning
  // is shown when the set of warnings changes, not again on every save.
  const lastEvaluationConfigWarningsRef = useRef('')
  const saveEvaluationConfigsToProject = async (
    evaluations: EvaluationConfig[],
    base: EvaluationConfig[],
  ) => {
    if (!projectId) return

    let response: any
    try {
      response = await apiClient.put(
        `/evaluations/projects/${projectId}/evaluation-config`,
        {
          evaluation_configs: evaluations,
          // The list this buffer started from: keys another writer changed
          // since then and this save did not touch keep the server's value.
          evaluation_configs_base: base,
        },
      )
      evaluationConfigsBaselineRef.current = evaluations
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : t('toasts.error.saveFailed')
      addToast(
        t('toasts.project.evaluationConfigsSaveFailed', {
          error: errorMessage,
        }),
        'error',
      )
      throw error
    }

    const warningMessages = describeEvaluationConfigWarnings(
      response?.warnings,
      evaluations,
      t,
    )
    const warningSignature = warningMessages.join('\n')
    if (
      warningSignature &&
      warningSignature !== lastEvaluationConfigWarningsRef.current
    ) {
      addToast(
        t('toasts.project.evaluationConfigsSavedWithWarnings', {
          warnings: warningMessages.join(' '),
        }),
        'warning',
        10000,
      )
    }
    lastEvaluationConfigWarningsRef.current = warningSignature
  }

  // Local state, flushed by the eval card's debounced auto-save
  // (saveEvaluationCard).
  const handleEvaluationConfigsChange = (evaluations: EvaluationConfig[]) => {
    markEvaluationDirty()
    evaluationConfigsRef.current = evaluations
    setEvaluationConfigs(evaluations)
  }

  // Handle evaluation started callback (modal handles the API call)
  const handleEvaluationStarted = () => {
    // Refresh evaluation data after evaluation is triggered
    // This callback is called when the modal successfully starts an evaluation
  }

  // Add router change event to force refresh when navigating to this page
  useEffect(() => {
    if (!projectId) return

    // Listen for navigation events using the browser's navigation API
    const handlePopState = () => {
      if (
        projectId &&
        window.location.pathname.includes(`/projects/${projectId}`)
      ) {
        setTimeout(() => fetchProject(projectId, { shared: true }), 100) // Small delay to ensure page is ready
      }
    }

    window.addEventListener('popstate', handlePopState)

    return () => {
      window.removeEventListener('popstate', handlePopState)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fetchProject is stable, only re-run when projectId changes
  }, [projectId])

  // Initialize values when project loads
  useEffect(() => {
    if (currentProject) {
      setTitleValue(currentProject.title)
      setDescriptionValue(currentProject.description || '')

      // Load evaluation defaults
      const projectEvalTemp =
        currentProject.evaluation_config?.default_temperature
      const projectEvalMaxTokens =
        currentProject.evaluation_config?.default_max_tokens
      setEvalDefaultTemperature(projectEvalTemp)
      setEvalDefaultMaxTokens(projectEvalMaxTokens)
      setEvalDefaultRunsPerTask(
        currentProject.evaluation_config?.runs_per_task ?? undefined,
      )
      setEvalDefaultsMode(
        (currentProject.evaluation_config?.defaults_mode as DefaultsMode) ||
          'recommended',
      )

      // Load generation defaults
      const genParams =
        currentProject.generation_config?.selected_configuration?.parameters ||
        {}
      setGenDefaultTemperature(genParams.temperature)
      setGenDefaultMaxTokens(genParams.max_tokens)
      setGenDefaultRunsPerTask(
        currentProject.generation_config?.runs_per_task ?? undefined,
      )
      setGenDefaultsMode(
        (currentProject.generation_config?.defaults_mode as DefaultsMode) ||
          'recommended',
      )

      setInstructions(currentProject.instructions || '')
      setInstructionsValue(currentProject.instructions || '')
      setLabelConfigValue(currentProject.label_config || '')
      // Load conditional instructions
      setConditionalInstructions(currentProject.conditional_instructions || [])

      setAdvancedSettings({
        show_instruction: currentProject.show_instruction !== false,
        instructions_always_visible:
          currentProject.instructions_always_visible || false,
        show_skip_button: currentProject.show_skip_button !== false,
        show_submit_button: currentProject.show_submit_button !== false,
        require_comment_on_skip:
          currentProject.require_comment_on_skip || false,
        require_confirm_before_submit:
          currentProject.require_confirm_before_submit || false,
        allow_external_paste: currentProject.allow_external_paste !== false,
        allow_solution_upload: currentProject.allow_solution_upload !== false,
        handwriting_ocr_enabled:
          currentProject.handwriting_ocr_enabled !== false,
        handwriting_ocr_model: currentProject.handwriting_ocr_model ?? null,
        skip_queue: currentProject.skip_queue || 'requeue_for_others',
        maximum_annotations: currentProject.maximum_annotations ?? 1,
        min_annotations_per_task: currentProject.min_annotations_per_task || 1,
        assignment_mode: currentProject.assignment_mode || 'open',
        randomize_task_order: currentProject.randomize_task_order || false,
        annotator_full_visibility_after_submit:
          (currentProject as any).annotator_full_visibility_after_submit ||
          false,
        annotator_step_detail_after_submit:
          (currentProject as any).annotator_step_detail_after_submit ?? null,
        review_enabled: currentProject.review_enabled || false,
        review_mode: currentProject.review_mode || 'in_place',
        allow_self_review: currentProject.allow_self_review || false,
        korrektur_enabled: currentProject.korrektur_enabled || false,
        korrektur_config: currentProject.korrektur_config || [],
        annotation_time_limit_enabled:
          (currentProject as any).annotation_time_limit_enabled || false,
        annotation_time_limit_seconds:
          (currentProject as any).annotation_time_limit_seconds ?? null,
        strict_timer_enabled:
          (currentProject as any).strict_timer_enabled || false,
        restorable_checkpoints_enabled:
          (currentProject as any).restorable_checkpoints_enabled || false,
      })
      setEvaluationSettings({
        immediate_evaluation_enabled:
          (currentProject as any).immediate_evaluation_enabled || false,
      })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- Using currentProject.id instead of currentProject to prevent unnecessary re-renders
  }, [currentProject?.id])

  // Model selection re-syncs from the refetched project once a model save
  // has settled (skipModelReset back to false). Kept apart from the
  // initialisation above, which used to re-run with it and overwrote
  // unsaved edits in the other cards with the stored values.
  useEffect(() => {
    if (currentProject) {
      // Only update selectedModelIds if they're different and we're not in the middle of a save
      // Read from generation_config first, fall back to llm_model_ids for backward compatibility
      const projectModelIds =
        currentProject.generation_config?.selected_configuration?.models ||
        currentProject.llm_model_ids ||
        []

      if (!skipModelReset && Array.isArray(projectModelIds)) {
        setSelectedModelIds((current) => {
          // Ensure both arrays are valid before comparing
          if (!Array.isArray(current)) return projectModelIds

          // Use JSON.stringify for deep comparison to avoid sorting issues
          const currentStr = JSON.stringify([...current].sort())
          const projectStr = JSON.stringify([...projectModelIds].sort())

          if (currentStr !== projectStr) {
            return [...projectModelIds] // Create new array to avoid reference issues
          }
          return current
        })
      }

      // Load model configs (thinking/reasoning budgets) - only if not in the middle of a save
      if (!skipModelReset) {
        const projectModelConfigs =
          currentProject.generation_config?.selected_configuration
            ?.model_configs || {}
        setModelConfigs(projectModelConfigs)
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- re-sync on project switch and after a model save settled
  }, [currentProject?.id, skipModelReset])

  // A soft-deleted project is open to superadmins only, to look inside: the
  // page is read-only until it is restored (DeletedProjectBanner).
  const isDeletedView = Boolean(currentProject?.deleted_at)

  // The backend's own edit decision (creator, superadmin or an elevated
  // membership in any of the project's orgs); public visitors get false.
  const canEditProject = () => {
    if (!user || !currentProject) return false
    if (isDeletedView) return false
    if (user.is_superadmin) return true
    if (isParticipant) return false
    return currentProject.can_edit === true
  }

  // Icon: creator, org admins and superadmins may change it later.
  const canEditIcon = () => {
    if (!user || !currentProject) return false
    if (isDeletedView) return false
    if (user.is_superadmin) return true
    if (isParticipant) return false
    if (String(currentProject.created_by) === String(user.id)) return true
    return currentProject.effective_role === 'ORG_ADMIN'
  }

  const handlePickIcon = async (icon: string) => {
    if (!projectId) return
    try {
      await updateProject(projectId, { icon })
    } catch {
      addToast(t('project.icon.saveFailed'), 'error')
    }
  }

  const canDeleteProject = () => {
    if (!user) return false
    if (isDeletedView) return false
    if (user.is_superadmin) return true
    if (isParticipant) return false
    // A private project is its creator's alone, even when a learning
    // platform link opens it to org staff (the API enforces the same rule).
    if (
      currentProject?.is_private &&
      String(currentProject.created_by) !== String(user.id)
    )
      return false
    return !isParticipant && currentProject?.effective_role === 'ORG_ADMIN'
  }

  const getReadOnlyMessage = (sectionTitle: string) =>
    currentProject?.organizations?.length
      ? t('project.permissions.orgAdminOnly', { section: sectionTitle })
      : t('project.permissions.creatorOnly', { section: sectionTitle })

  // A private project's creator resolves to ORG_ADMIN on the backend, so
  // the per-project role covers org and private projects alike.
  const canSeeQuickAction = (action: string) => {
    // Deleted: only the read-only way into the tasks and their answers.
    if (isDeletedView) return action === 'projectData'
    if (user?.is_superadmin) return true
    // Peer review: a participant who may grade fellow participants opens
    // the Korrektur page next to the staff graders.
    const isPeerReviewer = currentProject?.viewer_review_role === 'peer'
    if (isAttempted) return action === 'myTasks'
    if (isParticipant)
      return (
        action === 'startLabeling' ||
        action === 'myTasks' ||
        (action === 'feedback' && isPeerReviewer)
      )
    const role = currentProject?.effective_role
    switch (action) {
      case 'startLabeling':
      case 'myTasks':
        return true
      case 'feedback':
        return role === 'ORG_ADMIN' || role === 'CONTRIBUTOR' || isPeerReviewer
      case 'projectData':
      case 'review':
      case 'generation':
      case 'evaluations':
        return role === 'ORG_ADMIN' || role === 'CONTRIBUTOR'
      case 'editorActions':
        // Extended editor actions; their endpoints check edit rights too.
        return canEditProject()
      case 'deleteProject':
        return role === 'ORG_ADMIN'
      default:
        return true
    }
  }

  // Analysis runs of variant experiments open in the evaluations page's
  // Analyses view. The Evaluations quick action goes there directly when the
  // project has analysis runs or variant designs but no metric configs.
  // Only fetched for the viewers who may see the action, and only with the
  // variant_experiments flag (off, the action keeps its classic target).
  const mayOpenEvaluations = accessTierKnown && canSeeQuickAction('evaluations')
  const mayLookForAnalyses = variantExperiments && mayOpenEvaluations
  const [analysisPresence, setAnalysisPresence] = useState<{
    projectId: string
    any: boolean
    designs: number
  } | null>(null)
  useEffect(() => {
    if (!projectId || !mayLookForAnalyses) return
    let cancelled = false
    Promise.allSettled([
      analysisAPI.listRuns(projectId, 1),
      analysisAPI.listDesignKeys(projectId),
    ]).then(([runs, designs]) => {
      if (cancelled) return
      const hasRuns =
        runs.status === 'fulfilled' && (runs.value?.total ?? 0) > 0
      const hasDesigns =
        designs.status === 'fulfilled' && (designs.value?.length ?? 0) > 0
      setAnalysisPresence({
        projectId,
        any: hasRuns || hasDesigns,
        designs: hasDesigns ? designs.value.length : 0,
      })
    })
    return () => {
      cancelled = true
    }
  }, [projectId, mayLookForAnalyses])
  const opensAnalyses =
    analysisPresence?.projectId === projectId &&
    analysisPresence.any &&
    evaluationConfigs.length === 0

  // Variant designs, analysis plans and starting analysis runs (the
  // Analyses part of the Evaluation card): variant_experiments, edit rights
  // and the CONTRIBUTOR or ORG_ADMIN role, like starting a run in the API.
  const canManageAnalyses =
    variantExperiments &&
    canEditProject() &&
    (Boolean(user?.is_superadmin) ||
      currentProject?.effective_role === 'ORG_ADMIN' ||
      currentProject?.effective_role === 'CONTRIBUTOR')
  const analysisDesignCount =
    analysisPresence?.projectId === projectId ? analysisPresence.designs : 0
  const onAnalysesSummary = useCallback(
    (summary: { designs: number; plans: number }) => {
      setAnalysisPlanCount(summary.plans)
      setAnalysisPresence((prev) =>
        prev && prev.projectId === projectId
          ? {
              ...prev,
              designs: summary.designs,
              any: prev.any || summary.designs > 0,
            }
          : prev,
      )
    },
    [projectId],
  )

  const handleStartLabeling = () => {
    if (projectId) {
      router.push(`/projects/${projectId}/label`)
    }
  }

  const handleGenerateLLM = async () => {
    const id = projectId || currentProject?.id
    if (!id) return
    // Navigate to generations page with project preselected
    router.push(`/generations?projectId=${id}`)
  }

  const handleSaveLabelConfig = async (config: string) => {
    if (!projectId) return
    try {
      await updateProject(projectId, { label_config: config })
      // Refetch project to ensure all components get updated state
      await fetchProject(projectId)
    } catch (error) {
      console.error('Failed to save label configuration:', error)
      addToast(t('toasts.project.labelConfigFailed'), 'error')
      // Rethrow so the annotation card's auto-save keeps the card dirty.
      throw error
    }
  }

  const handleDeleteProject = async () => {
    if (!currentProject || !projectId) return

    setDeleting(true)
    try {
      await deleteProject(projectId)
      router.push('/projects')
      addToast(t('toasts.project.deleted'), 'success')
    } catch (err) {
      const errorMessage =
        err instanceof Error ? err.message : t('toasts.error.deleteFailed')
      addToast(
        t('toasts.project.deleteFailed', { error: errorMessage }),
        'error',
      )
      setDeleting(false)
    }
    setShowDeleteConfirm(false)
  }

  // Title editing handlers
  const handleStartEditTitle = () => {
    if (!currentProject) return
    setTitleValue(currentProject.title)
    setEditingTitle(true)
  }

  const handleCancelEditTitle = () => {
    setEditingTitle(false)
    setTitleValue(currentProject?.title || '')
  }

  const handleSaveTitle = async () => {
    if (!currentProject || !projectId || !titleValue.trim()) {
      addToast(t('toasts.project.titleEmpty'), 'warning')
      return
    }

    setIsUpdating(true)

    try {
      await updateProject(projectId, { title: titleValue })
      setEditingTitle(false)
      addToast(t('toasts.project.titleUpdated'), 'success')
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : t('toasts.error.updateFailed')
      addToast(
        t('toasts.project.titleUpdateFailed', { error: errorMessage }),
        'error',
      )
    } finally {
      setIsUpdating(false)
    }
  }

  // Description editing handlers
  const handleStartEditDescription = () => {
    if (!currentProject) return
    setDescriptionValue(currentProject.description || '')
    setEditingDescription(true)
  }

  const handleCancelEditDescription = () => {
    setEditingDescription(false)
    setDescriptionValue(currentProject?.description || '')
  }

  const handleSaveDescription = async () => {
    if (!currentProject || !projectId) return

    setIsUpdating(true)

    try {
      await updateProject(projectId, { description: descriptionValue })
      setEditingDescription(false)
      addToast(t('toasts.project.descriptionUpdated'), 'success')
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : t('toasts.error.updateFailed')
      addToast(
        t('toasts.project.descriptionUpdateFailed', { error: errorMessage }),
        'error',
      )
    } finally {
      setIsUpdating(false)
    }
  }

  const handleSaveInstructions = async (value: string) => {
    if (!currentProject || !projectId) return

    setIsUpdating(true)

    try {
      await updateProject(projectId, { instructions: value })
      setInstructions(value)
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : t('toasts.error.updateFailed')
      addToast(
        t('toasts.project.instructionsUpdateFailed', { error: errorMessage }),
        'error',
      )
      // Rethrow so saveAnnotationCard keeps the card in edit mode.
      throw error
    } finally {
      setIsUpdating(false)
    }
  }

  // Model selection handlers
  /** Resolve the per-model pre-fill values for (temperature, max_tokens)
   * based on the project's `defaults_mode`. Each branch is a deliberate
   * design choice:
   *
   * - **recommended**: pull each model's catalog `recommended_parameters`.
   *   Generation-mode block first, then the default block. Falls back to
   *   the model's documented constraint default if the catalog has no rec.
   * - **minimum**: use the lowest stable value the provider permits —
   *   `parameter_constraints.temperature.min` for temp, the constraint
   *   `max_tokens.default` (already a sane lower bound for evaluation) or
   *   1000 as a generic floor. Useful for deterministic comparison runs.
   * - **custom**: use the user-entered project-level defaults so a single
   *   config applies uniformly across all models added thereafter.
   *
   * The returned values still go through `getTemperatureConstraints`-style
   * clamping at the worker so a fixed-temperature model (GPT-5 family)
   * always lands at its required value regardless of mode. */
  const computeModeBasedPrefill = (
    modelId: string,
    mode: DefaultsMode,
    customTemp: number | undefined,
    customMaxTokens: number | undefined,
    rpMode: 'generation' | 'evaluation',
  ): {
    temperature?: number
    max_tokens?: number
    temperatureFixed?: boolean
  } => {
    const model = availableModels?.find((m) => m.id === modelId)
    const tempConstraints = getTemperatureConstraints(model)
    const constraintMaxTokens = getDefaultMaxTokens(model)
    const out: {
      temperature?: number
      max_tokens?: number
      temperatureFixed?: boolean
    } = {}

    // Always honor a fixed temperature constraint (e.g. GPT-5 → 1.0). The
    // mode controls the SOFT default, but a hard model requirement wins.
    if (tempConstraints.fixed) {
      out.temperature = tempConstraints.fixedValue ?? tempConstraints.default
      out.temperatureFixed = true
    } else if (mode === 'recommended') {
      const rec = getRecommendedParam(model, 'temperature', rpMode)
      out.temperature = typeof rec === 'number' ? rec : tempConstraints.default
    } else if (mode === 'minimum') {
      out.temperature = tempConstraints.min
    } else {
      // custom: use the project-level value the user entered
      out.temperature = customTemp ?? tempConstraints.default
    }

    if (mode === 'recommended') {
      const rec = getRecommendedParam(model, 'max_tokens', rpMode)
      out.max_tokens = typeof rec === 'number' ? rec : constraintMaxTokens
    } else if (mode === 'minimum') {
      // No provider documents a minimum max_tokens recommendation; use the
      // catalog's documented default (lowest sensible budget per model)
      // or a generic floor of 1000 tokens.
      out.max_tokens = constraintMaxTokens ?? 1000
    } else {
      out.max_tokens = customMaxTokens ?? constraintMaxTokens
    }
    return out
  }

  const handleModelToggle = (modelId: string) => {
    // Mark the card dirty so the change auto-saves.
    markGenerationDirty()

    const isCurrentlySelected = selectedModelIds.includes(modelId)

    if (isCurrentlySelected) {
      // Deselecting - just remove from list
      setSelectedModelIds((prev) => prev.filter((id) => id !== modelId))
    } else {
      // Selecting - add to list and pre-fill defaults if model has specific requirements
      setSelectedModelIds((prev) => [...prev, modelId])

      // Pre-fill model config based on the project's defaults mode
      // (recommended / minimum / custom). Only sets fields if not already
      // configured for this model. Read mode + customs from refs so that
      // a user pattern of "switch mode, then immediately tick a model"
      // sees the freshly-set values regardless of React render timing.
      if (!modelConfigs[modelId]) {
        const newConfig: Record<string, any> = {}
        const prefill = computeModeBasedPrefill(
          modelId,
          genDefaultsModeRef.current,
          genDefaultTempRef.current,
          genDefaultMaxTokensRef.current,
          'generation',
        )
        if (prefill.temperature !== undefined)
          newConfig.temperature = prefill.temperature
        if (prefill.temperatureFixed) newConfig.temperatureFixed = true
        if (prefill.max_tokens !== undefined)
          newConfig.max_tokens = prefill.max_tokens

        // Reasoning defaults from backend default_config (orthogonal to
        // the temperature/max_tokens mode logic).
        const reasoningConfig = getReasoningConfig(modelId)
        if (reasoningConfig) {
          newConfig[reasoningConfig.parameter] = reasoningConfig.default
        }

        if (Object.keys(newConfig).length > 0) {
          setModelConfigs((prev) => ({
            ...prev,
            [modelId]: { ...prev[modelId], ...newConfig },
          }))
        }
      }
    }
  }

  // Get reasoning config from backend default_config
  const getReasoningConfig = (modelId: string): ReasoningConfig | undefined => {
    const model = availableModels?.find((m) => m.id === modelId)
    const rc = model?.default_config?.reasoning_config
    if (!rc) return undefined
    return rc as ReasoningConfig
  }

  // Update model-specific config (thinking budget, max tokens, etc.)
  const updateModelConfig = (modelId: string, key: string, value: any) => {
    // A per-model setting is a change of the generation card like any
    // other: it must schedule the auto-save (it never did before).
    markGenerationDirty()
    setModelConfigs((prev) => ({
      ...prev,
      [modelId]: {
        ...prev[modelId],
        [key]: value,
      },
    }))
  }

  const handleSaveModels = async () => {
    if (!currentProject || !projectId) return

    logger.debug('[SAVE START] Selected models before save:', selectedModelIds)
    logger.debug(
      '[SAVE START] Current project generation_config:',
      currentProject.generation_config,
    )
    logger.debug('[SAVE START] skipModelReset flag:', skipModelReset)

    setIsUpdatingModels(true)
    setSkipModelReset(true) // Prevent useEffect from resetting selectedModelIds during save

    try {
      logger.debug('[API CALL] Saving model IDs:', selectedModelIds)
      logger.debug('[API CALL] Saving model configs:', modelConfigs)

      // Minimal patch — only the fields this handler owns. The backend
      // deep-merges (crud.py update_project), so unspecified keys inside
      // selected_configuration (parameters, prompt structures, …) are
      // preserved server-side. No spread of currentProject here: any
      // snapshot of it is stale by definition and re-sending it resurrects
      // old sibling values (issue #289: a re-sent stale `parameters`
      // clobbered handleSaveGenDefaults' write).
      await updateProject(projectId, {
        generation_config: {
          selected_configuration: {
            models: selectedModelIds,
            model_configs: modelConfigs,
          },
        },
      })
      logger.debug(
        '[API SUCCESS] Model IDs and configs saved successfully to generation_config',
      )

      // Refetch project to get the latest state with updated generation_config
      await fetchProject(projectId)
      logger.debug('[REFETCH SUCCESS] Project refetched after model save')

      // Check the current project state after update
      if (
        currentProject &&
        currentProject.generation_config?.selected_configuration?.models
      ) {
        logger.debug(
          '[PROJECT STATE] Current model IDs in generation_config:',
          currentProject.generation_config.selected_configuration.models,
        )
      } else {
        console.warn('[API RESPONSE] No models in generation_config!')
      }

      // Log state after API call
      setTimeout(() => {
        logger.debug(
          '[POST-SAVE] Selected models after API call:',
          selectedModelIds,
        )
        logger.debug('[POST-SAVE] skipModelReset flag:', skipModelReset)
      }, 100)
    } catch (error) {
      console.error('[ERROR] Error saving models:', error)
      const errorMessage =
        error instanceof Error ? error.message : t('toasts.error.saveFailed')
      addToast(
        t('toasts.project.modelsSaveFailed', { error: errorMessage }),
        'error',
      )
      // Rethrow so saveGenerationCard skips the defaults PATCH and keeps
      // the card in edit mode.
      throw error
    } finally {
      setIsUpdatingModels(false)
      // Reset the flag after a longer delay to ensure state updates complete
      setTimeout(() => {
        logger.debug('[CLEANUP] Resetting skipModelReset flag')
        setSkipModelReset(false)

        // Log final state
        setTimeout(() => {
          logger.debug(
            '[FINAL STATE] Selected models after cleanup:',
            selectedModelIds,
          )
        }, 100)
      }, 1000) // Increased from 500ms to 1000ms
    }
  }

  const handleSaveEvalDefaults = async () => {
    if (!currentProject || !projectId) return

    setIsUpdatingEvalDefaults(true)

    try {
      // Minimal patch — only the eval-defaults fields this handler owns.
      // PATCH /projects deep-merges server-side (crud.py), so sibling keys
      // in evaluation_config (evaluation_configs, selected_methods, …)
      // survive. Card saves are sequenced (saveEvaluationCard), so no two
      // writers of this JSONB column are ever in flight together.
      await updateProject(projectId, {
        evaluation_config: {
          default_temperature: evalDefaultTemperature,
          default_max_tokens: evalDefaultMaxTokens,
          // 3-mode picker for per-judge pre-fill; see DefaultsMode type.
          defaults_mode: evalDefaultsMode,
          // Multi-run default (migration 042); see comment on the state hook.
          // Unset is sent as an explicit null, which the deep merge turns
          // into a deleted key, so an undo back to unset is persisted too.
          runs_per_task: evalDefaultRunsPerTask ?? null,
        },
      })

      await fetchProject(projectId)
    } catch (error) {
      console.error('[ERROR] Error saving evaluation defaults:', error)
      const errorMessage =
        error instanceof Error ? error.message : t('toasts.error.saveFailed')
      addToast(
        t('toasts.project.evaluationDefaultsSaveFailed', {
          error: errorMessage,
        }),
        'error',
      )
      // Rethrow so saveEvaluationCard aborts the sequence and keeps the
      // card in edit mode.
      throw error
    } finally {
      setIsUpdatingEvalDefaults(false)
    }
  }

  const handleSaveGenDefaults = async () => {
    if (!currentProject || !projectId) return

    setIsUpdatingGenDefaults(true)

    try {
      // Minimal patch — only fields this handler owns. PATCH /projects
      // deep-merges server-side (crud.py), so sibling keys (e.g.
      // selected_configuration.models from handleSaveModels) and any other
      // parameters keys survive without re-sending a stale snapshot of
      // currentProject (issue #289).
      await updateProject(projectId, {
        generation_config: {
          // 3-mode picker for per-model pre-fill; see DefaultsMode type.
          defaults_mode: genDefaultsMode,
          // Multi-run default (migration 041): unset is sent as an explicit
          // null, which the deep merge turns into a deleted key, so the
          // server-side default of 1 stays implicit and an undo back to
          // unset is persisted too. Clamped to 1..25 by the input field
          // below and re-validated by the API router.
          runs_per_task: genDefaultRunsPerTask ?? null,
          selected_configuration: {
            parameters: {
              temperature: genDefaultTemperature,
              max_tokens: genDefaultMaxTokens,
            },
          },
        },
      })

      await fetchProject(projectId)
    } catch (error) {
      console.error('[ERROR] Error saving generation defaults:', error)
      const errorMessage =
        error instanceof Error ? error.message : t('toasts.error.saveFailed')
      addToast(
        t('toasts.project.generationDefaultsSaveFailed', {
          error: errorMessage,
        }),
        'error',
      )
      // Rethrow so saveGenerationCard keeps the card in edit mode.
      throw error
    } finally {
      setIsUpdatingGenDefaults(false)
    }
  }

  const handleSaveSettings = async (settings: AdvancedSettings) => {
    if (!currentProject || !projectId) return

    setIsUpdating(true)

    try {
      // korrektur_enabled / korrektur_config are server-derived from the
      // project's evaluation_config (after_eval_config_save hook). Stripping
      // them from the PATCH avoids clobbering server-side derivation with
      // stale local-buffer values.
      const {
        korrektur_enabled: _ke,
        korrektur_config: _kc,
        ...payload
      } = settings
      await updateProject(projectId, payload)
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : t('toasts.error.saveFailed')
      addToast(
        t('toasts.project.settingsSaveFailed', { error: errorMessage }),
        'error',
      )
      // Rethrow so saveAnnotationCard keeps the card in edit mode.
      throw error
    } finally {
      setIsUpdating(false)
    }
  }

  const handleSaveConditionalInstructions = async (
    variants: ConditionalInstruction[],
  ) => {
    if (!projectId) return
    try {
      await updateProject(projectId, {
        conditional_instructions: variants.length > 0 ? variants : null,
      })
    } catch (error) {
      addToast(t('project.conditionalInstructions.saveFailed'), 'error')
      throw error
    }
  }

  // Card-level auto-save (shared mechanism, components/shared/AutoSave).
  // Sub-sections are always editable for users with edit permission; every
  // user change marks its card's buffer, which saves the changed legs a
  // moment later (free text: on blur), shows ONE saved toast with undo,
  // and runs the legs of one card in sequence where they share a column
  // (issue #289). Risky changes are confirmed before they are applied
  // (components/shared/settingRisk, projectSettingRisks).
  const gateChange = useGatedSettingChange()

  const annotationBuffer = useAutoSaveBuffer({
    values: {
      instructions: instructionsValue,
      settings: advancedSettings,
      labelConfig: labelConfigValue,
      conditional: conditionalInstructions,
    },
    isLegValid: (leg, values) =>
      leg === 'labelConfig'
        ? labelConfigError(values.labelConfig, t) === null
        : leg === 'conditional'
          ? conditionalInstructionsValid(values.conditional)
          : true,
    save: async (legs, values) => {
      // Different columns: the legs may run side by side.
      await Promise.all([
        legs.includes('instructions')
          ? handleSaveInstructions(values.instructions)
          : null,
        legs.includes('settings') ? handleSaveSettings(values.settings) : null,
        legs.includes('labelConfig')
          ? handleSaveLabelConfig(values.labelConfig)
          : null,
        legs.includes('conditional')
          ? handleSaveConditionalInstructions(values.conditional)
          : null,
      ])
    },
    restore: (previous) => {
      if (previous.instructions !== undefined)
        setInstructionsValue(previous.instructions)
      if (previous.settings !== undefined)
        setAdvancedSettings(previous.settings)
      if (previous.labelConfig !== undefined)
        setLabelConfigValue(previous.labelConfig)
      if (previous.conditional !== undefined)
        setConditionalInstructions(previous.conditional)
    },
    riskChanges: (from, to) =>
      settingChanges(from.settings ?? {}, to.settings ?? {}),
    enabled: canEditProject(),
  })

  const generationBuffer = useAutoSaveBuffer({
    values: {
      models: { ids: selectedModelIds, configs: modelConfigs },
      defaults: {
        mode: genDefaultsMode,
        temperature: genDefaultTemperature,
        maxTokens: genDefaultMaxTokens,
        runs: genDefaultRunsPerTask,
      },
    },
    save: async (legs) => {
      // Sequential on purpose: both legs PATCH the generation_config JSONB
      // column, merged server-side by an unlocked read-merge-write; two
      // in-flight PATCHes let the later one resurrect stale keys (#289).
      if (legs.includes('models')) await handleSaveModels()
      if (legs.includes('defaults')) await handleSaveGenDefaults()
    },
    restore: (previous) => {
      if (previous.models) {
        setSelectedModelIds(previous.models.ids)
        setModelConfigs(previous.models.configs)
      }
      if (previous.defaults) {
        genDefaultsModeRef.current = previous.defaults.mode
        setGenDefaultsMode(previous.defaults.mode)
        setGenDefaultTemperature(previous.defaults.temperature)
        setGenDefaultMaxTokens(previous.defaults.maxTokens)
        setGenDefaultRunsPerTask(previous.defaults.runs)
      }
    },
    enabled: canEditProject(),
  })

  const evaluationBuffer = useAutoSaveBuffer({
    values: {
      settings: evaluationSettings,
      defaults: {
        mode: evalDefaultsMode,
        temperature: evalDefaultTemperature,
        maxTokens: evalDefaultMaxTokens,
        runs: evalDefaultRunsPerTask,
      },
      configs: evaluationConfigs,
    },
    save: async (legs, values) => {
      if (!projectId) return
      const base = evaluationConfigsBaselineRef.current
      let saveDone: () => void = () => {}
      evaluationConfigsSaveSeqRef.current += 1
      evaluationConfigsSaveInFlightRef.current = new Promise<void>(
        (resolve) => {
          saveDone = resolve
        },
      )
      try {
        // Sequential on purpose: the defaults PATCH and the configs PUT both
        // write the evaluation_config JSONB column via unlocked server-side
        // read-merge-writes (#289). The settings PATCH goes first so the
        // store's currentProject updates don't interleave either.
        if (legs.includes('settings')) {
          try {
            await updateProject(projectId, values.settings)
          } catch (error) {
            const errorMessage =
              error instanceof Error
                ? error.message
                : t('toasts.error.saveFailed')
            addToast(
              t('toasts.project.settingsSaveFailed', { error: errorMessage }),
              'error',
            )
            throw error
          }
        }
        if (legs.includes('defaults')) await handleSaveEvalDefaults()
        if (legs.includes('configs'))
          await saveEvaluationConfigsToProject(values.configs, base)
      } finally {
        evaluationConfigsSaveSeqRef.current += 1
        evaluationConfigsSaveInFlightRef.current = null
        saveDone()
      }
    },
    restore: (previous) => {
      if (previous.settings) setEvaluationSettings(previous.settings)
      if (previous.defaults) {
        setEvalDefaultsMode(previous.defaults.mode)
        setEvalDefaultTemperature(previous.defaults.temperature)
        setEvalDefaultMaxTokens(previous.defaults.maxTokens)
        setEvalDefaultRunsPerTask(previous.defaults.runs)
      }
      if (previous.configs) {
        evaluationConfigsRef.current = previous.configs
        setEvaluationConfigs(previous.configs)
      }
    },
    riskChanges: (from, to) =>
      settingChanges(from.settings ?? {}, to.settings ?? {}),
    enabled: canEditProject(),
  })

  const cardDirty = {
    annotation: annotationBuffer.dirty,
    generation: generationBuffer.dirty,
    evaluation: evaluationBuffer.dirty,
  }
  const cardSaving = {
    annotation: annotationBuffer.saving,
    generation: generationBuffer.saving,
    evaluation: evaluationBuffer.saving,
  }
  const markAnnotationDirty = () => annotationBuffer.markChanged()
  const markAnnotationTextDirty = () =>
    annotationBuffer.markChanged({ schedule: false })
  const markGenerationDirty = () => generationBuffer.markChanged()
  const markEvaluationDirty = () => evaluationBuffer.markChanged()

  // The settings buffer: risky changes (registry) ask first; a cancelled
  // change is never applied, so the control keeps its old value. Free text
  // (`deferSave`) saves on blur.
  const advancedSettingsRef = useRef(advancedSettings)
  advancedSettingsRef.current = advancedSettings
  const handleAdvancedSettingsChange: AdvancedSettingsSetter = (
    value,
    options,
  ) => {
    const prev = advancedSettingsRef.current
    const next = typeof value === 'function' ? value(prev) : value
    gateChange(
      settingChanges(prev, next),
      () => {
        annotationBuffer.markChanged({ schedule: !options?.deferSave })
        advancedSettingsRef.current = next
        setAdvancedSettings(next)
      },
      options?.onCancel,
    )
  }

  // Settings card: project type and which cards the page shows. Kind is
  // the single source of truth for the student surfaces (Entdecken, deck
  // workspace); the store echo refreshes updated_at, which re-runs the
  // sharing card's discoverability check. Saved shortly after a click.
  const storedProjectSettings = {
    kind: (currentProject?.kind ?? null) as string | null,
    features: {
      enable_annotation: currentProject?.enable_annotation !== false,
      enable_generation: currentProject?.enable_generation !== false,
      enable_evaluation: currentProject?.enable_evaluation !== false,
      enable_prompts: currentProject?.enable_prompts !== false,
    },
  }
  type ProjectSettingsValue = typeof storedProjectSettings
  const [projectSettingsDraft, setProjectSettingsDraft] =
    useState<ProjectSettingsValue | null>(null)
  const projectSettingsValue = projectSettingsDraft ?? storedProjectSettings
  const projectSettingsBuffer = useAutoSaveBuffer({
    values: projectSettingsValue,
    baseline: storedProjectSettings,
    delayMs: 300,
    save: async (legs, values) => {
      if (!projectId) return
      try {
        // Only the switches that changed: the others keep their stored
        // value (which may be unset, read as on).
        const features = Object.fromEntries(
          Object.entries(values.features).filter(
            ([key, on]) =>
              on !==
              storedProjectSettings.features[
                key as keyof ProjectSettingsValue['features']
              ],
          ),
        )
        await updateProject(projectId, {
          ...(legs.includes('kind') ? { kind: values.kind } : {}),
          ...(legs.includes('features') ? features : {}),
        } as any)
      } catch (error) {
        addToast(
          legs.includes('kind')
            ? t('project.details.kindSaveFailed')
            : t('toasts.project.settingsSaveFailed', {
                error: error instanceof Error ? error.message : '',
              }),
          'error',
        )
        throw error
      }
    },
    restore: (previous) =>
      setProjectSettingsDraft((draft) => ({
        ...(draft ?? storedProjectSettings),
        ...previous,
      })),
    riskChanges: (from, to) =>
      settingChanges(
        { kind: from.kind, ...from.features },
        { kind: to.kind, ...to.features },
      ),
    enabled: canEditProject(),
  })
  const handleKindChange = (kind: string | null) => {
    gateChange(
      [{ key: 'kind', from: projectSettingsValue.kind, to: kind }],
      () => {
        projectSettingsBuffer.markChanged()
        setProjectSettingsDraft({ ...projectSettingsValue, kind })
      },
    )
  }
  const handleFeatureVisibilityChange = (
    key: keyof ProjectSettingsValue['features'],
    enabled: boolean,
  ) => {
    gateChange(
      [{ key, from: projectSettingsValue.features[key], to: enabled }],
      () => {
        projectSettingsBuffer.markChanged()
        setProjectSettingsDraft({
          ...projectSettingsValue,
          features: { ...projectSettingsValue.features, [key]: enabled },
        })
      },
    )
  }

  const evaluationSettingsRef = useRef(evaluationSettings)
  evaluationSettingsRef.current = evaluationSettings
  const handleEvaluationSettingsChange = (next: typeof evaluationSettings) => {
    gateChange(settingChanges(evaluationSettingsRef.current, next), () => {
      markEvaluationDirty()
      setEvaluationSettings(next)
    })
  }

  // One step from loading to the full page: the project of this URL, the
  // flags, the per-user task check and (for participants) the participation
  // are all known before anything shows.
  if (
    !projectId ||
    (!currentProject && !notFound) ||
    (currentProject &&
      (!flagsReady ||
        nextCheckedFor !== projectId ||
        (isParticipant && participationFor !== projectId)))
  ) {
    return (
      // The same spot as the app loading screen it takes over from; the
      // min-h keeps the footer below the fold meanwhile.
      <div className="min-h-screen">
        <AppLoadingScreen label={t('project.loading')} covering={false} />
      </div>
    )
  }

  if (!currentProject) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <Card className="mx-auto max-w-2xl">
          <div className="p-12 text-center">
            <h2 className="mb-2 text-2xl font-bold text-zinc-900 dark:text-white">
              {t('project.notFound')}
            </h2>
            <p className="mb-6 text-zinc-600 dark:text-zinc-400">
              {t('project.notFoundDescription')}
            </p>
            <Button onClick={() => router.push('/projects')}>
              {t('project.backToProjects')}
            </Button>
          </div>
        </Card>
      </div>
    )
  }

  // Use server-calculated progress_percentage when present — it's the
  // source of truth and mixes the enabled stages (annotation /
  // generation / evaluation). The fallback below mirrors the backend's
  // _mix_progress for the rare case where the server hasn't populated
  // the field yet (e.g. a stale cached response).
  const completionRate = (() => {
    if (currentProject.progress_percentage !== undefined) {
      return Math.round(currentProject.progress_percentage)
    }
    const taskCount = currentProject.task_count ?? 0
    const genModels = currentProject.generation_models_count ?? 0
    const parts: Array<[number, number]> = []
    if (currentProject.enable_annotation !== false) {
      parts.push([currentProject.completed_tasks_count ?? 0, taskCount])
    }
    if (currentProject.enable_generation !== false) {
      // We don't have completed_generations on the client; treat the
      // generation stage as 0/0 in the fallback so it gets ignored.
      parts.push([0, taskCount * genModels])
    }
    if (currentProject.enable_evaluation !== false) {
      const completed = currentProject.evaluations_completed_count ?? 0
      const expected = currentProject.evaluation_count ?? 0
      parts.push([Math.min(completed, expected), expected])
    }
    const relevant = parts.filter(([, expected]) => expected > 0)
    if (relevant.length === 0) return 0
    const completedSum = relevant.reduce((acc, [c]) => acc + c, 0)
    const expectedSum = relevant.reduce((acc, [, e]) => acc + e, 0)
    return Math.min(100, Math.round((completedSum / expectedSum) * 100))
  })()

  return (
    <div className="mx-auto max-w-7xl px-4 pt-8 pb-10 sm:px-6">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-start justify-between">
          <div className="flex-1">
            {/* Breadcrumb Navigation */}
            <div className="mb-4">
              <ProjectBreadcrumb projectId={projectId} />
            </div>

            {/* Title */}
            <div>
              {editingTitle ? (
                <div className="flex items-center space-x-3">
                  <Input
                    value={titleValue}
                    onChange={(e) => setTitleValue(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') handleSaveTitle()
                      if (e.key === 'Escape') handleCancelEditTitle()
                    }}
                    className="flex-1 text-3xl font-bold"
                    autoFocus
                  />
                  <Button
                    onClick={handleSaveTitle}
                    disabled={isUpdating}
                    className="text-sm"
                  >
                    {isUpdating
                      ? t('project.editing.saving')
                      : t('project.editing.save')}
                  </Button>
                  <Button
                    onClick={handleCancelEditTitle}
                    variant="outline"
                    disabled={isUpdating}
                    className="text-sm"
                  >
                    {t('project.editing.cancel')}
                  </Button>
                </div>
              ) : (
                <div className="group flex min-w-0 flex-wrap items-center gap-3">
                  <h1 className="min-w-0 text-3xl font-bold tracking-tight break-words text-zinc-900 dark:text-white">
                    {canEditIcon() ? (
                      <button
                        type="button"
                        className="mr-2 rounded-md px-1 transition-colors hover:bg-zinc-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 dark:hover:bg-zinc-800"
                        title={t(
                          'projects.creation.wizard.step1.icon.clickToEdit',
                        )}
                        onClick={() => setIconPickerOpen(true)}
                        data-testid="project-header-icon"
                      >
                        {projectIcon(currentProject)}
                      </button>
                    ) : (
                      <span
                        className="mr-2"
                        aria-hidden
                        data-testid="project-header-icon"
                      >
                        {projectIcon(currentProject)}
                      </span>
                    )}
                    {currentProject.title}
                  </h1>
                  {iconPickerOpen && (
                    <IconPickerModal
                      isOpen={iconPickerOpen}
                      onClose={() => setIconPickerOpen(false)}
                      icon={currentProject.icon ?? ''}
                      projectKind={(currentProject.kind as any) ?? 'generic'}
                      onPick={handlePickIcon}
                    />
                  )}
                  {isParticipant && (
                    <span
                      className="inline-flex items-center gap-1 rounded-full bg-zinc-100 px-2.5 py-0.5 text-xs font-medium text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300"
                      data-testid="project-participant-badge"
                    >
                      <UserGroupIcon className="h-3.5 w-3.5" />
                      {isAttempted
                        ? t('projects.list.attemptedBadge')
                        : t('projects.list.participantBadge')}
                    </span>
                  )}
                  {/* The edit buttons show on hover; on a touch screen (no
                      hover) and for keyboard focus they always show, so
                      they are never invisible yet in the way. */}
                  {canEditProject() && (
                    <Button
                      onClick={handleStartEditTitle}
                      variant="outline"
                      className="opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100 [@media(hover:none)]:opacity-100"
                    >
                      <PencilIcon className="h-4 w-4" />
                    </Button>
                  )}
                  {canEditProject() &&
                    !currentProject.description &&
                    !editingDescription && (
                      <Button
                        onClick={handleStartEditDescription}
                        variant="outline"
                        className="text-sm opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100 [@media(hover:none)]:opacity-100"
                        data-testid="project-add-description"
                      >
                        {t('project.editing.addDescription')}
                      </Button>
                    )}
                </div>
              )}
            </div>

            {/* Description: no block at all without one, so an empty
                subtitle row does not push the cards down. Editors add
                one from the title row. */}
            {(editingDescription || currentProject.description) && (
              <div className="mt-4">
                {editingDescription ? (
                  <div className="space-y-3">
                    <Textarea
                      value={descriptionValue}
                      onChange={(e) => setDescriptionValue(e.target.value)}
                      placeholder={t('project.editing.titlePlaceholder')}
                      rows={3}
                      className="resize-none"
                    />
                    <div className="flex items-center space-x-2">
                      <Button
                        onClick={handleSaveDescription}
                        disabled={isUpdating}
                        className="text-sm"
                      >
                        {isUpdating
                          ? t('project.editing.saving')
                          : t('project.editing.save')}
                      </Button>
                      <Button
                        onClick={handleCancelEditDescription}
                        variant="outline"
                        disabled={isUpdating}
                        className="text-sm"
                      >
                        {t('project.editing.cancel')}
                      </Button>
                    </div>
                  </div>
                ) : (
                  <div className="group flex items-start space-x-3">
                    <p
                      className="text-zinc-600 dark:text-zinc-400"
                      data-testid="project-description"
                    >
                      {currentProject.description}
                    </p>
                    {canEditProject() && (
                      <Button
                        onClick={handleStartEditDescription}
                        variant="outline"
                        className="shrink-0 opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100 [@media(hover:none)]:opacity-100"
                      >
                        <PencilIcon className="h-4 w-4" />
                      </Button>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Delete Confirmation Modal */}
      {showDeleteConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4 dark:bg-black/50">
          <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl dark:bg-zinc-800">
            <h3 className="mb-4 text-lg font-semibold text-zinc-900 dark:text-white">
              {t('project.deleteConfirmTitle')}: {currentProject.title}
            </h3>
            <div className="mb-6">
              <p className="mb-3 text-zinc-600 dark:text-zinc-400">
                {t('project.deleteConfirmMessage')}
              </p>
              <ul className="list-inside list-disc space-y-1 text-sm text-zinc-500 dark:text-zinc-400">
                <li>{t('project.deleteConfirmItems.config')}</li>
                <li>
                  {t('project.deleteConfirmItems.tasks', {
                    count: currentProject.task_count,
                  })}
                </li>
                <li>
                  {t('project.deleteConfirmItems.annotations', {
                    count: currentProject.annotation_count,
                  })}
                </li>
                <li>{t('project.deleteConfirmItems.irreversible')}</li>
              </ul>
            </div>
            <div className="flex justify-end space-x-3">
              <Button
                variant="outline"
                onClick={() => setShowDeleteConfirm(false)}
                disabled={deleting}
              >
                {t('project.editing.cancel')}
              </Button>
              <Button
                onClick={handleDeleteProject}
                variant="dangerFilled"
                disabled={deleting}
              >
                {deleting ? t('project.deleting') : t('project.deleteProject')}
              </Button>
            </div>
          </div>
        </div>
      )}

      <div
        className={`grid grid-cols-1 gap-8 transition-all duration-300 ${
          isSidebarHidden ? 'lg:grid-cols-4' : 'lg:grid-cols-3'
        }`}
      >
        {/* Main Content */}
        <div
          className={`transition-all duration-300 ${
            isSidebarHidden ? 'lg:col-span-3' : 'lg:col-span-2'
          }`}
        >
          {/* Project Details */}
          <ProjectMetadataCard project={currentProject} t={t} />

          {/* Flashcard deck workspace (extended): study / cards / export for
              deck-shaped projects; renders nothing otherwise. */}
          {ProjectDeckWorkspace && (
            <div data-testid="project-deck-workspace" className="empty:hidden">
              <ProjectDeckWorkspace
                project={currentProject}
                canEdit={canEditProject()}
                onRefresh={() => fetchProject(projectId)}
              />
            </div>
          )}

          {/* Configuration cards: editors/annotators only. Participants (narrow
              tier) get the metadata, deck workspace and quick actions.
              Every sub-collapsible is a SubSection; settings inside it are
              titled SettingsGroups (components/projects/SettingsGroup). */}
          {!isParticipant && (
            <>
              {currentProject.enable_annotation && (
                <ConfigCard
                  title={t('project.annotationConfiguration.title')}
                  defaultExpanded={false}
                  dirty={cardDirty.annotation}
                  saving={cardSaving.annotation}
                >
                  <SubSection
                    title={t('project.annotationInstructions.title')}
                    badge={
                      instructionsValue || conditionalInstructions.length > 0
                        ? t('project.annotationInstructions.configured')
                        : t('project.annotationInstructions.notConfigured')
                    }
                    data-testid="annotation-instructions-section"
                  >
                    {canEditProject() ? (
                      <SettingsGroupStack>
                        <SettingsGroup
                          title={t('project.settings.groups.instructionText')}
                        >
                          <Textarea
                            aria-label={t(
                              'project.annotationInstructions.title',
                            )}
                            value={instructionsValue}
                            onChange={(e) => {
                              markAnnotationTextDirty()
                              setInstructionsValue(e.target.value)
                            }}
                            onBlur={() => void annotationBuffer.commit()}
                            placeholder={t(
                              'project.annotationInstructions.placeholder',
                            )}
                            rows={6}
                            className="w-full resize-none"
                          />
                        </SettingsGroup>
                        <InstructionDisplaySettings
                          t={t}
                          advancedSettings={advancedSettings}
                          setAdvancedSettings={handleAdvancedSettingsChange}
                          editing={canEditProject()}
                        />
                        <ConditionalInstructionsEditor
                          t={t}
                          variants={conditionalInstructions}
                          onChange={(variants, text) => {
                            annotationBuffer.markChanged({ schedule: !text })
                            setConditionalInstructions(variants)
                          }}
                          onCommit={() => void annotationBuffer.commit()}
                        />
                      </SettingsGroupStack>
                    ) : (
                      <div className="py-6 text-center">
                        <p className="text-sm text-zinc-500 dark:text-zinc-400">
                          {getReadOnlyMessage(
                            t('project.annotationInstructions.title'),
                          )}
                        </p>
                      </div>
                    )}
                  </SubSection>

                  <SubSection
                    title={t('project.labelConfiguration.title')}
                    badge={
                      currentProject.label_config
                        ? t('project.labelConfiguration.configured')
                        : t('project.labelConfiguration.notConfigured')
                    }
                    data-testid="label-configuration-section"
                  >
                    {canEditProject() ? (
                      // Saved by the annotation card's auto-save on blur,
                      // only while it parses (labelConfigError).
                      <LabelConfigEditor
                        initialConfig={currentProject.label_config || ''}
                        value={labelConfigValue}
                        onValueChange={(config) => {
                          markAnnotationTextDirty()
                          setLabelConfigValue(config)
                        }}
                        onBlur={() => void annotationBuffer.commit()}
                        onSave={handleSaveLabelConfig}
                        projectId={currentProject.id}
                        hideInternalControls
                      />
                    ) : (
                      <div className="py-6 text-center">
                        <p className="text-sm text-zinc-500 dark:text-zinc-400">
                          {getReadOnlyMessage(
                            t('project.labelConfiguration.title'),
                          )}
                        </p>
                      </div>
                    )}
                  </SubSection>

                  <SubSection
                    title={t('project.settings.annotationSettingsTitle')}
                    badge={`${t(`project.settings.annotationBehavior.modesShort.${advancedSettings.assignment_mode}`)}, ${t('project.settings.minAnnotations', { count: advancedSettings.min_annotations_per_task })}`}
                    data-testid="annotation-settings-section"
                  >
                    <AdvancedSettingsCard
                      t={t}
                      canEditProject={canEditProject}
                      getReadOnlyMessage={getReadOnlyMessage}
                      advancedSettings={advancedSettings}
                      setAdvancedSettings={handleAdvancedSettingsChange}
                      editing={canEditProject()}
                      ProjectSettingsExtended={ProjectSettingsExtended}
                      ProjectSettingsInterfaceExtra={
                        ProjectSettingsInterfaceExtra
                      }
                      ProjectSettingsAnnotationWork={
                        ProjectSettingsAnnotationWork
                      }
                    />
                  </SubSection>
                </ConfigCard>
              )}

              {currentProject.enable_generation && (
                <ConfigCard
                  title={t('project.generationConfiguration.title')}
                  defaultExpanded={false}
                  dirty={cardDirty.generation}
                  saving={cardSaving.generation}
                >
                  {/* What runs first, then how it runs. */}
                  <ModelSelectionSection
                    t={t}
                    canEditProject={canEditProject}
                    getReadOnlyMessage={getReadOnlyMessage}
                    expandedModels={expandedModels}
                    setExpandedModels={setExpandedModels}
                    modelsLoading={modelsLoading}
                    modelsError={modelsError}
                    sortedModels={sortedModels}
                    availableModels={availableModels}
                    selectedModelIds={selectedModelIds}
                    modelConfigs={modelConfigs}
                    handleModelToggle={handleModelToggle}
                    updateModelConfig={updateModelConfig}
                    getReasoningConfig={getReasoningConfig}
                    onNavigateToProfile={() => router.push('/profile')}
                  />

                  {/* Parameters and runs. runs_per_task is its own group:
                      a scheduling/budget knob the strategy picker does not
                      touch. */}
                  {canEditProject() && (
                    <GenerationDefaultsCard
                      t={t}
                      genDefaultsMode={genDefaultsMode}
                      setGenDefaultsMode={setGenDefaultsMode}
                      genDefaultsModeRef={genDefaultsModeRef}
                      genDefaultTemperature={genDefaultTemperature}
                      setGenDefaultTemperature={setGenDefaultTemperature}
                      genDefaultMaxTokens={genDefaultMaxTokens}
                      setGenDefaultMaxTokens={setGenDefaultMaxTokens}
                      selectedModelIds={selectedModelIds}
                      genRecConsensus={genRecConsensus}
                      // Always false so every change re-marks the card dirty and
                      // extends the auto-save debounce (the marker is idempotent).
                      cardEditingGeneration={false}
                      beginEditGeneration={markGenerationDirty}
                      runsPerTask={genDefaultRunsPerTask}
                      setRunsPerTask={setGenDefaultRunsPerTask}
                      maxRunsPerTask={maxRunsPerTask}
                    />
                  )}

                  {/* Always-visible "Generierung starten" CTA at the card
                      footer, parallel to the evaluation card's. The modal
                      handles the no-models case itself. */}
                  {canEditProject() && (
                    <div className="flex justify-end gap-2 border-t pt-4 dark:border-zinc-700">
                      <Button
                        onClick={() => setShowGenerationStartModal(true)}
                        className="flex items-center gap-2 text-sm"
                      >
                        <PlayIcon className="h-4 w-4" />
                        {t('project.generation.runCta')}
                      </Button>
                    </div>
                  )}
                </ConfigCard>
              )}

              {/* Prompts — every prompt the project uses or falls back to in
              one place: the generation prompt structures and the evaluation
              prompts of the configured judge methods plus the default judge
              templates. Read-only for viewers without edit rights; its own
              feature-visibility switch (enable_prompts). */}
              {currentProject.enable_prompts !== false && (
                <ConfigCard
                  title={t('project.prompts.title')}
                  description={t('project.prompts.help')}
                  defaultExpanded={false}
                >
                  <PromptStructuresManager
                    projectId={projectId || ''}
                    readOnly={!canEditProject()}
                    onStructuresChange={() => {
                      // Refetch project to update UI
                      if (projectId) {
                        fetchProject(projectId)
                      }
                    }}
                  />

                  <SubSection title={t('project.prompts.evaluation.title')}>
                    <EvaluationPromptsOverview
                      projectId={projectId || ''}
                      evaluationConfigs={evaluationConfigs}
                      onConfigsChange={
                        canEditProject()
                          ? handleEvaluationConfigsChange
                          : undefined
                      }
                    />
                  </SubSection>
                </ConfigCard>
              )}

              {currentProject.enable_evaluation && (
                <ConfigCard
                  title={t('project.evaluation.title')}
                  defaultExpanded={false}
                  dirty={cardDirty.evaluation}
                  saving={cardSaving.evaluation}
                >
                  {canEditProject() ? (
                    <>
                      {/* What is evaluated first, mirroring Modellauswahl. */}
                      <SubSection
                        title={t('project.evaluationMethods.title')}
                        badge={
                          evaluationConfigs.length > 0
                            ? evaluationConfigs.length === 1
                              ? t(
                                  'project.evaluation.evaluationConfigSingular',
                                  { count: evaluationConfigs.length },
                                )
                              : t('project.evaluation.evaluationConfigPlural', {
                                  count: evaluationConfigs.length,
                                })
                            : t('project.evaluation.notConfigured')
                        }
                      >
                        <EvaluationBuilder
                          projectId={projectId || ''}
                          availableFields={availableEvaluationFields}
                          evaluations={evaluationConfigs}
                          onEvaluationsChange={handleEvaluationConfigsChange}
                          onSave={handleEvaluationStarted}
                          defaultsMode={evalDefaultsMode}
                          customTemp={evalDefaultTemperature}
                          customMaxTokens={evalDefaultMaxTokens}
                        />
                      </SubSection>

                      {/* How evaluations run: parameters, runs, timing, and
                      the extension's Korrektur policy switches. */}
                      <EvaluationDefaultsCard
                        t={t}
                        evalDefaultsMode={evalDefaultsMode}
                        setEvalDefaultsMode={setEvalDefaultsMode}
                        evalDefaultTemperature={evalDefaultTemperature}
                        setEvalDefaultTemperature={setEvalDefaultTemperature}
                        evalDefaultMaxTokens={evalDefaultMaxTokens}
                        setEvalDefaultMaxTokens={setEvalDefaultMaxTokens}
                        selectedModelIds={selectedModelIds}
                        evalRecConsensus={evalRecConsensus}
                        // Always false so every change re-marks the card dirty
                        // and extends the auto-save debounce (idempotent).
                        cardEditingEvaluation={false}
                        beginEditEvaluation={markEvaluationDirty}
                        runsPerTask={evalDefaultRunsPerTask}
                        setRunsPerTask={setEvalDefaultRunsPerTask}
                        immediateEvaluation={
                          evaluationSettings.immediate_evaluation_enabled
                        }
                        onImmediateEvaluationChange={(enabled) =>
                          handleEvaluationSettingsChange({
                            ...evaluationSettings,
                            immediate_evaluation_enabled: enabled,
                          })
                        }
                        korrekturSettings={
                          ProjectEvaluationSettingsSection ? (
                            <ProjectEvaluationSettingsSection
                              projectId={projectId || ''}
                              evaluationConfigs={evaluationConfigs}
                              onEvaluationConfigsChange={
                                handleEvaluationConfigsChange
                              }
                            />
                          ) : null
                        }
                      />

                      {/* Grading section (extended slot, e.g. Korrektur):
                      how people grade, after the methods and their
                      settings and before the grade scale that maps the
                      results to grades. */}
                      {ProjectEvaluationGradingSection && currentProject && (
                        // The slot renders nothing for projects without
                        // such grading: no empty divided row in the card.
                        <div
                          data-testid="project-evaluation-grading-section"
                          className="empty:hidden"
                        >
                          <ProjectEvaluationGradingSection
                            project={currentProject}
                            projectId={projectId || ''}
                            onRefresh={() => {
                              void refreshEvaluationConfigsFromServer()
                              return fetchProject(projectId)
                            }}
                          />
                        </div>
                      )}

                      {/* Exam-level Notenschlüssel (extended slot): maps the
                      grading results to grades, so it follows the methods
                      and their settings. Saves itself. */}
                      {ProjectGradeScale && (
                        // The slot renders nothing when the exam needs no
                        // grade scale: no empty divided row in the card.
                        <div className="empty:hidden">
                          <ProjectGradeScale
                            projectId={projectId || ''}
                            evaluationConfig={
                              currentProject?.evaluation_config ?? null
                            }
                          />
                        </div>
                      )}

                      {/* Analyses of variant experiments: designs, saved
                      plans and the start dialog the evaluations page
                      shares. Saves itself. */}
                      {canManageAnalyses && projectId && (
                        <SubSection
                          title={t('analysis.section.title')}
                          badge={
                            analysisDesignCount > 0 || analysisPlanCount > 0
                              ? [
                                  analysisDesignCount === 1
                                    ? t('analysis.section.designsOne')
                                    : t('analysis.section.designsMany', {
                                        count: analysisDesignCount,
                                      }),
                                  analysisPlanCount === 1
                                    ? t('analysis.section.plansOne')
                                    : t('analysis.section.plansMany', {
                                        count: analysisPlanCount,
                                      }),
                                ].join(', ')
                              : t('project.evaluation.notConfigured')
                          }
                        >
                          <ProjectAnalysesSection
                            projectId={projectId}
                            onSummaryChange={onAnalysesSummary}
                          />
                        </SubSection>
                      )}
                    </>
                  ) : (
                    <div className="py-6 text-center">
                      <p className="text-sm text-zinc-500 dark:text-zinc-400">
                        {getReadOnlyMessage(t('project.evaluation.title'))}
                      </p>
                    </div>
                  )}

                  {/* Always-visible "Evaluierung starten" CTA at the card
                      footer: the one entry point to the run modal. */}
                  {canEditProject() &&
                    evaluationConfigs.filter((e: any) => e.enabled).length >
                      0 && (
                      <div className="flex justify-end gap-2 border-t pt-4 dark:border-zinc-700">
                        <Button
                          onClick={() => setShowEvaluationStartModal(true)}
                          className="flex items-center gap-2 text-sm"
                        >
                          <PlayIcon className="h-4 w-4" />
                          {t('project.evaluation.runCta')}
                        </Button>
                      </div>
                    )}
                </ConfigCard>
              )}

              {/* Questionnaires: before the task, after the submission and
                  at the Korrektur, one block per moment. Each block saves
                  itself (validated XML, versioned). */}
              {currentProject.enable_annotation && (
                <ConfigCard
                  title={t('questionnaires.card.title')}
                  description={t('questionnaires.card.description')}
                  badge={
                    activeQuestionnaires != null && activeQuestionnaires > 0
                      ? t('questionnaires.card.activeCount', {
                          count: activeQuestionnaires,
                        })
                      : undefined
                  }
                  defaultExpanded={false}
                >
                  <QuestionnairesSettings
                    projectId={projectId}
                    canEdit={canEditProject()}
                    onActiveCount={setActiveQuestionnaires}
                  />
                </ConfigCard>
              )}

              <ConfigCard
                title={t('project.settings.title')}
                defaultExpanded={false}
                dirty={projectSettingsBuffer.dirty}
                saving={projectSettingsBuffer.saving}
              >
                {/* Project type (exam / deck / generic) — the flag the student
              surfaces key discovery off. Student-created projects keep it
              locked (server-enforced too). */}
                {canEditProject() && currentProject.origin !== 'student' && (
                  <ProjectKindSection
                    project={{
                      ...currentProject,
                      kind: projectSettingsValue.kind,
                    }}
                    onKindChange={handleKindChange}
                  />
                )}

                {/* Who reaches the project, and when: visibility, access
              window, sharing (extended). */}
                {currentProject &&
                  !isDeletedView &&
                  (user?.is_superadmin ||
                    String(user?.id) === String(currentProject.created_by) ||
                    canEditProject()) && (
                    <div data-testid="project-visibility-danger-zone">
                      <SubSection
                        title={t('project.settings.visibilityDangerZone.title')}
                        badge={
                          currentProject.is_public
                            ? t('project.permissions.public')
                            : currentProject.is_private
                              ? t('project.permissions.private')
                              : t('project.permissions.organization')
                        }
                      >
                        <p className="mb-3 text-xs text-red-700 dark:text-red-300">
                          {t('project.settings.visibilityDangerZone.help')}
                        </p>
                        <p
                          className="mb-3 text-xs text-zinc-500 dark:text-zinc-400"
                          data-testid="project-visibility-prepare-hint"
                        >
                          {t(
                            'project.settings.visibilityDangerZone.prepareHint',
                          )}
                        </p>
                        <div className="rounded-md border border-red-500/40 bg-red-50/40 p-4 dark:border-red-500/40 dark:bg-red-900/10">
                          <ProjectPermissionsPanel
                            projectId={projectId}
                            projectCreatorId={currentProject.created_by}
                            effectiveRole={currentProject.effective_role}
                            initialVisibility={
                              currentProject.is_public
                                ? 'public'
                                : currentProject.is_private
                                  ? 'private'
                                  : 'organization'
                            }
                            initialPublicRole={
                              currentProject.public_role === 'CONTRIBUTOR'
                                ? 'CONTRIBUTOR'
                                : 'ANNOTATOR'
                            }
                            initialOrganizations={
                              currentProject.organizations ?? []
                            }
                            onSave={() => fetchProject(projectId)}
                          />
                        </div>
                        {ProjectLmsLinking &&
                          currentProject.kind === 'exam' && (
                            <div className="mt-6 empty:hidden">
                              <ProjectLmsLinking projectId={projectId} />
                            </div>
                          )}
                      </SubSection>
                    </div>
                  )}

                {/* Access window: when the access group may see and work on
              the project ("Privat" plus a window is how a project is
              prepared unseen). */}
                {currentProject && !isDeletedView && canEditProject() && (
                  <ProjectAccessWindowSection
                    windowStartAt={currentProject.window_start_at}
                    windowEndAt={currentProject.window_end_at}
                    onSave={(value) => updateProject(projectId, value)}
                  />
                )}

                {/* Sharing (extended): share links, participants and whether
              students can find the project. Not gated on enable_annotation,
              so flashcard decks get it too. */}
                {ProjectSharing && currentProject && canEditProject() && (
                  // The slot may render nothing: no empty divided row.
                  <div data-testid="project-sharing" className="empty:hidden">
                    <ProjectSharing
                      project={currentProject}
                      onRefresh={() => fetchProject(projectId)}
                    />
                  </div>
                )}

                {/* Exam-only: Safe Exam Browser and the aids writers get
              (extended). Both save on their own. */}
                {ProjectExamSecurity &&
                  currentProject &&
                  currentProject.enable_annotation !== false &&
                  canEditProject() && (
                    <ProjectExamSecurity
                      project={currentProject}
                      onRefresh={() => fetchProject(projectId)}
                    />
                  )}
                {ProjectExamTools &&
                  currentProject &&
                  currentProject.enable_annotation !== false &&
                  canEditProject() && (
                    <ProjectExamTools
                      project={currentProject}
                      onRefresh={() => fetchProject(projectId)}
                    />
                  )}

                {/* Which cards this page shows (and the statistics and
              progress count): about this page's layout, so last. */}
                {canEditProject() && (
                  <SubSection
                    title={t('project.settings.featureVisibility.title')}
                    description={t('project.settings.featureVisibility.help')}
                  >
                    <div className="space-y-2">
                      {(
                        [
                          [
                            'enable_annotation',
                            t('project.annotationConfiguration.title'),
                          ],
                          [
                            'enable_generation',
                            t('project.generationConfiguration.title'),
                          ],
                          ['enable_evaluation', t('project.evaluation.title')],
                          ['enable_prompts', t('project.prompts.title')],
                        ] as const
                      ).map(([key, label]) => (
                        <Checkbox
                          key={key}
                          id={`feature-${key}`}
                          label={label}
                          checked={projectSettingsValue.features[key] !== false}
                          onChange={(e) =>
                            handleFeatureVisibilityChange(key, e.target.checked)
                          }
                        />
                      ))}
                    </div>
                  </SubSection>
                )}
              </ConfigCard>
            </>
          )}
        </div>

        {/* Sidebar */}
        <div className="space-y-6">
          {/* Quick Actions */}
          <div className="rounded-lg border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
            <h2 className="mb-6 text-lg font-semibold text-zinc-900 dark:text-white">
              {t('project.quickActions.title')}
            </h2>
            <div className="space-y-3">
              {currentProject.enable_annotation !== false &&
                canSeeQuickAction('startLabeling') && (
                  <>
                    {userCompletedAllTasks && (
                      <div className="flex w-full items-center justify-center gap-2 rounded-md bg-emerald-50 px-4 py-2.5 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-400">
                        <CheckCircleIcon className="h-5 w-5" />
                        <span className="font-medium">
                          {t('project.quickActions.allTasksAnnotated')}
                        </span>
                      </div>
                    )}
                    <Button
                      onClick={handleStartLabeling}
                      variant="primary"
                      className="w-full"
                      disabled={currentProject.task_count === 0 || examNotReady}
                      title={
                        examNotReady
                          ? t('annotation.examNotReady.description')
                          : undefined
                      }
                      data-testid="project-start-labeling"
                    >
                      <PlayIcon className="mr-2 h-4 w-4" />
                      {t('project.quickActions.startLabeling')}
                    </Button>
                    {ProjectSolverActions && (
                      <div
                        data-testid="project-solver-actions"
                        className="empty:hidden"
                      >
                        <ProjectSolverActions project={currentProject} />
                      </div>
                    )}
                  </>
                )}

              {canSeeQuickAction('projectData') && (
                <Button
                  href={projectId ? `/projects/${projectId}/data` : '/projects'}
                  variant="outline"
                  className="w-full"
                >
                  {t('project.quickActions.projectData')}
                </Button>
              )}

              {/* My Tasks button */}
              {canSeeQuickAction('myTasks') && user && !user.is_superadmin && (
                <Button
                  href={
                    projectId ? `/projects/${projectId}/my-tasks` : '/projects'
                  }
                  variant="outline"
                  className="w-full"
                >
                  {t('project.quickActions.myTasks')}
                </Button>
              )}

              {ProjectEditorActions && canSeeQuickAction('editorActions') && (
                <div
                  data-testid="project-editor-actions"
                  // The slot may render nothing (e.g. a flag is off): no
                  // empty row in the stacked Quick Actions.
                  className="empty:hidden"
                >
                  <ProjectEditorActions project={currentProject} />
                </div>
              )}

              {canSeeQuickAction('generation') && (
                <Button
                  onClick={handleGenerateLLM}
                  variant="outline"
                  className="w-full"
                >
                  {t('project.quickActions.generation')}
                </Button>
              )}

              {canSeeQuickAction('evaluations') && (
                <Button
                  onClick={() =>
                    router.push(
                      evaluationsPath({
                        projectId,
                        type: opensAnalyses ? 'analysis' : 'metrics',
                      }),
                    )
                  }
                  variant="outline"
                  className="w-full"
                  data-testid="project-evaluations"
                >
                  {t('project.quickActions.evaluations')}
                </Button>
              )}

              {canSeeQuickAction('review') &&
                currentProject?.review_enabled && (
                  <Button
                    href={
                      projectId ? `/projects/${projectId}/review` : '/projects'
                    }
                    variant="outline"
                    className="w-full"
                  >
                    {t('project.quickActions.reviewWorkflow') || 'Review'}
                  </Button>
                )}

              {canSeeQuickAction('feedback') &&
                currentProject?.korrektur_enabled && (
                  <Button
                    href={
                      projectId
                        ? `/projects/${projectId}/korrektur`
                        : '/projects'
                    }
                    variant="outline"
                    className="w-full"
                  >
                    {t('project.quickActions.korrektur') || 'Correction'}
                  </Button>
                )}

              {canSeeQuickAction('deleteProject') && (
                <Button
                  onClick={() =>
                    canDeleteProject() && setShowDeleteConfirm(true)
                  }
                  variant="danger"
                  className="w-full"
                  disabled={deleting || !canDeleteProject()}
                >
                  {deleting
                    ? t('project.deleting')
                    : t('project.deleteProject')}
                </Button>
              )}
            </div>
          </div>

          {ProjectLmsActivities && (
            <ProjectLmsActivities projectId={currentProject.id} />
          )}

          {/* Participation: how the user got in, leaving, the cohort. Below
              the actions so the primary action stays first; the card hides
              itself when it has nothing actionable. */}
          {isParticipant && (
            <ParticipantCard
              projectId={projectId}
              via={currentProject.participant_via ?? null}
              participation={participation}
              onLeft={() => router.push('/projects')}
            />
          )}

          {/* Billing — whose API key pays for AI evaluations */}
          <ProjectBillingCard project={currentProject} />

          {/* Project Statistics */}
          <div className="rounded-lg border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
            <h2 className="mb-6 text-lg font-semibold text-zinc-900 dark:text-white">
              {t('project.statistics.title')}
            </h2>
            <dl className="space-y-3">
              <div className="flex justify-between">
                <dt className="text-sm text-zinc-500 dark:text-zinc-400">
                  {t('project.statistics.totalTasks')}
                </dt>
                <dd className="text-sm font-medium text-zinc-900 dark:text-white">
                  {currentProject.task_count}
                </dd>
              </div>
              {currentProject.enable_annotation !== false && (
                <div className="flex justify-between">
                  <dt className="text-sm text-zinc-500 dark:text-zinc-400">
                    {t('project.statistics.annotations')}
                  </dt>
                  <dd className="text-sm font-medium text-zinc-900 dark:text-white">
                    {currentProject.annotation_count}
                  </dd>
                </div>
              )}
              {currentProject.enable_generation !== false && (
                <div className="flex justify-between">
                  <dt className="text-sm text-zinc-500 dark:text-zinc-400">
                    {t('project.statistics.generations')}
                  </dt>
                  <dd className="text-sm font-medium text-zinc-900 dark:text-white">
                    {currentProject.generation_count ?? 0}
                  </dd>
                </div>
              )}
              {currentProject.enable_evaluation !== false && (
                <div className="flex justify-between">
                  <dt className="text-sm text-zinc-500 dark:text-zinc-400">
                    {t('project.statistics.evaluations')}
                  </dt>
                  <dd className="text-sm font-medium text-zinc-900 dark:text-white">
                    {currentProject.evaluation_count ?? 0}
                  </dd>
                </div>
              )}
              {variantExperiments &&
                (currentProject.analysis_count ?? 0) > 0 && (
                  <div className="flex justify-between">
                    <dt className="text-sm text-zinc-500 dark:text-zinc-400">
                      {t('project.statistics.analyses')}
                    </dt>
                    <dd
                      className="text-sm font-medium text-zinc-900 dark:text-white"
                      data-testid="project-statistics-analyses"
                    >
                      {currentProject.analysis_count}
                    </dd>
                  </div>
                )}
              {ProjectStatisticsExtended && (
                <ProjectStatisticsExtended project={currentProject} />
              )}
              <div className="flex justify-between">
                <dt className="text-sm text-zinc-500 dark:text-zinc-400">
                  {t('project.statistics.progress')}
                </dt>
                <dd className="text-sm font-medium text-zinc-900 dark:text-white">
                  {completionRate}%
                </dd>
              </div>
              <div className="mt-2 h-2 w-full rounded-full bg-zinc-200 dark:bg-zinc-700">
                <div
                  className="h-2 rounded-full bg-emerald-600 transition-all dark:bg-emerald-500"
                  style={{ width: `${Math.min(100, completionRate)}%` }}
                />
              </div>
            </dl>
          </div>

          {/* Recent Activity */}
          <div className="rounded-lg border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
            <h2 className="mb-6 text-lg font-semibold text-zinc-900 dark:text-white">
              {t('project.recentActivity.title')}
            </h2>
            {currentProject.task_count === 0 ? (
              <div className="py-4 text-center">
                <p className="mb-3 text-sm text-zinc-500 dark:text-zinc-400">
                  {t('project.recentActivity.noTasks')}
                </p>
                <Button
                  onClick={() => router.push(`/projects/${projectId}?tab=data`)}
                  variant="outline"
                  className="text-sm"
                >
                  {t('project.recentActivity.importData')}
                </Button>
              </div>
            ) : (
              <div className="space-y-3">
                <div className="flex items-center space-x-3">
                  <div className="shrink-0">
                    <DocumentTextIcon className="h-5 w-5 text-zinc-400" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm text-zinc-900 dark:text-white">
                      {t(
                        currentProject.task_count === 1
                          ? 'project.recentActivity.tasksImportedOne'
                          : 'project.recentActivity.tasksImported',
                        { count: currentProject.task_count },
                      )}
                    </p>
                    <p className="text-xs text-zinc-500 dark:text-zinc-400">
                      {formatDistanceToNow(
                        new Date(currentProject.created_at),
                        {
                          addSuffix: true,
                          locale: dateFnsLocale(locale),
                        },
                      )}
                    </p>
                  </div>
                </div>
                {(currentProject.annotation_count ?? 0) > 0 && (
                  <div className="flex items-center space-x-3">
                    <div className="shrink-0">
                      <CheckCircleIcon className="h-5 w-5 text-emerald-500" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm text-zinc-900 dark:text-white">
                        {t(
                          currentProject.annotation_count === 1
                            ? 'project.recentActivity.annotationsCompletedOne'
                            : 'project.recentActivity.annotationsCompleted',
                          { count: currentProject.annotation_count },
                        )}
                      </p>
                      <p className="text-xs text-zinc-500 dark:text-zinc-400">
                        {t('project.recentActivity.inProgress')}
                      </p>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Project Report - Issue #770 */}
          {!isDeletedView && reportStatus?.canEdit && (
            <div className="rounded-lg border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
              <div className="mb-4 flex items-center justify-between">
                <h2 className="text-lg font-semibold text-zinc-900 dark:text-white">
                  {t('project.report.title')}
                </h2>
                <DocumentChartBarIcon className="h-5 w-5 text-zinc-400" />
              </div>

              <div className="space-y-4">
                <PublicationToggle
                  projectId={projectId || ''}
                  reportId={reportStatus.reportId}
                  isPublished={reportStatus.isPublished}
                  isPublic={reportStatus.isPublic}
                  canPublish={reportStatus.canPublish}
                  canPublishReason={reportStatus.canPublishReason}
                  canEdit={reportStatus.canEdit}
                  onToggle={(published) => {
                    setReportStatus((prev) =>
                      prev ? { ...prev, isPublished: published } : null,
                    )
                    addToast(
                      published
                        ? t('project.report.publishedSuccessfully')
                        : t('project.report.unpublishedSuccessfully'),
                      'success',
                    )
                  }}
                  onChange={(next) => {
                    setReportStatus((prev) =>
                      prev
                        ? {
                            ...prev,
                            isPublished: next.is_published,
                            isPublic: next.is_public,
                          }
                        : null,
                    )
                  }}
                />
                <Button
                  onClick={() =>
                    router.push(`/projects/${projectId}/report/edit`)
                  }
                  variant="outline"
                  className="w-full"
                >
                  <PencilIcon className="mr-2 h-4 w-4" />
                  {t('project.report.editReport')}
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Footer-CTA-driven modals. Mounted at the page level so they're
          decoupled from any sub-component that also opens its own copy. */}
      <GenerationControlModal
        isOpen={showGenerationStartModal}
        projectId={projectId || undefined}
        models={
          (currentProject as any)?.generation_config?.selected_configuration
            ?.models ||
          (currentProject as any)?.llm_model_ids ||
          []
        }
        defaultSelectedModels={
          (currentProject as any)?.generation_config?.selected_configuration
            ?.models ||
          (currentProject as any)?.llm_model_ids ||
          []
        }
        project={currentProject as any}
        onClose={() => setShowGenerationStartModal(false)}
        onSuccess={() => {
          setShowGenerationStartModal(false)
          if (projectId) fetchProject(projectId)
        }}
      />
      <EvaluationControlModal
        isOpen={showEvaluationStartModal}
        projectId={projectId || undefined}
        evaluationConfigs={evaluationConfigs
          .filter((e: any) => e.enabled)
          .map((e: any) => ({
            id: e.id,
            metric: e.metric,
            prediction_fields: e.prediction_fields,
            reference_fields: e.reference_fields,
            metric_parameters: e.metric_parameters,
          }))}
        onClose={() => setShowEvaluationStartModal(false)}
        onSuccess={() => {
          setShowEvaluationStartModal(false)
        }}
      />
    </div>
  )
}

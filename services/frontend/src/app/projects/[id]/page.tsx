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

import { EvaluationBuilder } from '@/components/evaluation/EvaluationBuilder'
import { EvaluationControlModal } from '@/components/evaluation/EvaluationControlModal'
import { GenerationControlModal } from '@/components/generation/GenerationControlModal'
import { useSlot } from '@/lib/extensions/slots'
import {
  LabelConfigEditor,
  type LabelConfigEditorHandle,
} from '@/components/projects/LabelConfigEditor'
import { logger } from '@/lib/utils/logger'
import { AdvancedSettingsCard } from '@/components/projects/AdvancedSettingsCard'
import { EvaluationDefaultsCard } from '@/components/projects/EvaluationDefaultsCard'
import { GenerationDefaultsCard } from '@/components/projects/GenerationDefaultsCard'
import {
  ModelSelectionSection,
  providerColors,
  type ReasoningConfig,
} from '@/components/projects/ModelSelectionSection'
import { ProjectMetadataCard } from '@/components/projects/ProjectMetadataCard'
import { ProjectPermissionsPanel } from '@/components/projects/ProjectPermissionsPanel'
import { PromptStructuresManager } from '@/components/projects/PromptStructuresManager'
import { PublicationToggle } from '@/components/reports/PublicationToggle'
import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { Button } from '@/components/shared/Button'
import { Card } from '@/components/shared/Card'
import { ConfigCard } from '@/components/projects/ConfigCard'
import { SubSection } from '@/components/projects/SubSection'
import { Input } from '@/components/shared/Input'
import { Label } from '@/components/shared/Label'
import { Textarea } from '@/components/shared/Textarea'
import { useToast } from '@/components/shared/Toast'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { useModels } from '@/hooks/useModels'
import { apiClient } from '@/lib/api/client'
import {
  getTemperatureConstraints,
  getDefaultMaxTokens,
  getRecommendedParam,
  hasRecommendations,
} from '@/lib/modelConstraints'
import type {
  AvailableEvaluationFields,
  EvaluationConfig,
} from '@/lib/api/evaluation-types'
import { useUIStore } from '@/stores'
import { useProjectStore } from '@/stores/projectStore'
import {
  CheckCircleIcon,
  DocumentChartBarIcon,
  DocumentTextIcon,
  PencilIcon,
  PlayIcon,
  TagIcon,
} from '@heroicons/react/24/outline'
import { formatDistanceToNow } from 'date-fns'
import { de } from 'date-fns/locale'
import { useRouter } from 'next/navigation'
import { useEffect, useMemo, useRef, useState } from 'react'

// providerColors is shared with ModelSelectionSection — imported above.

// Provider sort order
const providerOrder: Record<string, number> = {
  OpenAI: 1,
  Anthropic: 2,
  Google: 3,
  DeepInfra: 4,
  Mistral: 5,
  Cohere: 6,
  Grok: 7,
}

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

export default function ProjectDetailPage({ params }: ProjectDetailPageProps) {
  const router = useRouter()
  const [projectId, setProjectId] = useState<string | null>(null)
  const { user, currentOrganization } = useAuth()
  const { addToast } = useToast()
  const { isSidebarHidden } = useUIStore()
  const { t } = useI18n()

  const {
    currentProject,
    loading,
    fetchProject,
    updateProject,
    deleteProject,
  } = useProjectStore()

  const isOrgProject = !!(currentOrganization && currentProject?.organizations?.length)

  const [tasks, setTasks] = useState([])
  const [userCompletedAllTasks, setUserCompletedAllTasks] = useState(false)
  const [showConfigEditor, setShowConfigEditor] = useState(false)
  const labelConfigRef = useRef<LabelConfigEditorHandle>(null)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [deleting, setDeleting] = useState(false)

  // Editing states
  const [editingTitle, setEditingTitle] = useState(false)
  const [titleValue, setTitleValue] = useState('')
  const [editingDescription, setEditingDescription] = useState(false)
  const [descriptionValue, setDescriptionValue] = useState('')
  const [isUpdating, setIsUpdating] = useState(false)

  // Expanded sections
  const [expandedConfig, setExpandedConfig] = useState(false)
  const [expandedModels, setExpandedModels] = useState(false)
  const [expandedInstructions, setExpandedInstructions] = useState(false)
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
  const [showGenerationStartModal, setShowGenerationStartModal] = useState(false)
  const [showEvaluationStartModal, setShowEvaluationStartModal] = useState(false)

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
  const [evalDefaultTemperature, setEvalDefaultTemperature] = useState<number | undefined>(undefined)
  const [evalDefaultMaxTokens, setEvalDefaultMaxTokens] = useState<number | undefined>(undefined)
  // Multi-run default for evaluation (migration 042). Used when no judge
  // ensemble is configured (i.e. metric_parameters.judges is empty); when an
  // ensemble exists, judge_runs are driven by the per-judge `runs` entries
  // instead. Bounded server-side at 1..25.
  const [evalDefaultRunsPerTask, setEvalDefaultRunsPerTask] = useState<number | undefined>(undefined)
  const [isUpdatingEvalDefaults, setIsUpdatingEvalDefaults] = useState(false)

  // Defaults mode for evaluation: drives the per-judge pre-fill when a new
  // judge metric is configured. Mirrors the generation-side mode below.
  type DefaultsMode = 'recommended' | 'minimum' | 'custom'
  const [evalDefaultsMode, setEvalDefaultsMode] = useState<DefaultsMode>('recommended')

  // Generation defaults
  const [genDefaultTemperature, setGenDefaultTemperature] = useState<number | undefined>(undefined)
  const [genDefaultMaxTokens, setGenDefaultMaxTokens] = useState<number | undefined>(undefined)
  // Multi-run default for generation (migration 041). Number of trials per
  // (task, model, structure). Per-trigger override is allowed in the
  // GenerationControlModal. Bounded server-side at 1..25.
  const [genDefaultRunsPerTask, setGenDefaultRunsPerTask] = useState<number | undefined>(undefined)
  // Defaults mode for generation: drives per-model pre-fill when a model is
  // toggled in. `recommended` reads model.recommended_parameters,
  // `minimum` uses parameter_constraints.temperature.min (lowest stable
  // value the provider allows), `custom` uses the values entered above.
  // Constraint clamping (e.g. GPT-5 forces temp=1.0) always wins.
  const [genDefaultsMode, setGenDefaultsMode] = useState<DefaultsMode>('recommended')
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
  } = useModels()

  // Sort models by provider for better organization
  const sortedModels = useMemo(() => {
    if (!availableModels) return null
    return [...availableModels].sort((a, b) => {
      const orderA = providerOrder[a.provider] ?? 99
      const orderB = providerOrder[b.provider] ?? 99
      if (orderA !== orderB) return orderA - orderB
      return a.name.localeCompare(b.name)
    })
  }, [availableModels])

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
  const [editingInstructions, setEditingInstructions] = useState(false)
  const [instructionsValue, setInstructionsValue] = useState('')

  //  settings
  const [expanded, setExpanded] = useState(false)
  const [editing, setEditing] = useState(false)
  const ProjectSettingsExtended = useSlot('project-settings-extended')
  const ProjectStatisticsExtended = useSlot('project-statistics-extended')
  const [advancedSettings, setAdvancedSettings] = useState({
    show_instruction: true,
    instructions_always_visible: false,
    show_skip_button: true,
    show_submit_button: true,
    require_comment_on_skip: false,
    require_confirm_before_submit: false,
    skip_queue: 'requeue_for_others' as 'requeue_for_me' | 'requeue_for_others' | 'ignore_skipped',
    questionnaire_enabled: false,
    questionnaire_config: '' as string,
    maximum_annotations: 1,
    min_annotations_per_task: 1,
    assignment_mode: 'open' as 'open' | 'manual' | 'auto',
    randomize_task_order: false,
    annotator_full_visibility_after_submit: false,
    review_enabled: false,
    review_mode: 'in_place' as 'in_place' | 'independent' | 'both',
    allow_self_review: false,
    korrektur_enabled: false,
    korrektur_config: [] as Array<{ value: string; background: string }>,
    annotation_time_limit_enabled: false,
    annotation_time_limit_seconds: null as number | null,
    strict_timer_enabled: false,
  })

  // Per-card buffer for evaluation-scoped settings. Decouples the Eval card's
  // Speichern from the Annotation card's so flushing one doesn't drag the
  // other's local buffer into the PATCH.
  const [evaluationSettings, setEvaluationSettings] = useState({
    immediate_evaluation_enabled: false,
  })

  // Per-project Korrektur (Falllösung) blind-mode toggles. Source of truth
  // is `metric_parameters` on the korrektur_falloesung evaluation_config,
  // surfaced here so users can flip them from project settings instead of
  // editing the metric config directly. Defaults match POLICY_DEFAULTS in
  // benger-extended (both true) — least-biased grading by default.
  const [korrekturBlindToPeers, setKorrekturBlindToPeers] = useState(true)
  const [korrekturBlindToLlm, setKorrekturBlindToLlm] = useState(true)
  const [korrekturBlindToNonJudge, setKorrekturBlindToNonJudge] = useState(true)
  const [korrekturKeepBlindAfterSubmit, setKorrekturKeepBlindAfterSubmit] = useState(false)

  // Conditional instructions state
  const [conditionalInstructions, setConditionalInstructions] = useState<
    { id: string; content: string; weight: number; ai_allowed?: boolean }[]
  >([])
  const [editingConditionalInstructions, setEditingConditionalInstructions] = useState(false)

  // Report state (Issue #770)
  const [reportStatus, setReportStatus] = useState<{
    exists: boolean
    isPublished: boolean
    canPublish: boolean
    canPublishReason: string
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

  // Fetch report status (Issue #770)
  const fetchReportStatus = async () => {
    if (!projectId || !user?.is_superadmin) return

    setLoadingReport(true)
    try {
      const response = await fetch(`/api/projects/${projectId}/report`, {
        credentials: 'include',
      })

      if (response.ok) {
        const data = await response.json()
        setReportStatus({
          exists: true,
          isPublished: data.is_published,
          canPublish: data.can_publish,
          canPublishReason: data.can_publish_reason,
        })
      } else if (response.status === 404) {
        setReportStatus({
          exists: false,
          isPublished: false,
          canPublish: false,
          canPublishReason: t('project.settings.review.reportNotCreated'),
        })
      }
    } catch (error) {
      console.error('Failed to fetch report status:', error)
    } finally {
      setLoadingReport(false)
    }
  }

  // Always fetch project data when component mounts - ensures fresh data
  useEffect(() => {
    if (projectId) {
      // Always fetch the project data to ensure we have the latest information
      // This handles both initial load and navigation back from other pages
      fetchProject(projectId)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fetchProject is stable, only re-run when projectId changes
  }, [projectId])
   

  // Check if current user has completed all tasks (per-user, not global)
  useEffect(() => {
    if (!projectId || !currentProject?.task_count) {
      setUserCompletedAllTasks(false)
      return
    }
    const checkUserCompletion = async () => {
      try {
        const result = await apiClient.get(`/projects/${projectId}/next`)
        setUserCompletedAllTasks(!result.task && result.remaining === 0)
      } catch {
        setUserCompletedAllTasks(false)
      }
    }
    checkUserCompletion()
  }, [projectId, currentProject?.task_count, currentProject?.annotation_count])

  // Fetch report status when user or projectId changes (Issue #770)
  useEffect(() => {
    if (projectId && user) {
      fetchReportStatus()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fetchReportStatus is stable, only re-run when projectId or user changes
  }, [projectId, user])
   

  // Fetch existing multi-field evaluations on page load (for badge display)
  useEffect(() => {
    const fetchEvaluationConfig = async () => {
      if (!projectId) return

      try {
        // Fetch existing evaluation config to load evaluation configs
        const configResponse = await apiClient.get(
          `/evaluations/projects/${projectId}/evaluation-config`
        )
        // Support current key (evaluation_configs) and legacy key (multi_field_evaluations)
        const existingConfigs = configResponse?.evaluation_configs || configResponse?.multi_field_evaluations || []
        if (existingConfigs.length > 0) {
          setEvaluationConfigs(existingConfigs)
        }
        // Hydrate the project-level blind toggles from the korrektur_falloesung
        // metric's parameters. Missing keys default to true (matches the
        // extended POLICY_DEFAULTS for least-biased grading).
        const fk = existingConfigs.find(
          (c: any) => c.metric === 'korrektur_falloesung',
        )
        const mp = fk?.metric_parameters || {}
        setKorrekturBlindToPeers(mp.blind_to_peer_correctors !== false)
        setKorrekturBlindToLlm(mp.blind_to_llm_judge !== false)
        setKorrekturBlindToNonJudge(mp.blind_to_non_judge_metrics !== false)
        setKorrekturKeepBlindAfterSubmit(mp.keep_blind_after_submit === true)
      } catch (error) {
        console.error('Failed to fetch evaluation config:', error)
      }
    }

    fetchEvaluationConfig()
  }, [projectId])

  useEffect(() => {
    const fetchAvailableFields = async () => {
      if (!projectId) return

      try {
        const fields =
          await apiClient.evaluations.getAvailableEvaluationFields(projectId)
        setAvailableEvaluationFields(fields)
      } catch (error) {
        console.error('Failed to fetch available fields:', error)
      }
    }

    fetchAvailableFields()
  }, [projectId])

  // Save evaluation configs to project config when they change
  const saveEvaluationConfigsToProject = async (
    evaluations: EvaluationConfig[]
  ) => {
    if (!projectId) return

    try {
      // Get existing config first
      const configResponse = await apiClient.get(
        `/evaluations/projects/${projectId}/evaluation-config`
      )
      const existingConfig = configResponse || {}

      // Update with evaluation configs
      await apiClient.put(
        `/evaluations/projects/${projectId}/evaluation-config`,
        {
          ...existingConfig,
          evaluation_configs: evaluations,
        }
      )
    } catch (error) {
      console.error('Failed to save evaluation config:', error)
    }
  }

  // Wrapper for onEvaluationsChange that also persists to backend
  const handleEvaluationConfigsChange = (
    evaluations: EvaluationConfig[]
  ) => {
    setEvaluationConfigs(evaluations)
    saveEvaluationConfigsToProject(evaluations)
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
        setTimeout(() => fetchProject(projectId), 100) // Small delay to ensure page is ready
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
          currentProject.generation_config?.selected_configuration?.model_configs || {}
        setModelConfigs(projectModelConfigs)
      }

      // Load evaluation defaults
      const projectEvalTemp = currentProject.evaluation_config?.default_temperature
      const projectEvalMaxTokens = currentProject.evaluation_config?.default_max_tokens
      setEvalDefaultTemperature(projectEvalTemp)
      setEvalDefaultMaxTokens(projectEvalMaxTokens)
      setEvalDefaultRunsPerTask(currentProject.evaluation_config?.runs_per_task)
      setEvalDefaultsMode(
        (currentProject.evaluation_config?.defaults_mode as DefaultsMode) || 'recommended',
      )

      // Load generation defaults
      const genParams = currentProject.generation_config?.selected_configuration?.parameters || {}
      setGenDefaultTemperature(genParams.temperature)
      setGenDefaultMaxTokens(genParams.max_tokens)
      setGenDefaultRunsPerTask(currentProject.generation_config?.runs_per_task)
      setGenDefaultsMode(
        (currentProject.generation_config?.defaults_mode as DefaultsMode) || 'recommended',
      )

      setInstructions(currentProject.instructions || '')
      setInstructionsValue(currentProject.instructions || '')
      // Load conditional instructions
      setConditionalInstructions(currentProject.conditional_instructions || [])

      setAdvancedSettings({
        show_instruction: currentProject.show_instruction !== false,
        instructions_always_visible: currentProject.instructions_always_visible || false,
        show_skip_button: currentProject.show_skip_button !== false,
        show_submit_button: currentProject.show_submit_button !== false,
        require_comment_on_skip:
          currentProject.require_comment_on_skip || false,
        require_confirm_before_submit:
          currentProject.require_confirm_before_submit || false,
        skip_queue: currentProject.skip_queue || 'requeue_for_others',
        questionnaire_enabled:
          currentProject.questionnaire_enabled || false,
        questionnaire_config:
          currentProject.questionnaire_config || '',
        maximum_annotations: currentProject.maximum_annotations ?? 1,
        min_annotations_per_task: currentProject.min_annotations_per_task || 1,
        assignment_mode: currentProject.assignment_mode || 'open',
        randomize_task_order: currentProject.randomize_task_order || false,
        annotator_full_visibility_after_submit:
          (currentProject as any).annotator_full_visibility_after_submit || false,
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
      })
      setEvaluationSettings({
        immediate_evaluation_enabled:
          (currentProject as any).immediate_evaluation_enabled || false,
      })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- Using currentProject.id instead of currentProject to prevent unnecessary re-renders
  }, [currentProject?.id, skipModelReset])

  const canEditProject = () => {
    if (!user || !currentProject) return false
    if (user.is_superadmin) return true
    if (isOrgProject) return user.role === 'ORG_ADMIN' || user.role === 'CONTRIBUTOR'
    return currentProject.created_by === user.id
  }

  const canDeleteProject = () => {
    if (!user) return false
    if (user.is_superadmin) return true
    if (isOrgProject) return user.role === 'ORG_ADMIN'
    return false
  }

  const getReadOnlyMessage = (sectionTitle: string) =>
    isOrgProject
      ? t('project.permissions.orgAdminOnly', { section: sectionTitle })
      : t('project.permissions.creatorOnly', { section: sectionTitle })

  const canSeeQuickAction = (action: string) => {
    if (!isOrgProject) return true
    if (user?.is_superadmin) return true
    const role = user?.role
    switch (action) {
      case 'startLabeling':
      case 'myTasks':
        return true
      case 'projectData':
      case 'review':
      case 'feedback':
      case 'generation':
      case 'evaluations':
        return role === 'ORG_ADMIN' || role === 'CONTRIBUTOR'
      case 'deleteProject':
        return role === 'ORG_ADMIN'
      default:
        return true
    }
  }

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
      addToast(t('toasts.project.labelConfigSaved'), 'success')
      // Close editor only after all async operations complete
      setShowConfigEditor(false)
    } catch (error) {
      console.error('Failed to save label configuration:', error)
      addToast(t('toasts.project.labelConfigFailed'), 'error')
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
      addToast(t('toasts.project.deleteFailed', { error: errorMessage }), 'error')
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
      addToast(t('toasts.project.titleUpdateFailed', { error: errorMessage }), 'error')
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
      addToast(t('toasts.project.descriptionUpdateFailed', { error: errorMessage }), 'error')
    } finally {
      setIsUpdating(false)
    }
  }

  // Instructions editing handlers
  const handleStartEditInstructions = () => {
    setInstructionsValue(instructions)
    setEditingInstructions(true)
  }

  const handleCancelEditInstructions = () => {
    setEditingInstructions(false)
    setInstructionsValue(instructions)
  }

  const handleSaveInstructions = async () => {
    if (!currentProject || !projectId) return

    setIsUpdating(true)

    try {
      await updateProject(projectId, { instructions: instructionsValue })
      setInstructions(instructionsValue)
      setEditingInstructions(false)
      addToast(t('toasts.project.instructionsUpdated'), 'success')
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : t('toasts.error.updateFailed')
      addToast(t('toasts.project.instructionsUpdateFailed', { error: errorMessage }), 'error')
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
  ): { temperature?: number; max_tokens?: number; temperatureFixed?: boolean } => {
    const model = availableModels?.find((m) => m.id === modelId)
    const tempConstraints = getTemperatureConstraints(model)
    const constraintMaxTokens = getDefaultMaxTokens(model)
    const out: { temperature?: number; max_tokens?: number; temperatureFixed?: boolean } = {}

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
    // Toggling a model checkbox is an edit — auto-enter the card's edit
    // mode so the Speichern button surfaces. Without this the user can
    // tick boxes without realising they aren't persisted until the card
    // is saved (Issue: model selection silently lost on refresh).
    if (!cardEditing.generation) beginEditGeneration()

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
        if (prefill.temperature !== undefined) newConfig.temperature = prefill.temperature
        if (prefill.temperatureFixed) newConfig.temperatureFixed = true
        if (prefill.max_tokens !== undefined) newConfig.max_tokens = prefill.max_tokens

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
    const model = availableModels?.find(m => m.id === modelId)
    const rc = model?.default_config?.reasoning_config
    if (!rc) return undefined
    return rc as ReasoningConfig
  }

  // Update model-specific config (thinking budget, max tokens, etc.)
  const updateModelConfig = (modelId: string, key: string, value: any) => {
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

    logger.debug(
      '[SAVE START] Selected models before save:',
      selectedModelIds
    )
    logger.debug(
      '[SAVE START] Current project generation_config:',
      currentProject.generation_config
    )
    logger.debug('[SAVE START] skipModelReset flag:', skipModelReset)

    setIsUpdatingModels(true)
    setSkipModelReset(true) // Prevent useEffect from resetting selectedModelIds during save

    try {
      logger.debug('[API CALL] Saving model IDs:', selectedModelIds)
      logger.debug('[API CALL] Saving model configs:', modelConfigs)

      // Build a MINIMAL patch — only the fields this handler owns.
      // The backend deep-merges at top level (see crud.py update_project),
      // so unspecified keys (defaults_mode, runs_per_task, prompt_structures
      // …) are preserved. Avoid spreading currentProject.generation_config
      // here: a sibling save (handleSaveGenDefaults) running in parallel
      // could see a stale snapshot if we did, racing-overwriting its
      // newer defaults_mode/parameters write. Issue surfaced when the
      // 3-mode picker was added — saves alternated between modes.
      const existingSelectedConfig =
        currentProject.generation_config?.selected_configuration || {}

      await updateProject(projectId, {
        generation_config: {
          selected_configuration: {
            ...existingSelectedConfig,
            models: selectedModelIds,
            model_configs: modelConfigs,
          },
        },
      })
      logger.debug(
        '[API SUCCESS] Model IDs and configs saved successfully to generation_config'
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
          currentProject.generation_config.selected_configuration.models
        )
      } else {
        console.warn('[API RESPONSE] No models in generation_config!')
      }

      addToast(t('toasts.project.modelsSaved'), 'success')

      // Collapse the section after successful save to show the updated count
      setExpandedModels(false)

      // Log state after API call
      setTimeout(() => {
        logger.debug(
          '[POST-SAVE] Selected models after API call:',
          selectedModelIds
        )
        logger.debug('[POST-SAVE] skipModelReset flag:', skipModelReset)
      }, 100)
    } catch (error) {
      console.error('[ERROR] Error saving models:', error)
      const errorMessage =
        error instanceof Error
          ? error.message
          : t('toasts.error.saveFailed')
      addToast(t('toasts.project.modelsSaveFailed', { error: errorMessage }), 'error')
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
            selectedModelIds
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
      // Backend deep-merges at top level so siblings (evaluation_configs,
      // immediate_evaluation_enabled, …) survive when other handlers in
      // the saveEvaluationCard Promise.all race write them concurrently.
      // Same fix as handleSaveModels / handleSaveGenDefaults.
      await updateProject(projectId, {
        evaluation_config: {
          default_temperature: evalDefaultTemperature,
          default_max_tokens: evalDefaultMaxTokens,
          // 3-mode picker for per-judge pre-fill; see DefaultsMode type.
          defaults_mode: evalDefaultsMode,
          // Multi-run default (migration 042); see comment on the state hook.
          ...(evalDefaultRunsPerTask !== undefined
            ? { runs_per_task: evalDefaultRunsPerTask }
            : {}),
        },
      })

      await fetchProject(projectId)
      addToast(t('toasts.project.evaluationDefaultsSaved'), 'success')
    } catch (error) {
      console.error('[ERROR] Error saving evaluation defaults:', error)
      const errorMessage =
        error instanceof Error
          ? error.message
          : t('toasts.error.saveFailed')
      addToast(t('toasts.project.evaluationDefaultsSaveFailed', { error: errorMessage }), 'error')
    } finally {
      setIsUpdatingEvalDefaults(false)
    }
  }

  const handleSaveGenDefaults = async () => {
    if (!currentProject || !projectId) return

    setIsUpdatingGenDefaults(true)

    try {
      // Minimal patch — only fields this handler owns. Backend deep-merges
      // at the top level so siblings (e.g. selected_configuration.models
      // from handleSaveModels) survive. Critical when both handlers fire
      // in parallel from saveGenerationCard.
      const existingParams =
        currentProject.generation_config?.selected_configuration?.parameters || {}

      await updateProject(projectId, {
        generation_config: {
          // 3-mode picker for per-model pre-fill; see DefaultsMode type.
          defaults_mode: genDefaultsMode,
          // Multi-run default (migration 041): omitted when undefined so the
          // server-side default of 1 stays implicit; clamped to 1..25 by the
          // input field below and re-validated by the API router.
          ...(genDefaultRunsPerTask !== undefined
            ? { runs_per_task: genDefaultRunsPerTask }
            : {}),
          selected_configuration: {
            parameters: {
              ...existingParams,
              temperature: genDefaultTemperature,
              max_tokens: genDefaultMaxTokens,
            },
          },
        },
      })

      await fetchProject(projectId)
      addToast(t('toasts.project.generationDefaultsSaved'), 'success')
    } catch (error) {
      console.error('[ERROR] Error saving generation defaults:', error)
      const errorMessage =
        error instanceof Error
          ? error.message
          : t('toasts.error.saveFailed')
      addToast(t('toasts.project.generationDefaultsSaveFailed', { error: errorMessage }), 'error')
    } finally {
      setIsUpdatingGenDefaults(false)
    }
  }

  const handleSaveSettings = async () => {
    if (!currentProject || !projectId) return

    setIsUpdating(true)

    try {
      // korrektur_enabled / korrektur_config are server-derived from the
      // project's evaluation_config (after_eval_config_save hook). Stripping
      // them from the PATCH avoids clobbering server-side derivation with
      // stale local-buffer values.
      const { korrektur_enabled: _ke, korrektur_config: _kc, ...payload } = advancedSettings
      await updateProject(projectId, payload)
      setEditing(false)
      addToast(t('toasts.project.settingsSaved'), 'success')
    } catch (error) {
      const errorMessage =
        error instanceof Error
          ? error.message
          : t('toasts.error.saveFailed')
      addToast(t('toasts.project.settingsSaveFailed', { error: errorMessage }), 'error')
    } finally {
      setIsUpdating(false)
    }
  }

  // Card-level edit lifecycle. Each ConfigCard exposes a single
  // Bearbeiten / Speichern / Abbrechen control. When entered, we flip every
  // dependent sub-section's edit flag at once; on Speichern the matching
  // save handlers run together so the card flushes atomically.
  const [cardEditing, setCardEditing] = useState({
    annotation: false,
    generation: false,
    evaluation: false,
  })
  const [cardSaving, setCardSaving] = useState({
    annotation: false,
    generation: false,
    evaluation: false,
  })

  const beginEditAnnotation = () => {
    setEditingInstructions(true)
    setEditing(true)
    setShowConfigEditor(true)
    setCardEditing((p) => ({ ...p, annotation: true }))
  }

  const cancelEditAnnotation = () => {
    setEditingInstructions(false)
    setInstructionsValue(instructions)
    setEditing(false)
    setShowConfigEditor(false)
    setCardEditing((p) => ({ ...p, annotation: false }))
  }

  const saveAnnotationCard = async () => {
    setCardSaving((p) => ({ ...p, annotation: true }))
    try {
      // Run all sub-section saves in parallel; LabelConfigEditor's imperative
      // save() short-circuits the Promise.all on validation error so the
      // user sees the inline alert and the other PATCHes still go through.
      await Promise.all([
        editingInstructions ? handleSaveInstructions() : Promise.resolve(),
        editing ? handleSaveSettings() : Promise.resolve(),
        showConfigEditor && labelConfigRef.current?.isDirty()
          ? labelConfigRef.current.save()
          : Promise.resolve(),
      ])
      setCardEditing((p) => ({ ...p, annotation: false }))
      setShowConfigEditor(false)
    } finally {
      setCardSaving((p) => ({ ...p, annotation: false }))
    }
  }

  // Generation/Evaluation cards have no per-section "edit mode" today — their
  // controls are always editable when the card is expanded. The card-level
  // Speichern just flushes the corresponding payload through one handler.
  const beginEditGeneration = () => setCardEditing((p) => ({ ...p, generation: true }))
  const cancelEditGeneration = () => setCardEditing((p) => ({ ...p, generation: false }))
  const saveGenerationCard = async () => {
    setCardSaving((p) => ({ ...p, generation: true }))
    try {
      await Promise.all([handleSaveModels(), handleSaveGenDefaults()])
      setCardEditing((p) => ({ ...p, generation: false }))
    } finally {
      setCardSaving((p) => ({ ...p, generation: false }))
    }
  }

  // Eval card hosts immediate_evaluation_enabled (now in its own evaluationSettings
  // buffer, decoupled from advancedSettings) plus the eval-defaults form. Card-edit
  // flips only cardEditing.evaluation; save PATCHes the buffer + eval defaults.
  const beginEditEvaluation = () => setCardEditing((p) => ({ ...p, evaluation: true }))
  const cancelEditEvaluation = () => {
    setEvaluationSettings({
      immediate_evaluation_enabled:
        (currentProject as any)?.immediate_evaluation_enabled || false,
    })
    // Also revert the blind toggles to whatever the saved config has, so
    // discarding the eval card resets *all* of its buffered fields.
    const fk = evaluationConfigs.find((c: any) => c.metric === 'korrektur_falloesung')
    const mp = fk?.metric_parameters || {}
    setKorrekturBlindToPeers(mp.blind_to_peer_correctors !== false)
    setKorrekturBlindToLlm(mp.blind_to_llm_judge !== false)
    setKorrekturBlindToNonJudge(mp.blind_to_non_judge_metrics !== false)
    setKorrekturKeepBlindAfterSubmit(mp.keep_blind_after_submit === true)
    setCardEditing((p) => ({ ...p, evaluation: false }))
  }
  const saveEvaluationCard = async () => {
    if (!projectId) return
    setCardSaving((p) => ({ ...p, evaluation: true }))
    try {
      // Patch the korrektur_falloesung config's metric_parameters with the
      // blind toggles before saving; the policy reader on extended sources
      // these from metric_parameters, so writing them here makes the
      // project-level UI the single point of edit for graders.
      const fkIdx = evaluationConfigs.findIndex(
        (c: any) => c.metric === 'korrektur_falloesung',
      )
      let configsToSave = evaluationConfigs
      if (fkIdx >= 0) {
        const next = [...evaluationConfigs]
        next[fkIdx] = {
          ...next[fkIdx],
          metric_parameters: {
            ...(next[fkIdx].metric_parameters || {}),
            blind_to_peer_correctors: korrekturBlindToPeers,
            blind_to_llm_judge: korrekturBlindToLlm,
            blind_to_non_judge_metrics: korrekturBlindToNonJudge,
            keep_blind_after_submit: korrekturKeepBlindAfterSubmit,
          },
        }
        configsToSave = next
        setEvaluationConfigs(next)
      }
      await Promise.all([
        handleSaveEvalDefaults(),
        updateProject(projectId, evaluationSettings),
        fkIdx >= 0 ? saveEvaluationConfigsToProject(configsToSave) : Promise.resolve(),
      ])
      setCardEditing((p) => ({ ...p, evaluation: false }))
    } finally {
      setCardSaving((p) => ({ ...p, evaluation: false }))
    }
  }

  if (!projectId || (loading && !currentProject)) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <div className="text-center">
          <div className="mx-auto h-12 w-12 animate-spin rounded-full border-b-2 border-emerald-500"></div>
          <p className="mt-4 text-zinc-600 dark:text-zinc-400">
            {t('project.loading')}
          </p>
        </div>
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
    <div className="mx-auto max-w-7xl px-4 pb-10 pt-16 sm:px-6 lg:px-8">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-start justify-between">
          <div className="flex-1">
            {/* Breadcrumb Navigation */}
            <div className="mb-4">
              <Breadcrumb
                items={[
                  { label: t('navigation.dashboard'), href: '/dashboard' },
                  { label: t('navigation.projects'), href: '/projects' },
                  {
                    label: currentProject?.title || t('projects.table.project'),
                    href: projectId ? `/projects/${projectId}` : '/projects',
                  },
                ]}
              />
            </div>

            {/* Title */}
            <div className="mb-4">
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
                <div className="group flex items-center space-x-3">
                  <h1 className="text-3xl font-bold text-zinc-900 dark:text-white">
                    {currentProject.title}
                  </h1>
                  {canEditProject() && (
                    <Button
                      onClick={handleStartEditTitle}
                      variant="outline"
                      className="opacity-0 transition-opacity group-hover:opacity-100"
                    >
                      <PencilIcon className="h-4 w-4" />
                    </Button>
                  )}
                </div>
              )}
            </div>

            {/* Description */}
            <div className="mb-4">
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
                  <p className="text-zinc-600 dark:text-zinc-400">
                    {currentProject.description ||
                      t('projects.noProjectsDescription')}
                  </p>
                  {canEditProject() && (
                    <Button
                      onClick={handleStartEditDescription}
                      variant="outline"
                      className="flex-shrink-0 opacity-0 transition-opacity group-hover:opacity-100"
                    >
                      <PencilIcon className="h-4 w-4" />
                    </Button>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Delete Confirmation Modal */}
      {showDeleteConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50 p-4">
          <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl dark:bg-zinc-900">
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
                className="bg-red-600 text-white hover:bg-red-700"
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

          {currentProject.enable_annotation && (
          <ConfigCard
            title={t('project.annotationConfiguration.title')}
            defaultExpanded={false}
            canEdit={canEditProject()}
            editing={cardEditing.annotation}
            saving={cardSaving.annotation}
            onEdit={beginEditAnnotation}
            onCancel={cancelEditAnnotation}
            onSave={saveAnnotationCard}
          >
          {/* Annotation Instructions Section */}
          <div className="bg-white dark:bg-zinc-900">
            {canEditProject() ? (
            <>
            <div className="mb-6 flex items-center justify-between">
              <button
                onClick={() => setExpandedInstructions(!expandedInstructions)}
                className="flex items-center space-x-3 text-left"
              >
                <h2 className="text-lg font-semibold text-zinc-900 dark:text-white">
                  {t('project.annotationInstructions.title')}
                </h2>
                {!expandedInstructions && (
                  <span className="rounded-md bg-zinc-100 px-2 py-1 text-sm leading-tight text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400">
                    {instructions || (conditionalInstructions && conditionalInstructions.length > 0)
                      ? t('project.annotationInstructions.configured')
                      : t('project.annotationInstructions.notConfigured')}
                  </span>
                )}
                <svg
                  className={`h-5 w-5 flex-shrink-0 text-zinc-400 transition-transform ${expandedInstructions ? 'rotate-90 transform' : ''}`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M9 5l7 7-7 7"
                  />
                </svg>
              </button>
              {/* Per-section edit button removed — card-level Bearbeiten is
                  the sole entry point. */}
            </div>

            {expandedInstructions && (
              <>
                {editingInstructions ? (
                  <div className="space-y-4">
                    <Textarea
                      value={instructionsValue}
                      onChange={(e) => setInstructionsValue(e.target.value)}
                      placeholder={t(
                        'project.annotationInstructions.placeholder'
                      )}
                      rows={6}
                      className="w-full resize-none"
                    />
                    {/* Per-section Save/Cancel removed — card-level Speichern flushes everything. */}
                  </div>
                ) : instructions ? (
                  <div className="text-sm text-gray-700 dark:text-gray-300">
                    <pre className="whitespace-pre-wrap rounded-lg bg-zinc-50 p-4 text-gray-700 dark:bg-zinc-800 dark:text-gray-300">
                      {instructions}
                    </pre>
                  </div>
                ) : (
                  <p className="text-sm text-zinc-500 dark:text-zinc-400">
                    {t('project.annotationInstructions.noInstructions')}
                    {canEditProject() &&
                      ` ${t('project.annotationInstructions.clickToAdd')}`}
                  </p>
                )}
              </>
            )}

            {/* Conditional Instructions Editor */}
            {expandedInstructions && canEditProject() && (
              <div className="mt-6 border-t border-zinc-200 pt-4 dark:border-zinc-700">
                <div className="flex items-center justify-between">
                  <div>
                    <h4 className="text-sm font-medium text-zinc-900 dark:text-white">
                      {t('project.conditionalInstructions.title', { defaultValue: 'Conditional Instructions' })}
                    </h4>
                    <p className="text-xs text-zinc-500 dark:text-zinc-400">
                      {t('project.conditionalInstructions.description', { defaultValue: 'Show different instructions to annotators based on randomized assignment per task' })}
                    </p>
                  </div>
                  <Button
                    onClick={() => setEditingConditionalInstructions(!editingConditionalInstructions)}
                    variant="outline"
                    className="text-sm"
                  >
                    {editingConditionalInstructions
                      ? t('project.editing.cancel')
                      : conditionalInstructions.length > 0
                        ? t('project.conditionalInstructions.edit', { defaultValue: 'Edit Variants' })
                        : t('project.conditionalInstructions.add', { defaultValue: 'Add Variants' })}
                  </Button>
                </div>

                {!editingConditionalInstructions && conditionalInstructions.length > 0 && (
                  <div className="mt-3 space-y-2">
                    {conditionalInstructions.map((variant) => (
                      <div key={variant.id} className="rounded-md bg-zinc-50 p-3 dark:bg-zinc-800">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                              {variant.id}
                            </span>
                            {variant.ai_allowed && (
                              <span className="inline-flex items-center rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-700 dark:bg-blue-900/30 dark:text-blue-400">
                                {t('project.conditionalInstructions.aiAllowed', { defaultValue: 'AI Allowed' })}
                              </span>
                            )}
                          </div>
                          <span className="inline-flex items-center rounded-full bg-zinc-100 px-2 py-0.5 text-xs font-medium text-zinc-700 dark:bg-zinc-700 dark:text-zinc-300">{variant.weight}%</span>
                        </div>
                        <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400 line-clamp-2">
                          {variant.content}
                        </p>
                      </div>
                    ))}
                  </div>
                )}

                {editingConditionalInstructions && (
                  <div className="mt-3 space-y-3">
                    {conditionalInstructions.map((variant, index) => (
                      <div key={index} className="rounded-md border border-zinc-200 p-3 dark:border-zinc-700">
                        <div className="flex items-center gap-2">
                          <div className="flex-1">
                            <label className="text-xs font-medium text-zinc-500 dark:text-zinc-400">
                              {t('project.conditionalInstructions.variantId', { defaultValue: 'Variant ID' })}
                            </label>
                            <input
                              type="text"
                              value={variant.id}
                              onChange={(e) => {
                                const updated = [...conditionalInstructions]
                                updated[index] = { ...updated[index], id: e.target.value }
                                setConditionalInstructions(updated)
                              }}
                              placeholder="e.g. ai, no_ai"
                              className="mt-1 block w-full rounded-md border border-zinc-300 bg-white px-2 py-1 text-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500 dark:border-zinc-600 dark:bg-zinc-800 dark:text-white"
                            />
                          </div>
                          <div className="w-24">
                            <label className="text-xs font-medium text-zinc-500 dark:text-zinc-400">
                              {t('project.conditionalInstructions.weight', { defaultValue: 'Weight (%)' })}
                            </label>
                            <input
                              type="number"
                              min="1"
                              max="100"
                              value={variant.weight}
                              onChange={(e) => {
                                const updated = [...conditionalInstructions]
                                updated[index] = { ...updated[index], weight: parseInt(e.target.value) || 0 }
                                setConditionalInstructions(updated)
                              }}
                              className="mt-1 block w-full rounded-md border border-zinc-300 bg-white px-2 py-1 text-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500 dark:border-zinc-600 dark:bg-zinc-800 dark:text-white"
                            />
                          </div>
                          <div className="flex items-center gap-1 mt-5">
                            <input
                              type="checkbox"
                              id={`ai-allowed-${index}`}
                              checked={variant.ai_allowed || false}
                              onChange={(e) => {
                                const updated = [...conditionalInstructions]
                                updated[index] = { ...updated[index], ai_allowed: e.target.checked }
                                setConditionalInstructions(updated)
                              }}
                              className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500"
                            />
                            <label htmlFor={`ai-allowed-${index}`} className="text-xs font-medium text-zinc-500 dark:text-zinc-400 whitespace-nowrap">
                              {t('project.conditionalInstructions.aiAllowed', { defaultValue: 'AI' })}
                            </label>
                          </div>
                          <button
                            onClick={() => {
                              setConditionalInstructions(conditionalInstructions.filter((_, i) => i !== index))
                            }}
                            className="mt-5 text-red-500 hover:text-red-700"
                          >
                            &times;
                          </button>
                        </div>
                        <div className="mt-2">
                          <label className="text-xs font-medium text-zinc-500 dark:text-zinc-400">
                            {t('project.conditionalInstructions.content', { defaultValue: 'Instruction Content' })}
                          </label>
                          <textarea
                            value={variant.content}
                            onChange={(e) => {
                              const updated = [...conditionalInstructions]
                              updated[index] = { ...updated[index], content: e.target.value }
                              setConditionalInstructions(updated)
                            }}
                            rows={2}
                            className="mt-1 block w-full resize-none rounded-md border border-zinc-300 bg-white px-2 py-1 text-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500 dark:border-zinc-600 dark:bg-zinc-800 dark:text-white"
                          />
                        </div>
                      </div>
                    ))}

                    <div className="flex items-center gap-3">
                      <Button
                        onClick={() => {
                          setConditionalInstructions([
                            ...conditionalInstructions,
                            { id: '', content: '', weight: 50, ai_allowed: false },
                          ])
                        }}
                        variant="outline"
                        className="text-sm"
                      >
                        {t('project.conditionalInstructions.addVariant', { defaultValue: '+ Add Variant' })}
                      </Button>
                      <Button
                        onClick={async () => {
                          const totalWeight = conditionalInstructions.reduce((s, v) => s + v.weight, 0)
                          if (conditionalInstructions.length > 0 && totalWeight !== 100) {
                            addToast(t('project.conditionalInstructions.weightError', { defaultValue: 'Weights must sum to 100%' }), 'error')
                            return
                          }
                          try {
                            await updateProject(projectId, {
                              conditional_instructions: conditionalInstructions.length > 0 ? conditionalInstructions : null,
                            })
                            setEditingConditionalInstructions(false)
                            addToast(t('project.conditionalInstructions.saved', { defaultValue: 'Conditional instructions saved' }), 'success')
                          } catch {
                            addToast(t('project.conditionalInstructions.saveFailed', { defaultValue: 'Failed to save' }), 'error')
                          }
                        }}
                        disabled={isUpdating}
                        className="text-sm"
                      >
                        {t('project.conditionalInstructions.save', { defaultValue: 'Save Variants' })}
                      </Button>
                    </div>

                    {conditionalInstructions.length > 0 && (() => {
                      const totalWeight = conditionalInstructions.reduce((s, v) => s + v.weight, 0)
                      return totalWeight !== 100 ? (
                        <p className="text-xs text-red-500">
                          {t('project.conditionalInstructions.weightWarning', { defaultValue: `Weights sum to ${totalWeight}%, must be 100%`, total: totalWeight })}
                        </p>
                      ) : null
                    })()}
                  </div>
                )}
              </div>
            )}
            </>
            ) : (
              <div className="py-6 text-center">
                <p className="text-sm text-zinc-500 dark:text-zinc-400">
                  {getReadOnlyMessage(t('project.annotationInstructions.title'))}
                </p>
              </div>
            )}
          </div>

          {/* Label Configuration Section */}
          <div className="bg-white dark:bg-zinc-900">
            {canEditProject() ? (
            <>
            <div className="mb-6 flex items-center justify-between">
              <button
                onClick={() => setExpandedConfig(!expandedConfig)}
                className="flex items-center space-x-3 text-left"
              >
                <h2 className="text-lg font-semibold text-zinc-900 dark:text-white">
                  {t('project.labelConfiguration.title')}
                </h2>
                {!expandedConfig && (
                  <span className="rounded-md bg-zinc-100 px-2 py-1 text-sm leading-tight text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400">
                    {currentProject.label_config
                      ? t('project.labelConfiguration.configured')
                      : t('project.labelConfiguration.notConfigured')}
                  </span>
                )}
                <svg
                  className={`h-5 w-5 flex-shrink-0 text-zinc-400 transition-transform ${expandedConfig ? 'rotate-90 transform' : ''}`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M9 5l7 7-7 7"
                  />
                </svg>
              </button>
              {/* Label-Konfiguration now folds into the card-level Speichern:
                  beginEditAnnotation flips showConfigEditor=true, and
                  saveAnnotationCard awaits labelConfigRef.current.save() in
                  Promise.all alongside the other sub-section saves. */}
            </div>

            {expandedConfig && (
              <>
                {showConfigEditor ? (
                  <LabelConfigEditor
                    ref={labelConfigRef}
                    initialConfig={currentProject.label_config || ''}
                    onSave={handleSaveLabelConfig}
                    onCancel={() => setShowConfigEditor(false)}
                    projectId={currentProject.id}
                    hideInternalControls={cardEditing.annotation}
                  />
                ) : (
                  <>
                    {currentProject.label_config ? (
                      <div className="space-y-4">
                        <pre className="overflow-x-auto rounded-lg bg-zinc-100 p-4 text-sm dark:bg-zinc-800">
                          <code className="text-zinc-900 dark:text-zinc-100">
                            {currentProject.label_config}
                          </code>
                        </pre>
                      </div>
                    ) : (
                      <div className="py-8 text-center">
                        <TagIcon className="mx-auto mb-4 h-12 w-12 text-zinc-400" />
                        <p className="mb-4 text-zinc-600 dark:text-zinc-400">
                          {t('project.labelConfiguration.noConfigSet')}
                        </p>
                        {canEditProject() && (
                          <Button
                            variant="outline"
                            onClick={() => setShowConfigEditor(true)}
                          >
                            {t('project.labelConfiguration.configureLabels')}
                          </Button>
                        )}
                      </div>
                    )}
                  </>
                )}
              </>
            )}
            </>
            ) : (
              <div className="py-6 text-center">
                <p className="text-sm text-zinc-500 dark:text-zinc-400">
                  {getReadOnlyMessage(t('project.labelConfiguration.title'))}
                </p>
              </div>
            )}
          </div>
          <SubSection
            title={t('project.settings.annotationSettingsTitle')}
            badge={`${t('project.settings.mode', { mode: advancedSettings.assignment_mode })}, ${t('project.settings.minAnnotations', { count: advancedSettings.min_annotations_per_task })}`}
          >
          {/*  Settings Section */}
          <AdvancedSettingsCard
            t={t}
            canEditProject={canEditProject}
            getReadOnlyMessage={getReadOnlyMessage}
            advancedSettings={advancedSettings}
            setAdvancedSettings={setAdvancedSettings}
            editing={editing}
            ProjectSettingsExtended={ProjectSettingsExtended}
          />
          </SubSection>

          </ConfigCard>
          )}

          {currentProject.enable_generation && (
          <ConfigCard
            title={t('project.generationConfiguration.title')}
            defaultExpanded={false}
            canEdit={canEditProject()}
            editing={cardEditing.generation}
            saving={cardSaving.generation}
            onEdit={beginEditGeneration}
            onCancel={cancelEditGeneration}
            onSave={saveGenerationCard}
          >
          {/* Generation Defaults — peer of Model Selection (was nested inside
              expandedModels until the multi-run feature; pulled out so the new
              "Default number of runs" knob is discoverable without expanding
              Model Selection first). Uses the shared SubSection wrapper so it
              matches the visual style of Modellauswahl / Prompt-Strukturen
              instead of looking like a one-off styled box. */}
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
              cardEditingGeneration={cardEditing.generation}
              beginEditGeneration={beginEditGeneration}
            />
          )}

          {/* runs_per_task lives in its own SubSection because it's a
              scheduling/budget knob — orthogonal to LLM parameters and
              not affected by the recommended/minimum/custom mode picker
              above. Splitting it makes the mode picker apply only to
              actual model parameters (temperature/max_tokens). */}
          {canEditProject() && (
            <div className="mb-6">
              <SubSection title={t('project.generationDefaults.runsTitle', 'Multi-Run')}>
                <p className="-mt-2 mb-3 text-xs text-zinc-500 dark:text-zinc-400">
                  {t('project.generationDefaults.runsDescription',
                     'Wie oft jede Task-Modell-Kombination generiert werden soll. Multipliziert die Kosten entsprechend.')}
                </p>
                <div className="max-w-xs">
                  <label className="block text-xs font-medium text-zinc-600 dark:text-zinc-400">
                    {t('project.generationDefaults.defaultRunsPerTask', 'Standard-Anzahl Läufe pro Task')}
                  </label>
                  <input
                    type="number"
                    min={1}
                    max={25}
                    step={1}
                    value={genDefaultRunsPerTask ?? 1}
                    placeholder="1"
                    onChange={(e) => {
                      // Auto-enter card edit mode so the Speichern button
                      // surfaces — same UX guarantee as the model toggle
                      // and the mode picker. Without this, typing a value
                      // doesn't persist on its own and the user has no
                      // visible save trigger.
                      if (!cardEditing.generation) beginEditGeneration()
                      setGenDefaultRunsPerTask(
                        e.target.value ? parseInt(e.target.value) : undefined
                      )
                    }}
                    className="mt-1 h-8 w-full rounded-md border border-zinc-300 px-2 text-sm dark:border-zinc-700 dark:bg-zinc-800"
                  />
                  <p className="mt-1 text-xs text-zinc-400 dark:text-zinc-500">
                    {t(
                      'project.generationDefaults.runsPerTaskHelp',
                      'Standardwert 1. Werte > 1 erzeugen mehrere Trials für Varianzanalyse. Cap 25.',
                    )}
                  </p>
                </div>
              </SubSection>
            </div>
          )}

          {/* Model Selection Section */}
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

          {/* Prompt Structures Section - Issue #762 */}
          <div className="bg-white dark:bg-zinc-900">
            {canEditProject() ? (
              <PromptStructuresManager
                projectId={projectId || ''}
                onStructuresChange={() => {
                  // Refetch project to update UI
                  if (projectId) {
                    fetchProject(projectId)
                  }
                }}
              />
            ) : (
              <div className="py-6 text-center">
                <p className="text-sm text-zinc-500 dark:text-zinc-400">
                  {getReadOnlyMessage(t('project.promptStructures.title'))}
                </p>
              </div>
            )}
          </div>

          {/* Always-visible "Generierung starten" CTA at the card footer.
              Mirrors the eval card's start button so both ConfigCards have
              parallel placement, and stays visible regardless of which
              sub-collapsibles inside are open. The modal itself handles
              the empty-models case ("Keine Modelle für die Generierung
              konfiguriert") so the button stays a discoverable entry
              point even when the user hasn't picked models yet. */}
          {canEditProject() && (
            <div className="flex justify-end gap-2 border-t pt-4 dark:border-zinc-700">
              <Button
                onClick={() => setShowGenerationStartModal(true)}
                className="flex items-center gap-2 text-sm"
              >
                <PlayIcon className="h-4 w-4" />
                {t('project.generation.runCta', 'Generierung starten')}
              </Button>
            </div>
          )}

          </ConfigCard>
          )}

          {currentProject.enable_evaluation && (
          <ConfigCard
            title={t('project.evaluation.title')}
            defaultExpanded={false}
            canEdit={canEditProject()}
            editing={cardEditing.evaluation}
            saving={cardSaving.evaluation}
            onEdit={beginEditEvaluation}
            onCancel={cancelEditEvaluation}
            onSave={saveEvaluationCard}
          >
          {/* Evaluation Configuration Section — flat sub-sections (no redundant
              middle collapsible). Direct children of the ConfigCard. */}
          {canEditProject() ? (
            <>
                  {/* Evaluation Defaults — placed at the top of the eval card
                      to mirror Generation Defaults' position in the gen card.
                      Owns the wizard-level temperature / max_tokens / runs
                      defaults that propagate into newly added eval configs. */}
                  {canEditProject() && (
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
                      cardEditingEvaluation={cardEditing.evaluation}
                      beginEditEvaluation={beginEditEvaluation}
                    />
                  )}

                  {/* runs_per_task lives in its own SubSection — it's a
                      scheduling/budget knob orthogonal to the parameter
                      strategy picker above. Same split as the gen side. */}
                  {canEditProject() && (
                    <div className="mb-6">
                      <SubSection title={t('project.evaluationDefaults.runsTitle', 'Multi-Run')}>
                        <p className="-mt-2 mb-3 text-xs text-zinc-500 dark:text-zinc-400">
                          {t('project.evaluationDefaults.runsDescription',
                             'Wie oft jede Task vom Judge bewertet werden soll. Greift, wenn kein Judge-Ensemble konfiguriert ist.')}
                        </p>
                        <div className="max-w-xs">
                          <label className="block text-xs font-medium text-zinc-600 dark:text-zinc-400">
                            {t('project.evaluationDefaults.defaultRunsPerTask', 'Standard-Anzahl Judge-Läufe')}
                          </label>
                          <input
                            type="number"
                            min={1}
                            max={25}
                            step={1}
                            value={evalDefaultRunsPerTask ?? 1}
                            placeholder="1"
                            onChange={(e) => {
                              // Auto-enter card edit mode so the Speichern
                              // button surfaces — mirrors gen-side fix.
                              if (!cardEditing.evaluation) beginEditEvaluation()
                              setEvalDefaultRunsPerTask(
                                e.target.value ? parseInt(e.target.value) : undefined
                              )
                            }}
                            className="mt-1 h-8 w-full rounded-md border border-zinc-300 px-2 text-sm dark:border-zinc-700 dark:bg-zinc-800"
                          />
                          <p className="mt-1 text-xs text-zinc-400 dark:text-zinc-500">
                            {t(
                              'project.evaluationDefaults.runsPerTaskHelp',
                              'Standardwert 1. Werte > 1 erzeugen mehrere Bewertungen für Varianz-/Konsistenzanalyse. Cap 25.',
                            )}
                          </p>
                        </div>
                      </SubSection>
                    </div>
                  )}

                  {/* Evaluation settings sub-section — owns its own state buffer,
                      flushed by the Eval card's single Speichern. */}
                  {canEditProject() && (
                    <SubSection title={t('project.evaluationSettings.title', 'Evaluierungseinstellungen')}>
                      <div className="flex items-center justify-between">
                        <div>
                          <Label>
                            {t(
                              'projects.creation.wizard.step7.immediateEvaluation',
                              'Immediate evaluation',
                            )}
                          </Label>
                          <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                            {t(
                              'projects.creation.wizard.step7.immediateEvaluationHint',
                              'Run the configured evaluations as soon as an annotation is submitted',
                            )}
                          </p>
                        </div>
                        <input
                          type="checkbox"
                          checked={evaluationSettings.immediate_evaluation_enabled}
                          onChange={(e) =>
                            setEvaluationSettings((prev) => ({
                              ...prev,
                              immediate_evaluation_enabled: e.target.checked,
                            }))
                          }
                          disabled={!cardEditing.evaluation}
                          className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
                        />
                      </div>
                      {evaluationConfigs.some(
                        (c: any) => c.metric === 'korrektur_falloesung',
                      ) && (
                        <>
                          <div className="mt-4 flex items-center justify-between">
                            <div>
                              <Label>
                                {t(
                                  'project.evaluationSettings.korrekturBlindToPeers',
                                  'Blinde Korrektur (andere Korrektoren)',
                                )}
                              </Label>
                              <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                                {t(
                                  'project.evaluationSettings.korrekturBlindToPeersHint',
                                  'Bewertungen anderer Korrektoren bleiben verborgen, bis du selbst eingereicht hast',
                                )}
                              </p>
                            </div>
                            <input
                              type="checkbox"
                              checked={korrekturBlindToPeers}
                              onChange={(e) => setKorrekturBlindToPeers(e.target.checked)}
                              disabled={!cardEditing.evaluation}
                              className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
                            />
                          </div>
                          <div className="mt-4 flex items-center justify-between">
                            <div>
                              <Label>
                                {t(
                                  'project.evaluationSettings.korrekturBlindToLlm',
                                  'Blinde Korrektur (LLM-Vorbewertung)',
                                )}
                              </Label>
                              <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                                {t(
                                  'project.evaluationSettings.korrekturBlindToLlmHint',
                                  'LLM-Vorbewertungen bleiben verborgen, bis du selbst eingereicht hast',
                                )}
                              </p>
                            </div>
                            <input
                              type="checkbox"
                              checked={korrekturBlindToLlm}
                              onChange={(e) => setKorrekturBlindToLlm(e.target.checked)}
                              disabled={!cardEditing.evaluation}
                              className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
                            />
                          </div>
                          <div className="mt-4 flex items-center justify-between">
                            <div>
                              <Label>
                                {t(
                                  'project.evaluationSettings.korrekturBlindToNonJudge',
                                  'Blinde Korrektur (klassische Metriken)',
                                )}
                              </Label>
                              <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                                {t(
                                  'project.evaluationSettings.korrekturBlindToNonJudgeHint',
                                  'Klassische automatische Bewertungen (BLEU, ROUGE, BERTScore …) bleiben verborgen, bis du selbst eingereicht hast',
                                )}
                              </p>
                            </div>
                            <input
                              type="checkbox"
                              checked={korrekturBlindToNonJudge}
                              onChange={(e) => setKorrekturBlindToNonJudge(e.target.checked)}
                              disabled={!cardEditing.evaluation}
                              className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
                            />
                          </div>
                          <div className="mt-4 flex items-center justify-between">
                            <div>
                              <Label>
                                {t(
                                  'project.evaluationSettings.korrekturKeepBlindAfterSubmit',
                                  'Blind auch nach eigener Bewertung',
                                )}
                              </Label>
                              <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                                {t(
                                  'project.evaluationSettings.korrekturKeepBlindAfterSubmitHint',
                                  'Wenn aktiv, bleiben die obigen Bewertungen verborgen — auch nachdem du deine eigene Bewertung eingereicht hast',
                                )}
                              </p>
                            </div>
                            <input
                              type="checkbox"
                              checked={korrekturKeepBlindAfterSubmit}
                              onChange={(e) => setKorrekturKeepBlindAfterSubmit(e.target.checked)}
                              disabled={!cardEditing.evaluation}
                              className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
                            />
                          </div>
                        </>
                      )}
                    </SubSection>
                  )}

                  {/* Evaluation methods sub-section — wraps the EvaluationBuilder.
                      Collapsed badge mirrors Modellauswahl / Prompt-Strukturen
                      style: grey pill with the configured-method count. */}
                  <SubSection
                    title={t('project.evaluationMethods.title', 'Evaluierungsmethoden')}
                    badge={
                      evaluationConfigs.length > 0
                        ? evaluationConfigs.length === 1
                          ? t('project.evaluation.evaluationConfigSingular', { count: evaluationConfigs.length })
                          : t('project.evaluation.evaluationConfigPlural', { count: evaluationConfigs.length })
                        : t('project.evaluation.notConfigured')
                    }
                  >
                  {/* Multi-Field Evaluation Builder (Phase 8: N:M Field Mapping) */}
                  <div className="mb-6">
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
                  </div>
                  </SubSection>
            </>
          ) : (
            <div className="py-6 text-center">
              <p className="text-sm text-zinc-500 dark:text-zinc-400">
                {getReadOnlyMessage(t('project.evaluation.title'))}
              </p>
            </div>
          )}

          {/* Always-visible "Evaluierung starten" CTA at the card footer.
              EvaluationBuilder also renders an internal trigger inside its
              Methoden sub-section (only visible when expanded); this footer
              one stays visible whenever the eval ConfigCard is open. Both
              open the same EvaluationControlModal — two paths to the same
              flow is fine. */}
          {canEditProject() && evaluationConfigs.filter((e: any) => e.enabled).length > 0 && (
            <div className="flex justify-end gap-2 border-t pt-4 dark:border-zinc-700">
              <Button
                onClick={() => setShowEvaluationStartModal(true)}
                className="flex items-center gap-2 text-sm"
              >
                <PlayIcon className="h-4 w-4" />
                {t('project.evaluation.runCta', 'Evaluierung starten')}
              </Button>
            </div>
          )}

          </ConfigCard>
          )}

          <ConfigCard title={t('project.settings.title')} defaultExpanded={false}>
          {/* Feature visibility — its own collapsed-by-default sub-section. */}
          {canEditProject() && (
            <SubSection title={t('project.settings.featureVisibility.title')}>
              <p className="mb-3 text-xs text-zinc-500 dark:text-zinc-400">
                {t('project.settings.featureVisibility.help')}
              </p>
              <div className="space-y-2">
                {([
                  ['enable_annotation', t('project.annotationConfiguration.title')],
                  ['enable_generation', t('project.generationConfiguration.title')],
                  ['enable_evaluation', t('project.evaluation.title')],
                ] as const).map(([key, label]) => (
                  <label
                    key={key}
                    className="flex items-center space-x-2 text-sm text-zinc-700 dark:text-zinc-300"
                  >
                    <input
                      type="checkbox"
                      checked={(currentProject as any)[key] !== false}
                      onChange={async (e) => {
                        if (!projectId) return
                        try {
                          await updateProject(projectId, { [key]: e.target.checked })
                        } catch (err) {
                          addToast(
                            t('toasts.project.settingsSaveFailed', {
                              error: err instanceof Error ? err.message : '',
                            }),
                            'error',
                          )
                        }
                      }}
                      className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500"
                    />
                    <span>{label}</span>
                  </label>
                ))}
              </div>
            </SubSection>
          )}

          {/* Visibility — collapsible sub-section, danger-zone styled
              because flipping to public exposes the project platform-wide. */}
          {currentProject &&
            (user?.is_superadmin ||
              String(user?.id) === String(currentProject.created_by)) && (
              <div
                className="mt-6"
                data-testid="project-visibility-danger-zone"
              >
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
                  <div className="rounded-md border border-red-500/40 bg-red-50/40 p-4 dark:border-red-500/40 dark:bg-red-900/10">
                    <ProjectPermissionsPanel
                      projectId={projectId}
                      projectCreatorId={currentProject.created_by}
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
                </SubSection>
              </div>
            )}
          </ConfigCard>
        </div>

        {/* Sidebar */}
        <div className="space-y-6">
          {/* Quick Actions */}
          <div className="rounded-lg border border-zinc-200 bg-white p-6 shadow-sm ring-1 ring-zinc-900/5 dark:border-zinc-700 dark:bg-zinc-900 dark:ring-white/10">
            <h2 className="mb-6 text-lg font-semibold text-zinc-900 dark:text-white">
              {t('project.quickActions.title')}
            </h2>
            <div className="space-y-3">
              {currentProject.enable_annotation !== false && (
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
                    disabled={currentProject.task_count === 0}
                  >
                    <PlayIcon className="mr-2 h-4 w-4" />
                    {t('project.quickActions.startLabeling')}
                  </Button>
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
                  <DocumentTextIcon className="mr-2 h-4 w-4" />
                  {t('project.quickActions.myTasks')}
                </Button>
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
                    router.push(`/evaluations?projectId=${projectId}`)
                  }
                  variant="outline"
                  className="w-full"
                >
                  {t('project.quickActions.evaluations')}
                </Button>
              )}

              {canSeeQuickAction('review') && currentProject?.review_enabled && (
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

              {canSeeQuickAction('feedback') && currentProject?.korrektur_enabled && (
                <Button
                  href={
                    projectId ? `/projects/${projectId}/korrektur` : '/projects'
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
                  variant="outline"
                  className={`w-full border-red-500 text-red-600 dark:border-red-400 dark:text-red-400 ${
                    canDeleteProject()
                      ? 'hover:bg-red-50 dark:hover:bg-red-400/10'
                      : 'cursor-not-allowed opacity-50'
                  }`}
                  disabled={deleting || !canDeleteProject()}
                >
                  {deleting
                    ? t('project.deleting')
                    : t('project.deleteProject')}
                </Button>
              )}
            </div>
          </div>

          {/* Project Statistics */}
          <div className="rounded-lg border border-zinc-200 bg-white p-6 shadow-sm ring-1 ring-zinc-900/5 dark:border-zinc-700 dark:bg-zinc-900 dark:ring-white/10">
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
          <div className="rounded-lg border border-zinc-200 bg-white p-6 shadow-sm ring-1 ring-zinc-900/5 dark:border-zinc-700 dark:bg-zinc-900 dark:ring-white/10">
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
                  <div className="flex-shrink-0">
                    <DocumentTextIcon className="h-5 w-5 text-zinc-400" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm text-zinc-900 dark:text-white">
                      {t('project.recentActivity.tasksImported', {
                        count: currentProject.task_count,
                      })}
                    </p>
                    <p className="text-xs text-zinc-500 dark:text-zinc-400">
                      {formatDistanceToNow(
                        new Date(currentProject.created_at),
                        {
                          addSuffix: true,
                          locale: de,
                        }
                      )}
                    </p>
                  </div>
                </div>
                {(currentProject.annotation_count ?? 0) > 0 && (
                  <div className="flex items-center space-x-3">
                    <div className="flex-shrink-0">
                      <CheckCircleIcon className="h-5 w-5 text-emerald-500" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm text-zinc-900 dark:text-white">
                        {t('project.recentActivity.annotationsCompleted', {
                          count: currentProject.annotation_count,
                        })}
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
          {(isOrgProject ? (user?.is_superadmin || user?.role === 'ORG_ADMIN' || user?.role === 'CONTRIBUTOR') : user?.is_superadmin) && reportStatus && (
            <div className="rounded-lg border border-zinc-200 bg-white p-6 shadow-sm ring-1 ring-zinc-900/5 dark:border-zinc-700 dark:bg-zinc-900 dark:ring-white/10">
                <div className="mb-4 flex items-center justify-between">
                  <h2 className="text-lg font-semibold text-zinc-900 dark:text-white">
                    {t('project.report.title')}
                  </h2>
                  <DocumentChartBarIcon className="h-5 w-5 text-zinc-400" />
                </div>

                {reportStatus.exists ? (
                  <div className="space-y-4">
                    <PublicationToggle
                      projectId={projectId || ''}
                      isPublished={reportStatus.isPublished}
                      canPublish={reportStatus.canPublish}
                      canPublishReason={reportStatus.canPublishReason}
                      onToggle={(published) => {
                        setReportStatus((prev) =>
                          prev ? { ...prev, isPublished: published } : null
                        )
                        addToast(
                          published
                            ? t('project.report.publishedSuccessfully')
                            : t('project.report.unpublishedSuccessfully'),
                          'success'
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
                ) : (
                  <div className="py-4 text-center">
                    <p className="mb-3 text-sm text-zinc-500 dark:text-zinc-400">
                      {t('project.report.autoGenerated')}
                    </p>
                    <p className="text-xs text-zinc-400">
                      {t('project.report.autoGeneratedHint')}
                    </p>
                  </div>
                )}
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
          (currentProject as any)?.generation_config?.selected_configuration?.models ||
          (currentProject as any)?.llm_model_ids ||
          []
        }
        defaultSelectedModels={
          (currentProject as any)?.generation_config?.selected_configuration?.models ||
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

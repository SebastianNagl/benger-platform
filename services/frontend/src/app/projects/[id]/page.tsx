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
import { LabelConfigEditor } from '@/components/projects/LabelConfigEditor'
import { logger } from '@/lib/utils/logger'
import { PromptStructuresManager } from '@/components/projects/PromptStructuresManager'
import { PublicationToggle } from '@/components/reports/PublicationToggle'
import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { Button } from '@/components/shared/Button'
import { Card } from '@/components/shared/Card'
import { Input } from '@/components/shared/Input'
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
import { Tooltip } from '@/components/shared/Tooltip'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { useModels } from '@/hooks/useModels'
import { apiClient } from '@/lib/api/client'
import { getTemperatureConstraints, getDefaultMaxTokens } from '@/lib/modelConstraints'
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
import { useEffect, useMemo, useState } from 'react'

// Provider colors for model selection badges
const providerColors: Record<string, string> = {
  OpenAI: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200',
  Anthropic: 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200',
  Google: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
  DeepInfra: 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200',
  Grok: 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200',
  Mistral: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900 dark:text-indigo-200',
  Cohere: 'bg-teal-100 text-teal-800 dark:bg-teal-900 dark:text-teal-200',
}

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

// Reasoning/Thinking config for models that support it
interface ThinkingPreset {
  label: string
  value: number
}

interface ReasoningConfig {
  parameter: string
  type: 'select' | 'budget'  // 'select' for API values (low/medium/high), 'budget' for token budgets with presets
  values?: string[]  // For 'select' type - API values like ['low', 'medium', 'high']
  presets?: ThinkingPreset[]  // For 'budget' type - preset options with token values
  min?: number
  max?: number
  default: string | number
  label: string
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
  const [expandedEvaluation, setExpandedEvaluation] = useState(false)

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
  const [isUpdatingEvalDefaults, setIsUpdatingEvalDefaults] = useState(false)

  // Generation defaults
  const [genDefaultTemperature, setGenDefaultTemperature] = useState<number | undefined>(undefined)
  const [genDefaultMaxTokens, setGenDefaultMaxTokens] = useState<number | undefined>(undefined)
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

  // Instructions state
  const [instructions, setInstructions] = useState('')
  const [editingInstructions, setEditingInstructions] = useState(false)
  const [instructionsValue, setInstructionsValue] = useState('')

  //  settings
  const [expanded, setExpanded] = useState(false)
  const [editing, setEditing] = useState(false)
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
  })

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
      } catch (error) {
        console.error('Failed to fetch evaluation config:', error)
      }
    }

    fetchEvaluationConfig()
  }, [projectId])

  // Fetch available fields when evaluation section is expanded
  useEffect(() => {
    const fetchAvailableFields = async () => {
      if (!projectId || !expandedEvaluation) return

      try {
        // Fetch available fields
        const fields =
          await apiClient.evaluations.getAvailableEvaluationFields(projectId)
        setAvailableEvaluationFields(fields)
      } catch (error) {
        console.error('Failed to fetch available fields:', error)
      }
    }

    fetchAvailableFields()
  }, [projectId, expandedEvaluation])

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

      // Load generation defaults
      const genParams = currentProject.generation_config?.selected_configuration?.parameters || {}
      setGenDefaultTemperature(genParams.temperature)
      setGenDefaultMaxTokens(genParams.max_tokens)

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
      case 'members':
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
  const handleModelToggle = (modelId: string) => {
    const isCurrentlySelected = selectedModelIds.includes(modelId)

    if (isCurrentlySelected) {
      // Deselecting - just remove from list
      setSelectedModelIds((prev) => prev.filter((id) => id !== modelId))
    } else {
      // Selecting - add to list and pre-fill defaults if model has specific requirements
      setSelectedModelIds((prev) => [...prev, modelId])

      // Pre-fill model config from backend parameter_constraints (only if not already configured)
      if (!modelConfigs[modelId]) {
        const model = availableModels?.find(m => m.id === modelId)
        const newConfig: Record<string, any> = {}

        // Temperature defaults from constraints
        const tempConstraints = getTemperatureConstraints(model)
        newConfig.temperature = tempConstraints.default
        if (tempConstraints.fixed) {
          newConfig.temperatureFixed = true
        }

        // Max tokens default from constraints
        const defaultMaxTokens = getDefaultMaxTokens(model)
        if (defaultMaxTokens) {
          newConfig.max_tokens = defaultMaxTokens
        }

        // Reasoning defaults from backend default_config
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

      // Build the generation_config structure
      const generationConfig = currentProject.generation_config || {
        selected_configuration: {},
      }

      await updateProject(projectId, {
        generation_config: {
          ...generationConfig,
          selected_configuration: {
            ...generationConfig.selected_configuration,
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
      // Build the evaluation_config structure
      const evaluationConfig = currentProject.evaluation_config || {}

      await updateProject(projectId, {
        evaluation_config: {
          ...evaluationConfig,
          default_temperature: evalDefaultTemperature,
          default_max_tokens: evalDefaultMaxTokens,
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
      // Build the generation_config structure
      const generationConfig = currentProject.generation_config || {}
      const selectedConfiguration = generationConfig.selected_configuration || {}
      const existingParams = selectedConfiguration.parameters || {}

      await updateProject(projectId, {
        generation_config: {
          ...generationConfig,
          selected_configuration: {
            ...selectedConfiguration,
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
      await updateProject(projectId, advancedSettings)
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

  // Use server-calculated progress_percentage if available (Issue #257)
  // This properly handles multi-annotator scenarios where progress is based on
  // completed tasks (meeting min_annotations_per_task requirement) rather than raw annotation count
  const completionRate =
    currentProject.progress_percentage !== undefined
      ? Math.round(currentProject.progress_percentage)
      : (currentProject.task_count ?? 0) > 0
        ? Math.min(
            100,
            Math.round(
              ((currentProject.annotation_count ?? 0) /
                (currentProject.task_count ?? 0)) *
                100
            )
          )
        : 0

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
          <div className="mb-8 rounded-lg bg-white p-6 shadow-sm ring-1 ring-zinc-900/5 dark:bg-zinc-900 dark:ring-white/10">
            <h2 className="mb-6 text-lg font-semibold text-zinc-900 dark:text-white">
              {t('project.details.title')}
            </h2>

            <dl className="grid grid-cols-1 gap-x-4 gap-y-6 sm:grid-cols-2">
              <div>
                <dt className="text-sm font-medium text-zinc-500 dark:text-zinc-400">
                  {t('project.details.status')}
                </dt>
                <dd className="mt-1 text-sm text-zinc-900 dark:text-white">
                  <span className="inline-flex items-center rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-medium text-emerald-800 ring-1 ring-inset ring-emerald-600/20 dark:bg-emerald-400/10 dark:text-emerald-400 dark:ring-emerald-400/30">
                    {t('project.details.active')}
                  </span>
                </dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-zinc-500 dark:text-zinc-400">
                  {t('project.details.createdBy')}
                </dt>
                <dd className="mt-1 text-sm text-zinc-900 dark:text-white">
                  {currentProject.created_by_name ||
                    t('project.details.unknown')}
                </dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-zinc-500 dark:text-zinc-400">
                  {t('project.details.projectId')}
                </dt>
                <dd className="mt-1 font-mono text-sm text-zinc-900 dark:text-white">
                  {currentProject.id}
                </dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-zinc-500 dark:text-zinc-400">
                  {t('project.details.created')}
                </dt>
                <dd className="mt-1 text-sm text-zinc-900 dark:text-white">
                  {new Date(currentProject.created_at).toLocaleDateString()}{' '}
                  {t('project.details.at')}{' '}
                  {new Date(currentProject.created_at).toLocaleTimeString()}
                </dd>
              </div>
              {currentProject.updated_at && (
                <div>
                  <dt className="text-sm font-medium text-zinc-500 dark:text-zinc-400">
                    {t('project.details.lastUpdated')}
                  </dt>
                  <dd className="mt-1 text-sm text-zinc-900 dark:text-white">
                    {new Date(currentProject.updated_at).toLocaleDateString()}{' '}
                    {t('project.details.at')}{' '}
                    {new Date(currentProject.updated_at).toLocaleTimeString()}
                  </dd>
                </div>
              )}
              <div>
                <dt className="text-sm font-medium text-zinc-500 dark:text-zinc-400">
                  {t('project.details.organizations')}
                </dt>
                <dd className="mt-1 text-sm text-zinc-900 dark:text-white">
                  <div className="flex items-center justify-between">
                    <div className="flex flex-wrap gap-2">
                      {currentProject.organizations &&
                      currentProject.organizations.length > 0 ? (
                        currentProject.organizations.map((org, index) => (
                          <span
                            key={org.id}
                            className="inline-flex items-center rounded-md bg-emerald-50 px-2 py-1 text-xs font-medium text-emerald-700 dark:bg-emerald-400/10 dark:text-emerald-400"
                          >
                            {org.name}
                          </span>
                        ))
                      ) : (
                        <span className="text-zinc-500 dark:text-zinc-400">
                          {t('project.details.noOrganizations')}
                        </span>
                      )}
                    </div>
                  </div>
                </dd>
              </div>
            </dl>
          </div>

          {/* Annotation Instructions Section */}
          <div className="mb-8 rounded-lg bg-white p-6 shadow-sm ring-1 ring-zinc-900/5 dark:bg-zinc-900 dark:ring-white/10">
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
              {canEditProject() &&
                !editingInstructions &&
                expandedInstructions && (
                  <Button
                    onClick={handleStartEditInstructions}
                    variant="outline"
                    className="text-sm"
                  >
                    {t('project.annotationInstructions.editInstructions')}
                  </Button>
                )}
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
                    <div className="flex items-center space-x-3">
                      <Button
                        onClick={handleSaveInstructions}
                        disabled={isUpdating}
                        className="text-sm"
                      >
                        {isUpdating
                          ? t('project.editing.saving')
                          : t(
                              'project.annotationInstructions.saveInstructions'
                            )}
                      </Button>
                      <Button
                        onClick={handleCancelEditInstructions}
                        variant="outline"
                        disabled={isUpdating}
                        className="text-sm"
                      >
                        {t('project.editing.cancel')}
                      </Button>
                    </div>
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
          <div className="mb-8 rounded-lg bg-white p-6 shadow-sm ring-1 ring-zinc-900/5 dark:bg-zinc-900 dark:ring-white/10">
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
              {expandedConfig && canEditProject() && !showConfigEditor && (
                <Button
                  onClick={() => setShowConfigEditor(true)}
                  variant="outline"
                  className="text-sm"
                >
                  {t('project.labelConfiguration.editConfiguration')}
                </Button>
              )}
            </div>

            {expandedConfig && (
              <>
                {showConfigEditor ? (
                  <LabelConfigEditor
                    initialConfig={currentProject.label_config || ''}
                    onSave={handleSaveLabelConfig}
                    onCancel={() => setShowConfigEditor(false)}
                    projectId={currentProject.id}
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

          {/* Model Selection Section */}
          <div className="mb-8 rounded-lg bg-white p-6 shadow-sm ring-1 ring-zinc-900/5 dark:bg-zinc-900 dark:ring-white/10">
            {canEditProject() ? (
            <>
            <div className="mb-6 flex items-center justify-between">
              <button
                onClick={() => setExpandedModels(!expandedModels)}
                className="flex items-center space-x-3 text-left"
              >
                <h2 className="text-lg font-semibold text-zinc-900 dark:text-white">
                  {t('project.modelSelection.title')}
                </h2>
                {!expandedModels && (
                  <span className="rounded-md bg-zinc-100 px-2 py-1 text-sm leading-tight text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400">
                    {modelsLoading
                      ? t('project.modelSelection.loading')
                      : modelsError
                        ? t('project.modelSelection.errorLoading')
                        : sortedModels
                          ? t('project.modelSelection.selectedCount', {
                              selected: selectedModelIds.length,
                              total: sortedModels.length,
                            })
                          : t('project.modelSelection.noModelsAvailable')}
                  </span>
                )}
                <svg
                  className={`h-5 w-5 flex-shrink-0 text-zinc-400 transition-transform ${expandedModels ? 'rotate-90 transform' : ''}`}
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
              {expandedModels &&
                canEditProject() &&
                sortedModels &&
                sortedModels.length > 0 && (
                  <Button
                    onClick={handleSaveModels}
                    disabled={isUpdatingModels}
                    className="text-sm"
                  >
                    {isUpdatingModels
                      ? t('project.editing.saving')
                      : t('project.modelSelection.saveSelection')}
                  </Button>
                )}
            </div>

            {expandedModels && (
              <>
                {/* Generation Defaults */}
                {canEditProject() && (
                  <div className="mb-6 rounded-lg bg-zinc-50 p-4 dark:bg-zinc-800/50">
                    <div className="flex items-center justify-between">
                      <div>
                        <h4 className="text-sm font-medium text-zinc-900 dark:text-white">
                          {t('project.generationDefaults.title')}
                        </h4>
                        <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                          {t('project.generationDefaults.description')}
                        </p>
                      </div>
                      <Button
                        onClick={handleSaveGenDefaults}
                        disabled={isUpdatingGenDefaults}
                        size="sm"
                        variant="outline"
                      >
                        {isUpdatingGenDefaults
                          ? t('project.editing.saving')
                          : t('project.generationDefaults.save')}
                      </Button>
                    </div>
                    <div className="mt-4 grid grid-cols-2 gap-4">
                      <div>
                        <label className="block text-xs font-medium text-zinc-600 dark:text-zinc-400">
                          {t('project.generationDefaults.defaultTemperature')}
                        </label>
                        <input
                          type="number"
                          min={0}
                          max={2}
                          step={0.1}
                          value={genDefaultTemperature ?? 0}
                          placeholder="0.0"
                          onChange={(e) =>
                            setGenDefaultTemperature(
                              e.target.value ? parseFloat(e.target.value) : undefined
                            )
                          }
                          className="mt-1 h-8 w-full rounded-md border border-zinc-300 px-2 text-sm dark:border-zinc-700 dark:bg-zinc-800"
                        />
                        <p className="mt-1 text-xs text-zinc-400 dark:text-zinc-500">
                          {t('project.generationDefaults.temperatureHelp')}
                        </p>
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-zinc-600 dark:text-zinc-400">
                          {t('project.generationDefaults.defaultMaxTokens')}
                        </label>
                        <input
                          type="number"
                          min={100}
                          max={128000}
                          step={100}
                          value={genDefaultMaxTokens ?? 4000}
                          placeholder="4000"
                          onChange={(e) =>
                            setGenDefaultMaxTokens(
                              e.target.value ? parseInt(e.target.value) : undefined
                            )
                          }
                          className="mt-1 h-8 w-full rounded-md border border-zinc-300 px-2 text-sm dark:border-zinc-700 dark:bg-zinc-800"
                        />
                        <p className="mt-1 text-xs text-zinc-400 dark:text-zinc-500">
                          {t('project.generationDefaults.maxTokensHelp')}
                        </p>
                      </div>
                    </div>
                  </div>
                )}

                {modelsLoading ? (
                  <div className="py-6 text-center">
                    <p className="text-sm text-zinc-500 dark:text-zinc-400">
                      {t('project.modelSelection.loadingModels')}
                    </p>
                  </div>
                ) : modelsError ? (
                  <div className="py-6 text-center">
                    <p className="text-sm text-red-600 dark:text-red-400">
                      {modelsError.type === 'NO_API_KEYS'
                        ? t('project.modelSelection.noApiKeys')
                        : modelsError.message ||
                          t('project.modelSelection.failedToLoad')}
                    </p>
                    {modelsError.type === 'NO_API_KEYS' && (
                      <Button
                        onClick={() => router.push('/profile')}
                        variant="outline"
                        className="mt-3 text-sm"
                      >
                        {t('project.modelSelection.configureApiKeys')}
                      </Button>
                    )}
                  </div>
                ) : canEditProject() ? (
                  <div className="space-y-1">
                    {sortedModels && sortedModels.length > 0 ? (
                      <>
                        {sortedModels.map((model) => {
                          const isSelected = selectedModelIds.includes(model.id)
                          const reasoningConfig = getReasoningConfig(model.id)

                          return (
                            <div
                              key={model.id}
                              className={`rounded px-3 py-2 transition-colors ${
                                isSelected
                                  ? 'bg-emerald-50 dark:bg-emerald-900/20'
                                  : 'hover:bg-zinc-50 dark:hover:bg-zinc-800/50'
                              }`}
                            >
                              <div className="flex items-center justify-between">
                                <div className="flex min-w-0 flex-1 items-center space-x-3">
                                  <input
                                    id={`model-${model.id}`}
                                    type="checkbox"
                                    checked={isSelected}
                                    onChange={() => handleModelToggle(model.id)}
                                    className="h-4 w-4 flex-shrink-0 rounded border-zinc-300 bg-white text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600 dark:bg-zinc-700"
                                  />
                                  <div className="min-w-0 flex-1">
                                    <label
                                      htmlFor={`model-${model.id}`}
                                      className="block cursor-pointer truncate text-sm font-medium text-zinc-900 dark:text-white"
                                    >
                                      {model.name}
                                    </label>
                                    {model.description && (
                                      <p className="truncate text-xs text-zinc-500 dark:text-zinc-400">
                                        {model.description}
                                      </p>
                                    )}
                                  </div>
                                </div>
                                <div className="ml-3 flex flex-shrink-0 items-center space-x-2">
                                  {reasoningConfig && (
                                    <span className="inline-flex items-center rounded bg-purple-100 px-1.5 py-0.5 text-xs font-medium text-purple-700 dark:bg-purple-900/30 dark:text-purple-400">
                                      {t('project.modelSelection.thinking', 'Thinking')}
                                    </span>
                                  )}
                                  <span className={`inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium ${providerColors[model.provider] || 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200'}`}>
                                    {model.provider}
                                  </span>
                                </div>
                              </div>

                              {/* Model Config (Temperature, Max Tokens, Thinking/Reasoning) for selected models */}
                              {isSelected && (
                                <div className="mt-2 ml-7 flex flex-wrap items-center gap-3 border-t border-emerald-200 pt-2 dark:border-emerald-800">
                                  {/* Per-model Temperature */}
                                  <div className="flex items-center gap-2">
                                    <label className="text-xs text-zinc-600 dark:text-zinc-400">
                                      {t('project.modelSelection.temperature', 'Temp')}:
                                    </label>
                                    {(() => {
                                      const tc = getTemperatureConstraints(availableModels?.find(m => m.id === model.id))
                                      return (
                                        <Tooltip
                                          content={tc.fixed
                                            ? t('project.modelSelection.temperatureFixed', `This model requires temperature=${tc.fixedValue}`)
                                            : tc.reason
                                              ? `${tc.reason} (${tc.min}-${tc.max})`
                                              : t('project.modelSelection.temperatureTooltip', 'Response randomness (0=deterministic)')
                                          }
                                        >
                                          <input
                                            type="number"
                                            min={tc.min}
                                            max={tc.max}
                                            step={0.1}
                                            value={modelConfigs[model.id]?.temperature ?? ''}
                                            placeholder={tc.default.toString()}
                                            disabled={tc.fixed}
                                            onChange={(e) =>
                                              updateModelConfig(
                                                model.id,
                                                'temperature',
                                                e.target.value ? parseFloat(e.target.value) : undefined
                                              )
                                            }
                                            className={`h-7 w-16 rounded-md border border-zinc-300 px-2 text-xs dark:border-zinc-700 dark:bg-zinc-800 ${
                                              tc.fixed ? 'bg-zinc-100 dark:bg-zinc-900 cursor-not-allowed' : ''
                                            }`}
                                          />
                                        </Tooltip>
                                      )
                                    })()}
                                  </div>

                                  {/* Per-model Max Tokens */}
                                  <div className="flex items-center gap-2">
                                    <label className="text-xs text-zinc-600 dark:text-zinc-400">
                                      {t('project.modelSelection.maxTokens', 'Max Tokens')}:
                                    </label>
                                    <input
                                      type="number"
                                      min={100}
                                      max={128000}
                                      step={100}
                                      value={modelConfigs[model.id]?.max_tokens ?? ''}
                                      placeholder={getDefaultMaxTokens(availableModels?.find(m => m.id === model.id))?.toString() ?? '4000'}
                                      onChange={(e) =>
                                        updateModelConfig(
                                          model.id,
                                          'max_tokens',
                                          e.target.value ? parseInt(e.target.value) : undefined
                                        )
                                      }
                                      className="h-7 w-20 rounded-md border border-zinc-300 px-2 text-xs dark:border-zinc-700 dark:bg-zinc-800"
                                    />
                                  </div>

                                  {/* Thinking/Reasoning Config */}
                                  {reasoningConfig && (
                                    <>
                                      <div className="h-4 border-l border-zinc-300 dark:border-zinc-700" />
                                      <label className="text-xs text-zinc-600 dark:text-zinc-400">
                                        {reasoningConfig.label}:
                                      </label>
                                      {reasoningConfig.type === 'select' && (
                                        <Select
                                          value={
                                            String(modelConfigs[model.id]?.[reasoningConfig.parameter] ||
                                            reasoningConfig.default)
                                          }
                                          onValueChange={(v) =>
                                            updateModelConfig(
                                              model.id,
                                              reasoningConfig.parameter,
                                              v
                                            )
                                          }
                                          displayValue={(() => {
                                            const val = String(modelConfigs[model.id]?.[reasoningConfig.parameter] || reasoningConfig.default)
                                            return val.charAt(0).toUpperCase() + val.slice(1)
                                          })()}
                                        >
                                          <SelectTrigger className="h-7 w-auto min-w-[5rem] text-xs">
                                            <SelectValue />
                                          </SelectTrigger>
                                          <SelectContent>
                                            {reasoningConfig.values?.map((value) => (
                                              <SelectItem key={value} value={value}>
                                                {value.charAt(0).toUpperCase() + value.slice(1)}
                                              </SelectItem>
                                            ))}
                                          </SelectContent>
                                        </Select>
                                      )}
                                      {reasoningConfig.type === 'budget' && reasoningConfig.presets && (
                                        <>
                                          {(() => {
                                            const currentValue = modelConfigs[model.id]?.[reasoningConfig.parameter]
                                            const isCustomMode = modelConfigs[model.id]?.[`${reasoningConfig.parameter}_custom`] === true
                                            const valueMatchesPreset = reasoningConfig.presets?.some(p => p.value === currentValue)
                                            const showCustomInput = isCustomMode || (currentValue !== undefined && !valueMatchesPreset)

                                            return (
                                              <>
                                                <Select
                                                  value={showCustomInput ? 'custom' : (currentValue?.toString() || reasoningConfig.default.toString())}
                                                  onValueChange={(v) => {
                                                    if (v === 'custom') {
                                                      // Enable custom mode, keep current value or use default
                                                      const val = currentValue ?? reasoningConfig.default
                                                      updateModelConfig(model.id, reasoningConfig.parameter, val)
                                                      updateModelConfig(model.id, `${reasoningConfig.parameter}_custom`, true)
                                                    } else {
                                                      // Select preset, disable custom mode
                                                      updateModelConfig(model.id, reasoningConfig.parameter, parseInt(v))
                                                      updateModelConfig(model.id, `${reasoningConfig.parameter}_custom`, false)
                                                    }
                                                  }}
                                                  displayValue={(() => {
                                                    if (showCustomInput) return 'Custom'
                                                    const val = currentValue?.toString() || reasoningConfig.default.toString()
                                                    const preset = reasoningConfig.presets?.find(p => p.value.toString() === val)
                                                    return preset ? `${preset.label} (${preset.value.toLocaleString()} tokens)` : val
                                                  })()}
                                                >
                                                  <SelectTrigger className="h-7 w-auto min-w-[8rem] text-xs">
                                                    <SelectValue />
                                                  </SelectTrigger>
                                                  <SelectContent>
                                                    {reasoningConfig.presets.map((preset) => (
                                                      <SelectItem key={preset.value} value={preset.value.toString()}>
                                                        {preset.label} ({preset.value.toLocaleString()} tokens)
                                                      </SelectItem>
                                                    ))}
                                                    <SelectItem value="custom">Custom</SelectItem>
                                                  </SelectContent>
                                                </Select>
                                                {showCustomInput && (
                                                  <input
                                                    type="number"
                                                    min={reasoningConfig.min}
                                                    max={reasoningConfig.max}
                                                    value={currentValue ?? ''}
                                                    onChange={(e) =>
                                                      updateModelConfig(
                                                        model.id,
                                                        reasoningConfig.parameter,
                                                        e.target.value ? parseInt(e.target.value) : undefined
                                                      )
                                                    }
                                                    className="h-7 w-24 rounded-md border border-zinc-300 px-2 text-xs dark:border-zinc-700 dark:bg-zinc-800"
                                                  />
                                                )}
                                              </>
                                            )
                                          })()}
                                          <span className="text-xs text-zinc-400">
                                            ({reasoningConfig.min?.toLocaleString()}-{reasoningConfig.max?.toLocaleString()})
                                          </span>
                                        </>
                                      )}
                                      {/* Show default only for select type (budget type shows range instead) */}
                                      {reasoningConfig.type === 'select' && (
                                        <span className="text-xs text-zinc-400">
                                          ({t('project.modelSelection.default', 'Default')}: {String(reasoningConfig.default)})
                                        </span>
                                      )}
                                    </>
                                  )}
                                </div>
                              )}
                            </div>
                          )
                        })}
                      </>
                    ) : (
                      <div className="py-6 text-center">
                        <p className="text-sm text-zinc-500 dark:text-zinc-400">
                          {t('project.modelSelection.noModelsForProfile')}
                        </p>
                        <Button
                          onClick={() => router.push('/profile')}
                          variant="outline"
                          className="mt-3 text-sm"
                        >
                          {t('project.modelSelection.configureApiKeys')}
                        </Button>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="py-6 text-center">
                    <p className="text-sm text-zinc-500 dark:text-zinc-400">
                      {getReadOnlyMessage(t('project.modelSelection.title'))}
                    </p>
                  </div>
                )}
              </>
            )}
            </>
            ) : (
              <div className="py-6 text-center">
                <p className="text-sm text-zinc-500 dark:text-zinc-400">
                  {getReadOnlyMessage(t('project.modelSelection.title'))}
                </p>
              </div>
            )}
          </div>

          {/* Prompt Structures Section - Issue #762 */}
          <div className="mb-8 rounded-lg bg-white p-6 shadow-sm ring-1 ring-zinc-900/5 dark:bg-zinc-900 dark:ring-white/10">
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

          {/* Evaluation Configuration Section */}
          <>
            <div className="mb-8 rounded-lg bg-white p-6 shadow-sm ring-1 ring-zinc-900/5 dark:bg-zinc-900 dark:ring-white/10">
              {canEditProject() ? (
              <>
              <div className="mb-6 flex items-center justify-between">
                <button
                  onClick={() => setExpandedEvaluation(!expandedEvaluation)}
                  className="flex items-center space-x-3 text-left"
                >
                  <h2 className="text-lg font-semibold text-zinc-900 dark:text-white">
                    {t('project.evaluation.title')}
                  </h2>
                  {!expandedEvaluation && (
                    <span className="rounded-md bg-zinc-100 px-2 py-1 text-sm leading-tight text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400">
                      {(() => {
                        // Check evaluation configs first (Phase 8: N:M Field Mapping)
                        const evalConfigCount = evaluationConfigs.length
                        if (evalConfigCount > 0) {
                          return evalConfigCount === 1
                            ? t('project.evaluation.evaluationConfigSingular', { count: evalConfigCount })
                            : t('project.evaluation.evaluationConfigPlural', { count: evalConfigCount })
                        }

                        const selectedMethods =
                          currentProject.evaluation_config?.selected_methods
                        if (!selectedMethods)
                          return t('project.evaluation.notConfigured')

                        // Count fields that have at least one method selected
                        let configuredFieldsCount = 0
                        let totalMethodsSelected = 0

                        Object.keys(selectedMethods).forEach((fieldName) => {
                          const fieldMethods = selectedMethods[fieldName]
                          const automatedCount =
                            fieldMethods?.automated?.length || 0
                          const humanCount = fieldMethods?.human?.length || 0
                          const fieldTotal = automatedCount + humanCount

                          if (fieldTotal > 0) {
                            configuredFieldsCount++
                            totalMethodsSelected += fieldTotal
                          }
                        })

                        if (configuredFieldsCount === 0) {
                          return t('project.evaluation.notConfigured')
                        }

                        if (
                          configuredFieldsCount === 1 &&
                          totalMethodsSelected === 1
                        ) {
                          return t(
                            'project.evaluation.fieldConfiguredWithMethods',
                            {
                              fields: configuredFieldsCount,
                              methods: totalMethodsSelected,
                            }
                          )
                        }

                        return t(
                          'project.evaluation.fieldsConfiguredWithMethods',
                          {
                            fields: configuredFieldsCount,
                            methods: totalMethodsSelected,
                          }
                        )
                      })()}
                    </span>
                  )}
                  <svg
                    className={`h-5 w-5 flex-shrink-0 text-zinc-400 transition-transform ${expandedEvaluation ? 'rotate-90 transform' : ''}`}
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
              </div>

              {expandedEvaluation && (
                <>
                  {/* Evaluation Defaults */}
                  {canEditProject() && (
                    <div className="mb-6 rounded-lg bg-zinc-50 p-4 dark:bg-zinc-800/50">
                      <div className="flex items-center justify-between">
                        <div>
                          <h4 className="text-sm font-medium text-zinc-900 dark:text-white">
                            {t('project.evaluationDefaults.title')}
                          </h4>
                          <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                            {t('project.evaluationDefaults.description')}
                          </p>
                        </div>
                        <Button
                          onClick={handleSaveEvalDefaults}
                          disabled={isUpdatingEvalDefaults}
                          size="sm"
                          variant="outline"
                        >
                          {isUpdatingEvalDefaults
                            ? t('project.editing.saving')
                            : t('project.evaluationDefaults.save')}
                        </Button>
                      </div>
                      <div className="mt-4 grid grid-cols-2 gap-4">
                        <div>
                          <label className="block text-xs font-medium text-zinc-600 dark:text-zinc-400">
                            {t('project.evaluationDefaults.defaultTemperature')}
                          </label>
                          <input
                            type="number"
                            min={0}
                            max={2}
                            step={0.1}
                            value={evalDefaultTemperature ?? 0}
                            placeholder="0.0"
                            onChange={(e) =>
                              setEvalDefaultTemperature(
                                e.target.value ? parseFloat(e.target.value) : undefined
                              )
                            }
                            className="mt-1 h-8 w-full rounded-md border border-zinc-300 px-2 text-sm dark:border-zinc-700 dark:bg-zinc-800"
                          />
                          <p className="mt-1 text-xs text-zinc-400 dark:text-zinc-500">
                            {t('project.evaluationDefaults.temperatureHelp')}
                          </p>
                        </div>
                        <div>
                          <label className="block text-xs font-medium text-zinc-600 dark:text-zinc-400">
                            {t('project.evaluationDefaults.defaultMaxTokens')}
                          </label>
                          <input
                            type="number"
                            min={100}
                            max={16000}
                            step={100}
                            value={evalDefaultMaxTokens ?? 500}
                            placeholder="500"
                            onChange={(e) =>
                              setEvalDefaultMaxTokens(
                                e.target.value ? parseInt(e.target.value) : undefined
                              )
                            }
                            className="mt-1 h-8 w-full rounded-md border border-zinc-300 px-2 text-sm dark:border-zinc-700 dark:bg-zinc-800"
                          />
                          <p className="mt-1 text-xs text-zinc-400 dark:text-zinc-500">
                            {t('project.evaluationDefaults.maxTokensHelp')}
                          </p>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Multi-Field Evaluation Builder (Phase 8: N:M Field Mapping) */}
                  <div className="mb-6">
                    <EvaluationBuilder
                      projectId={projectId || ''}
                      availableFields={availableEvaluationFields}
                      evaluations={evaluationConfigs}
                      onEvaluationsChange={handleEvaluationConfigsChange}
                      onSave={handleEvaluationStarted}
                    />
                  </div>
                </>
              )}
              </>
              ) : (
                <div className="py-6 text-center">
                  <p className="text-sm text-zinc-500 dark:text-zinc-400">
                    {getReadOnlyMessage(t('project.evaluation.title'))}
                  </p>
                </div>
              )}
            </div>
          </>

          {/*  Settings Section */}
          <div className="mb-8 rounded-lg bg-white p-6 shadow-sm ring-1 ring-zinc-900/5 dark:bg-zinc-900 dark:ring-white/10">
            {canEditProject() ? (
            <>
            <div className="mb-6 flex items-center justify-between">
              <button
                onClick={() => setExpanded(!expanded)}
                className="flex items-center space-x-3 text-left"
              >
                <h2 className="text-lg font-semibold text-zinc-900 dark:text-white">
                  {t('project.settings.title')}
                </h2>
                {!expanded && (
                  <span className="rounded-md bg-zinc-100 px-2 py-1 text-sm leading-tight text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400">
                    {t('project.settings.mode', {
                      mode: advancedSettings.assignment_mode,
                    })}
                    ,{' '}
                    {t('project.settings.minAnnotations', {
                      count: advancedSettings.min_annotations_per_task,
                    })}
                  </span>
                )}
                <svg
                  className={`h-5 w-5 flex-shrink-0 text-zinc-400 transition-transform ${expanded ? 'rotate-90 transform' : ''}`}
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
              {expanded && canEditProject() && !editing && (
                <Button
                  onClick={() => setEditing(true)}
                  variant="outline"
                  className="text-sm"
                >
                  {t('project.settings.editSettings')}
                </Button>
              )}
            </div>

            {expanded && (
              <div className="space-y-6">
                {/* Annotation Behavior */}
                <div>
                  <h3 className="text-md mb-4 font-medium text-zinc-900 dark:text-white">
                    {t('project.settings.annotationBehavior.title')}
                  </h3>
                  <div className="space-y-4">
                    <div>
                      <Label htmlFor="maximum_annotations">
                        {t(
                          'project.settings.annotationBehavior.maxAnnotations'
                        )}
                      </Label>
                      <Select
                        value={advancedSettings.maximum_annotations.toString()}
                        onValueChange={(value: string) =>
                          setAdvancedSettings((prev) => ({
                            ...prev,
                            maximum_annotations: parseInt(value),
                          }))
                        }
                        disabled={!editing}
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="1">
                            {t(
                              'project.settings.annotationBehavior.annotations.single'
                            )}
                          </SelectItem>
                          <SelectItem value="2">
                            {t(
                              'project.settings.annotationBehavior.annotations.double'
                            )}
                          </SelectItem>
                          <SelectItem value="3">
                            {t(
                              'project.settings.annotationBehavior.annotations.triple'
                            )}
                          </SelectItem>
                          <SelectItem value="5">
                            {t(
                              'project.settings.annotationBehavior.annotations.multiple'
                            )}
                          </SelectItem>
                          <SelectItem value="10">10</SelectItem>
                          <SelectItem value="50">50</SelectItem>
                          <SelectItem value="100">100</SelectItem>
                          <SelectItem value="0">
                            {t(
                              'project.settings.annotationBehavior.annotations.unlimited',
                              'Unbegrenzt'
                            )}
                          </SelectItem>
                        </SelectContent>
                      </Select>
                      <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                        {t(
                          'project.settings.annotationBehavior.maxAnnotationsHelp'
                        )}
                      </p>
                    </div>

                    <div>
                      <Label htmlFor="min_annotations_per_task">
                        {t(
                          'project.settings.annotationBehavior.minAnnotationsForCompletion'
                        )}
                      </Label>
                      <Select
                        value={advancedSettings.min_annotations_per_task.toString()}
                        onValueChange={(value: string) =>
                          setAdvancedSettings((prev) => ({
                            ...prev,
                            min_annotations_per_task: parseInt(value),
                          }))
                        }
                        disabled={!editing}
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="1">
                            {t(
                              'project.settings.annotationBehavior.annotations.count1'
                            )}
                          </SelectItem>
                          <SelectItem value="2">
                            {t(
                              'project.settings.annotationBehavior.annotations.count2'
                            )}
                          </SelectItem>
                          <SelectItem value="3">
                            {t(
                              'project.settings.annotationBehavior.annotations.count3'
                            )}
                          </SelectItem>
                          <SelectItem value="4">
                            {t(
                              'project.settings.annotationBehavior.annotations.count4'
                            )}
                          </SelectItem>
                          <SelectItem value="5">
                            {t(
                              'project.settings.annotationBehavior.annotations.count5'
                            )}
                          </SelectItem>
                        </SelectContent>
                      </Select>
                      <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                        {t(
                          'project.settings.annotationBehavior.minAnnotationsHelp'
                        )}
                      </p>
                    </div>

                    <div>
                      <Label htmlFor="assignment_mode">
                        {t(
                          'project.settings.annotationBehavior.assignmentMode'
                        )}
                      </Label>
                      <Select
                        value={advancedSettings.assignment_mode}
                        onValueChange={(value: string) =>
                          setAdvancedSettings((prev: any) => ({
                            ...prev,
                            assignment_mode: value as
                              | 'open'
                              | 'manual'
                              | 'auto',
                          }))
                        }
                        disabled={!editing}
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="open">
                            {t(
                              'project.settings.annotationBehavior.modes.open'
                            )}
                          </SelectItem>
                          <SelectItem value="manual">
                            {t(
                              'project.settings.annotationBehavior.modes.manual'
                            )}
                          </SelectItem>
                          <SelectItem value="auto">
                            {t(
                              'project.settings.annotationBehavior.modes.auto'
                            )}
                          </SelectItem>
                        </SelectContent>
                      </Select>
                      <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                        {t(
                          'project.settings.annotationBehavior.assignmentModeHelp'
                        )}
                      </p>
                    </div>

                    <div className="flex items-center justify-between">
                      <div>
                        <Label>
                          {t('project.settings.annotationBehavior.randomizeTaskOrder', 'Randomize task order')}
                        </Label>
                        <p className="text-sm text-zinc-500 dark:text-zinc-400">
                          {t('project.settings.annotationBehavior.randomizeTaskOrderHelp', 'Each annotator sees tasks in a different random order for even annotation distribution')}
                        </p>
                      </div>
                      <input
                        type="checkbox"
                        checked={advancedSettings.randomize_task_order}
                        onChange={(e) =>
                          setAdvancedSettings((prev: any) => ({
                            ...prev,
                            randomize_task_order: e.target.checked,
                          }))
                        }
                        disabled={!editing}
                        className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
                      />
                    </div>
                  </div>
                </div>

                {/* Interface Settings */}
                <div>
                  <h3 className="text-md mb-4 font-medium text-zinc-900 dark:text-white">
                    {t('project.settings.interface.title')}
                  </h3>
                  <div className="space-y-4">
                    <div className="flex items-center justify-between">
                      <div>
                        <Label>
                          {t('project.settings.interface.showInstructions')}
                        </Label>
                        <p className="text-sm text-zinc-500 dark:text-zinc-400">
                          {t('project.settings.interface.showInstructionsHelp')}
                        </p>
                      </div>
                      <input
                        type="checkbox"
                        checked={advancedSettings.show_instruction}
                        onChange={(e) =>
                          setAdvancedSettings((prev: any) => ({
                            ...prev,
                            show_instruction: e.target.checked,
                          }))
                        }
                        disabled={!editing}
                        className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
                      />
                    </div>

                    <div className="flex items-center justify-between">
                      <div>
                        <Label>
                          {t('project.settings.interface.instructionsAlwaysVisible', { defaultValue: 'Always show instructions' })}
                        </Label>
                        <p className="text-sm text-zinc-500 dark:text-zinc-400">
                          {t('project.settings.interface.instructionsAlwaysVisibleHelp', { defaultValue: "Show instructions on every task, even if annotator clicked 'don't show again'" })}
                        </p>
                      </div>
                      <input
                        type="checkbox"
                        checked={advancedSettings.instructions_always_visible}
                        onChange={(e) =>
                          setAdvancedSettings((prev: any) => ({
                            ...prev,
                            instructions_always_visible: e.target.checked,
                          }))
                        }
                        disabled={!editing}
                        className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
                      />
                    </div>

                    <div className="flex items-center justify-between">
                      <div>
                        <Label>
                          {t('project.settings.interface.showSkipButton')}
                        </Label>
                        <p className="text-sm text-zinc-500 dark:text-zinc-400">
                          {t('project.settings.interface.showSkipButtonHelp')}
                        </p>
                      </div>
                      <input
                        type="checkbox"
                        checked={advancedSettings.show_skip_button}
                        onChange={(e) =>
                          setAdvancedSettings((prev: any) => ({
                            ...prev,
                            show_skip_button: e.target.checked,
                          }))
                        }
                        disabled={!editing}
                        className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
                      />
                    </div>

                    <div className="flex items-center justify-between">
                      <div>
                        <Label>
                          {t('project.settings.interface.requireCommentOnSkip')}
                        </Label>
                        <p className="text-sm text-zinc-500 dark:text-zinc-400">
                          {t(
                            'project.settings.interface.requireCommentOnSkipHelp'
                          )}
                        </p>
                      </div>
                      <input
                        type="checkbox"
                        checked={advancedSettings.require_comment_on_skip}
                        onChange={(e) =>
                          setAdvancedSettings((prev: any) => ({
                            ...prev,
                            require_comment_on_skip: e.target.checked,
                          }))
                        }
                        disabled={!editing}
                        className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
                      />
                    </div>

                    <div className="flex items-center justify-between">
                      <div>
                        <Label>
                          {t('project.settings.interface.skipQueue', { defaultValue: 'Skip behavior' })}
                        </Label>
                        <p className="text-sm text-zinc-500 dark:text-zinc-400">
                          {t('project.settings.interface.skipQueueHelp', { defaultValue: 'Controls what happens when an annotator skips a task' })}
                        </p>
                      </div>
                      <Select
                        value={advancedSettings.skip_queue || 'requeue_for_others'}
                        onValueChange={(v) =>
                          setAdvancedSettings((prev: any) => ({
                            ...prev,
                            skip_queue: v,
                          }))
                        }
                        disabled={!editing}
                        displayValue={
                          (advancedSettings.skip_queue || 'requeue_for_others') === 'requeue_for_me'
                            ? t('project.settings.interface.skipQueueRequeueForMe', { defaultValue: 'Re-queue for me' })
                            : (advancedSettings.skip_queue || 'requeue_for_others') === 'requeue_for_others'
                            ? t('project.settings.interface.skipQueueRequeueForOthers', { defaultValue: 'Re-queue for others' })
                            : t('project.settings.interface.skipQueueIgnoreSkipped', { defaultValue: 'Skip permanently' })
                        }
                      >
                        <SelectTrigger className="w-auto min-w-[10rem]">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="requeue_for_me">
                            {t('project.settings.interface.skipQueueRequeueForMe', { defaultValue: 'Re-queue for me' })}
                          </SelectItem>
                          <SelectItem value="requeue_for_others">
                            {t('project.settings.interface.skipQueueRequeueForOthers', { defaultValue: 'Re-queue for others' })}
                          </SelectItem>
                          <SelectItem value="ignore_skipped">
                            {t('project.settings.interface.skipQueueIgnoreSkipped', { defaultValue: 'Skip permanently' })}
                          </SelectItem>
                        </SelectContent>
                      </Select>
                    </div>

                    <div className="flex items-center justify-between">
                      <div>
                        <Label>
                          {t('project.settings.interface.showSubmitButton')}
                        </Label>
                        <p className="text-sm text-zinc-500 dark:text-zinc-400">
                          {t('project.settings.interface.showSubmitButtonHelp')}
                        </p>
                      </div>
                      <input
                        type="checkbox"
                        checked={advancedSettings.show_submit_button}
                        onChange={(e) =>
                          setAdvancedSettings((prev: any) => ({
                            ...prev,
                            show_submit_button: e.target.checked,
                          }))
                        }
                        disabled={!editing}
                        className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
                      />
                    </div>

                    <div className="flex items-center justify-between">
                      <div>
                        <Label>
                          {t('project.settings.interface.requireConfirmBeforeSubmit', { defaultValue: 'Require confirmation before submit' })}
                        </Label>
                        <p className="text-sm text-zinc-500 dark:text-zinc-400">
                          {t('project.settings.interface.requireConfirmBeforeSubmitHelp', { defaultValue: 'Annotators must check a confirmation checkbox before submitting.' })}
                        </p>
                      </div>
                      <input
                        type="checkbox"
                        checked={advancedSettings.require_confirm_before_submit}
                        onChange={(e) =>
                          setAdvancedSettings((prev: any) => ({
                            ...prev,
                            require_confirm_before_submit: e.target.checked,
                          }))
                        }
                        disabled={!editing}
                        className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
                      />
                    </div>

                  </div>
                </div>

                {/* Post-Annotation Questionnaire (Issue #1208) */}
                <div>
                  <h3 className="text-md mb-4 font-medium text-zinc-900 dark:text-white">
                    {t('project.settings.questionnaireTitle', { defaultValue: 'Post-Annotation Questionnaire' })}
                  </h3>
                  <div className="space-y-4">
                    <div className="flex items-center justify-between">
                      <div>
                        <Label>
                          {t('project.settings.questionnaireEnabled', { defaultValue: 'Enable Questionnaire' })}
                        </Label>
                        <p className="text-sm text-zinc-500 dark:text-zinc-400">
                          {t('project.settings.questionnaireEnabledDescription', { defaultValue: 'Show a feedback form after each annotation submission' })}
                        </p>
                      </div>
                      <input
                        type="checkbox"
                        checked={advancedSettings.questionnaire_enabled}
                        onChange={(e) =>
                          setAdvancedSettings((prev: any) => ({
                            ...prev,
                            questionnaire_enabled: e.target.checked,
                          }))
                        }
                        disabled={!editing}
                        className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
                      />
                    </div>

                    {advancedSettings.questionnaire_enabled && (
                      <div className="space-y-3 border-t border-zinc-200 pt-3 dark:border-zinc-700">
                        <div>
                          <Label>
                            {t('project.settings.questionnaireTemplate', { defaultValue: 'Template' })}
                          </Label>
                          <Select
                            value=""
                            onValueChange={(v) => {
                              const templates: Record<string, string> = {
                                confidence_difficulty: `<View>
  <Header value="Post-Annotation Feedback"/>
  <Header value="How confident are you in your annotation?" size="4"/>
  <Rating name="confidence" toName="confidence" maxRating="5" required="true"/>
  <Header value="How difficult was this task?" size="4"/>
  <Rating name="difficulty" toName="difficulty" maxRating="5" required="true"/>
</View>`,
                                extended: `<View>
  <Header value="Post-Annotation Feedback"/>
  <Header value="How confident are you in your annotation?" size="4"/>
  <Rating name="confidence" toName="confidence" maxRating="5" required="true"/>
  <Header value="How difficult was this task?" size="4"/>
  <Rating name="difficulty" toName="difficulty" maxRating="5" required="true"/>
  <Header value="How clear were the annotation guidelines?" size="4"/>
  <Choices name="guideline_clarity" toName="guideline_clarity" choice="single" layout="horizontal" required="true">
    <Choice value="Very Clear"/>
    <Choice value="Clear"/>
    <Choice value="Neutral"/>
    <Choice value="Unclear"/>
    <Choice value="Very Unclear"/>
  </Choices>
  <Header value="Additional comments (optional)" size="4"/>
  <TextArea name="comments" toName="comments" rows="3" placeholder="Note any edge cases, ambiguities, or concerns..."/>
</View>`,
                                utaut_study: `<View>
  <Header value="Post-Annotations-Fragebogen" level="3"/>

  <Header value="Allgemeine Fragen" level="4"/>
  <Likert name="difficulty" toName="difficulty" min="1" max="7" required="true" label="Es fiel mir leicht die Aufgabe zu lösen."/>
  <Likert name="responsibility" toName="responsibility" min="1" max="7" required="true" label="Ich fühle mich verantwortlich für das von mir eingereichte Ergebnis."/>

  <Header value="Fragen zur KI-Unterstützung (nur beantworten, wenn Sie in der KI-Gruppe waren)" level="4"/>
  <Likert name="ai_adequate" toName="ai_adequate" min="1" max="7" label="Der Output der KI war auf Anhieb adäquat."/>
  <Likert name="ai_reviewed" toName="ai_reviewed" min="1" max="7" label="Ich habe den Output der KI überprüft."/>
  <Likert name="utaut_pe" toName="utaut_pe" min="1" max="7" label="Ich würde die KI in meiner Arbeit/meinem Studium als nützlich empfinden."/>
  <Likert name="utaut_ee" toName="utaut_ee" min="1" max="7" label="Ich empfinde die KI als einfach zu nutzen."/>
  <Likert name="utaut_att1" toName="utaut_att1" min="1" max="7" label="Die Nutzung der KI ist eine gute Idee."/>
  <Likert name="utaut_att2" toName="utaut_att2" min="1" max="7" label="Die Arbeit mit der KI macht Spaß."/>
  <Likert name="utaut_att3" toName="utaut_att3" min="1" max="7" label="Ich arbeite gerne mit der KI."/>

  <Header value="Anteil an der Fallbearbeitung (nur beantworten, wenn Sie in der KI-Gruppe waren)" level="4"/>
  <Number name="human_share" toName="human_share" min="0" max="100" label="x Prozent der Fallbearbeitung gehen auf mich zurück." hint="Wert zwischen 0 und 100"/>
  <Number name="ai_share" toName="ai_share" min="0" max="100" label="y Prozent der Fallbearbeitung gehen auf die KI zurück." hint="Wert zwischen 0 und 100"/>

  <Header value="Frage ohne KI (nur beantworten, wenn Sie NICHT in der KI-Gruppe waren)" level="4"/>
  <Likert name="desired_ai" toName="desired_ai" min="1" max="7" label="Ich hätte mir die KI für die Bearbeitung dieser Aufgabe gewünscht."/>
</View>`,
                              }
                              if (v in templates) {
                                setAdvancedSettings((prev: any) => ({
                                  ...prev,
                                  questionnaire_config: templates[v],
                                }))
                              }
                            }}
                            disabled={!editing}
                          >
                            <SelectTrigger className="mt-1">
                              <SelectValue placeholder={t('project.settings.questionnaireSelectTemplate', { defaultValue: 'Select a template...' })} />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="confidence_difficulty">
                                {t('project.settings.questionnaireTemplateConfidence', { defaultValue: 'Confidence & Difficulty (2 items)' })}
                              </SelectItem>
                              <SelectItem value="extended">
                                {t('project.settings.questionnaireTemplateExtended', { defaultValue: 'Extended Feedback (4 items)' })}
                              </SelectItem>
                              <SelectItem value="utaut_study">
                                {t('project.settings.questionnaireTemplateUtaut', { defaultValue: 'UTAUT Study (12 items, Likert 1-7)' })}
                              </SelectItem>
                            </SelectContent>
                          </Select>
                        </div>

                        <div>
                          <Label>
                            {t('project.settings.questionnaireConfig', { defaultValue: 'Questionnaire Config (Label Studio XML)' })}
                          </Label>
                          <textarea
                            value={advancedSettings.questionnaire_config}
                            onChange={(e) =>
                              setAdvancedSettings((prev: any) => ({
                                ...prev,
                                questionnaire_config: e.target.value,
                              }))
                            }
                            disabled={!editing}
                            rows={10}
                            className="mt-1 block w-full rounded-md border border-zinc-300 bg-white px-3 py-2 font-mono text-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500 dark:border-zinc-600 dark:bg-zinc-800 dark:text-white"
                            placeholder={`<View>\n  <Header value="Post-Annotation Feedback"/>\n  <Rating name="confidence" toName="confidence" maxRating="5" required="true"/>\n</View>`}
                          />
                        </div>
                      </div>
                    )}
                  </div>
                </div>


                {/* Save/Cancel buttons when editing */}
                {editing && (
                  <div className="flex items-center justify-end space-x-3 border-t border-zinc-200 pt-4 dark:border-zinc-700">
                    <Button
                      onClick={() => {
                        setEditing(false)
                        // Reset to current project values
                        setAdvancedSettings({
                          show_instruction:
                            currentProject?.show_instruction !== false,
                          instructions_always_visible:
                            currentProject?.instructions_always_visible || false,
                          show_skip_button:
                            currentProject?.show_skip_button !== false,
                          show_submit_button:
                            currentProject?.show_submit_button !== false,
                          require_comment_on_skip:
                            currentProject?.require_comment_on_skip || false,
                          require_confirm_before_submit:
                            currentProject?.require_confirm_before_submit || false,
                          skip_queue:
                            currentProject?.skip_queue || 'requeue_for_others',
                          questionnaire_enabled:
                            currentProject?.questionnaire_enabled || false,
                          questionnaire_config:
                            currentProject?.questionnaire_config || '',
                          maximum_annotations:
                            currentProject?.maximum_annotations ?? 1,
                          min_annotations_per_task:
                            currentProject?.min_annotations_per_task || 1,
                          assignment_mode:
                            currentProject?.assignment_mode || 'open',
                          randomize_task_order:
                            currentProject?.randomize_task_order || false,
                        })
                      }}
                      variant="outline"
                      disabled={isUpdating}
                      className="text-sm"
                    >
                      {t('project.editing.cancel')}
                    </Button>
                    <Button
                      onClick={handleSaveSettings}
                      disabled={isUpdating}
                      className="text-sm"
                    >
                      {isUpdating
                        ? t('project.editing.saving')
                        : t('project.settings.saveSettings')}
                    </Button>
                  </div>
                )}
              </div>
            )}
            </>
            ) : (
              <div className="py-6 text-center">
                <p className="text-sm text-zinc-500 dark:text-zinc-400">
                  {getReadOnlyMessage(t('project.settings.title'))}
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Sidebar */}
        <div className="space-y-6">
          {/* Quick Actions */}
          <div className="rounded-lg border border-zinc-200 bg-white p-6 shadow-sm ring-1 ring-zinc-900/5 dark:border-zinc-700 dark:bg-zinc-900 dark:ring-white/10">
            <h2 className="mb-6 text-lg font-semibold text-zinc-900 dark:text-white">
              {t('project.quickActions.title')}
            </h2>
            <div className="space-y-3">
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

              {canSeeQuickAction('members') && (
                <Button
                  href={
                    projectId ? `/projects/${projectId}/members` : '/projects'
                  }
                  variant="outline"
                  className="w-full"
                >
                  {t('project.quickActions.members')}
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
              <div className="flex justify-between">
                <dt className="text-sm text-zinc-500 dark:text-zinc-400">
                  {t('project.statistics.annotations')}
                </dt>
                <dd className="text-sm font-medium text-zinc-900 dark:text-white">
                  {currentProject.annotation_count}
                </dd>
              </div>
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
    </div>
  )
}

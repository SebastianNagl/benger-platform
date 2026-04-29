/**
 * Evaluations API client
 * Handles evaluation, model, and data-related operations
 */

import { BaseApiClient } from './base'
import {
  AddPromptsResponse,
  AnnotationStatistics,
  EvaluationResult,
  EvaluationType,
  HumanEvaluationConfigCreate,
  HumanEvaluationConfigResponse,
  HumanEvaluationResultSummary,
  HumanEvaluationSetupResponse,
  LLMModel,
  LLMModelResponse,
  ProjectType,
  SyntheticDataGenerationHistory,
  SyntheticDataGenerationRequest,
  SyntheticDataGenerationResponse,
  TaskData,
  UploadResponse,
  UploadedDataResponse,
} from './types'

export class EvaluationsClient extends BaseApiClient {
  // Dashboard statistics
  async getDashboardStats(): Promise<{
    project_count: number
    task_count: number
    annotation_count: number
    projects_with_generations: number
    projects_with_evaluations: number
  }> {
    return this.request('/dashboard/stats')
  }

  async getEvaluations(): Promise<EvaluationResult[]> {
    return this.request('/evaluations')
  }

  async getEvaluationStatus(evaluationId: string): Promise<{
    id: string
    status: string
    message?: string
    progress?: number
  }> {
    return this.request(`/evaluation/status/${evaluationId}`)
  }

  // Model operations
  async getModels(): Promise<LLMModel[]> {
    return this.request('/models')
  }

  async getLLMModels(): Promise<LLMModelResponse[]> {
    return this.request('/llm-models')
  }

  async getLLMModel(id: string): Promise<LLMModelResponse> {
    return this.request(`/llm-models/${id}`)
  }

  // Task evaluation configuration - REMOVED
  // These endpoints were removed as part of the Task→Project migration.
  // The backend no longer supports task-evaluation-configs.

  // Generation status endpoint
  async getGenerationStatus(generationId: string): Promise<{
    id: string
    status: string
    task_id: string
    model_id: string
    responses_generated: number
    error_message?: string
    created_at: string
    started_at?: string
    completed_at?: string
  }> {
    return await this.request(`/generation/status/${generationId}`, {
      method: 'GET',
    })
  }

  // Get recent generation statuses for a task
  async getTaskGenerationStatuses(taskId: string): Promise<
    {
      id: string
      status: string
      task_id: string
      model_id: string
      responses_generated: number
      error_message?: string
      created_at: string
      started_at?: string
      completed_at?: string
    }[]
  > {
    return await this.request(`/tasks/${taskId}/generation-statuses`, {
      method: 'GET',
    })
  }

  // Get generation result for a specific task-model combination
  async getGenerationResult(
    taskId: string,
    modelId: string,
    structureKey?: string,
    includeHistory?: boolean
  ): Promise<{
    task_id: string
    model_id: string
    results: Array<{
      task_id: string
      model_id: string
      generation_id: string
      status: string
      result?: Record<string, any>
      generated_at?: string
      generation_time_seconds?: number
      prompt_used?: string
      parameters?: Record<string, any>
      error_message?: string
      structure_key?: string
      created_by?: string
      created_by_name?: string
    }>
  }> {
    const params = new URLSearchParams({
      task_id: taskId,
      model_id: modelId,
    })
    if (structureKey) {
      params.append('structure_key', structureKey)
    }
    if (includeHistory) {
      params.append('include_history', 'true')
    }
    return await this.request(
      `/generation/generation-result?${params.toString()}`,
      { method: 'GET' }
    )
  }

  // Get per-task evaluation results for a task-model combination
  async getTaskEvaluation(
    taskId: string,
    modelId: string,
    includeHistory: boolean = true,
  ): Promise<{
    task_id: string
    model_id: string
    results: Array<{
      id: string
      evaluation_id: string
      field_name: string
      answer_type: string
      ground_truth: any
      prediction: any
      metrics: Record<string, any>
      passed: boolean
      confidence_score?: number
      error_message?: string
      processing_time_ms?: number
      created_at?: string
      evaluation_context?: {
        evaluation_type: string
        status: string
        eval_metadata?: Record<string, any>
      }
    }>
    total_count: number
    message?: string
  }> {
    const params = new URLSearchParams({
      task_id: taskId,
      model_id: modelId,
    })
    if (!includeHistory) {
      params.append('include_history', 'false')
    }
    return await this.request(
      `/evaluations/sample-result?${params.toString()}`,
      { method: 'GET' }
    )
  }

  // Task types and evaluation types
  async getTaskTypes(): Promise<ProjectType[]> {
    return this.request('/task-types')
  }

  async getTaskType(id: string): Promise<ProjectType> {
    return this.request(`/task-types/${id}`)
  }

  async getEvaluationTypes(
    taskTypeId?: string,
    category?: string
  ): Promise<EvaluationType[]> {
    const params = new URLSearchParams()
    if (taskTypeId) params.append('task_type_id', taskTypeId)
    if (category) params.append('category', category)
    const endpoint = params.toString()
      ? `/evaluation-types?${params.toString()}`
      : '/evaluation-types'
    return this.request(endpoint)
  }

  async getEvaluationType(id: string): Promise<EvaluationType> {
    return this.request(`/evaluation-types/${id}`)
  }

  // Prompts removed in Issue #759 - use generation_structure in project settings instead

  // Data operations -  to support both questions and prompts
  async uploadData(
    file: File,
    taskId: string,
    description?: string
  ): Promise<UploadResponse> {
    try {
      // Validate inputs
      if (!file) {
        throw new Error('File is required for upload')
      }
      if (!taskId) {
        throw new Error('Task ID is required for upload')
      }

      // Parse the file content
      let fileContent: string

      // Handle both modern browsers and test environments
      if (typeof file.text === 'function') {
        fileContent = await file.text()
      } else {
        // Fallback for environments that don't support File.text()
        fileContent = await new Promise((resolve, reject) => {
          const reader = new FileReader()
          reader.onload = () => resolve(reader.result as string)
          reader.onerror = (error) =>
            reject(new Error('Failed to read file: ' + error))
          reader.readAsText(file)
        })
      }

      // Validate file content
      if (!fileContent.trim()) {
        throw new Error('File is empty or contains no valid content')
      }

      let data: any[]
      try {
        data = JSON.parse(fileContent)
      } catch (parseError) {
        throw new Error('Invalid JSON format in file')
      }

      // Validate data format
      if (!Array.isArray(data)) {
        throw new Error('File must contain an array of items')
      }

      if (data.length === 0) {
        throw new Error('File contains no items')
      }

      // Auto-detect content type based on structure
      const firstItem = data[0]
      let contentType: 'questions' | 'prompts'

      if (firstItem.question !== undefined && firstItem.answer !== undefined) {
        contentType = 'questions'
      } else if (firstItem.prompt !== undefined) {
        contentType = 'prompts'
      } else {
        throw new Error(
          'Unknown content type - file must contain questions (with "question" and "answer" fields) or prompts (with "prompt" field)'
        )
      }

      if (contentType === 'questions') {
        // Transform questions to the format expected by add-questions endpoint
        const transformedQuestions = data.map((q: any, index: number) => {
          try {
            // Extract the actual question data from the wrapper
            if (q.question_data) {
              return q.question_data
            } else if (q.data) {
              return q.data
            } else {
              return q
            }
          } catch (transformError) {
            throw new Error(
              `Invalid question format at index ${index}: ${transformError}`
            )
          }
        })

        // Use the add-questions endpoint for question data
        const response = await this.request(`/tasks/${taskId}/add-questions`, {
          method: 'POST',
          body: JSON.stringify({ questions: transformedQuestions }),
        })

        // Validate response
        if (!response) {
          throw new Error('No response received from server')
        }

        // Transform response to match expected UploadResponse format
        return {
          message: response.message || 'Questions uploaded successfully',
          data_id: taskId,
          task_id: taskId,
          status: response.success !== false ? 'success' : 'error',
          uploaded_items: response.added_count || transformedQuestions.length,
        }
      } else {
        // Handle prompts
        const transformedPrompts = data.map((p: any, index: number) => {
          try {
            return {
              prompt: p.prompt,
              expected_output: p.expected_output,
              metadata: p.metadata || {},
            }
          } catch (transformError) {
            throw new Error(
              `Invalid prompt format at index ${index}: ${transformError}`
            )
          }
        })

        // Use the add-prompts endpoint for prompt data
        const response = await this.addPromptsToTask(taskId, transformedPrompts)

        // Transform response to match expected UploadResponse format
        return {
          message: response.message || 'Prompts uploaded successfully',
          data_id: taskId,
          task_id: taskId,
          status: response.success ? 'success' : 'error',
          uploaded_items: response.added_count || transformedPrompts.length,
        }
      }
    } catch (error) {
      //  error handling with specific error types
      if (error instanceof Error) {
        // Re-throw with more context
        throw new Error(`Data upload failed: ${error.message}`)
      } else {
        throw new Error('Data upload failed: Unknown error occurred')
      }
    }
  }

  // Import Universal Template (creates task + imports data)
  async importUniversalTemplate(file: File): Promise<any> {
    const formData = new FormData()
    formData.append('file', file)

    return this.request('/import', {
      method: 'POST',
      body: formData,
    })
  }

  async getUploadedData(): Promise<UploadedDataResponse[]> {
    return this.request('/uploaded-data')
  }

  async deleteUploadedData(dataId: string): Promise<void> {
    return this.request(`/uploaded-data/${dataId}`, {
      method: 'DELETE',
    })
  }

  async getProjects() {
    return this.request('/projects')
  }

  async getProject(id: number) {
    return this.request(`/projects/${id}`)
  }

  async getProjectTasks(projectId: string): Promise<TaskData[]> {
    // NO FALLBACK - Errors must be visible for scientific rigor
    const response = await this.request(`/projects/${projectId}/tasks`)
    return response?.results || []
  }

  async getTaskCompletionStats(
    taskId: string
  ): Promise<{ completed: number; total: number; completionRate: number }> {
    // NO FALLBACK - Errors must be visible for scientific rigor
    // Try dedicated endpoint first, fall back to task-based calculation (but not silent zeros)
    try {
      const stats = await this.request(`/projects/${taskId}/completion-stats`)
      return {
        completed: stats.completed,
        total: stats.total,
        completionRate: stats.completion_rate,
      }
    } catch (statsError) {
      // If dedicated endpoint fails, calculate from tasks (but still propagate errors)
      const tasks = await this.getProjectTasks(taskId)
      const completed = tasks.filter((task) => task.is_labeled).length
      const total = tasks.length
      const completionRate =
        total > 0 ? Math.round((completed / total) * 100) : 0
      return { completed, total, completionRate }
    }
  }

  // Synthetic data generation
  async generateSyntheticData(
    request: SyntheticDataGenerationRequest
  ): Promise<SyntheticDataGenerationResponse> {
    return this.request('/synthetic-data/generate', {
      method: 'POST',
      body: JSON.stringify(request),
    })
  }

  async getSyntheticDataGenerations(): Promise<
    SyntheticDataGenerationHistory[]
  > {
    return this.request('/synthetic-data/generations')
  }

  // Metrics support
  async getSupportedMetrics(taskType?: string): Promise<{
    status: string
    metrics?: string[]
    task_type?: string
    supported_metrics?: string[]
  }> {
    const endpoint = taskType
      ? `/supported-metrics?task_type=${taskType}`
      : '/supported-metrics'
    return this.request(endpoint)
  }

  // NEW: LLM Interactions Dashboard endpoints
  async getTaskData(taskId: string): Promise<{
    tasks: Array<{
      id: number
      question: string
      prompts: string
      case_data: any
      reference_answers: string[]
      human_annotators: Record<
        string,
        {
          name: string
          answers: string[]
          reasoning: string
          choices: string[]
        }
      >
    }>
    error?: string // For development error handling
    project_id?: string
    attempts?: number
  }> {
    return this.request(`/tasks/${taskId}/data`)
  }

  async getTaskResponses(taskId: string): Promise<{
    responses: Array<{
      id: string
      model_id: number
      task_data_id?: number
      response_text: string
      prompt_id: string
      prompt_name: string
      prompt_type: string
      created_at: string
    }>
  }> {
    return this.request(`/tasks/${taskId}/responses`)
  }

  async getTaskEvaluations(taskId: string): Promise<{
    evaluations: Array<{
      id: string
      model_id: number
      task_data_id?: number
      evaluation_result: any
      created_at: string
    }>
  }> {
    return this.request(`/tasks/${taskId}/evaluations`)
  }

  async getAnnotationOverview(taskId: string): Promise<AnnotationStatistics> {
    return this.request(`/tasks/${taskId}/annotation-overview`)
  }

  // Consolidated task data endpoint for unified table view
  async getConsolidatedTaskData(taskId: string): Promise<{
    rows: Array<{
      id: number
      question: string
      reference_answers: string[]
      context?: string
      userAnnotations: Record<string, any>
      modelResponses: Record<string, any>
      modelEvaluations: Record<string, any>
    }>
    users: Array<{ id: string; name?: string; email: string }>
    models: Array<{ id: string; name: string }>
    evaluationMethods: Array<{ id: string; name: string }>
    totalCount: number
  }> {
    return this.request(`/tasks/${taskId}/consolidated-data`)
  }

  // User API Keys Management
  async getUserApiKeys(): Promise<{
    api_key_status: {
      openai: boolean
      anthropic: boolean
      google: boolean
      deepinfra: boolean
      grok: boolean
      mistral: boolean
      cohere: boolean
    }
    available_providers: string[]
  }> {
    return this.request('/users/api-keys/status')
  }

  async setUserApiKey(provider: string, apiKey: string): Promise<void> {
    return this.request(`/users/api-keys/${provider}`, {
      method: 'POST',
      body: JSON.stringify({ api_key: apiKey }),
    })
  }

  async removeUserApiKey(provider: string): Promise<void> {
    return this.request(`/users/api-keys/${provider}`, {
      method: 'DELETE',
    })
  }

  async testUserApiKey(
    provider: string,
    apiKey: string
  ): Promise<{
    status: 'success' | 'error'
    message: string
  }> {
    return this.request(`/users/api-keys/${provider}/test`, {
      method: 'POST',
      body: JSON.stringify({ api_key: apiKey }),
    })
  }

  async testSavedUserApiKey(provider: string): Promise<{
    status: 'success' | 'error'
    message: string
  }> {
    return this.request(`/users/api-keys/${provider}/test-saved`, {
      method: 'POST',
    })
  }

  async getAvailableModels(): Promise<
    Array<{
      id: string
      name: string
      description: string
      provider: string
      model_type: string
      capabilities: string[]
      config_schema: any
      default_config: any
      parameter_constraints?: Record<string, any> | null
      is_active: boolean
      created_at: string | null
      updated_at: string | null
    }>
  > {
    return this.request('/users/api-keys/available-models')
  }

  // Convert imported predictions to LLM responses
  async convertTaskPredictions(taskId: string): Promise<{
    message: string
    task_id: string
    converted_count: number
  }> {
    return this.request(`/tasks/${taskId}/convert-predictions`, {
      method: 'POST',
    })
  }

  // ============= HUMAN EVALUATION (Project-based) =============
  // These methods now use project-based endpoints that work with human evaluation sessions.
  //
  // BACKEND ENDPOINTS (see services/api/routers/evaluations.py):
  //   POST   /evaluations/human/session/start - Start evaluation session for project
  //   GET    /evaluations/human/config/{project_id} - Get human eval config for project
  //   GET    /evaluations/human/session/{session_id}/progress - Get session progress
  //   DELETE /evaluations/human/session/{session_id} - Delete evaluation session
  //   GET    /evaluations/human/session/{session_id}/next - Get next item to evaluate
  //   POST   /evaluations/human/preference/submit - Submit preference ranking
  //   POST   /evaluations/human/likert/submit - Submit likert scale evaluation
  //   GET    /evaluations/human/sessions/{project_id} - Get all sessions for project
  // =====================================================================

  async setupHumanEvaluation(
    config: HumanEvaluationConfigCreate
  ): Promise<HumanEvaluationSetupResponse> {
    return this.request(`/evaluations/human/session/start`, {
      method: 'POST',
      body: JSON.stringify(config),
    })
  }

  async getHumanEvaluationConfig(
    projectId: string
  ): Promise<HumanEvaluationConfigResponse> {
    return this.request(`/evaluations/human/config/${projectId}`, {
      method: 'GET',
    })
  }

  async getHumanEvaluationResults(
    sessionId: string
  ): Promise<HumanEvaluationResultSummary> {
    return this.request(`/evaluations/human/session/${sessionId}/progress`, {
      method: 'GET',
    })
  }

  async deleteHumanEvaluation(sessionId: string): Promise<{
    session_id: string
    message: string
  }> {
    return this.request(`/evaluations/human/session/${sessionId}`, {
      method: 'DELETE',
    })
  }

  // Add Questions to Task
  async addQuestionsToTask(
    taskId: string,
    questions: Array<{
      question: string
      case?: string
      answer?: string[]
    }>
  ): Promise<{
    success: boolean
    added_count: number
    message: string
    task_count?: number
  }> {
    return this.request(`/tasks/${taskId}/add-questions`, {
      method: 'POST',
      body: JSON.stringify({ questions }),
    })
  }

  // Add Prompts to Task
  async addPromptsToTask(
    taskId: string,
    prompts: Array<{
      prompt: string
      expected_output?: string
      metadata?: {
        temperature?: number
        max_tokens?: number
        prompt_type?: string
        context?: string
      }
    }>
  ): Promise<AddPromptsResponse> {
    return this.request(`/tasks/${taskId}/add-prompts`, {
      method: 'POST',
      body: JSON.stringify({ prompts }),
    })
  }

  // Update Question in Task
  async updateTaskQuestion(
    taskId: string,
    questionIndex: number,
    questionData: {
      question?: string
      case?: string
      answer?: string[]
      reasoning?: string
      answer_config?: any
    }
  ): Promise<{
    success: boolean
    message: string
    updated_question: any
    updated_by: string
    updated_at: string
  }> {
    return this.request(`/tasks/${taskId}/questions/${questionIndex}`, {
      method: 'PATCH',
      body: JSON.stringify(questionData),
    })
  }

  // Delete Question from Task
  async deleteTaskQuestion(
    taskId: string,
    questionIndex: number
  ): Promise<{
    success: boolean
    message: string
    deleted_question: string
    remaining_questions: number
    deleted_by: string
    deleted_at: string
  }> {
    return this.request(`/tasks/${taskId}/questions/${questionIndex}`, {
      method: 'DELETE',
    })
  }

  // Annotation Overview and Organization Members
  async getTaskAnnotationOverview(taskId: string): Promise<any> {
    return this.request(`/tasks/${taskId}/annotation-overview`)
  }

  async getTaskOrganizationMembers(taskId: string): Promise<{
    task_id: string
    members: Array<{
      user_id: string
      user_name: string
      user_email: string
      organization_id: string
      organization_name: string
      organization_role: string
      joined_at: string | null
    }>
    total_members: number
    organizations: Array<{
      id: string
      name: string
    }>
  }> {
    return this.request(`/tasks/${taskId}/organization-members`)
  }

  async getUserAnnotationForItem(
    userId: string,
    taskId: string,
    itemId: string
  ): Promise<{
    user_id: string
    user_name: string
    user_email: string | null
    task_id: string
    item_id: string
    annotation: {
      id: string
      status: string
      annotation_data: any
      confidence_score: number | null
      quality_score: number | null
      flags: string[]
      metadata: any
      started_at: string | null
      completed_at: string | null
      lead_time_seconds: number | null
      version: number
      created_at: string | null
      updated_at: string | null
    } | null
    status?: string
    message?: string
  }> {
    return this.request(
      `/api/annotations/user/${userId}/task/${taskId}/item/${itemId}`
    )
  }

  // Bulk data import/export methods
  async importBulkData(formData: FormData): Promise<{
    success: boolean
    message: string
    imported_count: number
  }> {
    return this.request('/data/import', {
      method: 'POST',
      body: formData,
      // Don't set Content-Type header for FormData - browser will set it with boundary
      headers: {},
    })
  }

  async exportBulkData(format: 'json' | 'csv' | 'xml' | 'tsv'): Promise<Blob> {
    // Use the request method to handle auth and error handling
    // The request method will handle authentication and return the data
    const data = await this.request(`/data/export?format=${format}`, {
      method: 'GET',
    })

    // Convert the data to a blob for download
    return new Blob([JSON.stringify(data)], { type: 'application/json' })
  }

  // ============= EVALUATION (N:M Field Mapping) =============

  /**
   * Get available fields for evaluation mapping in a project.
   * Returns categorized fields: model response fields, human annotation fields, reference fields.
   */
  async getAvailableEvaluationFields(projectId: string): Promise<{
    model_response_fields: string[]
    human_annotation_fields: string[]
    reference_fields: string[]
    all_fields: string[]
  }> {
    return this.request(`/evaluations/projects/${projectId}/available-fields`)
  }

  /**
   * Run evaluation with N:M field mapping support.
   * Supports multiple prediction fields evaluated against multiple reference fields.
   */
  async runEvaluation(request: {
    project_id: string
    evaluation_configs: Array<{
      id: string
      metric: string
      display_name?: string
      metric_parameters?: Record<string, any>
      prediction_fields: string[]
      reference_fields: string[]
      enabled: boolean
    }>
    batch_size?: number
    label_config_version?: string
    force_rerun?: boolean  // If true, re-evaluate all; if false, only evaluate missing
    task_ids?: string[]    // Filter to specific tasks (for single-cell re-evaluation)
    model_ids?: string[]   // Filter to specific models (for single-cell re-evaluation)
  }): Promise<{
    evaluation_id: string
    project_id: string
    status: string
    message: string
    evaluation_configs_count: number
    task_id?: string
    started_at: string
  }> {
    return this.request('/evaluations/run', {
      method: 'POST',
      body: JSON.stringify(request),
    })
  }

  /**
   * Get detailed evaluation results.
   * Returns per-field-combination scores grouped by evaluation config.
   */
  async getEvaluationDetailResults(evaluationId: string): Promise<{
    evaluation_id: string
    project_id: string
    status: string
    evaluation_configs: Array<{
      id: string
      metric: string
      prediction_fields: string[]
      reference_fields: string[]
    }>
    results_by_config: Record<string, Record<string, Record<string, any>>>
    aggregated_metrics: Record<string, any>
    samples_evaluated: number
    samples_passed: number
    samples_failed: number
    samples_skipped: number
    created_at: string
    completed_at?: string
  }> {
    return this.request(`/evaluations/run/results/${evaluationId}`)
  }

  /**
   * Get evaluation results for a project.
   * Phase 9 Feature: Results accessible on evaluations page.
   *
   * @param projectId - The project ID to get results for
   * @param latestOnly - If true (default), return only the most recent evaluation.
   *                     If false, return all historical evaluation runs.
   */
  async getProjectEvaluationResults(
    projectId: string,
    latestOnly: boolean = true
  ): Promise<{
    project_id: string
    evaluations: Array<{
      evaluation_id: string
      status: string
      created_at: string | null
      completed_at: string | null
      samples_evaluated: number
      sample_results_count: number
      error_message: string | null
      evaluation_configs: Array<{
        id: string
        metric: string
        display_name?: string
        metric_parameters?: Record<string, any>
        prediction_fields: string[]
        reference_fields: string[]
        enabled: boolean
      }>
      results_by_config: Record<
        string,
        {
          field_results: Array<{
            combo_key: string
            prediction_field: string
            reference_field: string
            scores: Record<string, number>
          }>
          aggregate_score: number | null
        }
      >
      progress: {
        samples_passed: number
        samples_failed: number
        samples_skipped: number
      }
    }>
    total_count: number
  }> {
    const params = latestOnly ? '' : '?latest_only=false'
    return this.request(
      `/evaluations/run/results/project/${projectId}${params}`
    )
  }

  /**
   * Get evaluation results grouped by task and model.
   * Returns a matrix of scores for each task-model combination.
   * @param evaluationId - The evaluation ID to get results for
   */
  async getResultsByTaskModel(evaluationId: string): Promise<{
    evaluation_id: string
    models: string[]
    model_names: Record<string, string>
    tasks: Array<{
      task_id: string
      task_preview: string
      scores: Record<string, number>
    }>
    summary: Record<
      string,
      {
        avg: number
        count: number
        model_name: string
      }
    >
  }> {
    return this.request(
      `/evaluations/${evaluationId}/results/by-task-model`
    )
  }

  /**
   * Get aggregated evaluation results across ALL completed evaluations for a project.
   * Uses generation_id as natural deduplication key - if a generation was evaluated
   * in multiple runs, uses the LATEST result.
   * @param projectId - The project ID to get aggregated results for
   */
  async getProjectResultsByTaskModel(projectId: string, evaluationIds?: string[]): Promise<{
    project_id: string
    models: string[]
    model_names: Record<string, string>
    tasks: Array<{
      task_id: string
      task_preview: string
      scores: Record<string, number>
      has_annotation?: boolean
      generation_models?: string[]
    }>
    summary: Record<
      string,
      {
        avg: number
        count: number
        model_name: string
      }
    >
  }> {
    const params = evaluationIds?.length
      ? `?evaluation_ids=${evaluationIds.join(',')}`
      : ''
    return this.request(
      `/evaluations/projects/${projectId}/results/by-task-model${params}`
    )
  }

  /**
   * Get all models that have been evaluated for a project.
   * When includeConfigured is true, also returns models from generation_config
   * with status flags (is_configured, has_generations, has_results).
   */
  async getEvaluatedModels(
    projectId: string,
    includeConfigured: boolean = false
  ): Promise<
    Array<{
      model_id: string
      model_name: string
      provider: string
      evaluation_count: number
      total_samples: number
      last_evaluated: string | null
      average_score: number | null
      ci_lower: number | null
      ci_upper: number | null
      // Status flags (only present when includeConfigured=true)
      is_configured?: boolean
      has_generations?: boolean
      has_results?: boolean
    }>
  > {
    const params = includeConfigured ? '?include_configured=true' : ''
    return this.request(
      `/evaluations/projects/${projectId}/evaluated-models${params}`
    )
  }

  /**
   * Get all configured evaluation methods for a project with their result status.
   * Returns methods from evaluation_config.selected_methods with flags indicating
   * whether each method has actual results.
   */
  async getConfiguredMethods(projectId: string): Promise<{
    project_id: string
    fields: Array<{
      field_name: string
      field_type: string
      to_name: string
      automated_methods: Array<{
        method_name: string
        method_type: 'automated' | 'llm-judge'
        display_name: string
        is_configured: boolean
        has_results: boolean
        result_count: number
        last_run: string | null
        parameters?: Record<string, any>
        field_mapping?: { prediction_field: string; reference_field: string }
      }>
      human_methods: Array<{
        method_name: string
        method_type: 'human'
        display_name: string
        is_configured: boolean
        has_results: boolean
        result_count: number
        last_run: string | null
      }>
    }>
  }> {
    return this.request(`/evaluations/projects/${projectId}/configured-methods`)
  }

  /**
   * Get historical evaluation data for trend charts.
   */
  async getEvaluationHistory(params: {
    projectId: string
    modelIds: string[]
    metric: string
    startDate?: string
    endDate?: string
  }): Promise<{
    metric: string
    data: Array<{
      date: string
      model_id: string
      value: number
      ci_lower: number
      ci_upper: number
      sample_count: number
    }>
  }> {
    const queryParams = new URLSearchParams()
    params.modelIds.forEach((id) => queryParams.append('model_ids', id))
    queryParams.append('metric', params.metric)
    if (params.startDate) queryParams.append('start_date', params.startDate)
    if (params.endDate) queryParams.append('end_date', params.endDate)
    return this.request(
      `/evaluations/projects/${params.projectId}/evaluation-history?${queryParams.toString()}`
    )
  }

  /**
   * Get pairwise significance tests between models.
   */
  async getSignificanceTests(params: {
    projectId: string
    modelIds: string[]
    metrics: string[]
  }): Promise<{
    comparisons: Array<{
      model_a: string
      model_b: string
      metric: string
      p_value: number
      significant: boolean
      effect_size: number
      stars: string
    }>
  }> {
    const queryParams = new URLSearchParams()
    params.modelIds.forEach((id) => queryParams.append('model_ids', id))
    params.metrics.forEach((m) => queryParams.append('metrics', m))
    return this.request(
      `/evaluations/significance/${params.projectId}?${queryParams.toString()}`
    )
  }

  /**
   * Compute comprehensive statistics for evaluation results.
   * Supports multiple aggregation levels and statistical methods.
   */
  async computeStatistics(params: {
    projectId: string
    metrics: string[]
    aggregation: 'sample' | 'model' | 'field' | 'overall'
    methods: string[]
    compareModels?: string[]
  }): Promise<{
    aggregation: string
    metrics: Record<
      string,
      {
        mean: number
        median?: number
        std: number
        min?: number
        max?: number
        ci_lower: number
        ci_upper: number
        n: number
      }
    >
    pairwise_comparisons?: Array<{
      model_a: string
      model_b: string
      metric: string
      ttest_p?: number
      ttest_significant?: boolean
      bootstrap_p?: number
      bootstrap_significant?: boolean
      cohens_d?: number
      cohens_d_interpretation?: string
      cliffs_delta?: number
      cliffs_delta_interpretation?: string
      significant: boolean
    }>
    correlations?: Record<string, Record<string, number | null>>
  }> {
    return this.request(
      `/evaluations/projects/${params.projectId}/statistics`,
      {
        method: 'POST',
        body: JSON.stringify({
          metrics: params.metrics,
          aggregation: params.aggregation,
          methods: params.methods,
          compare_models: params.compareModels,
        }),
      }
    )
  }

  /**
   * Get project evaluation configuration.
   * Returns the complete evaluation config including selected_methods, available_methods, and detected answer types.
   */
  async getProjectEvaluationConfig(projectId: string): Promise<{
    detected_answer_types: Array<{
      name: string
      type: string
      tag: string
      to_name: string
      element_attrs?: Record<string, any>
      choices?: string[]
    }>
    available_methods: Record<
      string,
      {
        type: string
        tag: string
        to_name: string
        available_metrics: string[]
        available_human: string[]
        enabled_metrics: string[]
        enabled_human: string[]
      }
    >
    selected_methods: Record<
      string,
      {
        field_mapping?: { prediction_field: string; reference_field: string }
        automated: Array<
          string | { name: string; parameters: Record<string, any> }
        >
        human: string[]
      }
    >
    last_updated?: string
    label_config_version?: string
  }> {
    return this.request(`/evaluations/projects/${projectId}/evaluation-config`)
  }

  /**
   * Get actual annotators for a project (users who have annotated).
   */
  async getProjectAnnotators(projectId: string): Promise<{
    annotators: Array<{
      id: number
      name: string
      count: number
    }>
  }> {
    return this.request(`/projects/${projectId}/annotators`)
  }

  /**
   * Get per-sample evaluation results with filtering and pagination.
   * Enables drill-down analysis of evaluation performance at the sample level.
   */
  async getEvaluationSamples(
    evaluationId: string,
    params?: {
      fieldName?: string
      passed?: boolean
      page?: number
      pageSize?: number
    }
  ): Promise<{
    items: Array<{
      id: string
      evaluation_id: string
      task_id: string
      generation_id?: string
      field_name: string
      answer_type: string
      ground_truth: Record<string, any>
      prediction: Record<string, any>
      metrics: Record<string, number>
      passed: boolean
      confidence_score?: number
      error_message?: string
      processing_time_ms?: number
      created_at: string
    }>
    total: number
    page: number
    page_size: number
    has_next: boolean
  }> {
    const queryParams = new URLSearchParams()
    if (params?.fieldName) queryParams.append('field_name', params.fieldName)
    if (params?.passed !== undefined)
      queryParams.append('passed', String(params.passed))
    if (params?.page) queryParams.append('page', String(params.page))
    if (params?.pageSize)
      queryParams.append('page_size', String(params.pageSize))
    const queryString = queryParams.toString()
    return this.request(
      `/evaluations/${evaluationId}/samples${queryString ? `?${queryString}` : ''}`
    )
  }

  /**
   * Get distribution statistics for a specific metric across all samples.
   * Returns mean, median, std, quartiles, and histogram data for visualization.
   */
  async getMetricDistribution(
    evaluationId: string,
    metricName: string,
    fieldName?: string
  ): Promise<{
    metric_name: string
    mean: number
    median: number
    std: number
    min: number
    max: number
    quartiles: { q1: number; q2: number; q3: number }
    histogram: Record<string, number>
  }> {
    const queryParams = fieldName ? `?field_name=${fieldName}` : ''
    return this.request(
      `/evaluations/${evaluationId}/metrics/${metricName}/distribution${queryParams}`
    )
  }

}

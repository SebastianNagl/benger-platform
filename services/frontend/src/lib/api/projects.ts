/**
 * Projects API client - Label Studio aligned
 *
 * This module provides type-safe API calls for the new project-based
 * structure that follows Label Studio patterns.
 */

import apiClient from '@/lib/api'
import {
  Annotation,
  AnnotationCreate,
  AnnotationResult,
  AssignTasksRequest,
  ImportResult,
  PaginatedResponse,
  Project,
  ProjectCreate,
  ProjectUpdate,
  StartTimerResponse,
  Task,
  TaskAssignment,
  TimerStatusResponse,
} from '@/types/labelStudio'

export const projectsAPI = {
  /**
   * List all projects
   */
  list: async (
    page = 1,
    pageSize = 100,
    search?: string,
    isArchived?: boolean
  ): Promise<PaginatedResponse<Project>> => {
    const params = new URLSearchParams({
      page: page.toString(),
      page_size: pageSize.toString(),
    })

    if (search) {
      params.append('search', search)
    }

    // Only add is_archived param if explicitly set, not when undefined
    if (isArchived === true) {
      params.append('is_archived', 'true')
    } else if (isArchived === false) {
      params.append('is_archived', 'false')
    }

    // Add cache-busting parameter to ensure fresh data after deletions
    params.append('_', Date.now().toString())

    const response = await apiClient.get(`/projects/?${params}`)
    return response // Backend now returns PaginatedResponse directly
  },

  /**
   * Get a specific project
   */
  get: async (projectId: string): Promise<Project> => {
    // Add cache-busting parameter to ensure fresh data
    const cacheBuster = Date.now()
    const response = await apiClient.get(
      `/projects/${projectId}?_=${cacheBuster}`
    )
    return response
  },

  /**
   * Create a new project
   */
  create: async (data: ProjectCreate): Promise<Project> => {
    const response = await apiClient.post('/projects/', data)
    return response
  },

  /**
   * Update a project
   */
  update: async (projectId: string, data: ProjectUpdate): Promise<Project> => {
    const response = await apiClient.patch(`/projects/${projectId}`, data)
    return response
  },

  /**
   * Delete a project
   */
  delete: async (projectId: string): Promise<void> => {
    await apiClient.delete(`/projects/${projectId}`)
  },

  /**
   * Import data into a project
   */
  importData: async (
    projectId: string,
    data: { data: any[]; meta?: any }
  ): Promise<ImportResult> => {
    const response = await apiClient.post(`/projects/${projectId}/import`, data)
    return response
  },

  /**
   * Get tasks in a project
   */
  getTasks: async (
    projectId: string,
    options?: {
      page?: number
      pageSize?: number
      onlyLabeled?: boolean
      onlyUnlabeled?: boolean
      excludeMyAnnotations?: boolean
    }
  ): Promise<Task[]> => {
    const params = new URLSearchParams({
      page: (options?.page || 1).toString(),
      page_size: (options?.pageSize || 30).toString(),
    })

    if (options?.onlyLabeled !== undefined) {
      params.append('only_labeled', options.onlyLabeled.toString())
    }
    if (options?.onlyUnlabeled !== undefined) {
      params.append('only_unlabeled', options.onlyUnlabeled.toString())
    }
    if (options?.excludeMyAnnotations) {
      params.append('exclude_my_annotations', 'true')
    }

    const response = await apiClient.get(
      `/projects/${projectId}/tasks?${params}`
    )

    // Handle paginated response format
    if (response && typeof response === 'object' && 'items' in response) {
      return response.items || []
    }

    // Fallback for backward compatibility with non-paginated response
    if (Array.isArray(response)) {
      return response
    }

    return []
  },

  /**
   * Get next task to annotate
   */
  getNextTask: async (
    projectId: string
  ): Promise<{
    task: Task | null
    remaining: number
    current_position?: number
    total_tasks?: number
  }> => {
    const response = await apiClient.get(`/projects/${projectId}/next`)
    return response
  },

  /**
   * Get a specific task
   */
  getTask: async (taskId: string): Promise<Task> => {
    const response = await apiClient.get(`/projects/tasks/${taskId}`)
    return response
  },

  /**
   * Create an annotation
   */
  createAnnotation: async (
    taskId: string,
    data: AnnotationCreate
  ): Promise<Annotation> => {
    const response = await apiClient.post(
      `/projects/tasks/${taskId}/annotations`,
      data
    )
    return response
  },

  /**
   * Get annotations for a task
   */
  getTaskAnnotations: async (taskId: string, allUsers?: boolean): Promise<Annotation[]> => {
    let url = `/projects/tasks/${taskId}/annotations`
    if (allUsers) url += '?all_users=true'
    const response = await apiClient.get(url)
    return response
  },

  /**
   * Update an annotation
   */
  updateAnnotation: async (
    annotationId: string,
    data: Partial<AnnotationCreate>
  ): Promise<Annotation> => {
    const response = await apiClient.patch(
      `/projects/annotations/${annotationId}`,
      data
    )
    return response
  },

  /**
   * Export project data
   */
  export: async (
    projectId: string,
    format: 'json' | 'csv' | 'tsv' | 'txt' | 'label_studio' = 'json',
    download: boolean = true
  ): Promise<Blob> => {
    const params = new URLSearchParams({
      format,
      download: download.toString(),
    })

    const response = await apiClient.get(
      `/projects/${projectId}/export?${params}`
    )
    return response
  },

  /**
   * Bulk delete tasks
   */
  bulkDeleteTasks: async (
    projectId: string,
    taskIds: string[]
  ): Promise<{ deleted: number }> => {
    const response = await apiClient.post(
      `/projects/${projectId}/tasks/bulk-delete`,
      {
        task_ids: taskIds,
      }
    )
    return response
  },

  /**
   * Bulk export tasks
   */
  bulkExportTasks: async (
    projectId: string,
    taskIds: string[],
    format: 'json' | 'csv' | 'tsv' = 'json'
  ): Promise<Blob> => {
    const response = await apiClient.post(
      `/projects/${projectId}/tasks/bulk-export`,
      { task_ids: taskIds, format }
    )
    return response
  },

  /**
   * Bulk archive tasks
   */
  bulkArchiveTasks: async (
    projectId: string,
    taskIds: string[]
  ): Promise<{ archived: number }> => {
    const response = await apiClient.post(
      `/projects/${projectId}/tasks/bulk-archive`,
      {
        task_ids: taskIds,
      }
    )
    return response
  },

  /**
   * Bulk delete projects
   */
  bulkDeleteProjects: async (
    projectIds: string[]
  ): Promise<{ deleted: number }> => {
    const response = await apiClient.post('/projects/bulk-delete', {
      project_ids: projectIds,
    })
    return response
  },

  /**
   * Bulk archive projects
   */
  bulkArchiveProjects: async (
    projectIds: string[]
  ): Promise<{ archived: number }> => {
    const response = await apiClient.post('/projects/bulk-archive', {
      project_ids: projectIds,
    })
    return response
  },

  /**
   * Bulk unarchive projects
   */
  bulkUnarchiveProjects: async (
    projectIds: string[]
  ): Promise<{ unarchived: number }> => {
    const response = await apiClient.post('/projects/bulk-unarchive', {
      project_ids: projectIds,
    })
    return response
  },

  /**
   * Bulk export projects
   */
  bulkExportProjects: async (
    projectIds: string[],
    format: 'json' | 'csv' = 'json',
    includeData: boolean = true
  ): Promise<Blob> => {
    const response = await apiClient.post('/projects/bulk-export', {
      project_ids: projectIds,
      format,
      include_data: includeData,
    })
    return response
  },

  /**
   * Comprehensive bulk export of full projects
   * Returns a ZIP file with individual project JSON files containing all data
   */
  bulkExportFullProjects: async (projectIds: string[]): Promise<Blob> => {
    const response = await apiClient.post('/projects/bulk-export-full', {
      project_ids: projectIds,
    })
    return response
  },

  /**
   * Import a complete project from a JSON file
   * Creates a new project with all associated data
   */
  importProject: async (
    file: File
  ): Promise<{
    message: string
    project_id: string
    project_title: string
    project_url: string
    statistics: Record<string, any>
  }> => {
    const formData = new FormData()
    formData.append('file', file)

    const response = await apiClient.post(
      '/projects/import-project',
      formData
      // Note: Don't set Content-Type header manually for FormData
      // The browser automatically sets the correct multipart/form-data with boundary
    )
    return response
  },

  /**
   * Get project organizations
   */
  getOrganizations: async (
    projectId: string
  ): Promise<
    Array<{
      organization_id: string
      organization_name: string
      assigned_by: string
      assigned_at: string
    }>
  > => {
    const response = await apiClient.get(`/projects/${projectId}/organizations`)
    return response
  },

  /**
   * Add organization to project (superadmin only)
   */
  addOrganization: async (
    projectId: string,
    organizationId: string
  ): Promise<{
    message: string
    organization_id: string
    organization_name: string
  }> => {
    const response = await apiClient.post(
      `/projects/${projectId}/organizations/${organizationId}`
    )
    return response
  },

  /**
   * Remove organization from project (superadmin only)
   */
  removeOrganization: async (
    projectId: string,
    organizationId: string
  ): Promise<{
    message: string
  }> => {
    const response = await apiClient.delete(
      `/projects/${projectId}/organizations/${organizationId}`
    )
    return response
  },

  /**
   * Get project members
   */
  getMembers: async (
    projectId: string
  ): Promise<
    Array<{
      id: string
      user_id: string
      name: string
      email: string
      role: string
      is_direct_member: boolean
      organization_id: string | null
      organization_name: string | null
      added_at: string
    }>
  > => {
    const response = await apiClient.get(`/projects/${projectId}/members`)
    return response
  },

  /**
   * Add member to project
   */
  addMember: async (
    projectId: string,
    userId: string,
    role: string = 'ANNOTATOR'
  ): Promise<{
    message: string
    user_id: string
    user_name: string
    role: string
  }> => {
    const response = await apiClient.post(
      `/projects/${projectId}/members/${userId}`,
      { role }
    )
    return response
  },

  /**
   * Remove member from project
   */
  removeMember: async (
    projectId: string,
    userId: string
  ): Promise<{
    message: string
  }> => {
    const response = await apiClient.delete(
      `/projects/${projectId}/members/${userId}`
    )
    return response
  },

  /**
   * Update task data (Superadmin only)
   */
  updateTaskData: async (
    projectId: string,
    taskId: string,
    data: Record<string, any>
  ): Promise<Task> => {
    const response = await apiClient.put(
      `/projects/${projectId}/tasks/${taskId}`,
      {
        data,
      }
    )
    return response
  },

  /**
   * Assign tasks to users
   */
  assignTasks: async (
    projectId: string,
    data: AssignTasksRequest
  ): Promise<{
    assignments_created: number
    skipped_existing: number
    message: string
  }> => {
    const response = await apiClient.post(
      `/projects/${projectId}/tasks/assign`,
      data
    )
    return response
  },

  /**
   * Recalculate project statistics (Admin only)
   * Fixes annotation counts by excluding skipped/cancelled annotations
   */
  recalculateStats: async (
    projectId: string
  ): Promise<{
    message: string
    project_id: string
    task_count: number
    annotation_count: number
    completed_tasks_count: number
    progress_percentage: number
  }> => {
    const response = await apiClient.post(
      `/projects/${projectId}/recalculate-stats`
    )
    return response
  },

  /**
   * Get tasks assigned to current user
   */
  getMyTasks: async (
    projectId: string,
    page = 1,
    pageSize = 50,
    status?: string
  ): Promise<PaginatedResponse<Task & { assignment?: TaskAssignment }>> => {
    const params = new URLSearchParams({
      page: page.toString(),
      page_size: pageSize.toString(),
    })

    if (status) {
      params.append('status', status)
    }

    const response = await apiClient.get(
      `/projects/${projectId}/my-tasks?${params}`
    )
    return response
  },

  /**
   * Remove a task assignment
   */
  removeTaskAssignment: async (
    projectId: string,
    taskId: string,
    assignmentId: string
  ): Promise<void> => {
    await apiClient.delete(
      `/projects/${projectId}/tasks/${taskId}/assignments/${assignmentId}`
    )
  },

  /**
   * Get available task data fields for a project
   * Used for field mapping in LLM Judge, generation prompts, etc.
   */
  getTaskFields: async (
    projectId: string,
    sampleCount: number = 5
  ): Promise<{
    project_id: string
    fields: Array<{
      path: string
      display_name: string
      sample_value: string
      data_type: string
      is_nested: boolean
    }>
    sample_task_count: number
  }> => {
    const params = new URLSearchParams({
      sample_count: sampleCount.toString(),
    })
    const response = await apiClient.get(
      `/projects/${projectId}/task-fields?${params}`
    )
    return response
  },

  /**
   * Start an annotation timer session (Issue #1205)
   * Idempotent: returns existing session if already started
   */
  startTimer: async (
    projectId: string,
    taskId: string
  ): Promise<StartTimerResponse> => {
    const response = await apiClient.post(
      `/projects/${projectId}/tasks/${taskId}/start-timer`
    )
    return response
  },

  /**
   * Get timer status for a task (Issue #1205)
   * Returns the active session or null
   */
  getTimerStatus: async (
    projectId: string,
    taskId: string
  ): Promise<TimerStatusResponse> => {
    const response = await apiClient.get(
      `/projects/${projectId}/tasks/${taskId}/timer-status`
    )
    return response
  },

  /**
   * Save draft annotation data to the server.
   * Called periodically (every 30s) for all projects when annotations change.
   * Also mirrors to timer session for strict timer auto-submit.
   */
  saveDraft: async (
    projectId: string,
    taskId: string,
    result: any[]
  ): Promise<void> => {
    await apiClient.put(
      `/projects/${projectId}/tasks/${taskId}/draft`,
      { result }
    )
  },

  /**
   * Submit a post-annotation questionnaire response (Issue #1208)
   */
  submitQuestionnaireResponse: async (
    projectId: string,
    taskId: string,
    annotationId: string,
    result: any[]
  ): Promise<any> => {
    const response = await apiClient.post(
      `/projects/${projectId}/tasks/${taskId}/questionnaire-response`,
      { annotation_id: annotationId, result }
    )
    return response
  },
}

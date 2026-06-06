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
  PaginatedResponse,
  Project,
  ProjectCreate,
  ProjectUpdate,
  Task,
  TaskAssignment,
} from '@/types/labelStudio'

export type ExportJobState = 'pending' | 'running' | 'completed' | 'failed'

export interface ExportJobStatus {
  job_id: string
  project_id: string
  format: string
  status: ExportJobState
  progress: number
  byte_size: number | null
  error_message: string | null
  created_at: string | null
  updated_at: string | null
  expires_at: string | null
}

export type ImportJobState = 'pending' | 'running' | 'completed' | 'failed'

/** Result payload an import worker writes back on completion. */
export interface ImportJobResult {
  message?: string
  // Full-project (create-new) import:
  project_id?: string
  project_title?: string
  project_url?: string
  statistics?: Record<string, any>
  // Nested (into-existing-project) import:
  created_tasks?: number
  created_annotations?: number
  total_items?: number
  [key: string]: any
}

export interface ImportJobStatus {
  job_id: string
  project_id: string | null
  format: string | null
  status: ImportJobState
  progress: number
  byte_size: number | null
  error_message: string | null
  result: ImportJobResult | null
  created_at: string | null
  updated_at: string | null
  expires_at: string | null
}

/** Presigned-POST descriptor returned by the *.../imports/upload-url endpoints. */
export interface PresignedUpload {
  upload_url: string
  method: string
  file_key: string
  fields?: Record<string, string>
  expires_at?: string
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

export const projectsAPI = {
  /**
   * List all projects
   */
  list: async (
    page = 1,
    pageSize = 100,
    search?: string,
    isArchived?: boolean,
    includeAllPrivate?: boolean
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

    // Superadmin-only: broaden the response to include other users' private
    // projects. Backend ignores the flag for non-superadmins.
    if (includeAllPrivate === true) {
      params.append('include_all_private', 'true')
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
   * Change project visibility (private / org-assigned / public).
   *
   * Payload shapes accepted by the backend:
   * - { is_private: true, owner_user_id?: string }
   * - { is_private: false, organization_ids: string[] }
   * - { is_public: true, public_role: 'ANNOTATOR' | 'CONTRIBUTOR' }
   * - { public_role: 'ANNOTATOR' | 'CONTRIBUTOR' } (flip role on already-public)
   */
  updateVisibility: async (
    projectId: string,
    payload:
      | { is_private: true; owner_user_id?: string }
      | { is_private: false; organization_ids: string[] }
      | { is_public: true; public_role: 'ANNOTATOR' | 'CONTRIBUTOR' }
      | { public_role: 'ANNOTATOR' | 'CONTRIBUTOR' }
  ): Promise<Project> => {
    const response = await apiClient.patch(
      `/projects/${projectId}/visibility`,
      payload
    )
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
      search?: string
      dateFrom?: string
      dateTo?: string
      sortBy?: 'id' | 'created' | 'completed' | 'annotations' | 'generations'
      sortOrder?: 'asc' | 'desc'
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
    if (options?.search) {
      params.append('search', options.search)
    }
    if (options?.dateFrom) {
      params.append('date_from', options.dateFrom)
    }
    if (options?.dateTo) {
      params.append('date_to', options.dateTo)
    }
    if (options?.sortBy) {
      params.append('sort_by', options.sortBy)
    }
    if (options?.sortOrder) {
      params.append('sort_order', options.sortOrder)
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
   * Paginated variant that returns the full envelope (items + total + pages).
   * Use this when the UI drives pagination from the backend `total` (e.g.
   * AnnotationTab) instead of loading every page upfront.
   */
  getTasksPage: async (
    projectId: string,
    options?: {
      page?: number
      pageSize?: number
      onlyLabeled?: boolean
      onlyUnlabeled?: boolean
      excludeMyAnnotations?: boolean
      search?: string
      dateFrom?: string
      dateTo?: string
      sortBy?: 'id' | 'created' | 'completed' | 'annotations' | 'generations'
      sortOrder?: 'asc' | 'desc'
    }
  ): Promise<{
    items: Task[]
    total: number
    page: number
    page_size: number
    pages: number
  }> => {
    const params = new URLSearchParams({
      page: (options?.page || 1).toString(),
      page_size: (options?.pageSize || 50).toString(),
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
    if (options?.search) params.append('search', options.search)
    if (options?.dateFrom) params.append('date_from', options.dateFrom)
    if (options?.dateTo) params.append('date_to', options.dateTo)
    if (options?.sortBy) params.append('sort_by', options.sortBy)
    if (options?.sortOrder) params.append('sort_order', options.sortOrder)

    const response = await apiClient.get(
      `/projects/${projectId}/tasks?${params.toString()}`
    )

    if (response && typeof response === 'object' && 'items' in response) {
      return {
        items: response.items || [],
        total: response.total ?? 0,
        page: response.page ?? options?.page ?? 1,
        page_size: response.page_size ?? options?.pageSize ?? 50,
        pages: response.pages ?? 0,
      }
    }
    // Backwards-compatible degenerate response — treat array as one page.
    if (Array.isArray(response)) {
      return {
        items: response,
        total: response.length,
        page: options?.page ?? 1,
        page_size: options?.pageSize ?? 50,
        pages: 1,
      }
    }
    return { items: [], total: 0, page: 1, page_size: options?.pageSize ?? 50, pages: 0 }
  },

  /**
   * Return every task id that matches the given filters — no pagination,
   * no enrichment. The data tab's "select all matching" affordance uses
   * this so bulk delete/export/assign can operate on the full filtered
   * set rather than just the current 50-row page.
   */
  getTaskIds: async (
    projectId: string,
    options?: {
      onlyLabeled?: boolean
      onlyUnlabeled?: boolean
      excludeMyAnnotations?: boolean
      search?: string
      dateFrom?: string
      dateTo?: string
      idsLimit?: number
    }
  ): Promise<{ ids: string[]; total: number; truncated: boolean }> => {
    const params = new URLSearchParams({
      ids_only: 'true',
      page: '1',
      page_size: '1',
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
    if (options?.search) params.append('search', options.search)
    if (options?.dateFrom) params.append('date_from', options.dateFrom)
    if (options?.dateTo) params.append('date_to', options.dateTo)
    if (options?.idsLimit) params.append('ids_limit', String(options.idsLimit))

    const response = await apiClient.get(
      `/projects/${projectId}/tasks?${params.toString()}`
    )
    return {
      ids: response?.ids ?? [],
      total: response?.total ?? 0,
      truncated: !!response?.truncated,
    }
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
  getTaskAnnotations: async (
    taskId: string,
    allUsers?: boolean,
    completedByUsername?: string,
    latestOnly?: boolean,
  ): Promise<Annotation[]> => {
    const params = new URLSearchParams()
    if (allUsers) params.append('all_users', 'true')
    if (completedByUsername) params.append('completed_by_username', completedByUsername)
    if (latestOnly) params.append('latest_only', 'true')
    const qs = params.toString()
    const url = `/projects/tasks/${taskId}/annotations${qs ? '?' + qs : ''}`
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
   * Create an async export job. The worker streams the export to object storage;
   * the client polls status and downloads via a presigned URL.
   *
   * Pass `taskIds` to export only a task subset (selected/filtered export) — the
   * backend restricts subset export to the json format.
   */
  createExportJob: async (
    projectId: string,
    format: 'json' | 'csv' | 'tsv' | 'txt' | 'label_studio' | 'comprehensive' = 'json',
    taskIds?: string[]
  ): Promise<{ job_id: string; status: ExportJobState }> => {
    return apiClient.post(
      `/projects/${projectId}/exports?format=${encodeURIComponent(format)}`,
      taskIds && taskIds.length > 0 ? { task_ids: taskIds } : undefined
    )
  },

  /** Poll the status of an export job. */
  getExportJob: async (
    projectId: string,
    jobId: string
  ): Promise<ExportJobStatus> => {
    return apiClient.get(`/projects/${projectId}/exports/${jobId}`)
  },

  /**
   * Resolve a short-lived presigned download URL for a completed export job.
   * The URL points straight at object storage, so the actual bytes never pass
   * through the Next.js proxy or the browser's JS heap.
   */
  getExportDownloadUrl: async (
    projectId: string,
    jobId: string
  ): Promise<{ url: string; expires_in: number }> => {
    return apiClient.get(
      `/projects/${projectId}/exports/${jobId}/download?json=1`
    )
  },

  /**
   * Drive an export through the async job flow: enqueue, poll to completion,
   * then trigger a direct browser download from the presigned URL.
   *
   * This is the single export path — it moves the bulk data plane off the
   * request path, so it can't OOM the API or truncate a multi-GB download. Pass
   * `taskIds` to export only a selected/filtered subset (json-only on the
   * backend); omit it for the whole project.
   *
   * Throws an Error if the job fails (message = the worker's error_message),
   * or a DOMException `AbortError` if the caller's signal is aborted while
   * polling.
   */
  runProjectExportJob: async (
    projectId: string,
    format: 'json' | 'csv' | 'tsv' | 'txt' | 'label_studio' | 'comprehensive',
    callbacks?: { onStatus?: (status: ExportJobStatus) => void },
    options?: { pollIntervalMs?: number; signal?: AbortSignal; taskIds?: string[] }
  ): Promise<void> => {
    const pollIntervalMs = options?.pollIntervalMs ?? 2000
    const { job_id } = await projectsAPI.createExportJob(
      projectId,
      format,
      options?.taskIds
    )

    for (;;) {
      if (options?.signal?.aborted) {
        throw new DOMException('Export polling aborted', 'AbortError')
      }
      const status = await projectsAPI.getExportJob(projectId, job_id)
      callbacks?.onStatus?.(status)
      if (status.status === 'completed') break
      if (status.status === 'failed') {
        throw new Error(status.error_message || 'Export job failed')
      }
      await sleep(pollIntervalMs)
    }

    const { url } = await projectsAPI.getExportDownloadUrl(projectId, job_id)
    const link = document.createElement('a')
    link.href = url
    // The server sets Content-Disposition: attachment with the filename, so an
    // empty download attribute is enough to keep the browser from navigating.
    link.download = ''
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  },

  /**
   * Mint a presigned upload URL for a NESTED import (into an existing project).
   * The returned key is scoped to the project.
   */
  createImportUploadUrl: async (
    projectId: string,
    filename: string
  ): Promise<PresignedUpload> => {
    return apiClient.post(
      `/projects/${projectId}/imports/upload-url?filename=${encodeURIComponent(filename)}`
    )
  },

  /**
   * Mint a presigned upload URL for a FULL-PROJECT import (creates a new
   * project). The returned key is scoped to the requesting user.
   */
  createFullImportUploadUrl: async (
    filename: string
  ): Promise<PresignedUpload> => {
    return apiClient.post(
      `/projects/project-imports/upload-url?filename=${encodeURIComponent(filename)}`
    )
  },

  /**
   * Upload a file straight to object storage using a presigned-POST descriptor.
   *
   * The bytes go directly to storage (not through the API or the Next proxy), so
   * a multi-GB import never touches a server heap. For a presigned POST the
   * `fields` must precede the `file` part, and `file` must be the LAST field.
   */
  uploadToPresignedUrl: async (
    upload: PresignedUpload,
    file: File
  ): Promise<void> => {
    const formData = new FormData()
    for (const [key, value] of Object.entries(upload.fields || {})) {
      formData.append(key, value)
    }
    formData.append('file', file)
    const res = await fetch(upload.upload_url, {
      method: 'POST',
      body: formData,
    })
    if (!res.ok) {
      const body = await res.text().catch(() => '')
      throw new Error(
        `Upload to storage failed (${res.status}): ${body.slice(0, 500)}`
      )
    }
  },

  /** Create an async NESTED import job for an already-uploaded artifact. */
  createImportJob: async (
    projectId: string,
    objectKey: string
  ): Promise<{ job_id: string; status: ImportJobState }> => {
    return apiClient.post(`/projects/${projectId}/imports`, {
      object_key: objectKey,
    })
  },

  /** Create an async FULL-PROJECT import job for an already-uploaded artifact. */
  createFullImportJob: async (
    objectKey: string
  ): Promise<{ job_id: string; status: ImportJobState }> => {
    return apiClient.post('/projects/project-imports', { object_key: objectKey })
  },

  /** Poll the status of a nested import job. */
  getImportJob: async (
    projectId: string,
    jobId: string
  ): Promise<ImportJobStatus> => {
    return apiClient.get(`/projects/${projectId}/imports/${jobId}`)
  },

  /** Poll the status of a full-project import job. */
  getFullImportJob: async (jobId: string): Promise<ImportJobStatus> => {
    return apiClient.get(`/projects/project-imports/${jobId}`)
  },

  /**
   * Drive a NESTED import through the async job flow: presign → upload → enqueue
   * → poll. Resolves with the final (completed) job status.
   *
   * Throws an Error if the job fails (message = the worker's error_message), or
   * a DOMException `AbortError` if the caller's signal is aborted while polling.
   */
  runNestedImportJob: async (
    projectId: string,
    file: File,
    callbacks?: { onStatus?: (status: ImportJobStatus) => void },
    options?: { pollIntervalMs?: number; signal?: AbortSignal }
  ): Promise<ImportJobStatus> => {
    const pollIntervalMs = options?.pollIntervalMs ?? 2000
    const upload = await projectsAPI.createImportUploadUrl(projectId, file.name)
    await projectsAPI.uploadToPresignedUrl(upload, file)
    const { job_id } = await projectsAPI.createImportJob(
      projectId,
      upload.file_key
    )

    for (;;) {
      if (options?.signal?.aborted) {
        throw new DOMException('Import polling aborted', 'AbortError')
      }
      const status = await projectsAPI.getImportJob(projectId, job_id)
      callbacks?.onStatus?.(status)
      if (status.status === 'completed') return status
      if (status.status === 'failed') {
        throw new Error(status.error_message || 'Import job failed')
      }
      await sleep(pollIntervalMs)
    }
  },

  /**
   * Drive a FULL-PROJECT import (create-new) through the async job flow: presign
   * → upload → enqueue → poll. Resolves with the final (completed) job status;
   * the created project id is on `status.project_id` (and `status.result`).
   *
   * Throws an Error if the job fails (message = the worker's error_message), or
   * a DOMException `AbortError` if the caller's signal is aborted while polling.
   */
  runProjectImportJob: async (
    file: File,
    callbacks?: { onStatus?: (status: ImportJobStatus) => void },
    options?: { pollIntervalMs?: number; signal?: AbortSignal }
  ): Promise<ImportJobStatus> => {
    const pollIntervalMs = options?.pollIntervalMs ?? 2000
    const upload = await projectsAPI.createFullImportUploadUrl(file.name)
    await projectsAPI.uploadToPresignedUrl(upload, file)
    const { job_id } = await projectsAPI.createFullImportJob(upload.file_key)

    for (;;) {
      if (options?.signal?.aborted) {
        throw new DOMException('Import polling aborted', 'AbortError')
      }
      const status = await projectsAPI.getFullImportJob(job_id)
      callbacks?.onStatus?.(status)
      if (status.status === 'completed') return status
      if (status.status === 'failed') {
        throw new Error(status.error_message || 'Import job failed')
      }
      await sleep(pollIntervalMs)
    }
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
   * Get project members (used by annotator pickers, not by a per-project page).
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
   * Update task data (superadmins and organization admins)
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
   * Save draft annotation data to the server.
   * Called periodically (every 30s) for all projects when annotations change.
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

/**
 * Report API client
 *
 * Provides functions to interact with the report publishing system:
 * - Get project reports (draft or published)
 * - Update report content (superadmin only)
 * - Publish/unpublish reports
 * - List published reports (org-filtered)
 * - Get complete report data with statistics and charts
 */

import { apiClient } from './client'

// Types matching backend schema
export interface ReportSection {
  status: 'pending' | 'completed'
  editable: boolean
  visible: boolean
}

export interface ProjectInfoSection extends ReportSection {
  title: string
  description: string
  custom_title?: string | null
  custom_description?: string | null
}

export interface DataSection extends ReportSection {
  task_count?: number
  custom_text?: string | null
  show_count: boolean
}

export interface AnnotationsSection extends ReportSection {
  annotation_count?: number
  participants?: Array<{
    id: string
    name: string
    count: number
  }>
  custom_text?: string | null
  show_count: boolean
  show_participants: boolean
  acknowledgment_text?: string | null
}

export interface GenerationSection extends ReportSection {
  models?: string[]
  custom_text?: string | null
  show_models: boolean
  show_config: boolean
}

export interface EvaluationSection extends ReportSection {
  methods?: string[]
  metrics?: Record<string, any>
  charts_config?: Record<string, any>
  custom_interpretation?: string | null
  conclusions?: string | null
}

export interface ReportContent {
  sections: {
    project_info: ProjectInfoSection
    data: DataSection
    annotations: AnnotationsSection
    generation: GenerationSection
    evaluation: EvaluationSection
  }
  metadata: {
    last_auto_update: string
    sections_completed: string[]
    can_publish: boolean
  }
}

export interface ReportResponse {
  id: string
  project_id: string
  project_title: string
  content: ReportContent
  is_published: boolean
  published_at?: string | null
  published_by?: string | null
  created_by: string
  created_at: string
  updated_at?: string | null
  can_publish: boolean
  can_publish_reason: string
}

export interface PublishedReportListItem {
  id: string
  project_id: string
  project_title: string
  published_at: string
  task_count: number
  annotation_count: number
  model_count: number
  organizations: Array<{
    id: string
    name: string
  }>
}

export interface MetricMetadata {
  higher_is_better: boolean
  range: [number, number]
  name: string
  category: string
}

export interface ReportDataResponse {
  report: ReportResponse
  statistics: {
    task_count: number
    annotation_count: number
    participant_count: number
    model_count: number
  }
  participants: Array<{
    id: string
    username: string
    annotation_count: number
  }>
  models: string[]
  evaluation_charts: {
    by_model: Record<string, Record<string, number>>
    by_method: Record<string, Record<string, number>>
    metric_metadata?: Record<string, MetricMetadata>
  }
}

/**
 * Get report for a project
 * - Superadmins can view draft or published reports
 * - Org members can view only published reports
 */
export async function getProjectReport(
  projectId: string
): Promise<ReportResponse> {
  const response = await apiClient.get(`/projects/${projectId}/report`)
  return response.data
}

/**
 * Update report content (superadmin only)
 * Allows editing report sections while preserving auto-populated data
 */
export async function updateProjectReport(
  projectId: string,
  content: ReportContent
): Promise<ReportResponse> {
  const response = await apiClient.post(`/projects/${projectId}/report`, {
    content,
  })
  return response.data
}

/**
 * Publish a report (superadmin only)
 * Validates that all requirements are met before publishing
 */
export async function publishReport(
  projectId: string
): Promise<ReportResponse> {
  const response = await apiClient.put(`/projects/${projectId}/report/publish`)
  return response.data
}

/**
 * Unpublish a report (superadmin only)
 */
export async function unpublishReport(
  projectId: string
): Promise<ReportResponse> {
  const response = await apiClient.put(
    `/projects/${projectId}/report/unpublish`
  )
  return response.data
}

/**
 * List all published reports
 * - Superadmins: See all published reports
 * - Org members: See published reports from their organizations
 */
export async function listPublishedReports(): Promise<
  PublishedReportListItem[]
> {
  const response = await apiClient.get('/reports')
  return response.data
}

/**
 * Get complete report data including statistics and charts
 * Only accessible for published reports (or superadmins for drafts)
 */
export async function getReportData(
  reportId: string
): Promise<ReportDataResponse> {
  return await apiClient.get(`/reports/${reportId}/data`)
}
